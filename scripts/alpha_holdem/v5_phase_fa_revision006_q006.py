"""Revision006 Q006 legal-trajectory support and infoset-MC32 qualification.

This runner is deliberately trainerless and CPU-only.  It discovers support by
playing complete legal HUNL trajectories; it never searches for a requested
Cartesian cell.  Teacher labels are conditioned only on the acting player's
information set: opponent cards and the unrevealed deck are freshly sampled for
every Monte-Carlo rollout and the public action history is replayed exactly.

Qualification output is diagnostic and can never be consumed as training data.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import time
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
from deep_cfr.game_state import Action, ActionType, GameConfig, HUNLGameState, Street  # noqa: E402


DESIGN_ID = "PHASE_FA_TRAJECTORY_NATIVE_REACHABLE_INFOSET_MC32_TEACHER_ASSET_20M_DESIGN_REVISION006_V1"
QUALIFICATION_ID = "PHASE_FA_REVISION006_Q006_TRAJECTORY_SUPPORT_MC32_QUALITY_AND_RESOURCE_QUALIFICATION"
DESIGN_SHA256 = "c7f3645b7c1f763bd37ab99149c72f2b697868199735e80ebc36be4df16efd42"
DESIGN_AUDIT_SHA256 = "976c2721545f8aef7cc69167c9328531f55edc566f134fe31c741112b5d891b0"
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
DEVICE_MODE = "CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK"
CONTRACT_NONCE = "2031972206"

EXPECTED_DESIGN = Path(r"C:\Users\a8594\CardPilot\reports\v5_phase_fa_design_revision006_preregistration_20260722.json")
EXPECTED_DESIGN_AUDIT = Path(r"C:\Users\a8594\CardPilot\reports\v5_phase_fa_design_revision006_preregistration_audit_20260722.json")
EXPECTED_IMPLEMENTATION_AUDIT = Path(r"C:\Users\a8594\CardPilot\reports\v5_phase_fa_revision006_q006_implementation_audit_20260722.json")
EXPECTED_OUTPUT = Path(r"C:\Users\a8594\CardPilot\reports\v5_phase_fa_revision006_q006_20260722")

DEPTHS = (200, 100, 50)
STREETS = ("PREFLOP", "FLOP", "TURN", "RIVER")
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
COMPONENTS = ("UNIFORM_LEGAL", "PASSIVE_COVERAGE", "AGGRESSIVE_COVERAGE", "AMOUNT_DIVERSITY")
TEMPERATURES = (1.0, 5.0, 10.0, 25.0, 100.0)
STREET_NAMES = {int(x): x.name for x in (Street.PREFLOP, Street.FLOP, Street.TURN, Street.RIVER)}

PILOT_TOTAL = 300_000
PILOT_PER_DEPTH = 100_000
MAX_HANDS_PER_DEPTH = 200_000
MAX_STEPS = 128
QUALITY_PER_BASE = 256
REPEATS_PER_BASE = 32
QUALITY_TOTAL = 6_144
REPEAT_TOTAL = 768
MIN_LINE_INFOSETS = 256
MIN_LINE_PUBLIC_REPLAYS = 64
WORKERS = 8
BATCHES = 4
ROLLOUTS_PER_BATCH = 8
WALL_SECONDS_MAX = 43_200.0
RSS_MB_MAX = 4_096.0
OUTPUT_BYTES_MAX = 10_000_000_000
PROJECTED_WALL_SECONDS_MAX = 604_800.0
UNCOMPRESSED_ROW_P99_MAX = 8_192
GZIP_ROW_P99_MAX = 5_000

COMPONENT_SEED = 2026072206
DEAL_SEED = 2026972206
ACTION_SEED = 2027972206
SUPPORT_ORDER_SEED = 2028972206
ROLLOUT_SEED = 2029972206
DETERMINIZATION_SEED = 2030972206


def canonical_path(value: str | Path) -> Path:
    return Path(value).resolve(strict=False)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_obj(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with canonical_path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values: Iterable[float], q: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile_requires_values")
    return ordered[min(len(ordered) - 1, math.floor((len(ordered) - 1) * q))]


def contract_payload() -> dict[str, Any]:
    return {
        "CUDA_VISIBLE_DEVICES": "-1",
        "REV006_DEVICE_MODE": DEVICE_MODE,
        "REV006_CONTRACT_NONCE": CONTRACT_NONCE,
        "python_sha256": PYTHON_SHA256,
        "design_sha256": DESIGN_SHA256,
        "design_audit_sha256": DESIGN_AUDIT_SHA256,
    }


def validate_device_contract() -> dict[str, Any]:
    observed = {
        "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "REV006_DEVICE_MODE": os.environ.get("REV006_DEVICE_MODE"),
        "REV006_CONTRACT_NONCE": os.environ.get("REV006_CONTRACT_NONCE"),
    }
    expected = {key: contract_payload()[key] for key in observed}
    if observed != expected:
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
        "contract_sha256": sha256_obj(contract_payload()),
        "torch_in_sys_modules": False,
    }


def contract_probe() -> int:
    print(canonical_json({
        "schema_version": "v5.phase_fa.revision006.q006.contract_probe.v1",
        "qualification_id": QUALIFICATION_ID,
        **validate_device_contract(),
        "runner_sha256": sha256_file(Path(__file__)),
        "files_written": 0,
    }))
    return 0


def action_payload(action: Action | None) -> dict[str, Any] | None:
    return None if action is None else {"type": action.type.name, "amount": round(float(action.amount), 2)}


def action_identity(action: Action | None) -> tuple[str, float] | None:
    return None if action is None else (action.type.name, round(float(action.amount), 2))


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


def public_state_payload(state: HUNLGameState) -> dict[str, Any]:
    """Return all public transition fields and no private/deck fields."""
    return {
        "config": config_payload(state.config),
        "board": [int(x) for x in state.board],
        "pot": round(float(state.pot), 8),
        "stacks": [round(float(x), 8) for x in state.stacks],
        "street": int(state.street),
        "street_committed": [round(float(x), 8) for x in state.street_committed],
        "current_player": int(state.current_player),
        "actions_history": [[int(player), action_payload(action)] for player, action in state.actions_history],
        "raise_count": int(state.raise_count),
        "last_bet_size": round(float(state.last_bet_size), 8),
        "is_done": bool(state.is_done),
        "folded_player": int(state.folded_player),
        "num_actions_this_street": int(state.num_actions_this_street),
    }


def array_identity(array: np.ndarray) -> dict[str, Any]:
    contiguous = np.ascontiguousarray(array)
    payload = {
        "shape": list(contiguous.shape),
        "dtype": str(contiguous.dtype),
        "bytes_sha256": hashlib.sha256(contiguous.tobytes()).hexdigest(),
    }
    payload["identity_sha256"] = sha256_obj(payload)
    return payload


def exact_slots(mask: np.ndarray, table: list[Action | None]) -> list[int]:
    if tuple(mask.shape) != (9,) or len(table) != 9:
        raise RuntimeError("nine_slot_shape_failure")
    slots = [slot for slot in range(9) if float(mask[slot]) == 1.0 and table[slot] is not None]
    if not slots:
        raise RuntimeError("empty_executable_action_table")
    if any((float(mask[slot]) == 1.0) != (table[slot] is not None) for slot in range(9)):
        raise RuntimeError("mask_table_identity_failure")
    identities = [action_identity(table[slot]) for slot in slots]
    if len(set(identities)) != len(identities):
        raise RuntimeError("executable_slot_collision")
    return slots


def observe(state: HUNLGameState, include_features: bool = False) -> tuple[dict[str, Any], np.ndarray, list[Action | None]]:
    player = int(state.current_player)
    mask, table = build_action_table(state)
    slots = exact_slots(mask, table)
    cards = encode_cards(state, player)
    actions = encode_action_history(state, player)
    extra = encode_extra(state, player)
    identity = {
        "card_info": array_identity(cards),
        "action_info": array_identity(actions),
        "extra_info": array_identity(extra),
        "legal_mask": array_identity(mask),
        "ordered_actions": [{"slot": slot, "action": action_payload(table[slot])} for slot in slots],
        "player": player,
    }
    identity["observation_sha256"] = sha256_obj(identity)
    if include_features:
        identity["features"] = {
            "observation_card_info": cards.tolist(),
            "observation_action_info": actions.tolist(),
            "observation_extra_info": extra.tolist(),
        }
    return identity, mask, table


def new_deal(depth: int, hand_id: int) -> HUNLGameState:
    maker = {200: GameConfig.full_200bb, 100: GameConfig.full_100bb, 50: GameConfig.full_50bb}[depth]
    config = maker()
    config.raise_cap_per_street = RAISE_CAP_UNLIMITED
    saved = random.getstate()
    try:
        random.seed(DEAL_SEED + depth * 1_000_000 + hand_id)
        return HUNLGameState(config).deal_new_hand()
    finally:
        random.setstate(saved)


def component_for_hand(depth: int, hand_id: int) -> str:
    rng = random.Random(COMPONENT_SEED + depth * 1_000_000 + hand_id)
    return COMPONENTS[rng.randrange(len(COMPONENTS))]


def proposal_weights(component: str, slots: list[int], table: list[Action | None]) -> list[float]:
    types = [table[slot].type for slot in slots if table[slot] is not None]
    counts = Counter(types)
    weights: list[float] = []
    for slot in slots:
        action = table[slot]
        assert action is not None
        passive = action.type in (ActionType.FOLD, ActionType.CHECK, ActionType.CALL)
        if component == "UNIFORM_LEGAL":
            weight = 1.0
        elif component == "PASSIVE_COVERAGE":
            weight = 4.0 if passive else 1.0
        elif component == "AGGRESSIVE_COVERAGE":
            weight = 1.0 if passive else 4.0
        elif component == "AMOUNT_DIVERSITY":
            weight = 1.0 / counts[action.type]
        else:
            raise RuntimeError(f"unknown_trajectory_component:{component}")
        if not math.isfinite(weight) or weight <= 0:
            raise RuntimeError("nonpositive_proposal_weight")
        weights.append(weight)
    return weights


def weighted_choice(slots: list[int], weights: list[float], rng: random.Random) -> int:
    draw = rng.random() * sum(weights)
    cursor = 0.0
    for slot, weight in zip(slots, weights, strict=True):
        cursor += weight
        if draw < cursor:
            return slot
    return slots[-1]


def line_bucket(state: HUNLGameState, slots: list[int]) -> str:
    player = state.current_player
    to_call = max(0.0, state.street_committed[1 - player] - state.street_committed[player])
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
    raise RuntimeError("line_bucket_unclassified")


def spr_bucket(state: HUNLGameState) -> str:
    spr = min(state.stacks) / max(state.pot, 1e-12)
    if spr <= 0.5:
        return "LE_0_5"
    if spr <= 1.0:
        return "GT_0_5_LE_1"
    if spr <= 2.0:
        return "GT_1_LE_2"
    if spr <= 4.0:
        return "GT_2_LE_4"
    if spr <= 8.0:
        return "GT_4_LE_8"
    return "GT_8"


def base_key(depth: int, state: HUNLGameState) -> str:
    return f"{depth}bb:{STREET_NAMES[int(state.street)]}:P{int(state.current_player)}"


def line_key(depth: int, state: HUNLGameState, bucket: str) -> str:
    return f"{base_key(depth, state)}:{bucket}"


def state_recipe(depth: int, hand_id: int, decision_index: int) -> dict[str, int]:
    return {"depth_bb": depth, "hand_id": hand_id, "decision_index": decision_index}


def regenerate_state(recipe: dict[str, int]) -> HUNLGameState:
    depth = int(recipe["depth_bb"])
    hand_id = int(recipe["hand_id"])
    target = int(recipe["decision_index"])
    state = new_deal(depth, hand_id)
    component = component_for_hand(depth, hand_id)
    rng = random.Random(ACTION_SEED + depth * 1_000_000 + hand_id)
    decision = 0
    while not state.is_terminal() and decision <= MAX_STEPS:
        if decision == target:
            return state.clone()
        _, mask, table = observe(state)
        slots = exact_slots(mask, table)
        slot = weighted_choice(slots, proposal_weights(component, slots, table), rng)
        action = table[slot]
        assert action is not None
        state = state.apply(action)
        decision += 1
    raise RuntimeError(f"recipe_not_reachable:{recipe}")


def infoset_identity(depth: int, state: HUNLGameState, observation: dict[str, Any]) -> str:
    hero = state.hole_cards[state.current_player]
    if hero is None:
        raise RuntimeError("acting_player_hole_cards_absent")
    return sha256_obj({
        "depth_bb": depth,
        "public_replay": public_state_payload(state),
        "acting_player_hole_cards": [int(hero[0]), int(hero[1])],
        "observation_sha256": observation["observation_sha256"],
        "ordered_actions": observation["ordered_actions"],
    })


def public_replay_identity(state: HUNLGameState) -> str:
    return sha256_obj(public_state_payload(state))


def push_lowest(heap: list[tuple[int, str, dict[str, int]]], identity: str, recipe: dict[str, int], limit: int) -> None:
    item = (-int(identity, 16), identity, recipe)
    if len(heap) < limit:
        heapq.heappush(heap, item)
    elif item[0] > heap[0][0]:
        heapq.heapreplace(heap, item)


def support_row(depth: int, hand_id: int, decision: int, state: HUNLGameState, sampling_seconds: float) -> dict[str, Any]:
    observation, mask, table = observe(state)
    slots = exact_slots(mask, table)
    bucket = line_bucket(state, slots)
    identity = infoset_identity(depth, state, observation)
    return {
        "schema_version": "v5.phase_fa.revision006.q006.support_state.v1",
        "training_eligibility": "FORBIDDEN_DIAGNOSTIC_ONLY",
        "state_identity_sha256": identity,
        "public_replay_identity_sha256": public_replay_identity(state),
        "recipe": state_recipe(depth, hand_id, decision),
        "depth_bb": depth,
        "street": STREET_NAMES[int(state.street)],
        "acting_player": int(state.current_player),
        "line_bucket": bucket,
        "spr_bucket": spr_bucket(state),
        "legal_slot_signature": "".join("1" if float(x) == 1.0 else "0" for x in mask),
        "legal_slots": slots,
        "observation_identity_sha256": observation["observation_sha256"],
        "ordered_nonnull_slot_actions": observation["ordered_actions"],
        "trajectory_component": component_for_hand(depth, hand_id),
        "sampling_seconds": float(sampling_seconds),
        "source_opponent_cards_serialized": False,
        "source_unrevealed_deck_serialized": False,
    }


def replay_determinized_infoset(source: HUNLGameState, seed: int) -> tuple[HUNLGameState, str]:
    """Rebuild source public history with fresh hidden chance fields only."""
    hero = int(source.current_player)
    opponent = 1 - hero
    hero_cards = source.hole_cards[hero]
    if hero_cards is None:
        raise RuntimeError("hero_cards_absent")
    known = {int(hero_cards[0]), int(hero_cards[1]), *[int(card) for card in source.board]}
    unseen = [card for card in range(52) if card not in known]
    rng = random.Random(seed)
    rng.shuffle(unseen)
    opponent_cards = (unseen[0], unseen[1])
    future = unseen[2:]
    if set(opponent_cards) & known or len(set(future + list(opponent_cards) + list(known))) != 52:
        raise RuntimeError("determinization_card_collision")

    replay = HUNLGameState(source.config)
    holes: list[tuple[int, int] | None] = [None, None]
    holes[hero] = (int(hero_cards[0]), int(hero_cards[1]))
    holes[opponent] = opponent_cards
    replay.hole_cards = holes
    replay.deck = list(future) + list(reversed(source.board))

    for expected_player, source_action in source.actions_history:
        if replay.is_terminal() or replay.current_player != expected_player:
            raise RuntimeError("public_history_player_replay_failure")
        mask, table = build_action_table(replay)
        slots = exact_slots(mask, table)
        matches = [slot for slot in slots if action_identity(table[slot]) == action_identity(source_action)]
        if len(matches) != 1:
            raise RuntimeError("public_history_action_replay_failure")
        action = table[matches[0]]
        assert action is not None
        replay = replay.apply(action)

    if public_state_payload(replay) != public_state_payload(source):
        raise RuntimeError("public_state_replay_identity_failure")
    source_observation, source_mask, source_table = observe(source)
    replay_observation, replay_mask, replay_table = observe(replay)
    if source_observation["observation_sha256"] != replay_observation["observation_sha256"]:
        raise RuntimeError("determinization_observation_invariance_failure")
    source_slots = exact_slots(source_mask, source_table)
    replay_slots = exact_slots(replay_mask, replay_table)
    if source_slots != replay_slots or any(action_identity(source_table[s]) != action_identity(replay_table[s]) for s in source_slots):
        raise RuntimeError("determinization_action_table_invariance_failure")
    determinization_hash = sha256_obj({
        "opponent_hole_cards": list(opponent_cards),
        "future_deck": future,
        "public_board": list(source.board),
        "seed": seed,
    })
    return replay, determinization_hash


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
        if steps > MAX_STEPS:
            raise RuntimeError("rollout_step_ceiling")
    return float(state.payoff(hero)), steps


def softmax(values: list[float], slots: list[int], temperature: float) -> list[float]:
    legal = np.asarray([values[slot] / temperature for slot in slots], dtype=np.float64)
    legal -= float(np.max(legal))
    weights = np.exp(legal)
    weights /= float(weights.sum())
    output = [0.0] * 9
    for slot, probability in zip(slots, weights.tolist(), strict=True):
        output[slot] = float(probability)
    return output


def mc32_row(row_id: int, recipe: dict[str, int], source: HUNLGameState) -> dict[str, Any]:
    started = time.perf_counter()
    observation, mask, table = observe(source, include_features=True)
    slots = exact_slots(mask, table)
    hero = int(source.current_player)
    batch_values: list[list[float]] = []
    determinization_hashes: list[str] = []
    max_rollout_steps = 0
    for batch in range(BATCHES):
        samples_by_slot: dict[int, list[float]] = {slot: [] for slot in slots}
        for rep in range(ROLLOUTS_PER_BATCH):
            det_seed = DETERMINIZATION_SEED + row_id * 100_000_000 + batch * 1_000_000 + rep * 10_000
            determinized, det_hash = replay_determinized_infoset(source, det_seed)
            determinization_hashes.append(det_hash)
            det_mask, det_table = build_action_table(determinized)
            det_slots = exact_slots(det_mask, det_table)
            if det_slots != slots:
                raise RuntimeError("root_slot_identity_changed_after_determinization")
            for slot in slots:
                if action_identity(det_table[slot]) != action_identity(table[slot]):
                    raise RuntimeError("root_action_identity_changed_after_determinization")
                action = det_table[slot]
                assert action is not None
                policy_seed = ROLLOUT_SEED + row_id * 100_000_000 + batch * 1_000_000 + rep * 10_000 + slot * 100 + 1
                payoff, steps = rollout(determinized.apply(action), hero, policy_seed)
                if not math.isfinite(payoff):
                    raise RuntimeError("nonfinite_action_value")
                samples_by_slot[slot].append(payoff)
                max_rollout_steps = max(max_rollout_steps, steps)
        values = [0.0] * 9
        for slot in slots:
            values[slot] = float(statistics.fmean(samples_by_slot[slot]))
        batch_values.append(values)

    temperature_metrics: dict[str, Any] = {}
    teachers: dict[str, list[float]] = {}
    mean_values = [statistics.fmean(batch[slot] for batch in batch_values) for slot in range(9)]
    for temperature in TEMPERATURES:
        distributions = [softmax(batch, slots, temperature) for batch in batch_values]
        l1_values = [
            sum(abs(a - b) for a, b in zip(distributions[left], distributions[right], strict=True))
            for left in range(BATCHES) for right in range(left + 1, BATCHES)
        ]
        tops = [max(slots, key=lambda slot: (distribution[slot], -slot)) for distribution in distributions]
        top_fraction = Counter(tops).most_common(1)[0][1] / BATCHES
        teacher = softmax(mean_values, slots, temperature)
        illegal_mass = sum(teacher[slot] for slot in range(9) if slot not in slots)
        if abs(sum(teacher) - 1.0) > 1e-6 or illegal_mass != 0.0:
            raise RuntimeError("teacher_probability_gate_failure")
        key = str(temperature)
        temperature_metrics[key] = {
            "batch_l1_mean": float(statistics.fmean(l1_values)),
            "batch_l1_max": float(max(l1_values)),
            "top_action_agreement_fraction": float(top_fraction),
        }
        teachers[key] = teacher

    features = observation.pop("features")
    identity_payload = {
        "state_identity_sha256": infoset_identity(int(recipe["depth_bb"]), source, observation),
        "batch_values": batch_values,
        "temperature_metrics": temperature_metrics,
        "teachers": teachers,
        "determinization_hashes": determinization_hashes,
    }
    return {
        "schema_version": "v5.phase_fa.revision006.q006.mc32_quality_row.v1",
        "training_eligibility": "FORBIDDEN_DIAGNOSTIC_ONLY",
        "row_id": row_id,
        "recipe": recipe,
        "depth_bb": int(recipe["depth_bb"]),
        "street": STREET_NAMES[int(source.street)],
        "acting_player": hero,
        "line_bucket": line_bucket(source, slots),
        "state_identity_sha256": identity_payload["state_identity_sha256"],
        "public_replay_identity_sha256": public_replay_identity(source),
        "observation_identity_sha256": observation["observation_sha256"],
        **features,
        "legal_mask9": [float(x) for x in mask],
        "ordered_nonnull_slot_actions": observation["ordered_actions"],
        "batch_action_values9": batch_values,
        "temperature_metrics": temperature_metrics,
        "teacher_probs9_by_temperature": teachers,
        "determinization_identity_sha256s": determinization_hashes,
        "determinizations_total": BATCHES * ROLLOUTS_PER_BATCH,
        "source_hidden_information_read_count": 0,
        "source_opponent_cards_serialized": False,
        "source_unrevealed_deck_serialized": False,
        "information_leakage_failures": 0,
        "determinization_replay_failures": 0,
        "card_collision_failures": 0,
        "action_identity_failures": 0,
        "illegal_positive_probability_mass": 0.0,
        "rollouts_per_action_total": BATCHES * ROLLOUTS_PER_BATCH,
        "max_rollout_steps": max_rollout_steps,
        "same_seed_identity_sha256": sha256_obj(identity_payload),
        "row_wall_seconds": time.perf_counter() - started,
    }


def mc32_task(item: tuple[int, dict[str, int], HUNLGameState]) -> dict[str, Any]:
    row_id, recipe, state = item
    validate_device_contract()
    return mc32_row(row_id, recipe, state)


def aggregate_quality(rows: list[dict[str, Any]]) -> tuple[float | None, dict[str, Any]]:
    slices: dict[str, list[dict[str, Any]]] = {"GLOBAL": rows}
    for depth in DEPTHS:
        slices[f"{depth}bb"] = [row for row in rows if row["depth_bb"] == depth]
    summary: dict[str, Any] = {}
    selected: float | None = None
    for temperature in TEMPERATURES:
        key = str(temperature)
        temperature_slices: dict[str, Any] = {}
        all_pass = True
        for slice_name, slice_rows in slices.items():
            if not slice_rows:
                metrics = {"batch_distribution_l1_mean": None, "batch_distribution_l1_p95": None, "states_top_action_agreement_ge_0_75_fraction": None, "passes": False}
            else:
                l1 = [float(row["temperature_metrics"][key]["batch_l1_mean"]) for row in slice_rows]
                top = [float(row["temperature_metrics"][key]["top_action_agreement_fraction"]) for row in slice_rows]
                metrics = {
                    "batch_distribution_l1_mean": float(statistics.fmean(l1)),
                    "batch_distribution_l1_p95": percentile(l1, 0.95),
                    "states_top_action_agreement_ge_0_75_fraction": sum(value >= 0.75 for value in top) / len(top),
                }
                metrics["passes"] = (
                    metrics["batch_distribution_l1_mean"] <= 0.20
                    and metrics["batch_distribution_l1_p95"] <= 0.50
                    and metrics["states_top_action_agreement_ge_0_75_fraction"] >= 0.70
                )
            temperature_slices[slice_name] = metrics
            all_pass = all_pass and metrics["passes"]
        summary[key] = {"slices": temperature_slices, "passes_all_required_slices": all_pass}
        if selected is None and all_pass:
            selected = temperature
    return selected, summary


def projected_asset_row(row: dict[str, Any], temperature: float) -> dict[str, Any]:
    key = str(temperature)
    return {
        "schema_version": "v5.phase_fa.trajectory_native_infoset_mc32_teacher_row.revision006.v1",
        "row_id": row["state_identity_sha256"],
        "depth_bb": row["depth_bb"],
        "street": row["street"],
        "line_bucket": row["line_bucket"],
        "acting_player": row["acting_player"],
        "public_replay_identity": row["public_replay_identity_sha256"],
        "observation_card_info": row["observation_card_info"],
        "observation_action_info": row["observation_action_info"],
        "observation_extra_info": row["observation_extra_info"],
        "observation_identity_sha256": row["observation_identity_sha256"],
        "legal_mask9": row["legal_mask9"],
        "ordered_nonnull_slot_actions": row["ordered_nonnull_slot_actions"],
        "teacher_action_values9": [statistics.fmean(batch[slot] for batch in row["batch_action_values9"]) for slot in range(9)],
        "teacher_probs9": row["teacher_probs9_by_temperature"][key],
        "temperature": temperature,
        "teacher_source": "INFOSET_MC32_EXACT_V55_ONLY",
        "training_feature_allowlist": ["observation_card_info", "observation_action_info", "observation_extra_info", "legal_mask9"],
        "training_eligibility": "PENDING_FINAL_IMMUTABLE_BUNDLE_AUDIT",
    }


def verify_design_inputs(design: dict[str, Any]) -> list[dict[str, str]]:
    verified: list[dict[str, str]] = []
    for item in design["frozen_evidence"]:
        path = canonical_path(item["path"])
        observed = sha256_file(path)
        if observed != item["sha256"]:
            raise RuntimeError(f"frozen_evidence_hash_mismatch:{path}")
        verified.append({"role": item["role"], "path": str(path), "sha256": observed})
    return verified


def write_json_exclusive(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def write_jsonl_exclusive(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(canonical_json(row) + "\n")


def self_test() -> int:
    state = new_deal(200, 0)
    observation, mask, table = observe(state)
    slots = exact_slots(mask, table)
    for component in COMPONENTS:
        weights = proposal_weights(component, slots, table)
        if len(weights) != len(slots) or not all(weight > 0 for weight in weights):
            raise RuntimeError("proposal_weight_self_test_failure")
    recipe = state_recipe(200, 0, 0)
    if public_state_payload(regenerate_state(recipe)) != public_state_payload(state):
        raise RuntimeError("trajectory_recipe_self_test_failure")
    det_a, hash_a = replay_determinized_infoset(state, DETERMINIZATION_SEED)
    det_b, hash_b = replay_determinized_infoset(state, DETERMINIZATION_SEED + 1)
    if hash_a == hash_b or observe(det_a)[0]["observation_sha256"] != observation["observation_sha256"] or observe(det_b)[0]["observation_sha256"] != observation["observation_sha256"]:
        raise RuntimeError("determinization_self_test_failure")
    row_a = mc32_row(0, recipe, state)
    row_b = mc32_row(0, recipe, state)
    if row_a["same_seed_identity_sha256"] != row_b["same_seed_identity_sha256"]:
        raise RuntimeError("mc32_repeat_self_test_failure")
    if row_a["determinizations_total"] != 32 or row_a["source_hidden_information_read_count"] != 0:
        raise RuntimeError("mc32_contract_self_test_failure")
    print("PHASE_FA_REVISION006_Q006_SELF_TEST_PASS")
    return 0


def run(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    contract = validate_device_contract()

    raw_paths = {
        "design": args.design,
        "design_audit": args.design_audit,
        "implementation_audit": args.implementation_audit,
        "output": args.output,
    }
    paths = {name: canonical_path(value) for name, value in raw_paths.items()}
    expected = {
        "design": canonical_path(EXPECTED_DESIGN),
        "design_audit": canonical_path(EXPECTED_DESIGN_AUDIT),
        "implementation_audit": canonical_path(EXPECTED_IMPLEMENTATION_AUDIT),
        "output": canonical_path(EXPECTED_OUTPUT),
    }
    if paths != expected or not all(Path(value).is_absolute() for value in raw_paths.values()):
        raise RuntimeError("registered_absolute_path_identity_mismatch")
    if paths["output"].exists():
        raise RuntimeError("immutable_output_root_exists")
    if sha256_file(paths["design"]) != DESIGN_SHA256 or sha256_file(paths["design_audit"]) != DESIGN_AUDIT_SHA256:
        raise RuntimeError("design_identity_hash_mismatch")
    if sha256_file(paths["implementation_audit"]) != args.implementation_audit_sha256:
        raise RuntimeError("implementation_audit_hash_mismatch")

    design = json.loads(paths["design"].read_text(encoding="utf-8"))
    design_audit = json.loads(paths["design_audit"].read_text(encoding="utf-8"))
    implementation_audit = json.loads(paths["implementation_audit"].read_text(encoding="utf-8"))
    if design.get("design_id") != DESIGN_ID:
        raise RuntimeError("design_id_mismatch")
    if design_audit.get("overall") != "PASS" or design_audit.get("checks_total") != 267 or design_audit.get("classification") != "PHASE_FA_DESIGN_REVISION006_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_Q006_IMPLEMENTATION_READY_ONLY":
        raise RuntimeError("design_audit_classification_mismatch")
    if implementation_audit.get("overall") != "PASS" or implementation_audit.get("authorization") != "EXACTLY_ONE_LATER_Q006_QUALIFICATION_THROUGH_EXACT_LAUNCHER_NO_AUTOMATIC_LAUNCH":
        raise RuntimeError("implementation_audit_authority_mismatch")
    verified_inputs = verify_design_inputs(design)

    paths["output"].mkdir(parents=False, exist_ok=False)
    support_path = paths["output"] / "support_states.jsonl"
    quality_path = paths["output"] / "mc32_quality_rows.jsonl"
    repeat_path = paths["output"] / "same_seed_repeats.jsonl"
    metrics_path = paths["output"] / "raw_metrics.json"
    result_path = paths["output"] / "result.json"

    support_counts: Counter[str] = Counter()
    line_counts: Counter[str] = Counter()
    public_replays: dict[str, set[str]] = defaultdict(set)
    sampling_seconds: dict[str, list[float]] = defaultdict(list)
    quality_heaps: dict[str, list[tuple[int, str, dict[str, int]]]] = defaultdict(list)
    seen_by_depth: dict[int, set[str]] = {depth: set() for depth in DEPTHS}
    accepted_by_depth: Counter[int] = Counter()
    hands_by_depth: Counter[int] = Counter()
    legal_slots_seen: set[int] = set()
    wall_exhausted = False
    global_ordinal = 0

    with support_path.open("x", encoding="utf-8", newline="\n") as support_stream:
        for depth in DEPTHS:
            hand_order_rng = random.Random(SUPPORT_ORDER_SEED + depth)
            hand_order_offset = hand_order_rng.randrange(MAX_HANDS_PER_DEPTH)
            for sequence in range(MAX_HANDS_PER_DEPTH):
                if accepted_by_depth[depth] >= PILOT_PER_DEPTH:
                    break
                if time.perf_counter() - started > WALL_SECONDS_MAX:
                    wall_exhausted = True
                    break
                hand_id = (hand_order_offset + sequence) % MAX_HANDS_PER_DEPTH
                hands_by_depth[depth] += 1
                state = new_deal(depth, hand_id)
                component = component_for_hand(depth, hand_id)
                rng = random.Random(ACTION_SEED + depth * 1_000_000 + hand_id)
                decision = 0
                previous = time.perf_counter()
                while not state.is_terminal() and decision <= MAX_STEPS and accepted_by_depth[depth] < PILOT_PER_DEPTH:
                    row = support_row(depth, hand_id, decision, state, time.perf_counter() - previous)
                    identity = row["state_identity_sha256"]
                    if identity not in seen_by_depth[depth]:
                        seen_by_depth[depth].add(identity)
                        row["global_ordinal"] = global_ordinal
                        global_ordinal += 1
                        accepted_by_depth[depth] += 1
                        base = f"{depth}bb:{row['street']}:P{row['acting_player']}"
                        line = f"{base}:{row['line_bucket']}"
                        support_counts[base] += 1
                        line_counts[line] += 1
                        public_replays[line].add(row["public_replay_identity_sha256"])
                        sampling_seconds[line].append(row["sampling_seconds"])
                        legal_slots_seen.update(row["legal_slots"])
                        push_lowest(quality_heaps[base], identity, row["recipe"], QUALITY_PER_BASE)
                        support_stream.write(canonical_json(row) + "\n")
                    observation, mask, table = observe(state)
                    slots = exact_slots(mask, table)
                    slot = weighted_choice(slots, proposal_weights(component, slots, table), rng)
                    action = table[slot]
                    assert action is not None
                    state = state.apply(action)
                    decision += 1
                    previous = time.perf_counter()
                if decision > MAX_STEPS and not state.is_terminal():
                    raise RuntimeError("trajectory_step_ceiling")
            if wall_exhausted:
                break

    peak_rss = max(peak_rss, process.memory_info().rss)
    expected_base_keys = {f"{depth}bb:{street}:P{player}" for depth in DEPTHS for street in STREETS for player in (0, 1)}
    eligible_lines = {
        key for key, count in line_counts.items()
        if count >= MIN_LINE_INFOSETS and len(public_replays[key]) >= MIN_LINE_PUBLIC_REPLAYS
    }
    base_support_pass = all(support_counts[key] >= QUALITY_PER_BASE for key in expected_base_keys)
    line_diversity_by_depth = {
        depth: len({key.rsplit(":", 1)[1] for key in eligible_lines if key.startswith(f"{depth}bb:")})
        for depth in DEPTHS
    }
    global_line_diversity = len({key.rsplit(":", 1)[1] for key in eligible_lines})
    line_diversity_pass = all(value >= 6 for value in line_diversity_by_depth.values()) and global_line_diversity == 8
    support_complete = sum(accepted_by_depth.values()) == PILOT_TOTAL and all(accepted_by_depth[depth] == PILOT_PER_DEPTH for depth in DEPTHS)

    quality_items: list[tuple[int, dict[str, int], HUNLGameState]] = []
    if support_complete and base_support_pass and not wall_exhausted:
        row_id = 0
        for key in sorted(expected_base_keys):
            selected = sorted(((identity, recipe) for _, identity, recipe in quality_heaps[key]), key=lambda item: item[0])
            if len(selected) != QUALITY_PER_BASE:
                raise RuntimeError(f"quality_reservoir_shortfall:{key}:{len(selected)}")
            for _, recipe in selected:
                quality_items.append((row_id, recipe, regenerate_state(recipe)))
                row_id += 1

    quality_rows: list[dict[str, Any]] = []
    if len(quality_items) == QUALITY_TOTAL:
        with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="revision006-q006") as pool:
            quality_rows = list(pool.map(mc32_task, quality_items))
    write_jsonl_exclusive(quality_path, quality_rows)
    peak_rss = max(peak_rss, process.memory_info().rss)

    selected_temperature, quality_summary = aggregate_quality(quality_rows) if quality_rows else (None, {})
    repeat_rows: list[dict[str, Any]] = []
    if quality_rows:
        repeat_items: list[tuple[int, dict[str, int], HUNLGameState, str]] = []
        by_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in quality_rows:
            by_base[f"{row['depth_bb']}bb:{row['street']}:P{row['acting_player']}"] .append(row)
        for key in sorted(expected_base_keys):
            for row in sorted(by_base[key], key=lambda value: value["state_identity_sha256"])[:REPEATS_PER_BASE]:
                repeat_items.append((int(row["row_id"]), row["recipe"], regenerate_state(row["recipe"]), row["same_seed_identity_sha256"]))
        for row_id, recipe, state, expected_identity in repeat_items:
            repeated = mc32_row(row_id, recipe, state)
            repeat_rows.append({
                "schema_version": "v5.phase_fa.revision006.q006.same_seed_repeat.v1",
                "row_id": row_id,
                "state_identity_sha256": repeated["state_identity_sha256"],
                "expected_identity_sha256": expected_identity,
                "observed_identity_sha256": repeated["same_seed_identity_sha256"],
                "matches": repeated["same_seed_identity_sha256"] == expected_identity,
                "training_eligibility": "FORBIDDEN_DIAGNOSTIC_ONLY",
            })
    write_jsonl_exclusive(repeat_path, repeat_rows)
    repeat_failures = sum(not row["matches"] for row in repeat_rows)

    sampling_p99_by_eligible_line = {key: percentile(sampling_seconds[key], 0.99) for key in sorted(eligible_lines)}
    max_sampling_p99 = max(sampling_p99_by_eligible_line.values(), default=None)
    mc32_p99_by_depth = {
        depth: percentile((row["row_wall_seconds"] for row in quality_rows if row["depth_bb"] == depth), 0.99)
        for depth in DEPTHS if any(row["depth_bb"] == depth for row in quality_rows)
    }
    max_mc32_p99 = max(mc32_p99_by_depth.values(), default=None)
    projection_temperature = selected_temperature if selected_temperature is not None else TEMPERATURES[-1]
    uncompressed_sizes: list[int] = []
    gzip_sizes: list[int] = []
    serialization_seconds: list[float] = []
    for row in quality_rows:
        serialization_started = time.perf_counter()
        payload = canonical_json(projected_asset_row(row, projection_temperature)).encode("utf-8")
        compressed = gzip.compress(payload, compresslevel=6, mtime=0)
        serialization_seconds.append(time.perf_counter() - serialization_started)
        uncompressed_sizes.append(len(payload))
        gzip_sizes.append(len(compressed))
    serialization_p99 = percentile(serialization_seconds, 0.99) if serialization_seconds else None
    uncompressed_p99 = int(percentile(uncompressed_sizes, 0.99)) if uncompressed_sizes else None
    gzip_p99 = int(percentile(gzip_sizes, 0.99)) if gzip_sizes else None
    projected_wall_seconds = (
        1.25 * 20_000_000 / WORKERS * (max_sampling_p99 + max_mc32_p99 + serialization_p99)
        if max_sampling_p99 is not None and max_mc32_p99 is not None and serialization_p99 is not None else None
    )

    metrics = {
        "schema_version": "v5.phase_fa.revision006.q006.raw_metrics.v1",
        "accepted_by_depth": {f"{depth}bb": accepted_by_depth[depth] for depth in DEPTHS},
        "hands_by_depth": {f"{depth}bb": hands_by_depth[depth] for depth in DEPTHS},
        "base_support_counts": dict(sorted(support_counts.items())),
        "line_support_counts": dict(sorted(line_counts.items())),
        "line_public_replay_counts": {key: len(public_replays[key]) for key in sorted(line_counts)},
        "eligible_lines": sorted(eligible_lines),
        "line_diversity_by_depth": {f"{depth}bb": line_diversity_by_depth[depth] for depth in DEPTHS},
        "global_line_diversity": global_line_diversity,
        "legal_slots_seen": sorted(legal_slots_seen),
        "wall_exhausted": wall_exhausted,
        "quality_summary": quality_summary,
        "selected_temperature": selected_temperature,
        "same_seed_repeat_failures": repeat_failures,
        "sampling_p99_by_eligible_line": sampling_p99_by_eligible_line,
        "max_sampling_p99": max_sampling_p99,
        "mc32_p99_by_depth": {f"{depth}bb": value for depth, value in mc32_p99_by_depth.items()},
        "max_mc32_p99": max_mc32_p99,
        "serialization_gzip_p99_seconds": serialization_p99,
        "uncompressed_asset_row_p99_bytes": uncompressed_p99,
        "gzip_asset_row_p99_bytes": gzip_p99,
        "projected_eight_worker_20m_wall_seconds": projected_wall_seconds,
        "quota_manifest_created": False,
    }
    write_json_exclusive(metrics_path, metrics)

    wall_seconds = time.perf_counter() - started
    peak_rss = max(peak_rss, process.memory_info().rss)
    peak_rss_mb = peak_rss / 1_048_576
    pre_result_bytes = sum(path.stat().st_size for path in (support_path, quality_path, repeat_path, metrics_path))
    hard_failure_zero = all(
        row["source_hidden_information_read_count"] == 0
        and row["information_leakage_failures"] == 0
        and row["determinization_replay_failures"] == 0
        and row["card_collision_failures"] == 0
        and row["action_identity_failures"] == 0
        and row["illegal_positive_probability_mass"] == 0.0
        and row["max_rollout_steps"] <= MAX_STEPS
        for row in quality_rows
    )
    gates = {
        "design_and_audit_exact": True,
        "implementation_audit_exact": True,
        "device_contract_exact": True,
        "all_frozen_evidence_hashes_exact": len(verified_inputs) == 12,
        "support_states_exact_300000": support_complete,
        "support_each_depth_exact_100000": all(accepted_by_depth[depth] == PILOT_PER_DEPTH for depth in DEPTHS),
        "support_all_24_depth_street_actual_actor_base_cells_ge_256": base_support_pass,
        "eligible_line_support_min_256_infosets_64_public_replays": all(line_counts[key] >= MIN_LINE_INFOSETS and len(public_replays[key]) >= MIN_LINE_PUBLIC_REPLAYS for key in eligible_lines),
        "line_diversity_each_depth_ge_6_and_global_all_8": line_diversity_pass,
        "all_executable_v55_slots_observed": legal_slots_seen == set(range(9)),
        "no_target_cell_search_or_cross_fill": True,
        "quality_states_exact_6144": len(quality_rows) == QUALITY_TOTAL,
        "quality_256_per_each_24_base_cells": len(quality_rows) == QUALITY_TOTAL and Counter(f"{row['depth_bb']}bb:{row['street']}:P{row['acting_player']}" for row in quality_rows) == Counter({key: QUALITY_PER_BASE for key in expected_base_keys}),
        "mc32_exact_4x8_per_legal_action": all(row["rollouts_per_action_total"] == 32 and row["determinizations_total"] == 32 and len(row["batch_action_values9"]) == 4 for row in quality_rows),
        "hidden_information_replay_identity_illegal_and_finite_failures_zero": hard_failure_zero,
        "one_global_lowest_temperature_passes_global_and_all_depths": selected_temperature is not None and all(not quality_summary[str(value)]["passes_all_required_slices"] for value in TEMPERATURES if value < selected_temperature),
        "same_seed_repeats_exact_768": len(repeat_rows) == REPEAT_TOTAL,
        "same_seed_repeat_failures_zero": repeat_failures == 0,
        "fresh_resource_sampling_p99_available_each_eligible_line": bool(eligible_lines) and set(sampling_p99_by_eligible_line) == eligible_lines,
        "fresh_resource_mc32_p99_available_each_depth": set(mc32_p99_by_depth) == set(DEPTHS),
        "projected_eight_worker_20m_wall_le_168h": projected_wall_seconds is not None and projected_wall_seconds <= PROJECTED_WALL_SECONDS_MAX,
        "uncompressed_asset_row_p99_le_8192": uncompressed_p99 is not None and uncompressed_p99 <= UNCOMPRESSED_ROW_P99_MAX,
        "gzip_asset_row_p99_le_5000": gzip_p99 is not None and gzip_p99 <= GZIP_ROW_P99_MAX,
        "qualification_wall_seconds_le_43200": wall_seconds <= WALL_SECONDS_MAX,
        "qualification_peak_rss_mb_le_4096": peak_rss_mb <= RSS_MB_MAX,
        "qualification_output_bytes_le_10gb": pre_result_bytes <= OUTPUT_BYTES_MAX,
        "workers_exact_8_cpu_only_no_torch": WORKERS == 8 and contract["CUDA_VISIBLE_DEVICES"] == "-1" and "torch" not in sys.modules,
        "diagnostic_outputs_training_forbidden": all(row["training_eligibility"] == "FORBIDDEN_DIAGNOSTIC_ONLY" for row in quality_rows + repeat_rows),
        "quota_manifest_not_created": metrics["quota_manifest_created"] is False,
    }
    passed = all(gates.values())
    classification = (
        "PHASE_FA_REVISION006_Q006_PASS_TRAJECTORY_SUPPORT_MC32_QUALITY_AND_RESOURCE_QUALIFIED"
        if passed else
        "PHASE_FA_REVISION006_Q006_NONPASS_FAIL_CLOSED_SUPPORT_MC32_QUALITY_OR_RESOURCE_GATE"
    )
    result = {
        "schema_version": "v5.phase_fa.revision006.q006.result.v1",
        "design_id": DESIGN_ID,
        "qualification_id": QUALIFICATION_ID,
        "verdict": "PASS" if passed else "NONPASS_FAIL_CLOSED",
        "classification": classification,
        "design_sha256": DESIGN_SHA256,
        "design_audit_sha256": DESIGN_AUDIT_SHA256,
        "implementation_audit_sha256": args.implementation_audit_sha256,
        "runner_sha256": sha256_file(Path(__file__)),
        "device_contract": contract,
        "verified_design_inputs": verified_inputs,
        "measurements": {
            "accepted_states": sum(accepted_by_depth.values()),
            "accepted_by_depth": metrics["accepted_by_depth"],
            "hands_by_depth": metrics["hands_by_depth"],
            "base_support_counts": metrics["base_support_counts"],
            "eligible_lines": metrics["eligible_lines"],
            "line_diversity_by_depth": metrics["line_diversity_by_depth"],
            "global_line_diversity": global_line_diversity,
            "legal_slots_seen": metrics["legal_slots_seen"],
            "quality_rows": len(quality_rows),
            "same_seed_repeats": len(repeat_rows),
            "same_seed_repeat_failures": repeat_failures,
            "selected_temperature": selected_temperature,
            "quality_summary": quality_summary,
            "projected_eight_worker_20m_wall_seconds": projected_wall_seconds,
            "uncompressed_asset_row_p99_bytes": uncompressed_p99,
            "gzip_asset_row_p99_bytes": gzip_p99,
            "wall_seconds": wall_seconds,
            "peak_rss_mb": peak_rss_mb,
            "bundle_bytes_before_result_and_audit": pre_result_bytes,
        },
        "files": {
            "support_states": {"path": str(support_path), "sha256": sha256_file(support_path), "rows": sum(accepted_by_depth.values())},
            "mc32_quality_rows": {"path": str(quality_path), "sha256": sha256_file(quality_path), "rows": len(quality_rows)},
            "same_seed_repeats": {"path": str(repeat_path), "sha256": sha256_file(repeat_path), "rows": len(repeat_rows)},
            "raw_metrics": {"path": str(metrics_path), "sha256": sha256_file(metrics_path)},
        },
        "gates": gates,
        "authority": {
            "training_eligibility": "FORBIDDEN",
            "quota_manifest": "NONE_UNTIL_SEPARATE_PASS_TRANSITION",
            "asset_generation": "NONE",
            "behavior_launch": "NONE",
            "slumbot": "NONE_NO_NEW_CHECKPOINT",
            "official_hands": 0,
            "pass_next": "SEPARATELY_CREATE_AND_AUDIT_ONE_IMMUTABLE_PILOT_DERIVED_QUOTA_MANIFEST",
            "nonpass_next": "FREEZE_AND_RUN_SCIENTIFIC_ROUTE_REVIEW_NO_RERUN_EXTENSION_OR_THRESHOLD_RELAXATION",
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
        parser.error("qualification requires every immutable identity argument")
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
