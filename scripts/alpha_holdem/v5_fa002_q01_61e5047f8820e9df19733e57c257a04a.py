"""FA002 Q01 combined reachability, exact-V5.5 MC32 quality, and resource qualification.

This is a fresh implementation for the immutable FA002 program. ContractProbe is
strictly zero-file. Qualification is trainerless, CPU-only, one-attempt, and its rows
are diagnostic-only. It never imports torch and never creates a model checkpoint.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import heapq
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
import psutil

PROJECT = Path(__file__).resolve().parents[2]
SCRIPTS = PROJECT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from alpha_holdem.environment_v55 import (  # noqa: E402
    RAISE_CAP_UNLIMITED,
    build_action_table,
    encode_action_history,
    encode_cards,
    encode_extra,
)
from deep_cfr.game_state import Action, ActionType, GameConfig, HUNLGameState, Street  # noqa: E402

PROGRAM_ID = "FA002_61e5047f8820e9df19733e57c257a04a"
QUALIFICATION_ID = "FA002_Q01_61e5047f8820e9df19733e57c257a04a"
PREREG_SHA256 = "18765838ce043a6f560162770aeeb665eebac6a42b53f580934f6c69d6d849a7"
PREREG_AUDIT_SHA256 = "004090c0ab90388c9e494cf503f572a463fda38eaf65e6a41af886846db6e5f7"
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
DEVICE_MODE = "CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK"
EXECUTION_NONCE = "FA002_Q01_EXECUTION_2034972233"
PROBE_NONCES = (
    "FA002_Q01_PROBE_A_2032972233",
    "FA002_Q01_PROBE_B_2033972233",
)

EXPECTED_PREREG = PROJECT / "reports" / "v5_fa002_unified_candidate_preregistration_61e5047f8820e9df19733e57c257a04a_20260722.json"
EXPECTED_PREREG_AUDIT = PROJECT / "reports" / "v5_fa002_unified_candidate_preregistration_audit_61e5047f8820e9df19733e57c257a04a_20260722.json"
EXPECTED_IMPLEMENTATION_AUDIT = PROJECT / "reports" / "v5_fa002_q01_implementation_audit_61e5047f8820e9df19733e57c257a04a_20260722.json"
EXPECTED_OUTPUT = PROJECT / "reports" / "v5_fa002_q01_61e5047f8820e9df19733e57c257a04a_20260722"
EXPECTED_LAUNCHER = PROJECT / "scripts" / "alpha_holdem" / "v5_fa002_q01_launcher_61e5047f8820e9df19733e57c257a04a.ps1"
EXPECTED_AUDITOR = PROJECT / "scripts" / "alpha_holdem" / "v5_fa002_q01_audit_61e5047f8820e9df19733e57c257a04a.py"

DEPTHS = (200, 100, 50)
STREETS = (Street.PREFLOP, Street.FLOP, Street.TURN, Street.RIVER)
STREET_NAMES = {int(street): street.name for street in STREETS}
COMPONENTS = ("UNIFORM_LEGAL", "PASSIVE_WEIGHTED", "AGGRESSIVE_WEIGHTED", "SLOT_DIVERSITY_WEIGHTED")
DEAL_SEED = 2026072233
COMPONENT_SEED = 2026972233
ACTION_SEED = 2027972233
DETERMINIZATION_SEED = 2028972233
ROLLOUT_SEED = 2029972233
SHARD_ASSIGNMENT_SEED = 2030972233

ACCEPTED_PER_DEPTH = 40_000
ACCEPTED_TOTAL = 120_000
MAX_STARTED_HANDS_PER_DEPTH = 100_000
MAX_STEPS = 128
MIN_PER_CONTEXT = 256
QUALITY_PER_CONTEXT = 256
QUALITY_TOTAL = 6_144
REPEATS_PER_CONTEXT = 32
REPEATS_TOTAL = 768
BATCHES = 4
ROLLOUTS_PER_BATCH = 8
ROLLOUTS_PER_ACTION = 32
TEMPERATURE = 100.0
WORKERS = 8

QUALITY_L1_MEAN_MAX = 0.20
QUALITY_L1_P95_MAX = 0.50
QUALITY_TOP_AGREEMENT_FRACTION_MIN = 0.70
WALL_SECONDS_MAX = 21_600.0
RSS_MB_MAX = 4_096.0
OUTPUT_BYTES_MAX = 10_000_000_000
PROJECTED_WALL_HOURS_MAX = 168.0
PROJECTED_COMPRESSED_BYTES_MAX = 100_000_000_000
UNCOMPRESSED_ROW_P99_MAX = 8_192
GZIP_ROW_P99_MAX = 5_000


def canonical_path(value: str | Path) -> Path:
    return Path(value).resolve(strict=False)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_obj(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with canonical_path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values: Iterable[float], q: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile_requires_values")
    index = min(len(ordered) - 1, math.floor((len(ordered) - 1) * q))
    return ordered[index]


def validate_device_contract(expected_nonce: str) -> dict[str, Any]:
    observed = {
        "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "FA002_Q01_DEVICE_MODE": os.environ.get("FA002_Q01_DEVICE_MODE"),
        "FA002_Q01_CONTRACT_NONCE": os.environ.get("FA002_Q01_CONTRACT_NONCE"),
    }
    expected = {
        "CUDA_VISIBLE_DEVICES": "-1",
        "FA002_Q01_DEVICE_MODE": DEVICE_MODE,
        "FA002_Q01_CONTRACT_NONCE": expected_nonce,
    }
    if observed != expected:
        raise RuntimeError(f"device_contract_mismatch:{observed!r}")
    runtime = canonical_path(sys.executable)
    runtime_sha = sha256_file(runtime)
    if runtime_sha != PYTHON_SHA256:
        raise RuntimeError("runtime_python_sha_mismatch")
    if "torch" in sys.modules:
        raise RuntimeError("torch_in_sys_modules")
    payload = {
        **observed,
        "python_executable": str(runtime),
        "python_sha256": runtime_sha,
        "program_id": PROGRAM_ID,
        "qualification_id": QUALIFICATION_ID,
        "preregistration_sha256": PREREG_SHA256,
        "preregistration_audit_sha256": PREREG_AUDIT_SHA256,
        "torch_in_sys_modules": False,
    }
    payload["contract_sha256"] = sha256_obj(payload)
    return payload


def contract_probe(expected_nonce: str) -> int:
    if expected_nonce not in PROBE_NONCES:
        raise RuntimeError("unregistered_probe_nonce")
    if EXPECTED_OUTPUT.exists():
        raise RuntimeError("qualification_output_root_exists_before_probe")
    payload = {
        "schema_version": "v5.fa002.q01.contract_probe.v1",
        **validate_device_contract(expected_nonce),
        "runner_path": str(canonical_path(__file__)),
        "runner_sha256": sha256_file(__file__),
        "output_root": str(canonical_path(EXPECTED_OUTPUT)),
        "output_root_exists": False,
        "files_written": 0,
    }
    print(canonical_json(payload))
    return 0


def make_config(depth: int) -> GameConfig:
    if depth == 200:
        config = GameConfig.full_200bb()
    elif depth == 100:
        config = GameConfig.full_100bb()
    elif depth == 50:
        config = GameConfig.full_50bb()
    else:
        raise ValueError(f"unsupported_depth:{depth}")
    config.raise_cap_per_street = RAISE_CAP_UNLIMITED
    return config


def new_deal(depth: int, hand_id: int) -> HUNLGameState:
    state = HUNLGameState(make_config(depth))
    rng = random.Random(DEAL_SEED + depth * 1_000_000 + hand_id)
    rng.shuffle(state.deck)
    state.hole_cards = [(state.deck[0], state.deck[1]), (state.deck[2], state.deck[3])]
    return state


def action_payload(action: Action | None) -> dict[str, Any] | None:
    if action is None:
        return None
    return {"type": action.type.name, "amount_centibb": int(round(float(action.amount) * 100.0))}


def action_identity(action: Action | None) -> tuple[str, int] | None:
    payload = action_payload(action)
    if payload is None:
        return None
    return payload["type"], payload["amount_centibb"]


def exact_slots(mask: np.ndarray, table: list[Action | None]) -> list[int]:
    if len(mask) != 9 or len(table) != 9:
        raise RuntimeError("action_table_shape_failure")
    slots: list[int] = []
    for slot in range(9):
        legal = float(mask[slot]) == 1.0
        bound = table[slot] is not None
        if legal != bound:
            raise RuntimeError("mask_table_identity_failure")
        if legal:
            slots.append(slot)
    if not slots:
        raise RuntimeError("no_exact_legal_slots")
    if len({action_identity(table[slot]) for slot in slots}) != len(slots):
        raise RuntimeError("slot_action_collision")
    return slots


def array_payload(array: np.ndarray, include_values: bool = False) -> dict[str, Any]:
    contiguous = np.ascontiguousarray(array)
    identity_payload: dict[str, Any] = {
        "shape": list(contiguous.shape),
        "dtype": str(contiguous.dtype),
        "bytes_sha256": hashlib.sha256(contiguous.tobytes()).hexdigest(),
    }
    payload = dict(identity_payload)
    payload["identity_sha256"] = sha256_obj(identity_payload)
    if include_values:
        payload["values"] = contiguous.astype(np.float32, copy=False).reshape(-1).tolist()
    return payload


def observe(state: HUNLGameState, include_features: bool = False) -> tuple[dict[str, Any], np.ndarray, list[Action | None]]:
    hero = int(state.current_player)
    mask, table = build_action_table(state)
    slots = exact_slots(mask, table)
    card = encode_cards(state, hero)
    history = encode_action_history(state, hero)
    extra = encode_extra(state, hero)
    payload: dict[str, Any] = {
        "card_info": array_payload(card, include_features),
        "action_info": array_payload(history, include_features),
        "extra_info": array_payload(extra, include_features),
        "legal_mask": array_payload(mask, include_features),
        "player": hero,
        "ordered_actions": [{"slot": slot, "action": action_payload(table[slot])} for slot in slots],
    }
    payload["observation_sha256"] = sha256_obj({
        "card_info": payload["card_info"]["identity_sha256"],
        "action_info": payload["action_info"]["identity_sha256"],
        "extra_info": payload["extra_info"]["identity_sha256"],
        "legal_mask": payload["legal_mask"]["identity_sha256"],
        "player": hero,
        "ordered_actions": payload["ordered_actions"],
    })
    return payload, mask, table


def public_state_payload(state: HUNLGameState) -> dict[str, Any]:
    return {
        "effective_stack_centibb": int(round(float(state.config.effective_stack) * 100.0)),
        "include_preflop": bool(state.config.include_preflop),
        "raise_cap_preflop": int(state.config.raise_cap_preflop),
        "raise_cap_per_street": int(state.config.raise_cap_per_street),
        "board": [int(card) for card in state.board],
        "pot_centibb": int(round(float(state.pot) * 100.0)),
        "stacks_centibb": [int(round(float(value) * 100.0)) for value in state.stacks],
        "street": int(state.street),
        "current_player": int(state.current_player),
        "street_commitments_centibb": [int(round(float(value) * 100.0)) for value in state.street_committed],
        "raise_count": int(state.raise_count),
        "last_bet_size_centibb": int(round(float(state.last_bet_size) * 100.0)),
        "num_actions_this_street": int(state.num_actions_this_street),
        "is_done": bool(state.is_done),
        "folded_player": int(state.folded_player),
        "actions_history": [[int(player), action_payload(action)] for player, action in state.actions_history],
    }


def state_recipe(depth: int, hand_id: int, decision_index: int) -> dict[str, int]:
    return {"depth_bb": int(depth), "hand_id": int(hand_id), "decision_index": int(decision_index)}


def component_for_hand(depth: int, hand_id: int) -> str:
    digest = hashlib.sha256(f"{COMPONENT_SEED}|{depth}|{hand_id}".encode("ascii")).digest()
    return COMPONENTS[int.from_bytes(digest[:8], "big") % len(COMPONENTS)]


def proposal_weights(component: str, slots: list[int]) -> list[float]:
    if component == "UNIFORM_LEGAL":
        return [1.0 for _ in slots]
    if component == "PASSIVE_WEIGHTED":
        return [8.0 if slot == 1 else 1.0 for slot in slots]
    if component == "AGGRESSIVE_WEIGHTED":
        return [4.0 if 2 <= slot <= 8 else 1.0 for slot in slots]
    if component == "SLOT_DIVERSITY_WEIGHTED":
        return [float(slot + 1) for slot in slots]
    raise ValueError("unknown_trajectory_component")


def weighted_choice(slots: list[int], weights: list[float], rng: random.Random) -> int:
    if len(slots) != len(weights) or not slots or any(weight <= 0 or not math.isfinite(weight) for weight in weights):
        raise RuntimeError("invalid_proposal_weights")
    target = rng.random() * sum(weights)
    cumulative = 0.0
    for slot, weight in zip(slots, weights, strict=True):
        cumulative += weight
        if target < cumulative:
            return slot
    return slots[-1]


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
        slot = weighted_choice(slots, proposal_weights(component, slots), rng)
        action = table[slot]
        assert action is not None
        state = state.apply(action)
        decision += 1
    raise RuntimeError(f"recipe_not_reachable:{recipe!r}")


def infoset_payload(depth: int, state: HUNLGameState, observation: dict[str, Any]) -> dict[str, Any]:
    hero = state.hole_cards[state.current_player]
    if hero is None:
        raise RuntimeError("acting_player_hole_absent")
    return {
        "depth_bb": int(depth),
        "acting_player_hole_cards": [int(hero[0]), int(hero[1])],
        "public_state": public_state_payload(state),
        "observation_sha256": observation["observation_sha256"],
        "ordered_actions": observation["ordered_actions"],
    }


def infoset_identity(depth: int, state: HUNLGameState, observation: dict[str, Any]) -> tuple[str, str]:
    payload = infoset_payload(depth, state, observation)
    payload_sha = sha256_obj(payload)
    return payload_sha, payload_sha


def context_key(depth: int, state: HUNLGameState) -> str:
    if state.street not in STREETS or state.current_player not in (0, 1):
        raise RuntimeError("invalid_base_context")
    return f"{depth}bb|{STREET_NAMES[int(state.street)]}|actor{int(state.current_player)}"


def support_row(depth: int, hand_id: int, decision: int, state: HUNLGameState, sample_seconds: float) -> tuple[dict[str, Any], str]:
    observation, mask, table = observe(state)
    identity, payload_sha = infoset_identity(depth, state, observation)
    slots = exact_slots(mask, table)
    row = {
        "schema_version": "v5.fa002.q01.reached_state.v1",
        "training_eligibility": "FORBIDDEN_DIAGNOSTIC_ONLY",
        "state_identity_sha256": identity,
        "identity_payload_sha256": payload_sha,
        "public_replay_identity_sha256": sha256_obj(public_state_payload(state)),
        "recipe": state_recipe(depth, hand_id, decision),
        "depth_bb": depth,
        "street": STREET_NAMES[int(state.street)],
        "acting_player": int(state.current_player),
        "base_context": context_key(depth, state),
        "legal_slot_signature": "".join("1" if float(value) == 1.0 else "0" for value in mask),
        "legal_slots": slots,
        "observation_identity_sha256": observation["observation_sha256"],
        "ordered_nonnull_slot_actions": observation["ordered_actions"],
        "trajectory_component": component_for_hand(depth, hand_id),
        "sampling_seconds": float(sample_seconds),
        "source_opponent_cards_serialized": False,
        "source_unrevealed_deck_serialized": False,
    }
    return row, payload_sha


def replay_determinized_infoset(source: HUNLGameState, seed: int) -> tuple[HUNLGameState, str, str]:
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

    replay = HUNLGameState(make_config(int(source.config.effective_stack)))
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
    if source_slots != replay_slots:
        raise RuntimeError("determinization_slot_invariance_failure")
    if any(action_identity(source_table[slot]) != action_identity(replay_table[slot]) for slot in source_slots):
        raise RuntimeError("determinization_action_invariance_failure")
    hidden_pair_sha = sha256_obj(sorted(opponent_cards))
    determinization_sha = sha256_obj({"opponent_pair_sha256": hidden_pair_sha, "future_deck_sha256": sha256_obj(future), "seed": seed})
    return replay, determinization_sha, hidden_pair_sha


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
            raise RuntimeError("rollout_nonterminal_at_step_ceiling")
    payoff = float(state.payoff(hero))
    if not math.isfinite(payoff):
        raise RuntimeError("nonfinite_rollout_payoff")
    return payoff, steps


def softmax_legal(values: list[float], slots: list[int]) -> list[float]:
    legal = np.asarray([values[slot] / TEMPERATURE for slot in slots], dtype=np.float64)
    legal -= float(np.max(legal))
    weights = np.exp(legal)
    weights /= float(weights.sum())
    output = [0.0] * 9
    for slot, probability in zip(slots, weights.tolist(), strict=True):
        output[slot] = float(probability)
    if any(not math.isfinite(value) or value < 0 for value in output) or abs(sum(output) - 1.0) > 1e-12:
        raise RuntimeError("teacher_probability_invalid")
    if sum(output[slot] for slot in range(9) if slot not in slots) != 0.0:
        raise RuntimeError("illegal_teacher_probability_mass")
    return output


def mc32_quality_row(row_id: int, recipe: dict[str, int]) -> dict[str, Any]:
    started = time.perf_counter()
    source = regenerate_state(recipe)
    depth = int(recipe["depth_bb"])
    observation, mask, table = observe(source, include_features=True)
    slots = exact_slots(mask, table)
    hero = int(source.current_player)
    batch_values: list[list[float]] = []
    batch_distributions: list[list[float]] = []
    determinization_hashes: list[str] = []
    hidden_pair_hashes: list[str] = []
    max_rollout_steps = 0

    for batch in range(BATCHES):
        samples: dict[int, list[float]] = {slot: [] for slot in slots}
        for repeat in range(ROLLOUTS_PER_BATCH):
            det_seed = DETERMINIZATION_SEED + row_id * 100_000_000 + batch * 1_000_000 + repeat * 10_000
            determinized, det_hash, pair_hash = replay_determinized_infoset(source, det_seed)
            determinization_hashes.append(det_hash)
            hidden_pair_hashes.append(pair_hash)
            det_mask, det_table = build_action_table(determinized)
            det_slots = exact_slots(det_mask, det_table)
            if det_slots != slots:
                raise RuntimeError("root_slots_changed_after_determinization")
            for slot in slots:
                if action_identity(det_table[slot]) != action_identity(table[slot]):
                    raise RuntimeError("root_action_changed_after_determinization")
                action = det_table[slot]
                assert action is not None
                policy_seed = ROLLOUT_SEED + row_id * 100_000_000 + batch * 1_000_000 + repeat * 10_000 + slot * 100 + 1
                payoff, steps = rollout(determinized.apply(action), hero, policy_seed)
                samples[slot].append(payoff)
                max_rollout_steps = max(max_rollout_steps, steps)
        values = [0.0] * 9
        for slot in slots:
            if len(samples[slot]) != ROLLOUTS_PER_BATCH:
                raise RuntimeError("mc32_batch_sample_count_failure")
            values[slot] = float(statistics.fmean(samples[slot]))
        batch_values.append(values)
        batch_distributions.append(softmax_legal(values, slots))

    pairwise_l1 = [
        sum(abs(left - right) for left, right in zip(batch_distributions[a], batch_distributions[b], strict=True))
        for a in range(BATCHES)
        for b in range(a + 1, BATCHES)
    ]
    tops = [max(slots, key=lambda slot: (distribution[slot], -slot)) for distribution in batch_distributions]
    top_agreement = Counter(tops).most_common(1)[0][1] / BATCHES
    mean_values = [statistics.fmean(batch[slot] for batch in batch_values) for slot in range(9)]
    teacher = softmax_legal(mean_values, slots)
    if len(set(hidden_pair_hashes)) < 28:
        raise RuntimeError("hidden_pair_diversity_below28")

    features = {
        "observation_card_info": observation["card_info"]["values"],
        "observation_action_info": observation["action_info"]["values"],
        "observation_extra_info": observation["extra_info"]["values"],
    }
    identity_payload = {
        "state_identity_sha256": infoset_identity(depth, source, observation)[0],
        "batch_values": batch_values,
        "teacher_probs9": teacher,
        "determinization_hashes": determinization_hashes,
    }
    row = {
        "schema_version": "v5.fa002.q01.mc32_quality_row.v1",
        "training_eligibility": "FORBIDDEN_DIAGNOSTIC_ONLY",
        "row_id": int(row_id),
        "recipe": recipe,
        "depth_bb": depth,
        "street": STREET_NAMES[int(source.street)],
        "acting_player": hero,
        "base_context": context_key(depth, source),
        "state_identity_sha256": identity_payload["state_identity_sha256"],
        "public_replay_identity_sha256": sha256_obj(public_state_payload(source)),
        "observation_identity_sha256": observation["observation_sha256"],
        **features,
        "legal_mask9": [float(value) for value in mask],
        "ordered_nonnull_slot_actions": observation["ordered_actions"],
        "batch_action_values9": batch_values,
        "batch_teacher_probs9": batch_distributions,
        "teacher_action_values9": mean_values,
        "teacher_probs9": teacher,
        "teacher_probability_sha256": sha256_obj(teacher),
        "temperature_centibb": TEMPERATURE,
        "pairwise_batch_l1": pairwise_l1,
        "batch_distribution_l1_mean": float(statistics.fmean(pairwise_l1)),
        "batch_top_action_agreement_fraction": float(top_agreement),
        "determinizations_total": BATCHES * ROLLOUTS_PER_BATCH,
        "unique_opponent_private_pairs": len(set(hidden_pair_hashes)),
        "determinization_identity_sha256s": determinization_hashes,
        "source_hidden_information_read_count": 0,
        "source_opponent_cards_serialized": False,
        "source_unrevealed_deck_serialized": False,
        "illegal_positive_probability_mass": 0.0,
        "rollouts_per_action_total": BATCHES * ROLLOUTS_PER_BATCH,
        "max_rollout_steps": max_rollout_steps,
        "same_seed_identity_sha256": sha256_obj(identity_payload),
        "row_wall_seconds": float(time.perf_counter() - started),
    }
    return row


def mc32_task(item: tuple[int, dict[str, int]]) -> dict[str, Any]:
    validate_device_contract(EXECUTION_NONCE)
    return mc32_quality_row(item[0], item[1])


def projected_asset_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "v5.fa002.exact_v55_infoset_mc32_teacher_row.v1",
        "row_id": row["state_identity_sha256"],
        "split": "train",
        "depth_bb": row["depth_bb"],
        "street": row["street"],
        "actor": row["acting_player"],
        "state_identity_sha256": row["state_identity_sha256"],
        "public_replay_identity_sha256": row["public_replay_identity_sha256"],
        "observation_card_info": row["observation_card_info"],
        "observation_action_info": row["observation_action_info"],
        "observation_extra_info": row["observation_extra_info"],
        "observation_identity_sha256": row["observation_identity_sha256"],
        "legal_mask9": row["legal_mask9"],
        "ordered_nonnull_slot_actions": row["ordered_nonnull_slot_actions"],
        "teacher_action_values9": row["teacher_action_values9"],
        "teacher_probs9": row["teacher_probs9"],
        "teacher_probability_sha256": row["teacher_probability_sha256"],
        "teacher_source": "EXACT_V55_INFOSET_MC32_ONLY",
        "training_feature_allowlist": ["observation_card_info", "observation_action_info", "observation_extra_info", "legal_mask9"],
        "training_eligibility": "PENDING_FINAL_IMMUTABLE_BUNDLE_AUDIT",
    }


def process_tree_rss_mb() -> float:
    process = psutil.Process()
    total = process.memory_info().rss
    for child in process.children(recursive=True):
        try:
            total += child.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total / (1024.0 * 1024.0)


def write_json_exclusive(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def verify_authority_inputs(implementation_audit_sha256: str) -> dict[str, Any]:
    if sha256_file(EXPECTED_PREREG) != PREREG_SHA256:
        raise RuntimeError("preregistration_hash_mismatch")
    if sha256_file(EXPECTED_PREREG_AUDIT) != PREREG_AUDIT_SHA256:
        raise RuntimeError("preregistration_audit_hash_mismatch")
    if not EXPECTED_IMPLEMENTATION_AUDIT.is_file():
        raise RuntimeError("implementation_audit_absent")
    if sha256_file(EXPECTED_IMPLEMENTATION_AUDIT) != implementation_audit_sha256:
        raise RuntimeError("implementation_audit_hash_mismatch")
    audit = json.loads(EXPECTED_IMPLEMENTATION_AUDIT.read_text(encoding="utf-8"))
    if audit.get("overall") != "PASS" or audit.get("classification") != "PASS / FA002_Q01_IMPLEMENTATION_AUDIT_PASS_ONE_QUALIFICATION_READY_ONLY":
        raise RuntimeError("implementation_audit_classification_mismatch")
    locked = audit.get("implementation", {})
    expected_hashes = {
        "runner_sha256": sha256_file(__file__),
        "launcher_sha256": sha256_file(EXPECTED_LAUNCHER),
        "auditor_sha256": sha256_file(EXPECTED_AUDITOR),
    }
    if any(locked.get(key) != value for key, value in expected_hashes.items()):
        raise RuntimeError("implementation_hash_not_bound_by_audit")
    return {"implementation_audit_sha256": implementation_audit_sha256, **expected_hashes}


def quality_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    slices: dict[str, list[dict[str, Any]]] = {"GLOBAL": rows}
    for depth in DEPTHS:
        slices[f"{depth}bb"] = [row for row in rows if row["depth_bb"] == depth]
    result: dict[str, Any] = {}
    for name, subset in slices.items():
        l1 = [float(row["batch_distribution_l1_mean"]) for row in subset]
        top = [float(row["batch_top_action_agreement_fraction"]) for row in subset]
        metrics = {
            "rows": len(subset),
            "batch_distribution_l1_mean": float(statistics.fmean(l1)),
            "batch_distribution_l1_p95": percentile(l1, 0.95),
            "states_top_action_agreement_ge_0_75_fraction": sum(value >= 0.75 for value in top) / len(top),
        }
        metrics["passes"] = (
            metrics["batch_distribution_l1_mean"] <= QUALITY_L1_MEAN_MAX
            and metrics["batch_distribution_l1_p95"] <= QUALITY_L1_P95_MAX
            and metrics["states_top_action_agreement_ge_0_75_fraction"] >= QUALITY_TOP_AGREEMENT_FRACTION_MIN
        )
        result[name] = metrics
    return result


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for depth in DEPTHS:
        state = new_deal(depth, 0)
        observation, mask, table = observe(state)
        slots = exact_slots(mask, table)
        checks[f"depth_{depth}_initial_actor1"] = state.current_player == 1
        checks[f"depth_{depth}_observation_identity"] = len(observation["observation_sha256"]) == 64
        checks[f"depth_{depth}_legal_slots"] = bool(slots)
        for component in COMPONENTS:
            weights = proposal_weights(component, slots)
            checks[f"depth_{depth}_{component}_weights"] = len(weights) == len(slots) and all(value > 0 for value in weights)
    recipe = state_recipe(200, 7, 0)
    source = regenerate_state(recipe)
    observation, _, _ = observe(source)
    det_a, hash_a, pair_a = replay_determinized_infoset(source, DETERMINIZATION_SEED)
    det_b, hash_b, pair_b = replay_determinized_infoset(source, DETERMINIZATION_SEED + 1)
    checks["determinization_fresh"] = hash_a != hash_b and pair_a != pair_b
    checks["determinization_observation_invariant_a"] = observe(det_a)[0]["observation_sha256"] == observation["observation_sha256"]
    checks["determinization_observation_invariant_b"] = observe(det_b)[0]["observation_sha256"] == observation["observation_sha256"]
    row_a = mc32_quality_row(900_000_001, recipe)
    row_b = mc32_quality_row(900_000_001, recipe)
    checks["mc32_repeat_exact"] = row_a["same_seed_identity_sha256"] == row_b["same_seed_identity_sha256"]
    checks["mc32_4x8"] = row_a["determinizations_total"] == 32 and row_a["rollouts_per_action_total"] == 32
    checks["mc32_hidden_diversity"] = row_a["unique_opponent_private_pairs"] >= 28
    checks["mc32_illegal_mass_zero"] = row_a["illegal_positive_probability_mass"] == 0.0
    checks["mc32_probs_valid"] = abs(sum(row_a["teacher_probs9"]) - 1.0) <= 1e-12
    checks["projected_payload_schema"] = projected_asset_payload(row_a)["schema_version"] == "v5.fa002.exact_v55_infoset_mc32_teacher_row.v1"
    if not all(checks.values()):
        raise RuntimeError(f"self_test_failure:{[key for key, value in checks.items() if not value]}")
    return {"checks": checks, "pass_count": sum(checks.values()), "check_count": len(checks)}


def run_qualification(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    contract = validate_device_contract(EXECUTION_NONCE)
    paths = {
        "prereg": canonical_path(args.preregistration),
        "prereg_audit": canonical_path(args.preregistration_audit),
        "implementation_audit": canonical_path(args.implementation_audit),
        "output": canonical_path(args.output),
    }
    expected = {
        "prereg": canonical_path(EXPECTED_PREREG),
        "prereg_audit": canonical_path(EXPECTED_PREREG_AUDIT),
        "implementation_audit": canonical_path(EXPECTED_IMPLEMENTATION_AUDIT),
        "output": canonical_path(EXPECTED_OUTPUT),
    }
    if paths != expected or not all(Path(value).is_absolute() for value in (args.preregistration, args.preregistration_audit, args.implementation_audit, args.output)):
        raise RuntimeError("registered_absolute_path_identity_mismatch")
    if paths["output"].exists():
        raise RuntimeError("immutable_output_root_exists")
    implementation = verify_authority_inputs(args.implementation_audit_sha256)

    paths["output"].mkdir(parents=False, exist_ok=False)
    invocation = {
        "schema_version": "v5.fa002.q01.invocation.v1",
        "program_id": PROGRAM_ID,
        "qualification_id": QUALIFICATION_ID,
        "started_at_epoch": time.time(),
        "contract": contract,
        "implementation": implementation,
        "attempt": 1,
    }
    write_json_exclusive(paths["output"] / "invocation.json", invocation)

    reached_path = paths["output"] / "reached_states.jsonl.gz"
    quality_path = paths["output"] / "quality_rows.jsonl.gz"
    metrics_path = paths["output"] / "metrics.json"
    result_path = paths["output"] / "result.json"
    seen: dict[str, str] = {}
    context_counts: Counter[str] = Counter()
    depth_counts: Counter[int] = Counter()
    started_hands: Counter[int] = Counter()
    sample_times: dict[str, list[float]] = defaultdict(list)
    selection_heaps: dict[str, list[tuple[int, str, dict[str, int]]]] = defaultdict(list)
    peak_rss_mb = process_tree_rss_mb()

    with gzip.open(reached_path, "xt", encoding="utf-8", newline="\n", compresslevel=6) as reached_stream:
        for depth in DEPTHS:
            for hand_id in range(MAX_STARTED_HANDS_PER_DEPTH):
                if depth_counts[depth] >= ACCEPTED_PER_DEPTH:
                    break
                if time.perf_counter() - started > WALL_SECONDS_MAX:
                    raise RuntimeError("qualification_wall_bound_during_reachability")
                state = new_deal(depth, hand_id)
                component = component_for_hand(depth, hand_id)
                action_rng = random.Random(ACTION_SEED + depth * 1_000_000 + hand_id)
                started_hands[depth] += 1
                decision = 0
                while not state.is_terminal() and decision < MAX_STEPS and depth_counts[depth] < ACCEPTED_PER_DEPTH:
                    sample_started = time.perf_counter()
                    row, payload_sha = support_row(depth, hand_id, decision, state, 0.0)
                    elapsed = time.perf_counter() - sample_started
                    identity = row["state_identity_sha256"]
                    prior = seen.get(identity)
                    if prior is not None and prior != payload_sha:
                        raise RuntimeError("sha256_identity_collision_with_unequal_payload")
                    if prior is None:
                        seen[identity] = payload_sha
                        row["sampling_seconds"] = elapsed
                        reached_stream.write(canonical_json(row) + "\n")
                        depth_counts[depth] += 1
                        context = row["base_context"]
                        context_counts[context] += 1
                        sample_times[context].append(elapsed)
                        item = (-int(identity, 16), identity, row["recipe"])
                        heap = selection_heaps[context]
                        if len(heap) < QUALITY_PER_CONTEXT:
                            heapq.heappush(heap, item)
                        elif item[0] > heap[0][0]:
                            heapq.heapreplace(heap, item)
                    observation, mask, table = observe(state)
                    slots = exact_slots(mask, table)
                    slot = weighted_choice(slots, proposal_weights(component, slots), action_rng)
                    action = table[slot]
                    assert action is not None
                    state = state.apply(action)
                    decision += 1
                if decision >= MAX_STEPS and not state.is_terminal():
                    raise RuntimeError("trajectory_nonterminal_at_step_ceiling")
                if hand_id % 100 == 0:
                    peak_rss_mb = max(peak_rss_mb, process_tree_rss_mb())
                    if peak_rss_mb > RSS_MB_MAX:
                        raise RuntimeError("qualification_rss_bound_during_reachability")
            if depth_counts[depth] != ACCEPTED_PER_DEPTH:
                raise RuntimeError(f"reachability_depth_shortfall:{depth}:{depth_counts[depth]}")

    expected_contexts = [f"{depth}bb|{street.name}|actor{actor}" for depth in DEPTHS for street in STREETS for actor in (0, 1)]
    if len(seen) != ACCEPTED_TOTAL or sum(depth_counts.values()) != ACCEPTED_TOTAL:
        raise RuntimeError("reachability_total_count_failure")
    if any(context_counts[context] < MIN_PER_CONTEXT for context in expected_contexts):
        raise RuntimeError("base_context_minimum_shortfall")
    if any(len(selection_heaps[context]) != QUALITY_PER_CONTEXT for context in expected_contexts):
        raise RuntimeError("quality_selection_shortfall")

    selected: list[tuple[str, str, dict[str, int]]] = []
    for context in expected_contexts:
        entries = sorted(((identity, recipe) for _, identity, recipe in selection_heaps[context]), key=lambda item: item[0])
        selected.extend((context, identity, recipe) for identity, recipe in entries)
    if len(selected) != QUALITY_TOTAL:
        raise RuntimeError("quality_selection_total_failure")

    tasks = [(row_id, recipe) for row_id, (_, _, recipe) in enumerate(selected)]
    quality_rows: list[dict[str, Any]] = []
    uncompressed_bytes: list[int] = []
    gzip_bytes: list[int] = []
    serialization_seconds: list[float] = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=WORKERS) as executor:
        for row in executor.map(mc32_task, tasks, chunksize=1):
            payload = projected_asset_payload(row)
            encode_started = time.perf_counter()
            encoded = canonical_json(payload).encode("utf-8")
            compressed = gzip.compress(encoded, compresslevel=6, mtime=0)
            serialization_elapsed = time.perf_counter() - encode_started
            row["asset_projection_uncompressed_bytes"] = len(encoded)
            row["asset_projection_gzip_bytes"] = len(compressed)
            row["asset_projection_serialization_gzip_seconds"] = serialization_elapsed
            quality_rows.append(row)
            serialization_seconds.append(serialization_elapsed)
            uncompressed_bytes.append(len(encoded))
            gzip_bytes.append(len(compressed))
            peak_rss_mb = max(peak_rss_mb, process_tree_rss_mb())
            if time.perf_counter() - started > WALL_SECONDS_MAX:
                raise RuntimeError("qualification_wall_bound_during_mc32")
            if peak_rss_mb > RSS_MB_MAX:
                raise RuntimeError("qualification_rss_bound_during_mc32")

    if len(quality_rows) != QUALITY_TOTAL:
        raise RuntimeError("quality_row_count_failure")
    if Counter(row["base_context"] for row in quality_rows) != Counter({context: QUALITY_PER_CONTEXT for context in expected_contexts}):
        raise RuntimeError("quality_context_balance_failure")

    repeat_tasks: list[tuple[int, dict[str, int]]] = []
    originals: dict[int, str] = {}
    for context in expected_contexts:
        candidates = sorted((row for row in quality_rows if row["base_context"] == context), key=lambda row: row["state_identity_sha256"])
        for row in candidates[:REPEATS_PER_CONTEXT]:
            repeat_tasks.append((int(row["row_id"]), row["recipe"]))
            originals[int(row["row_id"])] = row["same_seed_identity_sha256"]
    repeat_failures = 0
    repeat_records: list[dict[str, Any]] = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=WORKERS) as executor:
        for row in executor.map(mc32_task, repeat_tasks, chunksize=1):
            original_sha = originals[int(row["row_id"])]
            repeated_sha = row["same_seed_identity_sha256"]
            matches = original_sha == repeated_sha
            repeat_records.append({
                "row_id": int(row["row_id"]),
                "base_context": row["base_context"],
                "original_same_seed_identity_sha256": original_sha,
                "repeated_same_seed_identity_sha256": repeated_sha,
                "matches": matches,
            })
            if not matches:
                repeat_failures += 1
            peak_rss_mb = max(peak_rss_mb, process_tree_rss_mb())
    if len(repeat_tasks) != REPEATS_TOTAL or repeat_failures != 0:
        raise RuntimeError("same_seed_repeat_failure")

    with gzip.open(quality_path, "xt", encoding="utf-8", newline="\n", compresslevel=6) as quality_stream:
        for row in quality_rows:
            quality_stream.write(canonical_json(row) + "\n")

    quality = quality_summary(quality_rows)
    context_sampling_p99 = {context: percentile(sample_times[context], 0.99) for context in expected_contexts}
    depth_mc32_p99 = {
        f"{depth}bb": percentile((row["row_wall_seconds"] for row in quality_rows if row["depth_bb"] == depth), 0.99)
        for depth in DEPTHS
    }
    serialization_p99 = percentile(serialization_seconds, 0.99)
    projected_seconds = 1.25 * 20_000_000 / WORKERS * (
        max(context_sampling_p99.values()) + max(depth_mc32_p99.values()) + serialization_p99
    )
    projected_hours = projected_seconds / 3600.0
    uncompressed_p99 = percentile(uncompressed_bytes, 0.99)
    gzip_p99 = percentile(gzip_bytes, 0.99)
    projected_compressed_bytes = int(20_000_000 * gzip_p99)
    elapsed = time.perf_counter() - started
    output_bytes_before_metrics = sum(path.stat().st_size for path in paths["output"].iterdir() if path.is_file())

    gates = {
        "reached_states_exact_120000": len(seen) == ACCEPTED_TOTAL,
        "depth_states_exact_40000_each": all(depth_counts[depth] == ACCEPTED_PER_DEPTH for depth in DEPTHS),
        "all24_contexts_min256": all(context_counts[context] >= MIN_PER_CONTEXT for context in expected_contexts),
        "quality_rows_exact_6144": len(quality_rows) == QUALITY_TOTAL,
        "quality_contexts_exact256": all(sum(row["base_context"] == context for row in quality_rows) == QUALITY_PER_CONTEXT for context in expected_contexts),
        "same_seed_repeats_exact768_zero_failures": len(repeat_tasks) == REPEATS_TOTAL and repeat_failures == 0,
        "quality_global_and_each_depth": all(metrics["passes"] for metrics in quality.values()),
        "hidden_pair_diversity_all_rows": all(row["unique_opponent_private_pairs"] >= 28 for row in quality_rows),
        "information_leakage_zero": all(row["source_hidden_information_read_count"] == 0 and not row["source_opponent_cards_serialized"] and not row["source_unrevealed_deck_serialized"] for row in quality_rows),
        "illegal_probability_mass_zero": all(row["illegal_positive_probability_mass"] == 0.0 for row in quality_rows),
        "all_rollouts_terminal_within128": all(row["max_rollout_steps"] <= MAX_STEPS for row in quality_rows),
        "projected_wall_hours_le168": projected_hours <= PROJECTED_WALL_HOURS_MAX,
        "projected_compressed_bytes_le100gb": projected_compressed_bytes <= PROJECTED_COMPRESSED_BYTES_MAX,
        "uncompressed_row_p99_le8192": uncompressed_p99 <= UNCOMPRESSED_ROW_P99_MAX,
        "gzip_row_p99_le5000": gzip_p99 <= GZIP_ROW_P99_MAX,
        "qualification_wall_seconds_le21600": elapsed <= WALL_SECONDS_MAX,
        "process_tree_peak_rss_mb_le4096": peak_rss_mb <= RSS_MB_MAX,
        "output_bytes_le10gb": output_bytes_before_metrics <= OUTPUT_BYTES_MAX,
        "torch_absent": "torch" not in sys.modules,
    }
    metrics = {
        "schema_version": "v5.fa002.q01.metrics.v1",
        "program_id": PROGRAM_ID,
        "qualification_id": QUALIFICATION_ID,
        "training_eligibility": "FORBIDDEN_DIAGNOSTIC_ONLY",
        "started_hands_by_depth": {str(depth): started_hands[depth] for depth in DEPTHS},
        "accepted_states_by_depth": {str(depth): depth_counts[depth] for depth in DEPTHS},
        "base_context_counts": dict(sorted(context_counts.items())),
        "quality": quality,
        "same_seed_repeats": len(repeat_tasks),
        "same_seed_failures": repeat_failures,
        "same_seed_repeat_records": repeat_records,
        "resource": {
            "context_sampling_p99_seconds": context_sampling_p99,
            "depth_mc32_p99_seconds": depth_mc32_p99,
            "serialization_gzip_p99_seconds": serialization_p99,
            "projected_eight_worker_wall_seconds": projected_seconds,
            "projected_eight_worker_wall_hours": projected_hours,
            "uncompressed_row_p99_bytes": uncompressed_p99,
            "gzip_row_p99_bytes": gzip_p99,
            "projected_compressed_bytes": projected_compressed_bytes,
            "qualification_wall_seconds": elapsed,
            "process_tree_peak_rss_mb": peak_rss_mb,
            "output_bytes_before_metrics": output_bytes_before_metrics,
        },
        "gates": gates,
    }
    write_json_exclusive(metrics_path, metrics)
    bundle = {
        "invocation.json": {"bytes": (paths["output"] / "invocation.json").stat().st_size, "sha256": sha256_file(paths["output"] / "invocation.json")},
        "reached_states.jsonl.gz": {"bytes": reached_path.stat().st_size, "sha256": sha256_file(reached_path)},
        "quality_rows.jsonl.gz": {"bytes": quality_path.stat().st_size, "sha256": sha256_file(quality_path)},
        "metrics.json": {"bytes": metrics_path.stat().st_size, "sha256": sha256_file(metrics_path)},
    }
    result = {
        "schema_version": "v5.fa002.q01.result.v1",
        "completed_at_epoch": time.time(),
        "program_id": PROGRAM_ID,
        "qualification_id": QUALIFICATION_ID,
        "verdict": "PASS" if all(gates.values()) else "NONPASS",
        "classification": "FA002_Q01_PASS_COMBINED_REACHABILITY_MC32_QUALITY_RESOURCE" if all(gates.values()) else "FA002_Q01_NONPASS_COMBINED_REACHABILITY_MC32_QUALITY_RESOURCE",
        "training_eligibility": "FORBIDDEN_DIAGNOSTIC_ONLY",
        "contract": contract,
        "implementation": implementation,
        "counts": {
            "accepted_states": len(seen),
            "quality_rows": len(quality_rows),
            "same_seed_repeats": len(repeat_tasks),
            "same_seed_failures": repeat_failures,
            "teacher_rows": 0,
            "training_hands": 0,
            "checkpoints": 0,
            "official_hands": 0,
        },
        "gates": gates,
        "bundle": bundle,
        "next_if_pass": "SEPARATE_ASSET_GENERATOR_IMPLEMENTATION_AND_INDEPENDENT_IMPLEMENTATION_AUDIT_ONLY",
        "next_if_nonpass": "FA002_QUALIFICATION_SCIENTIFIC_NONPASS_RETURN_TO_ROUTE_RANKING_NO_CORRECTED_IDENTITY",
        "strength": "L0",
    }
    write_json_exclusive(result_path, result)
    print(canonical_json({"verdict": result["verdict"], "result": str(result_path), "result_sha256": sha256_file(result_path)}))
    return 0 if result["verdict"] == "PASS" else 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("ContractProbe", "Qualification"))
    parser.add_argument("--expected-nonce", required=True)
    parser.add_argument("--preregistration")
    parser.add_argument("--preregistration-audit")
    parser.add_argument("--implementation-audit")
    parser.add_argument("--implementation-audit-sha256")
    parser.add_argument("--output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mode == "ContractProbe":
        if any((args.preregistration, args.preregistration_audit, args.implementation_audit, args.implementation_audit_sha256, args.output)):
            raise RuntimeError("contract_probe_path_arguments_forbidden")
        return contract_probe(args.expected_nonce)
    if args.expected_nonce != EXECUTION_NONCE:
        raise RuntimeError("qualification_execution_nonce_mismatch")
    if not all((args.preregistration, args.preregistration_audit, args.implementation_audit, args.implementation_audit_sha256, args.output)):
        raise RuntimeError("qualification_arguments_incomplete")
    return run_qualification(args)


if __name__ == "__main__":
    raise SystemExit(main())
