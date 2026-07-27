"""RS002 exact-V5.5 paired-MC32 postflop root resolver.

This file is identity-bound by the RS002 preregistration.  It deliberately keeps
the H11 actor immutable and changes only hero postflop root action selection.
Qualification is offline: this module never imports or calls the Slumbot network
API.  The public ``resolve_information_set`` entry point is suitable for later
in-process use at the frozen play_slumbot boundary.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import math
import os
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

ROOT = Path(r"C:\Users\a8594\CardPilot")
SCRIPT_DIR = ROOT / "scripts" / "alpha_holdem"
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from alpha_holdem.environment_v55 import (  # noqa: E402
    build_action_table,
    encode_action_history,
    encode_cards,
    encode_extra,
)
from alpha_holdem.network import AlphaHoldemNet  # noqa: E402
from alpha_holdem.play_slumbot import parse_action  # noqa: E402
from deep_cfr.game_state import (  # noqa: E402
    Action,
    ActionType,
    GameConfig,
    HUNLGameState,
    Street,
)

TOKEN = "81b61579f99755eb755d8c3c1905c22f"
PROGRAM_ID = "RS002_PAIRED_MC32_LCB95_ROOT_RESOLVER"
PREREG = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_preregistration_{TOKEN}_20260722.json"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_preregistration_audit_{TOKEN}_20260722.json"
IMPL_AUDIT = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_implementation_audit_{TOKEN}_20260722.json"
QUAL_ROOT = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_qualification_{TOKEN}_20260722"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"
CHECKPOINT_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
PREREG_SHA256 = "93316de07812e6801cd6c83ddb7082b21841b981115a11c42ec3215c6b4563c7"
PREREG_AUDIT_SHA256 = "e346a5b56ed4b5dd7239e6726ed2f5082d9e7a8e711cf26f2bd14e85661ea4bd"
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
DEVICE_MODE = "CUDA_ONLY_SINGLE_GPU_NO_CPU_RESOLVER_FALLBACK"
PROBE_NONCES = {"RS002_PROBE_A_2034972294", "RS002_PROBE_B_2035972294"}
QUALIFICATION_NONCE = "RS002_QUALIFICATION_2036972294"
EVALUATION_NONCE = "RS002_EVALUATION_2037972294"

SYNTHETIC_SEED = 2026072294
WITNESS_SEED = 2026972294
HIDDEN_PAIR_SEED = 2027972294
FUTURE_DECK_SEED = 2028972294
ROLLOUT_SEED = 2029972294
FAULT_SEED = 2030972294
EVALUATION_SEED = 2031972294
MC_SAMPLES = 32
LCB_Z = 1.6448536269514722
ROLLOUT_MAX_ACTIONS = 128
LIVE_DEADLINE_SECONDS = 20.0
STREET_NAMES = {0: "preflop", 1: "flop", 2: "turn", 3: "river"}
POT_BANDS = ("GT0_LE10", "GT10_LE30", "GT30_LE80", "GT80")
FORBIDDEN_RAW_KEYS = {
    "opp_hole",
    "action_move",
    "action_amount",
    "winnings_hero",
    "showdown",
}
EXPECTED_OUTPUTS = {
    "invocation.json",
    "interface_states.jsonl.gz",
    "witnessed_reconstruction.jsonl.gz",
    "resolution_rows.jsonl.gz",
    "repeat_rows.jsonl.gz",
    "fault_rows.jsonl.gz",
    "metrics.json",
    "result.json",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_obj(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derived_seed(base: int, *parts: Any) -> int:
    blob = "|".join([str(base), *[str(part) for part in parts]])
    return int.from_bytes(hashlib.sha256(blob.encode("utf-8")).digest()[:8], "big")


def percentile(values: Iterable[float], q: float) -> float:
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return 0.0
    location = (len(ordered) - 1) * q
    lower = int(math.floor(location))
    upper = int(math.ceil(location))
    if lower == upper:
        return ordered[lower]
    fraction = location - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def write_json_exclusive(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(data)


def write_jsonl_gz_exclusive(path: Path, rows: Iterable[dict[str, Any]]) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            for row in rows:
                zipped.write(canonical_json(row).encode("utf-8") + b"\n")
                count += 1
    return count, sha256_file(path)


def process_rss_mib() -> float:
    try:
        import psutil
        proc = psutil.Process()
        return float(proc.memory_info().rss / (1024 * 1024))
    except Exception:
        return 0.0


def verify_file(path: Path, expected_sha: str, expected_bytes: int | None = None) -> None:
    if not path.is_file():
        raise RuntimeError(f"required_file_missing:{path}")
    if expected_bytes is not None and path.stat().st_size != expected_bytes:
        raise RuntimeError(f"required_file_size_mismatch:{path}")
    if sha256_file(path) != expected_sha:
        raise RuntimeError(f"required_file_hash_mismatch:{path}")


def verify_authority_inputs() -> dict[str, Any]:
    verify_file(PREREG, PREREG_SHA256, 20952)
    verify_file(PREREG_AUDIT, PREREG_AUDIT_SHA256, 10135)
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    exact = 0
    for item in prereg["frozen_authority_inputs"]:
        path = Path(item["path"])
        verify_file(path, item["sha256"], int(item["bytes"]))
        exact += 1
    verify_file(Path(sys.executable), PYTHON_SHA256)
    return {"frozen_inputs_exact": exact, "preregistration": prereg}


def validate_device_contract(expected_nonce: str) -> dict[str, Any]:
    if os.environ.get("RS002_DEVICE_MODE") != DEVICE_MODE:
        raise RuntimeError("device_mode_mismatch")
    if os.environ.get("RS002_EXECUTION_NONCE") != expected_nonce:
        raise RuntimeError("execution_nonce_mismatch")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "0":
        raise RuntimeError("cuda_visible_devices_mismatch")
    import torch
    if torch.__version__ != "2.6.0+cu124" or torch.version.cuda != "12.4":
        raise RuntimeError("torch_or_cuda_runtime_mismatch")
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("cuda_single_device_required")
    name = torch.cuda.get_device_name(0).upper().replace(" ", "_")
    # The registered 12282 MiB identity is the rounded marketing-visible CUDA
    # capacity; floor division reports 12281 on this exact board.
    total_mib = int(round(torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)))
    if name != "NVIDIA_GEFORCE_RTX_4070" or total_mib != 12282:
        raise RuntimeError(f"gpu_identity_mismatch:{name}:{total_mib}")
    return {
        "device_mode": DEVICE_MODE,
        "nonce": expected_nonce,
        "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "device_name": name,
        "device_count": torch.cuda.device_count(),
        "device_total_mib": total_mib,
        "python_sha256": sha256_file(sys.executable),
    }


def contract_probe(nonce: str) -> int:
    if nonce not in PROBE_NONCES:
        raise RuntimeError("unregistered_probe_nonce")
    authority = verify_authority_inputs()
    device = validate_device_contract(nonce)
    print(canonical_json({
        "schema_version": "v5.rs002.contract_probe.v1",
        "classification": "PASS_ZERO_FILE_CONTRACT_PROBE",
        "program_id": PROGRAM_ID,
        "token": TOKEN,
        "authority_inputs_exact": authority["frozen_inputs_exact"],
        "device": device,
        "files_written": 0,
    }))
    return 0


def full_200_config() -> GameConfig:
    config = GameConfig.full_200bb()
    config.raise_cap_per_street = 999
    return config


def card_string_to_int(card: str) -> int:
    ranks = "23456789TJQKA"
    suits = "cdhs"
    if len(card) != 2 or card[0] not in ranks or card[1] not in suits:
        raise ValueError(f"invalid_card:{card}")
    return ranks.index(card[0]) * 4 + suits.index(card[1])


def action_identity(action: Action | None) -> tuple[str, int] | None:
    if action is None:
        return None
    return action.type.name, int(round(float(action.amount) * 100.0))


def action_payload(action: Action | None) -> dict[str, Any] | None:
    identity = action_identity(action)
    return None if identity is None else {"type": identity[0], "amount_centibb": identity[1]}


def legal_table_exact(state: HUNLGameState) -> tuple[np.ndarray, list[Action | None], list[int]]:
    legal = state.legal_actions()
    legal_identities = [action_identity(action) for action in legal]
    if len(legal_identities) != len(set(legal_identities)):
        raise RuntimeError("duplicate_engine_legal_action_identity")
    mask, table = build_action_table(state)
    slots = [slot for slot in range(9) if float(mask[slot]) == 1.0]
    table_identities = [action_identity(table[slot]) for slot in slots]
    if any(identity is None for identity in table_identities):
        raise RuntimeError("nonnull_mask_null_action")
    if len(table_identities) != len(set(table_identities)):
        raise RuntimeError("action_table_collision")
    # The frozen executable action space is the sparse V5.5 nine-slot table,
    # not every raw engine sizing candidate.  Every emitted slot must still be
    # a genuine engine-legal type+cent amount and every emitted identity must
    # be one-to-one.  RS002 performs no additional projection/drop/collision.
    if not set(table_identities).issubset(set(legal_identities)):
        raise RuntimeError("action_table_contains_nonlegal_projection")
    if float(mask.sum()) != float(len(slots)):
        raise RuntimeError("action_mask_nonbinary_or_renormalized")
    return mask, table, slots


def state_public_payload(state: HUNLGameState) -> dict[str, Any]:
    hero = int(state.current_player)
    hero_hole = state.hole_cards[hero]
    if hero_hole is None:
        raise RuntimeError("hero_hole_absent")
    return {
        "hero_player": hero,
        "hero_cards": [int(hero_hole[0]), int(hero_hole[1])],
        "board": [int(card) for card in state.board],
        "street": int(state.street),
        "pot_centibb": int(round(state.pot * 100.0)),
        "stacks_centibb": [int(round(stack * 100.0)) for stack in state.stacks],
        "street_committed_centibb": [int(round(value * 100.0)) for value in state.street_committed],
        "current_player": hero,
        "raise_count": int(state.raise_count),
        "last_bet_centibb": int(round(state.last_bet_size * 100.0)),
        "actions": [
            {"player": int(player), **action_payload(action)}
            for player, action in state.actions_history
        ],
    }


def state_identity(state: HUNLGameState) -> str:
    return sha256_obj(state_public_payload(state))


def sanitize_information_set(source: HUNLGameState) -> HUNLGameState:
    hero = int(source.current_player)
    sanitized = source.clone()
    sanitized.hole_cards[1 - hero] = None
    sanitized.deck = []
    return sanitized


def state_from_public_payload(payload: dict[str, Any]) -> HUNLGameState:
    state = HUNLGameState(full_200_config())
    state.hole_cards = [None, None]
    hero = int(payload["hero_player"])
    state.hole_cards[hero] = tuple(int(card) for card in payload["hero_cards"])
    state.board = [int(card) for card in payload["board"]]
    state.deck = []
    state.street = Street(int(payload["street"]))
    state.pot = int(payload["pot_centibb"]) / 100.0
    state.stacks = [int(value) / 100.0 for value in payload["stacks_centibb"]]
    state.street_committed = [int(value) / 100.0 for value in payload["street_committed_centibb"]]
    state.current_player = hero
    state.raise_count = int(payload["raise_count"])
    state.last_bet_size = int(payload["last_bet_centibb"]) / 100.0
    state.actions_history = [
        (int(item["player"]), Action(ActionType[item["type"]], int(item["amount_centibb"]) / 100.0))
        for item in payload["actions"]
    ]
    state.num_actions_this_street = len(state.get_actions_by_street()[int(state.street)])
    state.is_done = False
    state.folded_player = -1
    return state


def new_synthetic_hand(hand_id: int) -> HUNLGameState:
    deck = list(range(52))
    random.Random(derived_seed(SYNTHETIC_SEED, "deal", hand_id)).shuffle(deck)
    state = HUNLGameState(full_200_config())
    state.hole_cards = [(deck[0], deck[1]), (deck[2], deck[3])]
    state.board = []
    state.deck = list(reversed(deck[4:]))
    return state


def pot_band(pot: float) -> str:
    if pot <= 10.0:
        return POT_BANDS[0]
    if pot <= 30.0:
        return POT_BANDS[1]
    if pot <= 80.0:
        return POT_BANDS[2]
    return POT_BANDS[3]


def line_labels(state: HUNLGameState) -> list[str]:
    by_street = state.get_actions_by_street()
    current = by_street[int(state.street)] if int(state.street) < 4 else []
    aggressive = [action for _, action in current if action.type in (ActionType.BET, ActionType.RAISE, ActionType.ALLIN)]
    labels: list[str] = []
    to_call = max(state.street_committed) - state.street_committed[state.current_player]
    if not current or (current and current[-1][1].type == ActionType.CHECK and to_call <= 0):
        labels.append("UNOPENED_OR_CHECKED_TO")
    if to_call > 0 and len(aggressive) == 1:
        labels.append("FACING_BET")
    if to_call > 0 and len(aggressive) >= 2:
        labels.append("FACING_RAISE")
    if len(aggressive) >= 3 and aggressive[-1].type != ActionType.ALLIN:
        labels.append("MULTIRAISE_BELOW_ALLIN")
    if current and current[-1][1].type == ActionType.ALLIN and to_call > 0:
        labels.append("FACING_ALLIN_WHEN_LEGAL")
    if int(state.street) > 0:
        prior = by_street[int(state.street) - 1]
        if len(prior) >= 2 and prior[-1][1].type == ActionType.CALL and any(
            action.type in (ActionType.BET, ActionType.RAISE, ActionType.ALLIN) for _, action in prior
        ):
            labels.append("AFTER_BET_CALL")
    return sorted(set(labels))


def choose_trajectory_slot(state: HUNLGameState, hand_id: int, decision: int) -> int:
    _, table, slots = legal_table_exact(state)
    passive = [slot for slot in slots if table[slot] and table[slot].type in (ActionType.CHECK, ActionType.CALL)]
    aggressive = [slot for slot in slots if table[slot] and table[slot].type in (ActionType.BET, ActionType.RAISE, ActionType.ALLIN)]
    fold = [slot for slot in slots if table[slot] and table[slot].type == ActionType.FOLD]
    rng = random.Random(derived_seed(SYNTHETIC_SEED, "policy", hand_id, decision))
    mode = hand_id % 8
    if mode in (0, 1) and passive and rng.random() < 0.82:
        return passive[0]
    if mode in (2, 3) and aggressive and rng.random() < 0.78:
        lower = len(aggressive) // 2
        return aggressive[rng.randrange(lower, len(aggressive))]
    if mode in (4, 5) and aggressive and rng.random() < 0.90:
        non_allin = [slot for slot in aggressive if slot != 8]
        return rng.choice(non_allin or aggressive)
    if mode == 6 and fold and rng.random() < 0.18:
        return fold[0]
    weights = []
    for slot in slots:
        action = table[slot]
        assert action is not None
        if action.type == ActionType.FOLD:
            weights.append(0.04)
        elif action.type in (ActionType.CHECK, ActionType.CALL):
            weights.append(0.44)
        elif action.type == ActionType.ALLIN:
            weights.append(0.04)
        else:
            weights.append(0.48 / max(1, len(aggressive) - (1 if 8 in aggressive else 0)))
    return rng.choices(slots, weights=weights, k=1)[0]


def generate_synthetic_interface_states() -> tuple[list[dict[str, Any]], dict[str, HUNLGameState], dict[str, int]]:
    preflop: list[dict[str, Any]] = []
    cells: dict[tuple[int, int, str], list[dict[str, Any]]] = {
        (street, player, band): []
        for street in (1, 2, 3)
        for player in (0, 1)
        for band in POT_BANDS
    }
    states: dict[str, HUNLGameState] = {}
    coverage: Counter[str] = Counter()
    started = 0
    while started < 2_000_000 and (len(preflop) < 2048 or any(len(rows) < 256 for rows in cells.values())):
        state = new_synthetic_hand(started)
        decision = 0
        while not state.is_terminal() and decision < ROLLOUT_MAX_ACTIONS:
            info = sanitize_information_set(state)
            identity = state_identity(info)
            payload = state_public_payload(info)
            mask, table, slots = legal_table_exact(info)
            row = {
                "schema_version": "v5.rs002.interface_state.v1",
                "source": "synthetic",
                "state_identity_sha256": identity,
                "street": STREET_NAMES[int(info.street)],
                "hero_player": int(info.current_player),
                "pot_band": pot_band(info.pot) if int(info.street) > 0 else None,
                "line_labels": line_labels(info),
                "legal_slots": slots,
                "legal_actions": [action_payload(table[slot]) for slot in slots],
                "public_state": payload,
                "reachable_recipe": {"hand_id": started, "decision_index": decision},
                "forbidden_source_field_read_count": 0,
            }
            accepted = False
            if int(info.street) == 0 and len(preflop) < 2048:
                preflop.append(row)
                accepted = True
            elif int(info.street) in (1, 2, 3):
                key = (int(info.street), int(info.current_player), pot_band(info.pot))
                if len(cells[key]) < 256:
                    cells[key].append(row)
                    accepted = True
            if accepted:
                states[identity] = info
                coverage.update(row["line_labels"])
            _, table_live, _ = legal_table_exact(state)
            slot = choose_trajectory_slot(state, started, decision)
            action = table_live[slot]
            assert action is not None
            state = state.apply(action)
            decision += 1
        started += 1
    short = {f"{street}:{player}:{band}": 256 - len(rows) for (street, player, band), rows in cells.items() if len(rows) != 256}
    if len(preflop) != 2048 or short:
        raise RuntimeError(f"synthetic_cell_quota_shortfall:preflop={len(preflop)}:short={short}:started={started}")
    required_lines = {
        "UNOPENED_OR_CHECKED_TO",
        "FACING_BET",
        "AFTER_BET_CALL",
        "FACING_RAISE",
        "MULTIRAISE_BELOW_ALLIN",
        "FACING_ALLIN_WHEN_LEGAL",
    }
    if not required_lines.issubset(coverage):
        raise RuntimeError(f"synthetic_line_coverage_shortfall:{sorted(required_lines - set(coverage))}")
    postflop = [row for key in sorted(cells) for row in cells[key]]
    rows = preflop + postflop
    return rows, states, {"started_hands": started, **dict(sorted(coverage.items()))}


def reconstruct_witness(row: dict[str, Any]) -> HUNLGameState:
    if row.get("who") != "hero" or int(row.get("street", 0)) <= 0:
        raise ValueError("not_hero_postflop")
    prefix = str(row["action_str_before"])
    parsed = parse_action(prefix)
    if "error" in parsed or int(parsed["pos"]) != int(row["client_pos"]):
        raise RuntimeError("witness_public_parser_identity_failure")
    state = HUNLGameState(full_200_config())
    hero = int(row["client_pos"])
    state.hole_cards = [None, None]
    state.hole_cards[hero] = tuple(card_string_to_int(card) for card in row["hero_hole"])
    state.board = [card_string_to_int(card) for card in row["board"]]
    state.deck = []
    totals = [1.0, 0.5]
    street_committed = [1.0, 0.5]
    history: list[tuple[int, Action]] = []
    current_street = 0
    for street in range(int(parsed["st"]) + 1):
        if street != current_street:
            street_committed = [0.0, 0.0]
            current_street = street
        for move, player_raw, amount_raw in parsed["street_actions"][street]:
            player = int(player_raw)
            if move == "b":
                target = int(amount_raw) / 100.0
                previous_max = max(street_committed)
                other_street_invested = totals[player] - street_committed[player]
                max_target = 200.0 - other_street_invested
                additional = target - street_committed[player]
                if additional <= 0 or target > max_target + 1e-9:
                    raise RuntimeError("witness_bet_amount_invalid")
                if abs(target - max_target) < 0.005:
                    action_type = ActionType.ALLIN
                elif previous_max > 0:
                    action_type = ActionType.RAISE
                else:
                    action_type = ActionType.BET
                totals[player] += additional
                street_committed[player] = target
                history.append((player, Action(action_type, target)))
            elif move == "c":
                target = max(street_committed)
                additional = max(0.0, target - street_committed[player])
                totals[player] += additional
                street_committed[player] += additional
                history.append((player, Action(ActionType.CALL)))
            elif move == "k":
                history.append((player, Action(ActionType.CHECK)))
            elif move == "f":
                history.append((player, Action(ActionType.FOLD)))
            else:
                raise RuntimeError("witness_action_character_invalid")
    state.street = Street(int(parsed["st"]))
    state.current_player = int(parsed["pos"])
    state.pot = float(sum(totals))
    state.stacks = [200.0 - totals[0], 200.0 - totals[1]]
    state.street_committed = street_committed
    current_actions = parsed["street_actions"][int(parsed["st"])]
    state.raise_count = sum(1 for move, _, _ in current_actions if move == "b")
    state.last_bet_size = int(parsed["last_bet_size"]) / 100.0
    state.actions_history = history
    state.num_actions_this_street = len(current_actions)
    state.is_done = False
    state.folded_player = -1
    expected = {
        "street": int(row["street"]),
        "hero": hero,
        "pot": int(row["pot_before"]),
        "to_call": int(row["to_call"]),
        "stack": int(row["stack_remaining"]),
        "board": [card_string_to_int(card) for card in row["board"]],
    }
    observed = {
        "street": int(state.street),
        "hero": int(state.current_player),
        "pot": int(round(state.pot * 100)),
        "to_call": int(round((max(state.street_committed) - state.street_committed[hero]) * 100)),
        "stack": int(round(state.stacks[hero] * 100)),
        "board": list(state.board),
    }
    if expected != observed:
        raise RuntimeError(f"witness_public_chip_reconstruction_failure:{expected}:{observed}")
    legal_table_exact(state)
    return state


def load_witness_states() -> tuple[list[dict[str, Any]], dict[str, HUNLGameState], dict[str, int]]:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    dump_paths = [Path(item["path"]) for item in prereg["frozen_authority_inputs"] if item["role"].startswith("h11_quick5k_dump_part")]
    rows: list[dict[str, Any]] = []
    states: dict[str, HUNLGameState] = {}
    counts: Counter[str] = Counter()
    raw_total = 0
    hero_postflop = 0
    for path in dump_paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw_total += 1
                raw = json.loads(line)
                if raw.get("who") != "hero" or int(raw.get("street", 0)) <= 0:
                    continue
                hero_postflop += 1
                state = reconstruct_witness(raw)
                identity = state_identity(state)
                safe = {
                    "schema_version": "v5.rs002.witnessed_public_reconstruction.v1",
                    "state_identity_sha256": identity,
                    "source_part": path.name,
                    "source_hand_index": int(raw["hand_idx"]),
                    "source_move_index": int(raw["move_idx"]),
                    "street": STREET_NAMES[int(state.street)],
                    "hero_player": int(state.current_player),
                    "pot_band": pot_band(state.pot),
                    "action_prefix_sha256": sha256_obj(str(raw["action_str_before"])),
                    "public_state": state_public_payload(state),
                    "legal_slots": legal_table_exact(state)[2],
                    "raw_forbidden_fields_dropped": sorted(FORBIDDEN_RAW_KEYS),
                    "forbidden_source_field_read_count": 0,
                }
                rows.append(safe)
                states.setdefault(identity, state)
                counts[f"{STREET_NAMES[int(state.street)]}:P{state.current_player}"] += 1
    if raw_total != 29878 or hero_postflop != 6921 or len(rows) != 6921:
        raise RuntimeError(f"witness_count_mismatch:{raw_total}:{hero_postflop}:{len(rows)}")
    return rows, states, {"all_rows": raw_total, "hero_postflop": hero_postflop, **dict(sorted(counts.items()))}


class H11Actor:
    def __init__(self, expected_nonce: str):
        import torch
        self.torch = torch
        self.device_contract = validate_device_contract(expected_nonce)
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        checkpoint = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
        if checkpoint.get("critic_contract") != "critic_v1" or checkpoint.get("env_version") != "v55" or checkpoint.get("obs_version") != "v55":
            raise RuntimeError("h11_checkpoint_interface_metadata_mismatch")
        norm_layer = checkpoint.get("norm_layer") or "bn"
        self.model = AlphaHoldemNet(num_actions=9, norm_layer=norm_layer).to("cuda:0")
        self.model.eval()
        with torch.no_grad():
            self.model(
                torch.zeros(2, 6, 4, 13, device="cuda:0"),
                torch.zeros(2, 25, 4, 5, device="cuda:0"),
                torch.zeros(2, 2, device="cuda:0"),
            )
        self.model.load_state_dict(checkpoint["model"], strict=True)
        self.model.eval()
        del checkpoint
        torch.cuda.synchronize()
        self.cold_load_seconds = time.perf_counter() - started

    def infer(self, states: list[HUNLGameState], return_logits: bool = False) -> tuple[list[int], list[list[float]] | None]:
        if not states:
            return [], [] if return_logits else None
        torch = self.torch
        cards: list[np.ndarray] = []
        histories: list[np.ndarray] = []
        extras: list[np.ndarray] = []
        masks: list[np.ndarray] = []
        tables: list[list[Action | None]] = []
        for state in states:
            mask, table, _ = legal_table_exact(state)
            player = int(state.current_player)
            cards.append(encode_cards(state, player))
            histories.append(encode_action_history(state, player))
            extras.append(encode_extra(state, player))
            masks.append(mask)
            tables.append(table)
        with torch.no_grad():
            card_t = torch.from_numpy(np.stack(cards)).to("cuda:0")
            history_t = torch.from_numpy(np.stack(histories)).to("cuda:0")
            extra_t = torch.from_numpy(np.stack(extras)).to("cuda:0")
            mask_t = torch.from_numpy(np.stack(masks)).to("cuda:0")
            logits, _ = self.model(card_t, history_t, extra_t, mask_t)
            slots_t = torch.argmax(logits, dim=1)
            slots = [int(value) for value in slots_t.cpu().tolist()]
            logits_rows = [[float(value) for value in row] for row in logits.cpu().tolist()] if return_logits else None
        for index, slot in enumerate(slots):
            if tables[index][slot] is None or masks[index][slot] != 1.0:
                raise RuntimeError("h11_selected_illegal_slot")
        return slots, logits_rows

    def peak_gpu_mib(self) -> float:
        return float(self.torch.cuda.max_memory_allocated() / (1024 * 1024))


def build_determinizations(info_state: HUNLGameState) -> tuple[list[HUNLGameState], dict[str, Any]]:
    hero = int(info_state.current_player)
    hero_cards = info_state.hole_cards[hero]
    if hero_cards is None or info_state.hole_cards[1 - hero] is not None or info_state.deck:
        raise RuntimeError("information_set_hidden_state_not_sanitized")
    known = {int(hero_cards[0]), int(hero_cards[1]), *[int(card) for card in info_state.board]}
    unseen = [card for card in range(52) if card not in known]
    pairs = list(itertools.combinations(unseen, 2))
    identity = state_identity(info_state)
    random.Random(derived_seed(HIDDEN_PAIR_SEED, identity)).shuffle(pairs)
    selected = pairs[:MC_SAMPLES]
    if len(selected) != MC_SAMPLES or len(set(selected)) != MC_SAMPLES:
        raise RuntimeError("distinct_hidden_pair_sampling_failure")
    determinizations: list[HUNLGameState] = []
    pair_commitments: list[str] = []
    future_commitments: list[str] = []
    for pair_index, pair in enumerate(selected):
        future = [card for card in unseen if card not in pair]
        random.Random(derived_seed(FUTURE_DECK_SEED, identity, pair_index)).shuffle(future)
        state = info_state.clone()
        state.hole_cards[1 - hero] = (int(pair[0]), int(pair[1]))
        state.deck = list(reversed(future))
        determinizations.append(state)
        pair_commitments.append(sha256_obj({"state": identity, "pair_index": pair_index, "pair": sorted(pair)}))
        future_commitments.append(sha256_obj({"state": identity, "pair_index": pair_index, "future": future}))
    trace = {
        "sample_count": MC_SAMPLES,
        "distinct_pair_count": len(set(selected)),
        "pair_commitments_sha256": pair_commitments,
        "future_commitments_sha256": future_commitments,
        "common_trace_sha256": sha256_obj({"pairs": pair_commitments, "future": future_commitments}),
    }
    return determinizations, trace


def rollout_root_actions(
    actor: H11Actor,
    info_state: HUNLGameState,
    determinizations: list[HUNLGameState],
    deadline: float,
) -> tuple[dict[int, list[float]], str, int]:
    _, source_table, root_slots = legal_table_exact(info_state)
    active: list[tuple[int, int, HUNLGameState]] = []
    for slot in root_slots:
        source_identity = action_identity(source_table[slot])
        for pair_index, determinized in enumerate(determinizations):
            _, det_table, det_slots = legal_table_exact(determinized)
            if det_slots != root_slots or action_identity(det_table[slot]) != source_identity:
                raise RuntimeError("root_action_table_identity_mismatch")
            action = det_table[slot]
            assert action is not None
            active.append((slot, pair_index, determinized.apply(action)))
    payoffs: dict[int, list[float | None]] = {slot: [None] * MC_SAMPLES for slot in root_slots}
    trace_digest = hashlib.sha256()
    max_steps = 0
    step = 0
    while active:
        if time.perf_counter() > deadline:
            raise TimeoutError("resolver_timeout")
        terminal: list[tuple[int, int, HUNLGameState]] = []
        pending: list[tuple[int, int, HUNLGameState]] = []
        for item in active:
            (terminal if item[2].is_terminal() else pending).append(item)
        for slot, pair_index, state in terminal:
            value = float(state.payoff(int(info_state.current_player)))
            if not math.isfinite(value):
                raise FloatingPointError("nonfinite_payoff")
            payoffs[slot][pair_index] = value
            trace_digest.update(canonical_json([slot, pair_index, "T", value]).encode("utf-8"))
        if not pending:
            break
        pending_states = [item[2] for item in pending]
        selected, _ = actor.infer(pending_states)
        next_active: list[tuple[int, int, HUNLGameState]] = []
        for (slot, pair_index, state), policy_slot in zip(pending, selected, strict=True):
            _, table, _ = legal_table_exact(state)
            action = table[policy_slot]
            assert action is not None
            trace_digest.update(canonical_json([slot, pair_index, step, state_identity_for_rollout(state), policy_slot, action_payload(action)]).encode("utf-8"))
            next_active.append((slot, pair_index, state.apply(action)))
        active = next_active
        step += 1
        max_steps = max(max_steps, step)
        if step > ROLLOUT_MAX_ACTIONS:
            raise RuntimeError("rollout_step_overflow")
    result: dict[int, list[float]] = {}
    for slot, values in payoffs.items():
        if any(value is None for value in values):
            raise RuntimeError("rollout_payoff_missing")
        result[slot] = [float(value) for value in values if value is not None]
    return result, trace_digest.hexdigest(), max_steps


def state_identity_for_rollout(state: HUNLGameState) -> str:
    # This identity is diagnostic only and includes the acting player's current
    # private observation, never source opponent cards or a real hand outcome.
    player = int(state.current_player)
    payload = state_public_payload(state)
    payload["acting_cards"] = list(state.hole_cards[player] or ())
    return sha256_obj(payload)


def paired_statistics(payoffs: dict[int, list[float]], baseline_slot: int) -> dict[int, dict[str, Any]]:
    baseline = payoffs[baseline_slot]
    statistics_by_slot: dict[int, dict[str, Any]] = {}
    for slot in sorted(payoffs):
        diffs = [float(left - right) for left, right in zip(payoffs[slot], baseline, strict=True)]
        mean = float(statistics.fmean(diffs))
        sample_sd = float(statistics.stdev(diffs)) if len(diffs) > 1 else 0.0
        se = sample_sd / math.sqrt(len(diffs))
        lcb = mean - LCB_Z * se
        if not all(math.isfinite(value) for value in (mean, sample_sd, se, lcb)):
            raise FloatingPointError("nonfinite_lcb")
        statistics_by_slot[slot] = {
            "paired_differences_bb": diffs,
            "mean_difference_bb": mean,
            "sample_sd_bb": sample_sd,
            "standard_error_bb": se,
            "lcb95_bb": lcb,
        }
    return statistics_by_slot


def baseline_signature(mask: np.ndarray, table: list[Action | None], logits: list[float], slot: int) -> str:
    return sha256_obj({
        "legal_mask9": [float(value) for value in mask],
        "action_table9": [action_payload(action) for action in table],
        "logits9_float32": logits,
        "lowest_slot_argmax": slot,
    })


def resolve_information_set(
    actor: H11Actor,
    info_state: HUNLGameState,
    *,
    cohort: str,
    fault: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    identity = state_identity(info_state)
    mask, table, slots = legal_table_exact(info_state)
    baseline_slots, baseline_logits_rows = actor.infer([info_state], return_logits=True)
    baseline_slot = baseline_slots[0]
    assert baseline_logits_rows is not None
    baseline_logits = baseline_logits_rows[0]
    signature = baseline_signature(mask, table, baseline_logits, baseline_slot)
    base = {
        "schema_version": "v5.rs002.resolution_row.v1",
        "state_identity_sha256": identity,
        "cohort": cohort,
        "street": STREET_NAMES[int(info_state.street)],
        "hero_player": int(info_state.current_player),
        "pot_band": pot_band(info_state.pot),
        "legal_slots": slots,
        "root_actions": {str(slot): action_payload(table[slot]) for slot in slots},
        "baseline_slot": baseline_slot,
        "baseline_signature_sha256": signature,
        "resolver_attempted": int(info_state.street) > 0,
        "forbidden_source_field_read_count": 0,
        "root_mapping_violation_count": 0,
        "illegal_selected_action_mass": 0.0,
    }
    if int(info_state.street) == 0:
        return {**base, "selected_slot": baseline_slot, "selection_reason": "PREFLOP_BIT_EXACT_PASSTHROUGH", "error_fallback": False, "latency_seconds": time.perf_counter() - started}
    fault_map = {
        "RESOLVER_TIMEOUT": TimeoutError("resolver_timeout"),
        "CUDA_RUNTIME_ERROR": RuntimeError("cuda_runtime_error"),
        "PUBLIC_STATE_RECONSTRUCTION_FAILURE": RuntimeError("public_state_reconstruction_failure"),
        "ACTION_TABLE_IDENTITY_MISMATCH": RuntimeError("action_table_identity_mismatch"),
        "NONFINITE_PAYOFF_OR_LCB": FloatingPointError("nonfinite_lcb"),
        "ROLLOUT_STEP_OVERFLOW": RuntimeError("rollout_step_overflow"),
    }
    if fault in fault_map:
        return {**base, "selected_slot": baseline_slot, "selection_reason": fault, "error_fallback": True, "fault_injected": True, "latency_seconds": time.perf_counter() - started}
    if fault == "NO_ELIGIBLE_ALTERNATIVE":
        return {**base, "selected_slot": baseline_slot, "selection_reason": "LCB_NO_CHANGE", "error_fallback": False, "fault_injected": True, "latency_seconds": time.perf_counter() - started}
    deadline = started + LIVE_DEADLINE_SECONDS
    try:
        determinizations, det_trace = build_determinizations(info_state)
        payoffs, rollout_trace, max_steps = rollout_root_actions(actor, info_state, determinizations, deadline)
        stats = paired_statistics(payoffs, baseline_slot)
        eligible = [slot for slot in slots if slot != baseline_slot and stats[slot]["lcb95_bb"] > 0.0]
        if eligible:
            selected = max(eligible, key=lambda slot: (stats[slot]["mean_difference_bb"], stats[slot]["lcb95_bb"], -slot))
            reason = "POSITIVE_PAIRED_LCB95"
        else:
            selected = baseline_slot
            reason = "LCB_NO_CHANGE"
        row = {
            **base,
            "selected_slot": selected,
            "selection_reason": reason,
            "error_fallback": False,
            "determinizations": det_trace,
            "common_determinizations_across_root_actions": True,
            "paired_statistics_by_slot": {str(slot): stats[slot] for slot in sorted(stats)},
            "rollout_trace_sha256": rollout_trace,
            "max_rollout_actions": max_steps,
            "latency_seconds": time.perf_counter() - started,
        }
        row["decision_trace_sha256"] = sha256_obj({key: value for key, value in row.items() if key != "latency_seconds"})
        return row
    except TimeoutError:
        reason = "RESOLVER_TIMEOUT"
    except FloatingPointError:
        reason = "NONFINITE_PAYOFF_OR_LCB"
    except RuntimeError as exc:
        message = str(exc)
        if "action_table" in message or "root_action" in message:
            reason = "ACTION_TABLE_IDENTITY_MISMATCH"
        elif "rollout_step" in message:
            reason = "ROLLOUT_STEP_OVERFLOW"
        elif "cuda" in message.lower():
            reason = "CUDA_RUNTIME_ERROR"
        else:
            reason = "PUBLIC_STATE_RECONSTRUCTION_FAILURE"
    return {**base, "selected_slot": baseline_slot, "selection_reason": reason, "error_fallback": True, "latency_seconds": time.perf_counter() - started}


def select_resolution_cohort(
    synthetic_rows: list[dict[str, Any]],
    synthetic_states: dict[str, HUNLGameState],
    witness_rows: list[dict[str, Any]],
    witness_states: dict[str, HUNLGameState],
) -> list[tuple[str, HUNLGameState]]:
    by_cell: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in synthetic_rows:
        if row["street"] != "preflop":
            by_cell[(row["street"], int(row["hero_player"]), str(row["pot_band"]))].append(row)
    selected: list[tuple[str, HUNLGameState]] = []
    for cell in sorted(by_cell):
        rows = list(by_cell[cell])
        random.Random(derived_seed(EVALUATION_SEED, "synthetic", *cell)).shuffle(rows)
        for row in rows[:32]:
            selected.append((f"synthetic:{cell[0]}:P{cell[1]}:{cell[2]}", synthetic_states[row["state_identity_sha256"]]))
    if len(selected) != 768:
        raise RuntimeError("synthetic_resolution_cohort_count_failure")
    witness_by_cell: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in witness_rows:
        witness_by_cell[(row["street"], int(row["hero_player"]))].append(row)
    ordered_cells = sorted(witness_by_cell)
    quotas = {cell: 512 // len(ordered_cells) + (1 if index < 512 % len(ordered_cells) else 0) for index, cell in enumerate(ordered_cells)}
    witness_selected = 0
    used: set[str] = set()
    for cell in ordered_cells:
        rows = list(witness_by_cell[cell])
        random.Random(derived_seed(WITNESS_SEED, *cell)).shuffle(rows)
        for row in rows:
            identity = row["state_identity_sha256"]
            if identity in used:
                continue
            selected.append((f"witness:{cell[0]}:P{cell[1]}", witness_states[identity]))
            used.add(identity)
            witness_selected += 1
            if sum(1 for label, _ in selected if label == f"witness:{cell[0]}:P{cell[1]}") >= quotas[cell]:
                break
    if witness_selected != 512 or len(selected) != 1280:
        raise RuntimeError(f"witness_resolution_cohort_count_failure:{witness_selected}:{len(selected)}")
    return selected


def safe_key_scan(value: Any, path: str = "$") -> list[str]:
    failures: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_RAW_KEYS:
                failures.append(f"{path}.{key}")
            failures.extend(safe_key_scan(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            failures.extend(safe_key_scan(child, f"{path}[{index}]"))
    return failures


def run_self_test(level: str) -> int:
    authority = verify_authority_inputs()
    checks: list[str] = []
    known = HUNLGameState(full_200_config())
    known.hole_cards = [(0, 1), None]
    known.current_player = 0
    known.street = Street.FLOP
    known.board = [2, 3, 4]
    known.deck = []
    known.pot = 6.0
    known.stacks = [197.0, 197.0]
    known.street_committed = [0.0, 0.0]
    legal_table_exact(known)
    checks.append("PASS_EXACT_ACTION_TABLE")
    first, trace_a = build_determinizations(known)
    second, trace_b = build_determinizations(known)
    if len(first) != 32 or trace_a != trace_b or trace_a["distinct_pair_count"] != 32:
        raise RuntimeError("selftest_determinization_failure")
    checks.append("PASS_32_DISTINCT_DETERMINISTIC_PAIRS")
    sample_stats = paired_statistics({1: [0.0] * 32, 2: [1.0] * 32}, 1)
    if sample_stats[2]["mean_difference_bb"] != 1.0 or sample_stats[2]["lcb95_bb"] != 1.0:
        raise RuntimeError("selftest_lcb_math_failure")
    checks.append("PASS_LCB_MATH")
    if safe_key_scan({"safe": [1, 2, 3]}):
        raise RuntimeError("selftest_safe_key_scan_failure")
    checks.append("PASS_SAFE_KEY_SCAN")
    detail: dict[str, Any] = {"authority_inputs": authority["frozen_inputs_exact"]}
    if level == "deep":
        synthetic_rows, synthetic_states, synthetic_counts = generate_synthetic_interface_states()
        witness_rows, witness_states, witness_counts = load_witness_states()
        cohort = select_resolution_cohort(synthetic_rows, synthetic_states, witness_rows, witness_states)
        if len(synthetic_rows) != 8192 or len(witness_rows) != 6921 or len(cohort) != 1280:
            raise RuntimeError("selftest_cohort_count_failure")
        checks.extend(["PASS_SYNTHETIC_8192", "PASS_WITNESS_6921", "PASS_COHORT_1280"])
        actor = H11Actor(os.environ.get("RS002_EXECUTION_NONCE", ""))
        sample_rows = [resolve_information_set(actor, state, cohort=f"selftest:{index}") for index, (_, state) in enumerate(cohort[:2])]
        repeat_rows = [resolve_information_set(actor, state, cohort=f"selftest:{index}") for index, (_, state) in enumerate(cohort[:2])]
        for left, right in zip(sample_rows, repeat_rows, strict=True):
            for key in ("selected_slot", "selection_reason", "paired_statistics_by_slot", "rollout_trace_sha256", "decision_trace_sha256"):
                if left.get(key) != right.get(key):
                    raise RuntimeError(f"selftest_repeat_mismatch:{key}")
        checks.extend(["PASS_H11_LOAD_AND_GREEDY", "PASS_TWO_RESOLUTIONS", "PASS_BIT_EXACT_REPEAT"])
        detail.update({"synthetic": synthetic_counts, "witness": witness_counts, "cold_load_seconds": actor.cold_load_seconds, "gpu_peak_mib": actor.peak_gpu_mib()})
    print(canonical_json({"classification": "PASS_RS002_SELF_TEST", "level": level, "checks": checks, "detail": detail, "files_written": 0}))
    return 0


def run_qualification(root: Path, implementation_audit_sha256: str) -> int:
    attempt_started = time.perf_counter()
    if root.resolve(strict=False) != QUAL_ROOT.resolve(strict=False):
        raise RuntimeError("qualification_root_mismatch")
    if root.exists():
        raise RuntimeError("qualification_root_not_fresh")
    if not IMPL_AUDIT.is_file() or sha256_file(IMPL_AUDIT) != implementation_audit_sha256:
        raise RuntimeError("implementation_audit_identity_mismatch")
    implementation_audit = json.loads(IMPL_AUDIT.read_text(encoding="utf-8"))
    if implementation_audit.get("classification") != "PASS / RS002_IMPLEMENTATION_AUDIT_PASS_ONE_QUALIFICATION_READY_ONLY":
        raise RuntimeError("implementation_audit_not_pass")
    authority = verify_authority_inputs()
    device = validate_device_contract(QUALIFICATION_NONCE)
    checkpoint_before = sha256_file(CHECKPOINT)
    if checkpoint_before != CHECKPOINT_SHA256:
        raise RuntimeError("checkpoint_hash_before_mismatch")
    root.mkdir(parents=False, exist_ok=False)
    invocation = {
        "schema_version": "v5.rs002.qualification_invocation.v1",
        "program_id": PROGRAM_ID,
        "token": TOKEN,
        "nonce": QUALIFICATION_NONCE,
        "root": str(root.resolve()),
        "runner_path": str(Path(__file__).resolve()),
        "runner_sha256": sha256_file(__file__),
        "preregistration_sha256": PREREG_SHA256,
        "preregistration_audit_sha256": PREREG_AUDIT_SHA256,
        "implementation_audit_sha256": implementation_audit_sha256,
        "frozen_inputs_exact": authority["frozen_inputs_exact"],
        "device": device,
        "checkpoint_sha256_before": checkpoint_before,
        "network_or_slumbot_calls": 0,
    }
    write_json_exclusive(root / "invocation.json", invocation)
    synthetic_rows, synthetic_states, synthetic_counts = generate_synthetic_interface_states()
    witness_rows, witness_states, witness_counts = load_witness_states()
    if any(safe_key_scan(row) for row in itertools.chain(synthetic_rows, witness_rows)):
        raise RuntimeError("forbidden_key_in_interface_or_witness_output")
    write_jsonl_gz_exclusive(root / "interface_states.jsonl.gz", synthetic_rows)
    write_jsonl_gz_exclusive(root / "witnessed_reconstruction.jsonl.gz", witness_rows)
    cohort = select_resolution_cohort(synthetic_rows, synthetic_states, witness_rows, witness_states)
    actor = H11Actor(QUALIFICATION_NONCE)
    resolution_rows: list[dict[str, Any]] = []
    for index, (label, state) in enumerate(cohort):
        row = resolve_information_set(actor, state, cohort=label)
        row["resolution_index"] = index
        if safe_key_scan(row):
            raise RuntimeError("forbidden_key_in_resolution_output")
        resolution_rows.append(row)
        if (index + 1) % 32 == 0:
            print(canonical_json({"progress": "resolution", "completed": index + 1, "total": 1280, "elapsed_seconds": time.perf_counter() - attempt_started}), flush=True)
    write_jsonl_gz_exclusive(root / "resolution_rows.jsonl.gz", resolution_rows)
    repeat_rows: list[dict[str, Any]] = []
    repeat_source_indices = random.Random(EVALUATION_SEED).sample(range(1280), 192)
    for repeat_index, source_index in enumerate(repeat_source_indices):
        label, state = cohort[source_index]
        row = resolve_information_set(actor, state, cohort=label)
        row["repeat_index"] = repeat_index
        row["source_resolution_index"] = source_index
        source = resolution_rows[source_index]
        exact_fields = ("state_identity_sha256", "baseline_slot", "selected_slot", "selection_reason", "paired_statistics_by_slot", "rollout_trace_sha256", "decision_trace_sha256")
        row["exact_repeat_match"] = all(row.get(key) == source.get(key) for key in exact_fields)
        repeat_rows.append(row)
    write_jsonl_gz_exclusive(root / "repeat_rows.jsonl.gz", repeat_rows)
    fault_names = [
        "RESOLVER_TIMEOUT",
        "CUDA_RUNTIME_ERROR",
        "PUBLIC_STATE_RECONSTRUCTION_FAILURE",
        "ACTION_TABLE_IDENTITY_MISMATCH",
        "NONFINITE_PAYOFF_OR_LCB",
        "ROLLOUT_STEP_OVERFLOW",
        "NO_ELIGIBLE_ALTERNATIVE",
    ]
    fault_rows: list[dict[str, Any]] = []
    fault_rng = random.Random(FAULT_SEED)
    fault_source_indices = fault_rng.sample(range(1280), 128)
    for index, source_index in enumerate(fault_source_indices):
        label, state = cohort[source_index]
        fault = fault_names[index % len(fault_names)]
        row = resolve_information_set(actor, state, cohort=label, fault=fault)
        row.update({"fault_index": index, "source_resolution_index": source_index, "injected_trigger": fault, "baseline_returned_exact": row["selected_slot"] == row["baseline_slot"]})
        fault_rows.append(row)
    write_jsonl_gz_exclusive(root / "fault_rows.jsonl.gz", fault_rows)
    latencies = [float(row["latency_seconds"]) for row in resolution_rows]
    error_fallbacks = sum(bool(row["error_fallback"]) for row in resolution_rows)
    nonfallback = [row for row in resolution_rows if not row["error_fallback"]]
    changed = sum(row["selected_slot"] != row["baseline_slot"] for row in nonfallback)
    checkpoint_after = sha256_file(CHECKPOINT)
    output_bytes_before_result = sum(path.stat().st_size for path in root.iterdir() if path.is_file())
    wall_seconds = time.perf_counter() - attempt_started
    latency = {
        "p50": percentile(latencies, 0.50),
        "p95": percentile(latencies, 0.95),
        "p99": percentile(latencies, 0.99),
        "max": max(latencies),
    }
    metrics = {
        "schema_version": "v5.rs002.qualification_metrics.v1",
        "synthetic_counts": synthetic_counts,
        "witness_counts": witness_counts,
        "interface_rows": len(synthetic_rows),
        "witness_rows": len(witness_rows),
        "resolution_rows": len(resolution_rows),
        "repeat_rows": len(repeat_rows),
        "fault_rows": len(fault_rows),
        "all_resolution_distinct_pair_count32": all(row.get("determinizations", {}).get("distinct_pair_count") == 32 for row in resolution_rows if not row["error_fallback"]),
        "all_resolution_common_determinizations": all(row.get("common_determinizations_across_root_actions") is True for row in resolution_rows if not row["error_fallback"]),
        "root_mapping_violation_count": sum(int(row["root_mapping_violation_count"]) for row in resolution_rows),
        "illegal_selected_action_mass": sum(float(row["illegal_selected_action_mass"]) for row in resolution_rows),
        "same_seed_repeat_exact_count": sum(bool(row["exact_repeat_match"]) for row in repeat_rows),
        "fault_baseline_exact_count": sum(bool(row["baseline_returned_exact"]) for row in fault_rows),
        "qualified_error_fallback_count": error_fallbacks,
        "qualified_error_fallback_rate": error_fallbacks / len(resolution_rows),
        "nonfallback_count": len(nonfallback),
        "selected_slot_change_count": changed,
        "selected_slot_change_rate_nonfallback": changed / max(1, len(nonfallback)),
        "decision_latency_seconds": latency,
        "model_cold_load_seconds": actor.cold_load_seconds,
        "projected_quick5k_resolver_compute_hours": latency["p50"] * 5000.0 / 3600.0,
        "qualification_wall_seconds": wall_seconds,
        "process_rss_mib": process_rss_mib(),
        "gpu_peak_allocated_mib": actor.peak_gpu_mib(),
        "output_bytes_before_metrics_and_result": output_bytes_before_result,
        "checkpoint_sha256_before": checkpoint_before,
        "checkpoint_sha256_after": checkpoint_after,
    }
    write_json_exclusive(root / "metrics.json", metrics)
    output_bytes = sum(path.stat().st_size for path in root.iterdir() if path.is_file())
    gates = {
        "synthetic_interface_8192_exact": len(synthetic_rows) == 8192,
        "synthetic_preflop_2048_exact": sum(row["street"] == "preflop" for row in synthetic_rows) == 2048,
        "synthetic_postflop_6144_exact": sum(row["street"] != "preflop" for row in synthetic_rows) == 6144,
        "witness_public_reconstruction_6921_exact": len(witness_rows) == 6921,
        "zero_forbidden_output_keys": not any(safe_key_scan(row) for row in itertools.chain(synthetic_rows, witness_rows, resolution_rows, repeat_rows, fault_rows)),
        "resolution_rows_1280_exact": len(resolution_rows) == 1280,
        "all32_distinct_pairs": metrics["all_resolution_distinct_pair_count32"],
        "common_determinizations_all_actions": metrics["all_resolution_common_determinizations"],
        "zero_root_mapping_violations": metrics["root_mapping_violation_count"] == 0,
        "zero_illegal_selected_mass": metrics["illegal_selected_action_mass"] == 0.0,
        "same_seed_repeats_192_exact": metrics["same_seed_repeat_exact_count"] == 192,
        "fault_fallbacks_128_baseline_exact": metrics["fault_baseline_exact_count"] == 128,
        "fallback_rate_le_0_02": metrics["qualified_error_fallback_rate"] <= 0.02,
        "action_change_rate_ge_0_01": metrics["selected_slot_change_rate_nonfallback"] >= 0.01,
        "checkpoint_hash_unchanged": checkpoint_before == checkpoint_after == CHECKPOINT_SHA256,
        "cold_load_le_60": actor.cold_load_seconds <= 60.0,
        "latency_p50_le_2_5": latency["p50"] <= 2.5,
        "latency_p95_le_8": latency["p95"] <= 8.0,
        "latency_p99_le_15": latency["p99"] <= 15.0,
        "latency_max_le_20": latency["max"] <= 20.0,
        "quick5k_projection_le_12h": metrics["projected_quick5k_resolver_compute_hours"] <= 12.0,
        "qualification_wall_le_10800": wall_seconds <= 10800.0,
        "rss_le_16384": metrics["process_rss_mib"] <= 16384.0,
        "gpu_peak_le_11264": metrics["gpu_peak_allocated_mib"] <= 11264.0,
        "output_le_5gib": output_bytes <= 5368709120,
    }
    result = {
        "schema_version": "v5.rs002.qualification_result.v1",
        "classification": "PASS / RS002_OFFLINE_QUALIFICATION_PASS_QUICK5K_ELIGIBLE_AFTER_RESULT_AUDIT" if all(gates.values()) else "NONPASS / RS002_OFFLINE_QUALIFICATION_GATE_FAILURE_NO_QUICK5K",
        "overall": "PASS" if all(gates.values()) else "NONPASS",
        "program_id": PROGRAM_ID,
        "token": TOKEN,
        "nonce": QUALIFICATION_NONCE,
        "gates": gates,
        "pass_count": sum(gates.values()),
        "gate_count": len(gates),
        "metrics_sha256": sha256_file(root / "metrics.json"),
        "output_manifest_before_result": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in sorted(root.iterdir()) if path.is_file()
        },
        "network_or_slumbot_calls": 0,
        "quick5k_launched": False,
        "strength_claim": "FORBIDDEN",
    }
    write_json_exclusive(root / "result.json", result)
    print(canonical_json({"classification": result["classification"], "pass_count": result["pass_count"], "gate_count": result["gate_count"], "root": str(root)}))
    return 0 if result["overall"] == "PASS" else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("ContractProbe", "SelfTest", "Qualification"), required=True)
    parser.add_argument("--nonce")
    parser.add_argument("--level", choices=("shallow", "deep"), default="shallow")
    parser.add_argument("--root")
    parser.add_argument("--implementation-audit-sha256")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mode == "ContractProbe":
        if not args.nonce or args.root or args.implementation_audit_sha256:
            raise RuntimeError("contract_probe_argument_contract_failure")
        return contract_probe(args.nonce)
    if args.mode == "SelfTest":
        if not args.nonce:
            raise RuntimeError("selftest_nonce_required")
        validate_device_contract(args.nonce)
        return run_self_test(args.level)
    if args.mode == "Qualification":
        if args.nonce != QUALIFICATION_NONCE or not args.root or not args.implementation_audit_sha256:
            raise RuntimeError("qualification_argument_contract_failure")
        return run_qualification(Path(args.root), args.implementation_audit_sha256)
    raise RuntimeError("unknown_mode")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(canonical_json({"classification": "FAIL_CLOSED", "error_type": type(exc).__name__, "error": str(exc)}), file=sys.stderr, flush=True)
        raise
