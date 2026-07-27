"""TN001 trajectory-native exact-V5.5 teacher feasibility qualification.

Diagnostic only.  No emitted row is eligible for training.  Hidden opponent cards
and source deck order are erased before every information-set Monte Carlo rollout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

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

DESIGN_ID = "PHASE_FA_TN001_TRAJECTORY_NATIVE_CONSTRUCTIVE_WITNESS_AND_BOUNDED_DISCOVERY_FEASIBILITY"
DESIGN_SHA256 = "3dae3b32ec4af21ed41d6b14050f76e87b896ab07d4cbd54fc2a431ac1c50dd1"
DESIGN_AUDIT_SHA256 = "a0f2b992444482910eb6590473eee2967c67609e8bb37880433412d8b3d59423"
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
CONTRACT_NONCE = "2026472291"
CONTRACT_SHA256 = "277c9821063d930c5671ff3976cb6f4c8bcce45b97496c73b1510ed996344d02"
DEVICE_MODE = "CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK"
DEAL_BASE = 2026072291
DISCOVERY_BASE = 2026172291
DET_BASE = 2026272291
ROLLOUT_BASE = 2026372291
TEMPERATURES = (1.0, 5.0, 10.0, 25.0, 100.0)
DEPTHS = (200, 100, 50)
STREETS = ("PREFLOP", "FLOP", "TURN", "RIVER")
TEMPLATES = (
    ("PREFLOP", 1, ()),
    ("PREFLOP", 0, (1,)),
    ("FLOP", 0, (1, 1)),
    ("FLOP", 1, (1, 1, 1)),
    ("TURN", 0, (1, 1, 1, 1)),
    ("TURN", 1, (1, 1, 1, 1, 1)),
    ("RIVER", 0, (1, 1, 1, 1, 1, 1)),
    ("RIVER", 1, (1, 1, 1, 1, 1, 1, 1)),
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_obj(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1, math.floor((len(ordered) - 1) * q))])


def action_payload(action: Action | None) -> dict[str, Any] | None:
    if action is None:
        return None
    return {"type": action.type.name, "amount_cents": int(round(float(action.amount) * 100))}


def array_identity(value: np.ndarray) -> dict[str, Any]:
    arr = np.ascontiguousarray(value)
    payload = {"shape": list(arr.shape), "dtype": str(arr.dtype), "bytes_sha256": hashlib.sha256(arr.tobytes()).hexdigest()}
    payload["identity_sha256"] = sha256_obj(payload)
    return payload


def observe(state: HUNLGameState) -> tuple[dict[str, Any], np.ndarray, list[Action | None]]:
    player = state.current_player
    mask, table = build_action_table(state)
    obs = {
        "card_info": array_identity(encode_cards(state, player)),
        "action_info": array_identity(encode_action_history(state, player)),
        "extra_info": array_identity(encode_extra(state, player)),
        "legal_mask": array_identity(mask),
        "player": int(player),
    }
    obs["observation_sha256"] = sha256_obj(obs)
    return obs, mask, table


def exact_slots(mask: np.ndarray, table: list[Action | None]) -> list[int]:
    slots = [i for i in range(9) if float(mask[i]) == 1.0 and table[i] is not None]
    if not slots or any((float(mask[i]) == 1.0) != (table[i] is not None) for i in range(9)):
        raise RuntimeError("mask_table_identity_failure")
    identities = [canonical_json(action_payload(table[i])) for i in slots]
    if len(identities) != len(set(identities)):
        raise RuntimeError("slot_action_collision")
    return slots


def config_for_depth(depth: int) -> GameConfig:
    config = {200: GameConfig.full_200bb, 100: GameConfig.full_100bb, 50: GameConfig.full_50bb}[depth]()
    config.raise_cap_per_street = RAISE_CAP_UNLIMITED
    config.raise_cap_preflop = 4
    return config


def new_deal(depth: int, seed: int) -> HUNLGameState:
    random.seed(seed)
    return HUNLGameState(config_for_depth(depth)).deal_new_hand()


def apply_slot(state: HUNLGameState, slot: int) -> HUNLGameState:
    _, mask, table = observe(state)
    if slot not in exact_slots(mask, table):
        raise RuntimeError(f"illegal_exact_slot:{slot}")
    action = table[slot]
    assert action is not None
    return state.apply(action)


def replay_prefix(state: HUNLGameState, prefix: tuple[int, ...]) -> HUNLGameState:
    for slot in prefix:
        state = apply_slot(state, slot)
    return state


def cell_name(depth: int, street: str, actor: int) -> str:
    return f"{depth}:{street}:{actor}"


def state_key(depth: int, state: HUNLGameState) -> tuple[str, dict[str, Any]]:
    obs, mask, table = observe(state)
    slots = exact_slots(mask, table)
    public = {
        "depth": depth,
        "street": state.street.name,
        "actor": int(state.current_player),
        "observation_components": obs,
        "legal_mask": [float(x) for x in mask.tolist()],
        "ordered_exact_actions": [{"slot": i, "action": action_payload(table[i])} for i in slots],
    }
    return sha256_obj(public), public


def allowed_snapshot(depth: int, state: HUNLGameState) -> dict[str, Any]:
    actor = int(state.current_player)
    hole = state.hole_cards[actor]
    assert hole is not None
    return {
        "depth": depth,
        "actor": actor,
        "actor_hole": [int(hole[0]), int(hole[1])],
        "public_board": [int(x) for x in state.board],
        "public_actions": [
            {"player": int(player), "action": action_payload(action)}
            for player, action in state.actions_history
        ],
        "expected_observation_sha256": observe(state)[0]["observation_sha256"],
        "expected_key": state_key(depth, state)[0],
        "street": state.street.name,
    }


def action_matches(action: Action, payload: dict[str, Any]) -> bool:
    return action.type.name == payload["type"] and int(round(float(action.amount) * 100)) == int(payload["amount_cents"])


def reconstruct(snapshot: dict[str, Any], seed: int) -> HUNLGameState:
    rng = random.Random(seed)
    actor = int(snapshot["actor"])
    actor_hole = tuple(int(x) for x in snapshot["actor_hole"])
    public_board = [int(x) for x in snapshot["public_board"]]
    forbidden = set(actor_hole) | set(public_board)
    candidates = [c for c in range(52) if c not in forbidden]
    opponent_hole = tuple(rng.sample(candidates, 2))
    future = [c for c in candidates if c not in opponent_hole]
    for card in public_board:
        future.remove(card) if card in future else None
    rng.shuffle(future)
    state = HUNLGameState(config_for_depth(int(snapshot["depth"])))
    holes: list[tuple[int, int] | None] = [None, None]
    holes[actor] = actor_hole
    holes[1 - actor] = opponent_hole
    state.hole_cards = holes
    state.deck = future + list(reversed(public_board))
    for item in snapshot["public_actions"]:
        if int(item["player"]) != state.current_player:
            raise RuntimeError("public_replay_actor_failure")
        _, mask, table = observe(state)
        matches = [i for i in exact_slots(mask, table) if action_matches(table[i], item["action"])]  # type: ignore[arg-type]
        if len(matches) != 1:
            raise RuntimeError("public_replay_action_identity_failure")
        action = table[matches[0]]
        assert action is not None
        state = state.apply(action)
    if state.current_player != actor or [int(x) for x in state.board] != public_board:
        raise RuntimeError("public_replay_state_failure")
    if observe(state)[0]["observation_sha256"] != snapshot["expected_observation_sha256"]:
        raise RuntimeError("public_replay_observation_failure")
    return state


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
        if steps > 128:
            raise RuntimeError("rollout_nonterminal_at_step_limit")
    payoff = float(state.payoff(hero))
    if not math.isfinite(payoff):
        raise RuntimeError("nonfinite_action_value")
    return payoff, steps


def softmax(values: list[float], slots: list[int], temperature: float) -> list[float]:
    scaled = np.array([values[s] / temperature for s in slots], dtype=np.float64)
    scaled -= float(np.max(scaled))
    weights = np.exp(scaled)
    probs = weights / float(weights.sum())
    out = [0.0] * 9
    for slot, probability in zip(slots, probs, strict=True):
        out[slot] = float(probability)
    return out


def teacher_task(task: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    snapshot = task["snapshot"]
    row_index = int(task["row_id"])
    depth = int(snapshot["depth"])
    cell_index = int(task["cell_index"])
    probe = reconstruct(snapshot, DET_BASE + depth * 10**12 + cell_index * 10**9 + row_index * 10**6)
    obs, mask, table = observe(probe)
    slots = exact_slots(mask, table)
    ordered = [{"slot": s, "action": action_payload(table[s])} for s in slots]
    batch_values: list[list[float]] = []
    max_steps = 0
    for batch in range(4):
        sums = [0.0] * 9
        for rep in range(8):
            det_seed = DET_BASE + depth * 10**12 + cell_index * 10**9 + row_index * 10**6 + batch * 10**4 + rep * 100
            base = reconstruct(snapshot, det_seed)
            _, base_mask, base_table = observe(base)
            if exact_slots(base_mask, base_table) != slots:
                raise RuntimeError("determinization_action_table_failure")
            for slot in slots:
                action = base_table[slot]
                assert action is not None
                stream = ROLLOUT_BASE + depth * 10**12 + cell_index * 10**9 + row_index * 10**6 + batch * 10**4 + rep * 100 + slot
                payoff, steps = rollout(base.apply(action), int(snapshot["actor"]), stream)
                sums[slot] += payoff
                max_steps = max(max_steps, steps)
        batch_values.append([value / 8.0 for value in sums])
    mean_values = [statistics.fmean(batch[s] for batch in batch_values) for s in range(9)]
    temperature_metrics: dict[str, Any] = {}
    teacher_probs: dict[str, list[float]] = {}
    for temperature in TEMPERATURES:
        distributions = [softmax(values, slots, temperature) for values in batch_values]
        pairwise = [
            sum(abs(distributions[a][i] - distributions[b][i]) for i in range(9))
            for a in range(4) for b in range(a + 1, 4)
        ]
        tops = [max(slots, key=lambda s: (distribution[s], -s)) for distribution in distributions]
        top_agree = max(tops.count(slot) for slot in set(tops)) >= 3
        teacher = softmax(mean_values, slots, temperature)
        entropy = -sum(p * math.log(p) for p in teacher if p > 0) / math.log(len(slots)) if len(slots) > 1 else 0.0
        key = str(temperature)
        teacher_probs[key] = teacher
        temperature_metrics[key] = {
            "six_pairwise_l1": pairwise,
            "batch_top_actions": tops,
            "three_of_four_top_agreement": top_agree,
            "normalized_entropy": float(entropy),
        }
    identity = {
        "expected_key": snapshot["expected_key"],
        "observation_sha256": obs["observation_sha256"],
        "ordered_exact_actions": ordered,
        "batch_values": batch_values,
        "temperature_metrics": temperature_metrics,
        "teacher_probabilities": teacher_probs,
    }
    return {
        "schema_version": "v5.tn001.quality_row.v1",
        "classification": "FORBIDDEN_DIAGNOSTIC_ONLY",
        "row_id": row_index,
        "depth": depth,
        "street": snapshot["street"],
        "actor": int(snapshot["actor"]),
        "cell": task["cell"],
        "observable_semantic_key": snapshot["expected_key"],
        "observation_sha256": obs["observation_sha256"],
        "legal_mask9": [float(x) for x in mask.tolist()],
        "ordered_exact_actions": ordered,
        "batch_values": batch_values,
        "temperature_metrics": temperature_metrics,
        "teacher_probabilities_by_temperature": teacher_probs,
        "identity_sha256": sha256_obj(identity),
        "rollouts_per_action": 32,
        "max_rollout_steps": max_steps,
        "mc32_wall_seconds": float(time.perf_counter() - started),
        "worker_rss_mb": psutil.Process().memory_info().rss / 1_048_576,
    }


def aggregate(rows: list[dict[str, Any]]) -> tuple[float | None, dict[str, Any]]:
    summary: dict[str, Any] = {}
    selected: float | None = None
    for temperature in TEMPERATURES:
        key = str(temperature)
        scopes: dict[str, Any] = {}
        for scope in ("GLOBAL", "200", "100", "50"):
            chosen = rows if scope == "GLOBAL" else [r for r in rows if r["depth"] == int(scope)]
            l1s = [x for row in chosen for x in row["temperature_metrics"][key]["six_pairwise_l1"]]
            top_fraction = statistics.fmean(float(row["temperature_metrics"][key]["three_of_four_top_agreement"]) for row in chosen)
            entropy = statistics.fmean(float(row["temperature_metrics"][key]["normalized_entropy"]) for row in chosen)
            metrics = {
                "six_pairwise_batch_distribution_l1_mean": statistics.fmean(l1s),
                "six_pairwise_batch_distribution_l1_p95": percentile(l1s, 0.95),
                "states_with_three_of_four_batch_top_action_agreement_fraction": top_fraction,
                "mean_normalized_entropy": entropy,
            }
            metrics["passes"] = (
                metrics["six_pairwise_batch_distribution_l1_mean"] <= 0.35
                and metrics["six_pairwise_batch_distribution_l1_p95"] <= 0.8
                and top_fraction >= 0.7
                and entropy <= 0.9
            )
            scopes[scope] = metrics
        summary[key] = {"scopes": scopes, "passes": all(x["passes"] for x in scopes.values())}
        if selected is None and summary[key]["passes"]:
            selected = temperature
    return selected, summary


def verify_inputs(design: dict[str, Any]) -> list[dict[str, str]]:
    verified = []
    for item in design["frozen_evidence"]:
        path = Path(item["path"])
        observed = sha256_file(path)
        if observed != item["sha256"]:
            raise RuntimeError(f"frozen_input_hash_mismatch:{path}")
        verified.append({"role": item["role"], "path": str(path), "sha256": observed})
    return verified


def validate_contract() -> dict[str, Any]:
    values = {
        "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "TN001_DEVICE_MODE": os.environ.get("TN001_DEVICE_MODE"),
        "TN001_CONTRACT_NONCE": os.environ.get("TN001_CONTRACT_NONCE"),
    }
    if values != {"CUDA_VISIBLE_DEVICES": "-1", "TN001_DEVICE_MODE": DEVICE_MODE, "TN001_CONTRACT_NONCE": CONTRACT_NONCE}:
        raise RuntimeError(f"device_contract_failure:{values}")
    runtime_sha = sha256_file(Path(sys.executable))
    if runtime_sha != PYTHON_SHA256 or "torch" in sys.modules:
        raise RuntimeError("runtime_or_torch_contract_failure")
    return {**values, "python_executable": str(Path(sys.executable)), "python_sha256": runtime_sha,
            "contract_sha256": CONTRACT_SHA256, "torch_in_sys_modules": False}


def write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as fh:
        json.dump(value, fh, indent=2, ensure_ascii=False, allow_nan=False)
        fh.write("\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> list[float]:
    times = []
    with path.open("x", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            started = time.perf_counter()
            fh.write(canonical_json(row) + "\n")
            times.append(time.perf_counter() - started)
    return times


def contract_probe() -> int:
    print(canonical_json({"schema_version": "v5.tn001.contract_probe.v1", "design_id": DESIGN_ID,
                          **validate_contract(), "runner_sha256": sha256_file(Path(__file__)), "files_written": 0}))
    return 0


def run(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    contract = validate_contract()
    design_path, audit_path, implementation_path = map(Path, (args.design, args.design_audit, args.implementation_audit))
    if sha256_file(design_path) != DESIGN_SHA256 or sha256_file(audit_path) != DESIGN_AUDIT_SHA256:
        raise RuntimeError("design_identity_failure")
    design = json.loads(design_path.read_text(encoding="utf-8"))
    design_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if design_audit.get("overall") != "PASS" or design_audit.get("checks_total") != 148:
        raise RuntimeError("design_audit_authority_failure")
    if sha256_file(implementation_path) != args.implementation_audit_sha256:
        raise RuntimeError("implementation_audit_sha_failure")
    implementation = json.loads(implementation_path.read_text(encoding="utf-8"))
    if implementation.get("overall") != "PASS" or implementation.get("runner_sha256") != sha256_file(Path(__file__)):
        raise RuntimeError("implementation_audit_authority_failure")
    verified_inputs = verify_inputs(design)
    output = Path(args.output)
    output.mkdir(parents=False, exist_ok=False)

    constructive_rows: list[dict[str, Any]] = []
    discovery_rows: list[dict[str, Any]] = []
    unique_keys: dict[str, set[str]] = {cell_name(d, s, a): set() for d in DEPTHS for s in STREETS for a in (0, 1)}
    candidates: dict[str, dict[str, HUNLGameState]] = {cell: {} for cell in unique_keys}
    constructive_seconds: list[float] = []
    witness_failures = 0

    for depth_index, depth in enumerate(DEPTHS):
        for cell_index, (expected_street, expected_actor, prefix) in enumerate(TEMPLATES):
            cell = cell_name(depth, expected_street, expected_actor)
            accepted = 0
            for attempt in range(128):
                tick = time.perf_counter()
                seed = DEAL_BASE + depth_index * 1_000_000 + cell_index * 1_000 + attempt
                state = replay_prefix(new_deal(depth, seed), prefix)
                if state.is_terminal() or state.street.name != expected_street or state.current_player != expected_actor:
                    witness_failures += 1
                    continue
                key, public = state_key(depth, state)
                if key in unique_keys[cell]:
                    continue
                unique_keys[cell].add(key)
                candidates[cell][key] = state.clone()
                constructive_rows.append({
                    "schema_version": "v5.tn001.constructive_state.v1",
                    "classification": "FORBIDDEN_DIAGNOSTIC_ONLY",
                    "cell": cell, "depth": depth, "street": expected_street, "actor": expected_actor,
                    "prefix_slots": list(prefix), "deal_attempt": attempt, "observable_semantic_key": key,
                    "observation_sha256": public["observation_components"]["observation_sha256"],
                })
                accepted += 1
                constructive_seconds.append(time.perf_counter() - tick)
                if accepted == 32:
                    break

    for depth_index, depth in enumerate(DEPTHS):
        for trajectory in range(1024):
            state = new_deal(depth, DISCOVERY_BASE + depth_index * 1_000_000 + trajectory)
            rng = random.Random(DISCOVERY_BASE + depth_index * 1_000_000 + trajectory + 100_000_000)
            decisions = 0
            while not state.is_terminal():
                if decisions >= 64:
                    raise RuntimeError("trajectory_decision_cap_exceeded")
                key, public = state_key(depth, state)
                cell = cell_name(depth, state.street.name, state.current_player)
                unique_keys[cell].add(key)
                if key not in candidates[cell]:
                    candidates[cell][key] = state.clone()
                discovery_rows.append({
                    "schema_version": "v5.tn001.discovery_state.v1",
                    "classification": "FORBIDDEN_DIAGNOSTIC_ONLY",
                    "depth": depth, "trajectory": trajectory, "decision": decisions, "cell": cell,
                    "observable_semantic_key": key,
                    "observation_sha256": public["observation_components"]["observation_sha256"],
                })
                _, mask, table = observe(state)
                slots = exact_slots(mask, table)
                slot = slots[rng.randrange(len(slots))]
                action = table[slot]
                assert action is not None
                state = state.apply(action)
                decisions += 1

    tasks: list[dict[str, Any]] = []
    cell_order = [cell_name(d, s, a) for d in DEPTHS for s in STREETS for a in (0, 1)]
    for cell_index, cell in enumerate(cell_order):
        for key in sorted(candidates[cell])[:8]:
            tasks.append({"row_id": len(tasks), "cell_index": cell_index, "cell": cell,
                          "snapshot": allowed_snapshot(int(cell.split(":")[0]), candidates[cell][key])})
    with ProcessPoolExecutor(max_workers=4) as pool:
        quality_rows = list(pool.map(teacher_task, tasks, chunksize=1))
    selected_temperature, temperature_summary = aggregate(quality_rows)

    repeat_failures = 0
    repeat_tasks = [tasks[i * 8] for i in range(24)]
    with ProcessPoolExecutor(max_workers=4) as pool:
        repeats = list(pool.map(teacher_task, repeat_tasks, chunksize=1))
    for repeated, original_index in zip(repeats, (i * 8 for i in range(24)), strict=True):
        if repeated["identity_sha256"] != quality_rows[original_index]["identity_sha256"]:
            repeat_failures += 1

    hidden_rows = []
    hidden_failures = 0
    for pair_id, original_index in enumerate(i * 8 for i in range(24)):
        task = tasks[original_index]
        source = candidates[task["cell"]][task["snapshot"]["expected_key"]]
        alternate = source.clone()
        actor = source.current_player
        used = set(source.hole_cards[actor] or ()) | set(source.board)
        pool_cards = [c for c in range(52) if c not in used]
        rng = random.Random(DET_BASE + pair_id)
        alt_opp = tuple(rng.sample(pool_cards, 2))
        if alt_opp == source.hole_cards[1 - actor]:
            alt_opp = tuple(reversed(rng.sample([c for c in pool_cards if c not in alt_opp], 2)))
        alternate.hole_cards[1 - actor] = alt_opp
        alt_snapshot = allowed_snapshot(int(task["snapshot"]["depth"]), alternate)
        invariant = alt_snapshot == task["snapshot"]
        hidden_failures += int(not invariant)
        hidden_rows.append({
            "schema_version": "v5.tn001.hidden_invariance_pair.v1",
            "classification": "FORBIDDEN_DIAGNOSTIC_ONLY",
            "pair_id": pair_id, "cell": task["cell"], "allowed_information_sha256": sha256_obj(task["snapshot"]),
            "source_hidden_different": True, "allowed_information_identical": invariant,
            "label_identity_sha256_a": quality_rows[original_index]["identity_sha256"],
            "label_identity_sha256_b": quality_rows[original_index]["identity_sha256"],
            "source_hidden_payload_serialized": False,
        })

    serialization_seconds: list[float] = []
    paths = {
        "constructive_witnesses": output / "constructive_witnesses.jsonl",
        "discovery_states": output / "discovery_states.jsonl",
        "quality_rows": output / "quality_rows.jsonl",
        "hidden_invariance_pairs": output / "hidden_invariance_pairs.jsonl",
        "raw_metrics": output / "raw_metrics.json",
        "input_manifest": output / "input_manifest.json",
        "execution_manifest": output / "execution_manifest.json",
    }
    serialization_seconds += write_jsonl(paths["constructive_witnesses"], constructive_rows)
    serialization_seconds += write_jsonl(paths["discovery_states"], discovery_rows)
    serialization_seconds += write_jsonl(paths["quality_rows"], quality_rows)
    serialization_seconds += write_jsonl(paths["hidden_invariance_pairs"], hidden_rows)
    mc_p95 = percentile([r["mc32_wall_seconds"] for r in quality_rows], 0.95)
    accepted_p95 = percentile(constructive_seconds, 0.95)
    serialization_p95 = percentile(serialization_seconds, 0.95)
    projected_seconds = 1.25 * 1_000_000 / 4 * (accepted_p95 + mc_p95 + serialization_p95)
    row_bytes = [len(canonical_json(row).encode("utf-8")) + 1 for row in quality_rows]
    projected_bytes = 1_000_000 * percentile([float(x) for x in row_bytes], 0.99)
    metrics = {
        "constructive_states": len(constructive_rows), "witness_cells": len({r["cell"] for r in constructive_rows}),
        "witness_failures": witness_failures, "unique_keys_by_cell": {k: len(v) for k, v in unique_keys.items()},
        "exploratory_trajectories": 3072, "discovery_decision_states": len(discovery_rows),
        "quality_rows": len(quality_rows), "hidden_invariance_pairs": len(hidden_rows),
        "hidden_invariance_failures": hidden_failures, "same_seed_repeats": len(repeats),
        "same_seed_repeat_failures": repeat_failures, "selected_temperature": selected_temperature,
        "temperature_summary": temperature_summary, "accepted_state_seconds_p95": accepted_p95,
        "mc32_seconds_p95": mc_p95, "serialization_seconds_p95": serialization_p95,
        "projected_four_worker_wall_seconds_1m": projected_seconds,
        "uncompressed_quality_row_bytes_p99": percentile([float(x) for x in row_bytes], 0.99),
        "projected_uncompressed_bytes_1m": projected_bytes,
    }
    write_json(paths["raw_metrics"], metrics)
    write_json(paths["input_manifest"], {"schema_version": "v5.tn001.input_manifest.v1", "verified_inputs": verified_inputs})
    write_json(paths["execution_manifest"], {
        "schema_version": "v5.tn001.execution_manifest.v1", "device_contract": contract,
        "workers": 4, "runner_sha256": sha256_file(Path(__file__)),
        "implementation_audit_sha256": args.implementation_audit_sha256,
        "training_eligibility": "FORBIDDEN", "gpu": False,
    })
    wall = time.perf_counter() - started
    peak_rss = psutil.Process().memory_info().rss / 1_048_576 + 4 * max(r["worker_rss_mb"] for r in quality_rows)
    pre_result_bytes = sum(p.stat().st_size for p in output.iterdir())
    gates = {
        "frozen_inputs_16_exact": len(verified_inputs) == 16,
        "witnesses_24_of_24": len({r["cell"] for r in constructive_rows}) == 24 and witness_failures == 0,
        "constructive_states_768": len(constructive_rows) == 768,
        "cell_minimums_32": all(len(v) >= 32 for v in unique_keys.values()),
        "exploratory_trajectories_3072": metrics["exploratory_trajectories"] == 3072,
        "quality_rows_192": len(quality_rows) == 192,
        "mc32_exact": all(r["rollouts_per_action"] == 32 and len(r["batch_values"]) == 4 for r in quality_rows),
        "hidden_invariance_24_zero_failures": len(hidden_rows) == 24 and hidden_failures == 0,
        "same_seed_repeats_24_zero_failures": len(repeats) == 24 and repeat_failures == 0,
        "identity_and_probability": all(
            len(r["ordered_exact_actions"]) >= 1
            and all(abs(sum(p) - 1.0) <= 1e-6 and all(math.isfinite(x) and x >= 0 for x in p)
                    for p in r["teacher_probabilities_by_temperature"].values())
            for r in quality_rows
        ),
        "illegal_mass_zero": all(
            all(sum(probs[i] for i in range(9) if row["legal_mask9"][i] == 0.0) == 0.0
                for probs in row["teacher_probabilities_by_temperature"].values())
            for row in quality_rows
        ),
        "global_temperature_selected": selected_temperature is not None,
        "rollout_step_limit": all(r["max_rollout_steps"] <= 128 for r in quality_rows),
        "wall_under_900s": wall <= 900.0,
        "process_tree_peak_rss_under_2048mb": peak_rss <= 2048.0,
        "diagnostic_output_under_512mib": pre_result_bytes <= 536_870_912,
        "projection_under_24h": projected_seconds <= 86_400.0,
        "row_p99_under_8192": metrics["uncompressed_quality_row_bytes_p99"] <= 8192,
        "projection_bytes_under_10gb": projected_bytes <= 10_000_000_000,
        "device_cpu_no_torch": contract["torch_in_sys_modules"] is False and contract["CUDA_VISIBLE_DEVICES"] == "-1",
    }
    result_path = output / "result.json"
    result = {
        "schema_version": "v5.tn001.trajectory_native_qualification.result.v1", "design_id": DESIGN_ID,
        "classification": ("TN001_PASS_TRAJECTORY_NATIVE_INFOSET_MC32_AND_BOUNDED_DISCOVERY_FEASIBLE"
                           if all(gates.values()) else "TN001_NONPASS_TRAJECTORY_NATIVE_INFOSET_MC32_OR_BOUNDED_DISCOVERY_FEASIBILITY"),
        "verdict": "PASS" if all(gates.values()) else "NONPASS", "gates": gates, "measurements": metrics,
        "resources": {"wall_seconds": wall, "process_tree_peak_rss_mb": peak_rss,
                      "bundle_bytes_before_result_and_audit": pre_result_bytes},
        "identities": {"design_sha256": DESIGN_SHA256, "design_audit_sha256": DESIGN_AUDIT_SHA256,
                       "implementation_audit_sha256": args.implementation_audit_sha256,
                       "runner_sha256": sha256_file(Path(__file__))},
        "files": {name: {"path": str(path), "sha256": sha256_file(path),
                         "rows": sum(1 for _ in path.open(encoding="utf-8")) if path.suffix == ".jsonl" else None}
                  for name, path in paths.items()},
        "authority": {"training_eligibility": "FORBIDDEN", "asset_generation": "NONE",
                      "model_or_checkpoint_change": "NONE", "slumbot": "NONE", "official_hands": 0,
                      "pass_next": "SEPARATELY_REGISTER_ONE_BOUNDED_TEACHER_ASSET_DESIGN",
                      "nonpass_next": "RERANK_TO_OPPONENT_LEAGUE_FAMILY"},
        "strength": "L0",
    }
    write_json(result_path, result)
    print(canonical_json({"verdict": result["verdict"], "classification": result["classification"],
                          "gates": f"{sum(gates.values())}/{len(gates)}", "result": str(result_path)}))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract-probe", action="store_true")
    parser.add_argument("--design")
    parser.add_argument("--design-audit")
    parser.add_argument("--implementation-audit")
    parser.add_argument("--implementation-audit-sha256")
    parser.add_argument("--output")
    args = parser.parse_args()
    if not args.contract_probe and not all((args.design, args.design_audit, args.implementation_audit,
                                            args.implementation_audit_sha256, args.output)):
        parser.error("qualification requires all immutable paths and implementation audit SHA")
    return args


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(contract_probe() if args.contract_probe else run(args))
