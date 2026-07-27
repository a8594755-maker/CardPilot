"""Phase FA Q001 exact-CFR-mapper and MC32 quality qualification.

This is a trainerless, CPU-only diagnostic. It can never emit training-eligible
rows. Current CFR assets are accepted only when every exact V5.5 identity needed
by the mapper is present and replayable; bucket-only and legacy 54-dim rows are
therefore rejected with a stable reason instead of being projected.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import math
import os
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import psutil

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from alpha_holdem.environment_v55 import (  # noqa: E402
    RAISE_CAP_UNLIMITED,
    build_action_table,
    encode_action_history,
    encode_cards,
    encode_extra,
)
from deep_cfr.game_state import (  # noqa: E402
    Action,
    ActionType,
    GameConfig,
    HUNLGameState,
    Street,
)

DESIGN_ID = "PHASE_FA_Q001_EXACT_CFR_MAPPER_AND_MC32_QUALITY_QUALIFICATION"
DESIGN_SHA256 = "74b7aeda43d46c1ec84ea72f58f3795c32279b548fdc7674f8fa837e99669a82"
DESIGN_AUDIT_SHA256 = "ee245f813fc9fd4a301f6a9dfc92761b4e3db51becf7de5361cd59aa8fb0ba68"
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
CONTRACT_SHA256 = "5b7ed3ccd8acc12366f93537f4426eaacb273006b7b0bbaeeb907ece6be579e3"
CONTRACT_NONCE = "2029972201"
DEVICE_MODE = "CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK"

EXPECTED_DESIGN = Path(r"C:\Users\a8594\CardPilot\reports\v5_phase_fa_full_teacher_asset_design_preregistration_20260722.json")
EXPECTED_DESIGN_AUDIT = Path(r"C:\Users\a8594\CardPilot\reports\v5_phase_fa_full_teacher_asset_design_preregistration_audit_20260722.json")
EXPECTED_IMPLEMENTATION_AUDIT = Path(r"C:\Users\a8594\CardPilot\reports\v5_phase_fa_teacher_qualification_implementation_audit_20260722.json")
EXPECTED_OUTPUT = Path(r"C:\Users\a8594\CardPilot\reports\phase_fa_teacher_qualification_20260722")
PATH1_ROOT = Path(r"C:\Users\a8594\CardPilot\data\cfr\pipeline_v3_hu_srp_200bb_legalallin_v2")
PATH1_SELECTION = PATH1_ROOT / "path1-selection-manifest.json"
LEGACY_ROOTS = {
    "CFR_100BB_SRP_SAMPLED": Path(r"C:\Users\a8594\CardPilot\data\training\cfr_srp_100bb_sampled"),
    "CFR_100BB_3BET_SAMPLED": Path(r"C:\Users\a8594\CardPilot\data\training\cfr_3bet_100bb_sampled"),
    "CFR_50BB_SRP_SAMPLED": Path(r"C:\Users\a8594\CardPilot\data\training\v3_srp_50bb_sampled"),
    "CFR_50BB_3BET_SAMPLED": Path(r"C:\Users\a8594\CardPilot\data\training\cfr_3bet_50bb_sampled"),
}

MAPPER_COUNTS = {"200bb": 4096, "100bb": 4096, "50bb": 4096}
MAPPER_ACCEPTANCE = {"200bb": 0.20, "100bb": 0.10, "50bb": 0.10}
MC_STATES = 4096
STREET_QUOTA = 1024
CELL_QUOTA = 128
WORKERS = 8
DEAL_SEED = 2026072201
ROLLOUT_SEED = 2027972201
ROLLOUTS_PER_BATCH = 8
BATCHES = 4
TEMPERATURES = (1.0, 5.0, 10.0, 25.0, 100.0)
MAX_ROLLOUT_STEPS = 128
WALL_SECONDS_MAX = 900.0
RSS_MB_MAX = 2048.0
OUTPUT_BYTES_MAX = 2_000_000_000
LINE_BUCKETS = (
    "ALLIN_RESPONSE_ONLY",
    "SHORT_SPR_FACING",
    "SHORT_SPR_UNOPENED",
    "FACING_DEEP_RERAISE",
    "FACING_FIRST_RAISE",
    "FACING_FIRST_BET",
    "CHECKED_TO_NO_BET",
    "OPEN_ACTION_NO_BET",
)
STREET_NAMES = {int(x): x.name for x in (Street.PREFLOP, Street.FLOP, Street.TURN, Street.RIVER)}


def canonical_path(value: str | Path) -> Path:
    return Path(value).resolve(strict=False)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_obj(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with canonical_path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_device_contract() -> dict[str, Any]:
    observed = {
        "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "PHASE_FA_DEVICE_MODE": os.environ.get("PHASE_FA_DEVICE_MODE"),
        "PHASE_FA_CONTRACT_NONCE": os.environ.get("PHASE_FA_CONTRACT_NONCE"),
    }
    if observed != {
        "CUDA_VISIBLE_DEVICES": "-1",
        "PHASE_FA_DEVICE_MODE": DEVICE_MODE,
        "PHASE_FA_CONTRACT_NONCE": CONTRACT_NONCE,
    }:
        raise RuntimeError(f"device_contract_mismatch:{observed}")
    runtime = canonical_path(sys.executable)
    runtime_sha = sha256_file(runtime)
    if runtime_sha != PYTHON_SHA256:
        raise RuntimeError("runtime_python_sha_mismatch")
    if "torch" in sys.modules:
        raise RuntimeError("torch_in_sys_modules")
    return {
        **observed,
        "python_executable": str(runtime),
        "python_sha256": runtime_sha,
        "contract_sha256": CONTRACT_SHA256,
        "torch_in_sys_modules": False,
    }


def contract_probe() -> int:
    print(canonical_json({
        "schema_version": "v5.phase_fa.q001.contract_probe.v1",
        "design_id": DESIGN_ID,
        **validate_device_contract(),
        "runner_sha256": sha256_file(Path(__file__)),
        "files_written": 0,
    }))
    return 0


def action_payload(action: Action | None) -> dict[str, Any] | None:
    return None if action is None else {"type": action.type.name, "amount": float(action.amount)}


def config_payload(config: GameConfig) -> dict[str, Any]:
    return {
        "starting_pot": float(config.starting_pot),
        "effective_stack": float(config.effective_stack),
        "raise_cap_per_street": int(config.raise_cap_per_street),
        "raise_cap_preflop": int(config.raise_cap_preflop),
        "include_preflop": bool(config.include_preflop),
        "bet_sizes": {
            "preflop": [float(x) for x in config.bet_sizes.preflop],
            "flop": [float(x) for x in config.bet_sizes.flop],
            "turn": [float(x) for x in config.bet_sizes.turn],
            "river": [float(x) for x in config.bet_sizes.river],
        },
    }


def state_payload(state: HUNLGameState) -> dict[str, Any]:
    return {
        "config": config_payload(state.config),
        "deck": [int(x) for x in state.deck],
        "hole_cards": [None if x is None else [int(x[0]), int(x[1])] for x in state.hole_cards],
        "board": [int(x) for x in state.board],
        "pot": float(state.pot),
        "stacks": [float(x) for x in state.stacks],
        "street": int(state.street),
        "street_committed": [float(x) for x in state.street_committed],
        "current_player": int(state.current_player),
        "actions_history": [[int(p), action_payload(a)] for p, a in state.actions_history],
        "raise_count": int(state.raise_count),
        "last_bet_size": float(state.last_bet_size),
        "is_done": bool(state.is_done),
        "folded_player": int(state.folded_player),
        "num_actions_this_street": int(state.num_actions_this_street),
    }


def array_identity(array: np.ndarray) -> dict[str, Any]:
    arr = np.ascontiguousarray(array)
    value = {"shape": list(arr.shape), "dtype": str(arr.dtype), "bytes_sha256": hashlib.sha256(arr.tobytes()).hexdigest()}
    value["identity_sha256"] = sha256_obj(value)
    return value


def observe(state: HUNLGameState) -> tuple[dict[str, Any], np.ndarray, list[Action | None]]:
    player = state.current_player
    mask, table = build_action_table(state)
    identity = {
        "card_info": array_identity(encode_cards(state, player)),
        "action_info": array_identity(encode_action_history(state, player)),
        "extra_info": array_identity(encode_extra(state, player)),
        "legal_mask": array_identity(mask),
        "player": int(player),
    }
    identity["observation_sha256"] = sha256_obj(identity)
    return identity, mask, table


def exact_slots(mask: np.ndarray, table: list[Action | None]) -> list[int]:
    if len(mask) != 9 or len(table) != 9:
        raise RuntimeError("nine_slot_shape_failure")
    slots = [i for i in range(9) if float(mask[i]) == 1.0 and table[i] is not None]
    if not slots or any(float(mask[i]) != 0.0 and table[i] is None for i in range(9)):
        raise RuntimeError("mask_table_identity_failure")
    if len({(table[i].type, round(float(table[i].amount), 2)) for i in slots if table[i] is not None}) != len(slots):
        raise RuntimeError("executable_slot_collision")
    return slots


def new_deal(deal_id: int, depth: int = 200) -> HUNLGameState:
    random.seed(DEAL_SEED + deal_id)
    maker = {200: GameConfig.full_200bb, 100: GameConfig.full_100bb, 50: GameConfig.full_50bb}[depth]
    config = maker()
    config.raise_cap_per_street = RAISE_CAP_UNLIMITED
    return HUNLGameState(config).deal_new_hand()


def line_bucket(state: HUNLGameState, slots: list[int]) -> str | None:
    to_call = max(0.0, state.street_committed[1 - state.current_player] - state.street_committed[state.current_player])
    spr = min(state.stacks) / max(state.pot, 1e-12)
    if to_call > 0 and set(slots).issubset({0, 1}):
        return "ALLIN_RESPONSE_ONLY"
    if to_call > 0 and spr <= 1.0:
        return "SHORT_SPR_FACING"
    if to_call == 0 and spr <= 1.0:
        return "SHORT_SPR_UNOPENED"
    if to_call > 0 and state.raise_count >= 3:
        return "FACING_DEEP_RERAISE"
    if to_call > 0 and state.raise_count == 2:
        return "FACING_FIRST_RAISE"
    if to_call > 0 and state.raise_count == 1:
        return "FACING_FIRST_BET"
    if to_call == 0 and state.num_actions_this_street >= 1:
        return "CHECKED_TO_NO_BET"
    if to_call == 0 and state.num_actions_this_street == 0:
        return "OPEN_ACTION_NO_BET"
    return None


def exact_mapper(candidate: dict[str, Any]) -> dict[str, Any]:
    """Map only a fully reconstructed exact state/action policy; never project."""
    base = {
        "candidate_id": candidate["candidate_id"],
        "depth": candidate["depth"],
        "source_id": candidate["source_id"],
        "source_identity": candidate["source_identity"],
        "training_eligibility": "FORBIDDEN_DIAGNOSTIC_ONLY",
    }
    if candidate.get("schema") == "LEGACY_54DIM_F_H_L_S_SZ_NOT_EXACT_V55":
        return {**base, "accepted": False, "rejection_reason": "LEGACY_54DIM_LACKS_EXACT_CARDS_STATE_ACTION_HISTORY_AND_9SLOT_IDENTITY"}
    if not all(k in candidate for k in ("exact_state", "source_actions", "source_probabilities")):
        return {**base, "accepted": False, "rejection_reason": "BUCKET_POLICY_LACKS_FROZEN_EXACT_STATE_AND_CARD_CONCRETIZATION_IDENTITY"}
    state = candidate["exact_state"]
    if not isinstance(state, HUNLGameState):
        return {**base, "accepted": False, "rejection_reason": "EXACT_STATE_OWNER_TYPE_MISMATCH"}
    obs, mask, table = observe(state)
    slots = exact_slots(mask, table)
    source_actions = candidate["source_actions"]
    probs = [float(x) for x in candidate["source_probabilities"]]
    if len(source_actions) != len(probs) or not probs or any(not math.isfinite(x) or x < 0 for x in probs):
        return {**base, "accepted": False, "rejection_reason": "SOURCE_PROBABILITY_SCHEMA_FAILURE"}
    if abs(sum(probs) - 1.0) > 1e-6:
        return {**base, "accepted": False, "rejection_reason": "SOURCE_PROBABILITY_RENORMALIZATION_FORBIDDEN"}
    slot_by_identity = {(table[i].type.name, round(float(table[i].amount), 2)): i for i in slots if table[i] is not None}
    mapped: list[int] = []
    for source_action in source_actions:
        identity = (str(source_action["type"]), round(float(source_action.get("amount", 0.0)), 2))
        if identity not in slot_by_identity:
            return {**base, "accepted": False, "rejection_reason": "SOURCE_ACTION_PROJECTION_OR_DROP_REQUIRED"}
        mapped.append(slot_by_identity[identity])
    if len(set(mapped)) != len(mapped):
        return {**base, "accepted": False, "rejection_reason": "SOURCE_ACTION_COLLISION"}
    target = [0.0] * 9
    for slot, probability in zip(mapped, probs, strict=True):
        target[slot] = probability
    illegal_mass = sum(target[i] for i in range(9) if i not in slots)
    if illegal_mass != 0.0:
        return {**base, "accepted": False, "rejection_reason": "ILLEGAL_POSITIVE_PROBABILITY_MASS"}
    transitions = []
    for slot in mapped:
        action = table[slot]
        assert action is not None
        transitions.append({"slot": slot, "next_state_sha256": sha256_obj(state_payload(state.apply(action)))})
    return {
        **base,
        "accepted": True,
        "rejection_reason": None,
        "state_payload_sha256": sha256_obj(state_payload(state)),
        "observation_identity_sha256": obs["observation_sha256"],
        "legal_mask9": [float(x) for x in mask],
        "source_action_to_slot": mapped,
        "teacher_probs9": target,
        "teacher_probability_sha256": sha256_obj(target),
        "next_state_sha256_by_source_action": transitions,
        "projection_drop_collision_or_renormalization": False,
    }


def iter_jsonl(path: Path) -> Iterable[tuple[int, str, dict[str, Any]]]:
    opener = gzip.open if path.suffix == ".gz" else Path.open
    kwargs = {"mode": "rt", "encoding": "utf-8", "newline": ""}
    with opener(path, **kwargs) as fh:  # type: ignore[arg-type]
        for ordinal, line in enumerate(fh):
            if line.strip():
                yield ordinal, line, json.loads(line)


def collect_path1_candidates() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = json.loads(PATH1_SELECTION.read_text(encoding="utf-8"))
    board_ids = [int(x) for x in manifest["selectedBoardIds"] if int(x) != 1747]
    chosen = board_ids[:8]
    candidates: list[dict[str, Any]] = []
    hashed: list[dict[str, Any]] = []
    per_board = MAPPER_COUNTS["200bb"] // len(chosen)
    for board_id in chosen:
        stem = f"flop_{board_id:03d}"
        gz_path = PATH1_ROOT / f"{stem}.jsonl.gz"
        meta_path = PATH1_ROOT / f"{stem}.meta.json"
        if not gz_path.exists() or not meta_path.exists():
            raise RuntimeError(f"path1_selected_pair_missing:{board_id}")
        for path in (gz_path, meta_path):
            hashed.append({"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size})
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if int(meta.get("boardId", -1)) != board_id or meta.get("config") != "pipeline_srp_v3_200bb":
            raise RuntimeError(f"path1_metadata_identity_failure:{board_id}")
        taken = 0
        for ordinal, line, row in iter_jsonl(gz_path):
            if taken >= per_board:
                break
            candidates.append({
                "candidate_id": f"200bb:{board_id}:{ordinal}",
                "depth": "200bb",
                "source_id": "CFR_200BB_SRP_PATH1_LEGALALLIN_V2",
                "source_identity": {"path": str(gz_path), "file_sha256": hashed[-2]["sha256"], "row_ordinal": ordinal, "row_sha256": hashlib.sha256(line.encode("utf-8")).hexdigest()},
                "schema": "BUCKETED_POLICY_ONLY",
                "raw_key": row.get("key"),
            })
            taken += 1
        if taken != per_board:
            raise RuntimeError(f"path1_candidate_shortfall:{board_id}:{taken}")
    return candidates, hashed


def collect_legacy_candidates(source_id: str, depth: str, count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    files = sorted(LEGACY_ROOTS[source_id].glob("*.jsonl"))
    if not files:
        raise RuntimeError(f"legacy_source_files_absent:{source_id}")
    path = files[0]
    file_sha = sha256_file(path)
    hashed = [{"path": str(path), "sha256": file_sha, "bytes": path.stat().st_size}]
    candidates = []
    for ordinal, line, row in iter_jsonl(path):
        if len(candidates) >= count:
            break
        if set(row) != {"f", "h", "l", "s", "sz"}:
            raise RuntimeError(f"legacy_schema_changed:{source_id}:{ordinal}")
        candidates.append({
            "candidate_id": f"{depth}:{source_id}:{ordinal}",
            "depth": depth,
            "source_id": source_id,
            "source_identity": {"path": str(path), "file_sha256": file_sha, "row_ordinal": ordinal, "row_sha256": hashlib.sha256(line.encode("utf-8")).hexdigest(), "legacy_hand_id": row["h"]},
            "schema": "LEGACY_54DIM_F_H_L_S_SZ_NOT_EXACT_V55",
        })
    if len(candidates) != count:
        raise RuntimeError(f"legacy_candidate_shortfall:{source_id}:{len(candidates)}")
    return candidates, hashed


def collect_mapper_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates, source_hashes = collect_path1_candidates()
    for depth, source_ids in (("100bb", ("CFR_100BB_SRP_SAMPLED", "CFR_100BB_3BET_SAMPLED")), ("50bb", ("CFR_50BB_SRP_SAMPLED", "CFR_50BB_3BET_SAMPLED"))):
        for source_id in source_ids:
            rows, hashes = collect_legacy_candidates(source_id, depth, 2048)
            candidates.extend(rows)
            source_hashes.extend(hashes)
    if Counter(x["depth"] for x in candidates) != Counter(MAPPER_COUNTS):
        raise RuntimeError("mapper_candidate_depth_count_failure")
    return [exact_mapper(x) for x in candidates], source_hashes


def choose_trajectory_slot(state: HUNLGameState, slots: list[int], mode: int, step: int) -> int:
    sized = [x for x in slots if 2 <= x <= 7]
    if mode == 0 and 8 in slots:
        return 8
    if mode in (1, 2, 3) and sized:
        return sized[(step + mode) % len(sized)]
    if mode == 4 and 1 in slots:
        return 1
    if mode == 5 and sized:
        return sized[-1]
    if mode == 6 and sized:
        return sized[0]
    return slots[(step + mode) % len(slots)]


def collect_balanced_states(limit_per_cell: int = CELL_QUOTA) -> tuple[list[tuple[int, HUNLGameState, str]], dict[str, int], int]:
    quotas = {(street, bucket): limit_per_cell for street in STREET_NAMES.values() for bucket in LINE_BUCKETS}
    rows: list[tuple[int, HUNLGameState, str]] = []
    deal_id = 0
    max_deals = max(2048, limit_per_cell * 8 * 256)
    while any(value > 0 for value in quotas.values()) and deal_id < max_deals:
        depth = (200, 100, 50)[deal_id % 3]
        state = new_deal(deal_id, depth)
        mode = deal_id % 8
        step = 0
        while not state.is_terminal() and step <= MAX_ROLLOUT_STEPS:
            _, mask, table = observe(state)
            slots = exact_slots(mask, table)
            street = STREET_NAMES[int(state.street)]
            bucket = line_bucket(state, slots)
            key = (street, bucket) if bucket is not None else None
            if key is not None and quotas[key] > 0:
                rows.append((deal_id, state.clone(), bucket))
                quotas[key] -= 1
            slot = choose_trajectory_slot(state, slots, mode, step)
            action = table[slot]
            assert action is not None
            state = state.apply(action)
            step += 1
        deal_id += 1
    missing = {f"{k[0]}:{k[1]}": v for k, v in quotas.items() if v}
    expected = limit_per_cell * 4 * 8
    if not missing and len(rows) != expected:
        raise RuntimeError(f"balanced_state_count_failure:{len(rows)}:{expected}")
    return rows, missing, deal_id


def rollout(state: HUNLGameState, hero: int, seed: int) -> tuple[float, int]:
    rng = random.Random(seed)
    steps = 0
    while not state.is_terminal():
        mask, table = build_action_table(state)
        slots = exact_slots(mask, table)
        slot = slots[rng.randrange(len(slots))]
        action = table[slot]
        assert action is not None
        state = state.apply(action)
        steps += 1
        if steps > MAX_ROLLOUT_STEPS:
            raise RuntimeError("rollout_step_ceiling")
    return float(state.payoff(hero)), steps


def softmax(values: list[float], slots: list[int], temperature: float) -> list[float]:
    scaled = np.array([values[x] / temperature for x in slots], dtype=np.float64)
    scaled -= float(np.max(scaled))
    weights = np.exp(scaled)
    weights /= float(weights.sum())
    output = [0.0] * 9
    for slot, probability in zip(slots, weights.tolist(), strict=True):
        output[slot] = float(probability)
    return output


def mc32_row(row_id: int, deal_id: int, state: HUNLGameState, bucket: str) -> dict[str, Any]:
    started = time.perf_counter()
    obs, mask, table = observe(state)
    slots = exact_slots(mask, table)
    batch_values: list[list[float]] = []
    max_steps = 0
    for batch in range(BATCHES):
        values = [0.0] * 9
        for slot in slots:
            action = table[slot]
            assert action is not None
            samples = []
            for rep in range(ROLLOUTS_PER_BATCH):
                seed = ROLLOUT_SEED + row_id * 1_000_000 + batch * 100_000 + slot * 1_000 + rep
                payoff, steps = rollout(state.apply(action), state.current_player, seed)
                samples.append(payoff)
                max_steps = max(max_steps, steps)
            values[slot] = float(statistics.fmean(samples))
        batch_values.append(values)
    temperature_metrics = {}
    selected_payloads = {}
    for temperature in TEMPERATURES:
        distributions = [softmax(values, slots, temperature) for values in batch_values]
        l1s = [sum(abs(a - b) for a, b in zip(distributions[i], distributions[j], strict=True)) for i in range(4) for j in range(i + 1, 4)]
        tops = [max(slots, key=lambda slot: (distribution[slot], -slot)) for distribution in distributions]
        top_fraction = Counter(tops).most_common(1)[0][1] / 4.0
        mean_values = [statistics.fmean(values[i] for values in batch_values) for i in range(9)]
        teacher = softmax(mean_values, slots, temperature)
        entropy = -sum(x * math.log(x) for x in teacher if x > 0) / math.log(len(slots)) if len(slots) > 1 else 0.0
        key = str(temperature)
        temperature_metrics[key] = {"batch_l1_mean": statistics.fmean(l1s), "batch_l1_max": max(l1s), "top_action_agreement_fraction": top_fraction, "normalized_entropy": entropy}
        selected_payloads[key] = teacher
    ordered_actions = [{"slot": slot, "action": action_payload(table[slot])} for slot in slots]
    transitions = []
    for slot in slots:
        action = table[slot]
        assert action is not None
        transitions.append({"slot": slot, "next_state_sha256": sha256_obj(state_payload(state.apply(action)))})
    return {
        "schema_version": "v5.phase_fa.q001.mc32_row.v1",
        "classification": "FORBIDDEN_DIAGNOSTIC_ONLY",
        "row_id": row_id,
        "deal_id": deal_id,
        "depth_bb": int(state.config.effective_stack),
        "street": STREET_NAMES[int(state.street)],
        "state_line_bucket": bucket,
        "player": int(state.current_player),
        "state_payload_sha256": sha256_obj(state_payload(state)),
        "observation_identity_sha256": obs["observation_sha256"],
        "legal_mask9": [float(x) for x in mask],
        "ordered_nonnull_slot_actions": ordered_actions,
        "next_state_sha256_by_legal_slot": transitions,
        "batch_values": batch_values,
        "temperature_metrics": temperature_metrics,
        "teacher_probs9_by_temperature": selected_payloads,
        "same_seed_identity_sha256": sha256_obj({"batch_values": batch_values, "temperature_metrics": temperature_metrics, "teacher": selected_payloads}),
        "illegal_positive_probability_mass": 0.0,
        "rollouts_per_action_total": BATCHES * ROLLOUTS_PER_BATCH,
        "max_rollout_steps": max_steps,
        "row_wall_seconds": time.perf_counter() - started,
    }


def mc32_task(item: tuple[int, tuple[int, HUNLGameState, str]]) -> dict[str, Any]:
    row_id, (deal_id, state, bucket) = item
    validate_device_contract()
    return mc32_row(row_id, deal_id, state, bucket)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1, math.floor((len(ordered) - 1) * q))])


def aggregate_temperature(rows: list[dict[str, Any]]) -> tuple[float | None, dict[str, Any]]:
    summary = {}
    selected = None
    for temperature in TEMPERATURES:
        key = str(temperature)
        l1 = [float(row["temperature_metrics"][key]["batch_l1_mean"]) for row in rows]
        top = [float(row["temperature_metrics"][key]["top_action_agreement_fraction"]) for row in rows]
        entropy = [float(row["temperature_metrics"][key]["normalized_entropy"]) for row in rows]
        metrics = {
            "batch_distribution_l1_mean": statistics.fmean(l1),
            "batch_distribution_l1_p95": percentile(l1, 0.95),
            "states_top_action_agreement_ge_0_75_fraction": sum(x >= 0.75 for x in top) / len(top),
            "mean_normalized_entropy": statistics.fmean(entropy),
        }
        metrics["passes"] = (
            metrics["batch_distribution_l1_mean"] <= 0.20
            and metrics["batch_distribution_l1_p95"] <= 0.50
            and metrics["states_top_action_agreement_ge_0_75_fraction"] >= 0.70
            and metrics["mean_normalized_entropy"] <= 0.85
        )
        summary[key] = metrics
        if selected is None and metrics["passes"]:
            selected = temperature
    return selected, summary


def write_json_exclusive(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as fh:
        json.dump(value, fh, indent=2, ensure_ascii=False, allow_nan=False)
        fh.write("\n")


def write_jsonl_exclusive(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(canonical_json(row) + "\n")


def verify_design_inputs(design: dict[str, Any]) -> list[dict[str, str]]:
    items = list(design["frozen_semantic_owners"]) + list(design["prior_asset_evidence"])
    verified = []
    for item in items:
        path = canonical_path(item["path"])
        observed = sha256_file(path)
        if observed != item["sha256"]:
            raise RuntimeError(f"design_input_hash_mismatch:{path}")
        verified.append({"path": str(path), "sha256": observed})
    if sha256_file(PATH1_SELECTION) != "fe35f02a09b8e9a8c0368c010e3b3366ec2b06c502f4aa5f88cd355a7af69515":
        raise RuntimeError("path1_selection_hash_mismatch")
    return verified


def self_test() -> int:
    validate_device_contract()
    state = new_deal(0)
    _, mask, table = observe(state)
    slots = exact_slots(mask, table)
    actions = [action_payload(table[x]) for x in slots]
    assert all(action is not None for action in actions)
    probs = [1.0 / len(actions)] * len(actions)
    accepted = exact_mapper({"candidate_id": "fixture-pass", "depth": "200bb", "source_id": "SELF_TEST", "source_identity": {}, "exact_state": state, "source_actions": actions, "source_probabilities": probs})
    assert accepted["accepted"] is True and sum(accepted["teacher_probs9"]) == 1.0
    rejected = exact_mapper({"candidate_id": "fixture-reject", "depth": "200bb", "source_id": "SELF_TEST", "source_identity": {}, "schema": "LEGACY_54DIM_F_H_L_S_SZ_NOT_EXACT_V55"})
    assert rejected["accepted"] is False
    mini, missing, attempts = collect_balanced_states(1)
    assert mini and missing and attempts == 2048
    assert all(b in LINE_BUCKETS and STREET_NAMES[int(s.street)] in STREET_NAMES.values() for _, s, b in mini)
    probe = mc32_row(0, mini[0][0], mini[0][1], mini[0][2])
    assert probe["rollouts_per_action_total"] == 32 and len(probe["legal_mask9"]) == 9
    print("PHASE_FA_Q001_SELF_TEST_PASS")
    return 0


def run(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    contract = validate_device_contract()
    raw_paths = {"design": args.design, "design_audit": args.design_audit, "implementation_audit": args.implementation_audit, "output": args.output}
    paths = {key: canonical_path(value) for key, value in raw_paths.items()}
    expected = {"design": canonical_path(EXPECTED_DESIGN), "design_audit": canonical_path(EXPECTED_DESIGN_AUDIT), "implementation_audit": canonical_path(EXPECTED_IMPLEMENTATION_AUDIT), "output": canonical_path(EXPECTED_OUTPUT)}
    if paths != expected or not all(Path(value).is_absolute() for value in raw_paths.values()):
        raise RuntimeError("registered_absolute_path_identity_mismatch")
    if paths["output"].exists():
        raise RuntimeError("immutable_output_root_exists")
    if sha256_file(paths["design"]) != DESIGN_SHA256 or sha256_file(paths["design_audit"]) != DESIGN_AUDIT_SHA256:
        raise RuntimeError("design_identity_hash_mismatch")
    if sha256_file(paths["implementation_audit"]) != args.implementation_audit_sha256:
        raise RuntimeError("implementation_audit_hash_mismatch")
    implementation = json.loads(paths["implementation_audit"].read_text(encoding="utf-8"))
    if implementation.get("overall") != "PASS" or implementation.get("authorization") != "EXACTLY_ONE_Q001_QUALIFICATION_LAUNCH_THROUGH_EXACT_LAUNCHER_ON_LATER_AUTHORIZED_TRANSITION":
        raise RuntimeError("implementation_audit_authority_mismatch")
    design = json.loads(paths["design"].read_text(encoding="utf-8"))
    design_audit = json.loads(paths["design_audit"].read_text(encoding="utf-8"))
    if design.get("design_id") != "PHASE_FA_FULL_EXACT_V55_TEACHER_ASSET_20M_DESIGN_V1" or design_audit.get("overall") != "PASS" or design_audit.get("checks_total") != 197:
        raise RuntimeError("design_audit_classification_mismatch")
    verified_inputs = verify_design_inputs(design)

    paths["output"].mkdir(parents=False, exist_ok=False)
    mapper_rows, source_hashes = collect_mapper_rows()
    peak_rss = max(peak_rss, process.memory_info().rss)
    states, quota_shortfall, state_sampling_deals = collect_balanced_states()
    peak_rss = max(peak_rss, process.memory_info().rss)
    with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="phase-fa-q001") as pool:
        mc_rows = list(pool.map(mc32_task, enumerate(states)))
    peak_rss = max(peak_rss, process.memory_info().rss)
    selected_temperature, temperature_summary = aggregate_temperature(mc_rows)
    repeat_failures = 0
    for index in sorted(range(len(mc_rows)), key=lambda i: sha256_obj(mc_rows[i]["state_payload_sha256"]))[:64]:
        deal_id, state, bucket = states[index]
        repeated = mc32_row(index, deal_id, state, bucket)
        if repeated["same_seed_identity_sha256"] != mc_rows[index]["same_seed_identity_sha256"]:
            repeat_failures += 1

    mapper_counts = Counter(row["depth"] for row in mapper_rows)
    mapper_accepts = Counter(row["depth"] for row in mapper_rows if row["accepted"])
    acceptance = {depth: mapper_accepts[depth] / mapper_counts[depth] for depth in MAPPER_COUNTS}
    rejection_reasons = Counter(row.get("rejection_reason") for row in mapper_rows if not row["accepted"])
    cell_counts = Counter((row["street"], row["state_line_bucket"]) for row in mc_rows)
    street_counts = Counter(row["street"] for row in mc_rows)
    wall = time.perf_counter() - started
    peak_rss = max(peak_rss, process.memory_info().rss)
    rss_mb = peak_rss / 1_048_576

    mapper_path = paths["output"] / "mapper_candidates.jsonl"
    mc_path = paths["output"] / "mc32_rows.jsonl"
    metrics_path = paths["output"] / "raw_metrics.json"
    result_path = paths["output"] / "result.json"
    write_jsonl_exclusive(mapper_path, mapper_rows)
    write_jsonl_exclusive(mc_path, mc_rows)
    metrics = {
        "schema_version": "v5.phase_fa.q001.raw_metrics.v1",
        "mapper_acceptance": acceptance,
        "mapper_rejection_reasons": dict(rejection_reasons),
        "temperature_summary": temperature_summary,
        "selected_temperature": selected_temperature,
        "same_seed_repeat_failures": repeat_failures,
        "mc32_quota_shortfall": quota_shortfall,
        "state_sampling_deals": state_sampling_deals,
        "row_wall_seconds": [row["row_wall_seconds"] for row in mc_rows],
        "source_hashes_before_first_read": source_hashes,
    }
    write_json_exclusive(metrics_path, metrics)
    pre_result_bytes = sum(path.stat().st_size for path in (mapper_path, mc_path, metrics_path))
    gates = {
        "design_and_audit_exact": True,
        "implementation_audit_exact": True,
        "device_contract_exact": True,
        "frozen_semantic_inputs_exact": True,
        "mapper_candidates_exact_4096_each_depth": mapper_counts == Counter(MAPPER_COUNTS),
        "mapper_200bb_acceptance_ge_0_20": acceptance["200bb"] >= MAPPER_ACCEPTANCE["200bb"],
        "mapper_100bb_acceptance_ge_0_10": acceptance["100bb"] >= MAPPER_ACCEPTANCE["100bb"],
        "mapper_50bb_acceptance_ge_0_10": acceptance["50bb"] >= MAPPER_ACCEPTANCE["50bb"],
        "accepted_mapping_identity_failures_zero": all(row.get("state_payload_sha256") and row.get("observation_identity_sha256") for row in mapper_rows if row["accepted"]),
        "accepted_mapping_projection_drop_collision_renormalization_zero": all(row.get("projection_drop_collision_or_renormalization") is False for row in mapper_rows if row["accepted"]),
        "mc32_states_4096": len(mc_rows) == MC_STATES and not quota_shortfall,
        "mc32_street_balance_1024_each": street_counts == Counter({street: STREET_QUOTA for street in STREET_NAMES.values()}),
        "mc32_cell_balance_128_each": not quota_shortfall and cell_counts == Counter({(street, bucket): CELL_QUOTA for street in STREET_NAMES.values() for bucket in LINE_BUCKETS}),
        "rollouts_exact_4_batches_x8": all(row["rollouts_per_action_total"] == 32 and len(row["batch_values"]) == 4 for row in mc_rows),
        "temperature_selected_lowest_passing": selected_temperature is not None and all(not temperature_summary[str(t)]["passes"] for t in TEMPERATURES if t < selected_temperature),
        "same_seed_repeat_failures_zero": repeat_failures == 0,
        "illegal_positive_probability_mass_zero": all(row["illegal_positive_probability_mass"] == 0.0 for row in mc_rows),
        "wall_seconds_le_900": wall <= WALL_SECONDS_MAX,
        "aggregate_peak_rss_mb_le_2048": rss_mb <= RSS_MB_MAX,
        "output_bytes_le_2gb": pre_result_bytes <= OUTPUT_BYTES_MAX,
        "workers_exact_8": WORKERS == 8,
        "gpu_false": contract["CUDA_VISIBLE_DEVICES"] == "-1" and "torch" not in sys.modules,
        "diagnostic_training_eligibility_forbidden": all(row["training_eligibility"] == "FORBIDDEN_DIAGNOSTIC_ONLY" for row in mapper_rows) and all(row["classification"] == "FORBIDDEN_DIAGNOSTIC_ONLY" for row in mc_rows),
    }
    passed = all(gates.values())
    classification = "PHASE_FA_Q001_PASS_EXACT_CFR_MAPPER_AND_MC32_QUALITY_QUALIFIED" if passed else "PHASE_FA_Q001_NONPASS_FAIL_CLOSED_EXACT_MAPPER_OR_MC32_QUALITY_GATE"
    result = {
        "schema_version": "v5.phase_fa.q001.result.v1",
        "design_id": DESIGN_ID,
        "verdict": "PASS" if passed else "NONPASS_FAIL_CLOSED",
        "classification": classification,
        "design_sha256": DESIGN_SHA256,
        "design_audit_sha256": DESIGN_AUDIT_SHA256,
        "implementation_audit_sha256": args.implementation_audit_sha256,
        "runner_sha256": sha256_file(Path(__file__)),
        "device_contract": contract,
        "verified_design_inputs": verified_inputs,
        "scope": {"mapper_candidates": MAPPER_COUNTS, "mc32_states": MC_STATES, "workers": WORKERS, "gpu": False, "training_eligibility": "FORBIDDEN_DIAGNOSTIC_ONLY"},
        "measurements": {"mapper_acceptance": acceptance, "selected_temperature": selected_temperature, "temperature_summary": temperature_summary, "same_seed_repeat_failures": repeat_failures, "mc32_quota_shortfall": quota_shortfall, "state_sampling_deals": state_sampling_deals, "wall_seconds": wall, "peak_rss_mb": rss_mb, "bundle_bytes_before_result_and_audit": pre_result_bytes},
        "files": {
            "mapper_candidates": {"path": str(mapper_path), "sha256": sha256_file(mapper_path), "rows": len(mapper_rows)},
            "mc32_rows": {"path": str(mc_path), "sha256": sha256_file(mc_path), "rows": len(mc_rows)},
            "raw_metrics": {"path": str(metrics_path), "sha256": sha256_file(metrics_path)},
        },
        "gates": gates,
        "authority": {
            "training_eligibility": "FORBIDDEN",
            "full_asset_generation": "NONE",
            "behavior_launch": "NONE",
            "official_hands": 0,
            "pass_next": "SEPARATELY_REGISTERED_PHASE_FA_GENERATION_WINDOW_000_NO_AUTOMATIC_LAUNCH",
            "nonpass_next": "SEPARATELY_REGISTERED_PHASE_FA_DESIGN_REVIEW_002_OR_ROUTE_REVIEW031_AS_EXACTLY_JUDGED",
        },
        "path1_action": False,
        "strength_claim": "FORBIDDEN_L0",
    }
    write_json_exclusive(result_path, result)
    print(canonical_json({"verdict": result["verdict"], "classification": classification, "result": str(result_path)}))
    return 0 if passed else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design")
    parser.add_argument("--design-audit")
    parser.add_argument("--implementation-audit")
    parser.add_argument("--implementation-audit-sha256")
    parser.add_argument("--output")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract-probe", action="store_true")
    args = parser.parse_args()
    if args.self_test and args.contract_probe:
        parser.error("self-test and contract-probe are mutually exclusive")
    if not args.self_test and not args.contract_probe and not all((args.design, args.design_audit, args.implementation_audit, args.implementation_audit_sha256, args.output)):
        parser.error("qualification requires all immutable identity arguments")
    return args


def main() -> int:
    args = parse_args()
    if args.contract_probe:
        return contract_probe()
    if args.self_test:
        return self_test()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
