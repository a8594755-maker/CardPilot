"""PCV018 exact-V5.5 teacher-interface bounded CPU smoke with Windows-safe device admission.

Single registered correction over terminal PCV017: the parent launcher sets
CUDA_VISIBLE_DEVICES=-1 (present-nonempty, PowerShell 5.1-safe) plus PCV018_DEVICE_MODE
and PCV018_CONTRACT_NONCE, and this child validates the exact contract at its own
boundary before any output.  Science, interface, seeds-scope shape, and gates are
preserved from the immutable PCV017 reference with new PCV018 seeds/paths/outputs.

This produces reporting-only smoke rows.  They are permanently forbidden as training
data and grant no full-asset, behavior, evaluation, or strength authority.
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
from deep_cfr.game_state import Action, GameConfig, HUNLGameState, Street  # noqa: E402

PREREG_SHA256 = "951422e693e680a950b1d4395822a83e500fa0dbf8d7aad0979df9289fe60f6a"
PREREG_AUDIT_SHA256 = "bdc7a472a6a36c2b494b39dc7da1d058adcd86e3f3fd58656b149ee23fc34dd0"
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
CONTRACT_NONCE = "2027972092"
CONTRACT_SHA256 = "921ed4befb30f3a910eae2894be150722138d9f4150511727deda0ca1f8a0e05"
DEAL_SEED = 2026072092
ROLLOUT_SEED = 2026972092
DEALS = 16
ROWS = 64
ROLLOUTS_PER_ACTION = 4
MAX_ROLLOUT_STEPS = 128
TEMPERATURE = 100.0
REPEAT_ROWS = 8
WALL_SECONDS_MAX = 180.0
RSS_MB_MAX = 2048.0
BUNDLE_BYTES_MAX = 26_214_400
ROW_P95_MAX = 2.0
EXTRAPOLATION_ROWS = 1_000_000
EXTRAPOLATED_SECONDS_MAX = 2_592_000.0
EXTRAPOLATED_BYTES_MAX = 53_687_091_200
BATCH_L1_MEAN_MAX = 0.75
BATCH_L1_MAX_MAX = 1.75
STREET_NAMES = {int(Street.PREFLOP): "PREFLOP", int(Street.FLOP): "FLOP", int(Street.TURN): "TURN", int(Street.RIVER): "RIVER"}
TERMINAL_CLASSES = ("FOLD_AFTER_EXACT_SIZED_ACTION", "ALLIN_CALL_SHOWDOWN", "PASSIVE_RIVER_SHOWDOWN")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_obj(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_device_contract() -> dict[str, Any]:
    observed_cvd = os.environ.get("CUDA_VISIBLE_DEVICES")
    observed_mode = os.environ.get("PCV018_DEVICE_MODE")
    observed_nonce = os.environ.get("PCV018_CONTRACT_NONCE")
    if observed_cvd != "-1":
        raise RuntimeError(f"device_contract_cuda_visible_devices_mismatch:{observed_cvd!r}")
    if observed_mode != "CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK":
        raise RuntimeError(f"device_contract_device_mode_mismatch:{observed_mode!r}")
    if observed_nonce != CONTRACT_NONCE:
        raise RuntimeError(f"device_contract_nonce_mismatch:{observed_nonce!r}")
    runtime_path = Path(sys.executable)
    runtime_sha = sha256_file(runtime_path)
    if runtime_sha != PYTHON_SHA256:
        raise RuntimeError("runtime_python_sha_mismatch")
    contract_string = (
        f"CUDA_VISIBLE_DEVICES={observed_cvd}"
        f"|PCV018_DEVICE_MODE={observed_mode}"
        f"|PCV018_CONTRACT_NONCE={observed_nonce}"
        f"|PYTHON_SHA256={runtime_sha}"
    )
    contract_sha = hashlib.sha256(contract_string.encode("utf-8")).hexdigest()
    if contract_sha != CONTRACT_SHA256:
        raise RuntimeError("device_contract_canonical_sha_mismatch")
    if "torch" in sys.modules:
        raise RuntimeError("torch_in_sys_modules")
    return {
        "CUDA_VISIBLE_DEVICES": observed_cvd,
        "PCV018_DEVICE_MODE": observed_mode,
        "PCV018_CONTRACT_NONCE": observed_nonce,
        "python_executable": str(runtime_path),
        "python_sha256": runtime_sha,
        "contract_sha256": contract_sha,
        "torch_in_sys_modules": False,
    }


def contract_probe() -> int:
    contract = validate_device_contract()
    payload = {
        "schema_version": "v5.pcv018.contract_probe.v1",
        "design_id": "PCV018",
        **contract,
        "runner_sha256": sha256_file(Path(__file__)),
        "files_written": 0,
    }
    print(canonical_json(payload))
    return 0


def action_payload(action: Action | None) -> dict[str, Any] | None:
    if action is None:
        return None
    return {"type": action.type.name, "amount": float(action.amount)}


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
        "hole_cards": [None if h is None else [int(h[0]), int(h[1])] for h in state.hole_cards],
        "board": [int(x) for x in state.board],
        "pot": float(state.pot),
        "stacks": [float(x) for x in state.stacks],
        "street": int(state.street),
        "current_player": int(state.current_player),
        "street_committed": [float(x) for x in state.street_committed],
        "raise_count": int(state.raise_count),
        "last_bet_size": float(state.last_bet_size),
        "is_done": bool(state.is_done),
        "folded_player": int(state.folded_player),
        "num_actions_this_street": int(state.num_actions_this_street),
        "actions_history": [[int(p), action_payload(a)] for p, a in state.actions_history],
    }


def array_identity(array: np.ndarray) -> dict[str, Any]:
    arr = np.ascontiguousarray(array)
    payload = {
        "shape": list(arr.shape),
        "dtype": str(arr.dtype),
        "bytes_sha256": hashlib.sha256(arr.tobytes()).hexdigest(),
    }
    payload["identity_sha256"] = sha256_obj(payload)
    return payload


def observe(state: HUNLGameState) -> tuple[dict[str, Any], np.ndarray, list[Action | None]]:
    player = state.current_player
    mask, table = build_action_table(state)
    identities = {
        "card_info": array_identity(encode_cards(state, player)),
        "action_info": array_identity(encode_action_history(state, player)),
        "extra_info": array_identity(encode_extra(state, player)),
        "legal_mask": array_identity(mask),
        "player": int(player),
    }
    identities["observation_sha256"] = sha256_obj(identities)
    return identities, mask, table


def exact_slots(mask: np.ndarray, table: list[Action | None]) -> list[int]:
    slots = [i for i in range(9) if float(mask[i]) == 1.0 and table[i] is not None]
    if not slots or any(float(mask[i]) != 0.0 and table[i] is None for i in range(9)):
        raise RuntimeError("mask_table_identity_failure")
    return slots


def new_deal(deal_id: int) -> HUNLGameState:
    random.seed(DEAL_SEED + deal_id)
    config = GameConfig.full_200bb()
    config.raise_cap_per_street = RAISE_CAP_UNLIMITED
    return HUNLGameState(config).deal_new_hand()


def apply_slot(state: HUNLGameState, slot: int) -> HUNLGameState:
    _, mask, table = observe(state)
    if slot not in exact_slots(mask, table):
        raise RuntimeError(f"illegal_exact_slot:{slot}")
    action = table[slot]
    assert action is not None
    return state.apply(action)


def advance_passive_street(state: HUNLGameState) -> HUNLGameState:
    initial = state.street
    steps = 0
    while not state.is_terminal() and state.street == initial:
        state = apply_slot(state, 1)
        steps += 1
        if steps > 3:
            raise RuntimeError("passive_street_did_not_advance")
    return state


def collect_decision_states() -> list[tuple[int, HUNLGameState]]:
    rows: list[tuple[int, HUNLGameState]] = []
    for deal_id in range(DEALS):
        state = new_deal(deal_id)
        for street in (Street.PREFLOP, Street.FLOP, Street.TURN, Street.RIVER):
            if state.is_terminal() or state.street != street:
                raise RuntimeError(f"passive_line_coverage_failure:{deal_id}:{street.name}")
            rows.append((deal_id, state.clone()))
            state = advance_passive_street(state)
        if not state.is_terminal() or state.street != Street.SHOWDOWN:
            raise RuntimeError(f"passive_showdown_failure:{deal_id}")
    if len(rows) != ROWS:
        raise RuntimeError("decision_row_count_failure")
    return rows


def rollout(state: HUNLGameState, hero: int, seed: int) -> tuple[float, int]:
    # Trajectory-identical to the immutable PCV017 reference: the observation
    # encoders are pure and consume no randomness, so sampling directly over
    # build_action_table's exact non-null slots preserves the registered
    # UNIFORM_OVER_EXACT_NON_NULL_V55_TABLE_SLOTS policy bit-for-bit.
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
            raise RuntimeError("rollout_nonterminal_at_step_ceiling")
    return float(state.payoff(hero)), steps


def action_values(state: HUNLGameState, row_id: int, batch: int, slots: list[int], table: list[Action | None]) -> tuple[list[float], int]:
    values = [0.0] * 9
    max_steps = 0
    hero = state.current_player
    for slot in slots:
        action = table[slot]
        assert action is not None
        samples = []
        for rep in range(ROLLOUTS_PER_ACTION):
            seed = ROLLOUT_SEED + row_id * 1_000_000 + batch * 100_000 + slot * 1_000 + rep
            payoff, steps = rollout(state.apply(action), hero, seed)
            samples.append(payoff)
            max_steps = max(max_steps, steps)
        values[slot] = float(statistics.fmean(samples))
    return values, max_steps


def softmax_legal(values: list[float], slots: list[int]) -> list[float]:
    scaled = np.array([values[s] / TEMPERATURE for s in slots], dtype=np.float64)
    scaled -= float(np.max(scaled))
    weights = np.exp(scaled)
    probs = weights / float(weights.sum())
    out = np.zeros(9, dtype=np.float64)
    for slot, probability in zip(slots, probs, strict=True):
        out[slot] = float(probability)
    return out.tolist()


def make_teacher_row(row_id: int, deal_id: int, state: HUNLGameState) -> tuple[dict[str, Any], int]:
    start = time.perf_counter()
    obs_a, mask_a, table_a = observe(state)
    obs_b, mask_b, table_b = observe(state.clone())
    if obs_a["observation_sha256"] != obs_b["observation_sha256"] or not np.array_equal(mask_a, mask_b):
        raise RuntimeError("observation_repeat_identity_failure")
    slots = exact_slots(mask_a, table_a)
    ordered_actions = [{"slot": slot, "action": action_payload(table_a[slot])} for slot in slots]
    if len({x["slot"] for x in ordered_actions}) != len(ordered_actions):
        raise RuntimeError("slot_collision")
    next_state_hashes = []
    for slot in slots:
        action_a, action_b = table_a[slot], table_b[slot]
        if action_payload(action_a) != action_payload(action_b):
            raise RuntimeError("action_repeat_identity_failure")
        assert action_a is not None and action_b is not None
        hash_a = sha256_obj(state_payload(state.apply(action_a)))
        hash_b = sha256_obj(state_payload(state.clone().apply(action_b)))
        if hash_a != hash_b:
            raise RuntimeError("transition_repeat_identity_failure")
        next_state_hashes.append({"slot": slot, "next_state_sha256": hash_a})
    values_a, max_steps_a = action_values(state, row_id, 0, slots, table_a)
    values_b, max_steps_b = action_values(state, row_id, 1, slots, table_a)
    probs_a = softmax_legal(values_a, slots)
    probs_b = softmax_legal(values_b, slots)
    mean_values = [(a + b) / 2.0 for a, b in zip(values_a, values_b, strict=True)]
    teacher = softmax_legal(mean_values, slots)
    illegal_mass = sum(teacher[i] for i in range(9) if i not in slots)
    if illegal_mass != 0.0 or any(not math.isfinite(x) or x < 0 for x in teacher) or abs(sum(teacher) - 1.0) > 1e-12:
        raise RuntimeError("teacher_probability_gate_failure")
    row = {
        "schema_version": "v5.pcv018.teacher_row.smoke.v1",
        "classification": "FORBIDDEN_TRAINING_SMOKE_ONLY",
        "row_id": row_id,
        "deal_id": deal_id,
        "street": STREET_NAMES[int(state.street)],
        "player": int(state.current_player),
        "state_sha256": sha256_obj(state_payload(state)),
        "observation_sha256": obs_a["observation_sha256"],
        "observation_components": obs_a,
        "legal_mask": [float(x) for x in mask_a.tolist()],
        "legal_mask_sha256": obs_a["legal_mask"]["identity_sha256"],
        "ordered_slot_actions": ordered_actions,
        "next_state_hashes": next_state_hashes,
        "batch_a_values": values_a,
        "batch_b_values": values_b,
        "teacher_probabilities": teacher,
        "teacher_probability_sha256": sha256_obj(teacher),
        "batch_l1": float(sum(abs(a - b) for a, b in zip(probs_a, probs_b, strict=True))),
        "illegal_positive_probability_mass": float(illegal_mass),
        "seed_identity": {"deal_seed": DEAL_SEED + deal_id, "rollout_seed_base": ROLLOUT_SEED, "row_id": row_id},
        "max_rollout_steps": max(max_steps_a, max_steps_b),
        "row_wall_seconds": float(time.perf_counter() - start),
    }
    return row, row["max_rollout_steps"]


def terminal_probe(deal_id: int, terminal_class: str) -> dict[str, Any]:
    state = new_deal(deal_id)
    if terminal_class == "FOLD_AFTER_EXACT_SIZED_ACTION":
        _, mask, table = observe(state)
        sized = [s for s in exact_slots(mask, table) if 2 <= s <= 7]
        if not sized:
            raise RuntimeError("fold_probe_no_sized_action")
        state = apply_slot(state, sized[0])
        state = apply_slot(state, 0)
    elif terminal_class == "ALLIN_CALL_SHOWDOWN":
        state = apply_slot(state, 8)
        state = apply_slot(state, 1)
    elif terminal_class == "PASSIVE_RIVER_SHOWDOWN":
        while not state.is_terminal():
            state = advance_passive_street(state)
    else:
        raise RuntimeError("unknown_terminal_class")
    if not state.is_terminal():
        raise RuntimeError("terminal_probe_not_terminal")
    payoff0, payoff1 = float(state.payoff(0)), float(state.payoff(1))
    if abs(payoff0 + payoff1) > 1e-9:
        raise RuntimeError("terminal_zero_sum_failure")
    payload = {
        "schema_version": "v5.pcv018.terminal_probe.v1",
        "classification": "FORBIDDEN_TRAINING_SMOKE_ONLY",
        "deal_id": deal_id,
        "terminal_class": terminal_class,
        "terminal": True,
        "street": state.street.name,
        "board_cards": len(state.board),
        "payoff0": payoff0,
        "payoff1": payoff1,
        "state_sha256": sha256_obj(state_payload(state)),
    }
    payload["probe_sha256"] = sha256_obj(payload)
    return payload


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.floor((len(ordered) - 1) * q))
    return float(ordered[index])


def write_json_exclusive(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as fh:
        json.dump(value, fh, indent=2, ensure_ascii=False, allow_nan=False)
        fh.write("\n")


def write_jsonl_exclusive(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(canonical_json(row) + "\n")


def verify_inputs(prereg: dict[str, Any]) -> list[dict[str, str]]:
    verified = []
    for item in prereg["frozen_existing_inputs"]:
        path = Path(item["path"])
        observed = sha256_file(path)
        if observed != item["sha256"]:
            raise RuntimeError(f"frozen_input_hash_mismatch:{path}")
        verified.append({"path": str(path), "sha256": observed})
    return verified


def self_test() -> None:
    state = new_deal(0)
    obs, mask, table = observe(state)
    slots = exact_slots(mask, table)
    assert obs["player"] in (0, 1) and len(slots) >= 2
    action = table[slots[0]]
    assert action is not None
    assert sha256_obj(state_payload(state.apply(action))) == sha256_obj(state_payload(state.clone().apply(action)))
    rollout_mask, rollout_table = build_action_table(state)
    assert np.array_equal(rollout_mask, mask) and exact_slots(rollout_mask, rollout_table) == slots
    print("PCV018_SELF_TEST_PASS")


def run(args: argparse.Namespace) -> int:
    start = time.perf_counter()
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    prereg = json.loads(Path(args.preregistration).read_text(encoding="utf-8"))
    if sha256_file(Path(args.preregistration)) != PREREG_SHA256:
        raise RuntimeError("preregistration_hash_mismatch")
    if sha256_file(Path(args.preregistration_audit)) != PREREG_AUDIT_SHA256:
        raise RuntimeError("preregistration_audit_hash_mismatch")
    if sha256_file(Path(args.implementation_audit)) != args.implementation_audit_sha256:
        raise RuntimeError("implementation_audit_hash_mismatch")
    implementation_audit = json.loads(Path(args.implementation_audit).read_text(encoding="utf-8"))
    if implementation_audit.get("overall") != "PASS":
        raise RuntimeError("implementation_audit_not_pass")
    verified_inputs = verify_inputs(prereg)
    if len(verified_inputs) != 15:
        raise RuntimeError("frozen_input_count_not_15")
    device_contract = validate_device_contract()
    output = Path(args.output)
    if output.exists():
        raise RuntimeError("immutable_output_root_exists")
    output.mkdir(parents=False)

    decision_states = collect_decision_states()
    teacher_rows: list[dict[str, Any]] = []
    for row_id, (deal_id, state) in enumerate(decision_states):
        row, _ = make_teacher_row(row_id, deal_id, state)
        teacher_rows.append(row)
        peak_rss = max(peak_rss, process.memory_info().rss)
        if time.perf_counter() - start > WALL_SECONDS_MAX:
            raise RuntimeError("wall_seconds_hard_limit")
        if peak_rss / 1048576 > RSS_MB_MAX:
            raise RuntimeError("rss_hard_limit")

    repeat_failures = 0
    for row_id, (deal_id, state) in enumerate(decision_states[:REPEAT_ROWS]):
        repeated, _ = make_teacher_row(row_id, deal_id, state)
        original = teacher_rows[row_id]
        keys = ("state_sha256", "observation_sha256", "legal_mask_sha256", "ordered_slot_actions", "next_state_hashes", "teacher_probability_sha256")
        if any(repeated[key] != original[key] for key in keys):
            repeat_failures += 1
        peak_rss = max(peak_rss, process.memory_info().rss)

    probes = [terminal_probe(deal_id, terminal_class) for terminal_class in TERMINAL_CLASSES for deal_id in range(DEALS)]
    street_counts = {name: sum(row["street"] == name for row in teacher_rows) for name in STREET_NAMES.values()}
    terminal_counts = {name: sum(row["terminal_class"] == name for row in probes) for name in TERMINAL_CLASSES}
    l1_values = [float(row["batch_l1"]) for row in teacher_rows]
    row_times = [float(row["row_wall_seconds"]) for row in teacher_rows]
    max_rollout_steps = max(int(row["max_rollout_steps"]) for row in teacher_rows)
    wall_seconds = float(time.perf_counter() - start)
    peak_rss_mb = float(peak_rss / 1048576)

    rows_path = output / "teacher_rows.jsonl"
    probes_path = output / "terminal_probes.jsonl"
    metrics_path = output / "raw_metrics.json"
    result_path = output / "result.json"
    write_jsonl_exclusive(rows_path, teacher_rows)
    write_jsonl_exclusive(probes_path, probes)
    raw_metrics = {
        "schema_version": "v5.pcv018.raw_metrics.v1",
        "row_wall_seconds": row_times,
        "batch_l1": l1_values,
        "peak_rss_mb": peak_rss_mb,
        "wall_seconds_before_output_finalization": wall_seconds,
    }
    write_json_exclusive(metrics_path, raw_metrics)

    payload_bytes = rows_path.stat().st_size + probes_path.stat().st_size + metrics_path.stat().st_size
    row_p95 = percentile(row_times, 0.95)
    extrapolated_seconds = row_p95 * EXTRAPOLATION_ROWS
    bytes_per_row_ceiling = math.ceil(payload_bytes / ROWS)
    extrapolated_bytes = bytes_per_row_ceiling * EXTRAPOLATION_ROWS
    gates = {
        "input_hashes_15_of_15": len(verified_inputs) == 15,
        "runtime_python_sha_exact": device_contract["python_sha256"] == PYTHON_SHA256,
        "device_contract_exact": device_contract["contract_sha256"] == CONTRACT_SHA256,
        "implementation_audit_pass": True,
        "decision_rows_64": len(teacher_rows) == 64,
        "street_counts_exact": street_counts == {"PREFLOP": 16, "FLOP": 16, "TURN": 16, "RIVER": 16},
        "terminal_probe_counts_minimum": all(terminal_counts[x] >= 16 for x in TERMINAL_CLASSES),
        "exact_replay_failures_zero": True,
        "observation_or_action_identity_failures_zero": True,
        "probability_failures_zero": True,
        "projection_drop_renormalization_collision_zero": True,
        "illegal_positive_probability_mass_zero": all(row["illegal_positive_probability_mass"] == 0.0 for row in teacher_rows),
        "same_seed_repeat_hash_failures_zero": repeat_failures == 0,
        "rollout_nonterminal_failures_zero": max_rollout_steps <= MAX_ROLLOUT_STEPS,
        "batch_l1_mean": statistics.fmean(l1_values) <= BATCH_L1_MEAN_MAX,
        "batch_l1_max": max(l1_values) <= BATCH_L1_MAX_MAX,
        "wall_seconds": wall_seconds <= WALL_SECONDS_MAX,
        "peak_rss_mb": peak_rss_mb <= RSS_MB_MAX,
        "bundle_bytes_before_audit": payload_bytes <= BUNDLE_BYTES_MAX,
        "row_wall_seconds_p95": row_p95 <= ROW_P95_MAX,
        "extrapolated_serial_wall_seconds": extrapolated_seconds <= EXTRAPOLATED_SECONDS_MAX,
        "extrapolated_storage_bytes": extrapolated_bytes <= EXTRAPOLATED_BYTES_MAX,
        "gpu_visible_or_used_false": device_contract["CUDA_VISIBLE_DEVICES"] == "-1" and device_contract["torch_in_sys_modules"] is False,
    }
    passed = all(gates.values())
    result = {
        "schema_version": "v5.pcv018.result.v1",
        "design_id": "PCV018",
        "judged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": "PASS" if passed else "FAIL",
        "classification": "PCV018_PASS_EXACT_V55_INTERFACE_AND_BOUNDED_CPU_SMOKE" if passed else "PCV018_FAIL_CLOSED_DEVICE_INTERFACE_OR_BOUNDED_CPU_SMOKE_GATE",
        "preregistration_sha256": PREREG_SHA256,
        "preregistration_audit_sha256": PREREG_AUDIT_SHA256,
        "implementation_audit_sha256": args.implementation_audit_sha256,
        "runner_sha256": sha256_file(Path(__file__)),
        "device_contract": device_contract,
        "verified_inputs": verified_inputs,
        "scope": {
            "classification": "FORBIDDEN_TRAINING_SMOKE_ONLY",
            "deal_seed": DEAL_SEED,
            "rollout_seed": ROLLOUT_SEED,
            "contract_nonce_seed": int(CONTRACT_NONCE),
            "deals": DEALS,
            "decision_rows": len(teacher_rows),
            "street_counts": street_counts,
            "terminal_probe_counts": terminal_counts,
            "rollouts_per_action_per_batch": ROLLOUTS_PER_ACTION,
            "teacher_batches": 2,
            "teacher_temperature": TEMPERATURE,
            "max_rollout_steps_limit": MAX_ROLLOUT_STEPS,
            "same_seed_repeat_rows": REPEAT_ROWS,
            "cpu_workers": 1,
            "gpu": False,
        },
        "measurements": {
            "wall_seconds": wall_seconds,
            "peak_rss_mb": peak_rss_mb,
            "bundle_bytes_before_result_and_audit": payload_bytes,
            "row_wall_seconds_p95": row_p95,
            "batch_l1_mean": statistics.fmean(l1_values),
            "batch_l1_max": max(l1_values),
            "max_rollout_steps": max_rollout_steps,
            "same_seed_repeat_hash_failures": repeat_failures,
            "illegal_positive_probability_mass_max": max(row["illegal_positive_probability_mass"] for row in teacher_rows),
        },
        "extrapolation": {
            "target_rows": EXTRAPOLATION_ROWS,
            "serial_wall_seconds_from_p95": extrapolated_seconds,
            "storage_bytes_from_payload_ceiling": extrapolated_bytes,
            "bytes_per_row_ceiling": bytes_per_row_ceiling,
            "peak_rss_mb_no_scale_down": peak_rss_mb,
            "authority": "PLANNING_BOUND_ONLY_NOT_FULL_ASSET_RUNTIME_CLAIM",
        },
        "gates": gates,
        "files": {
            "teacher_rows": {"path": str(rows_path), "sha256": sha256_file(rows_path), "rows": len(teacher_rows)},
            "terminal_probes": {"path": str(probes_path), "sha256": sha256_file(probes_path), "rows": len(probes)},
            "raw_metrics": {"path": str(metrics_path), "sha256": sha256_file(metrics_path)},
        },
        "authority": {
            "training_eligibility": "FORBIDDEN",
            "full_asset_generation": "NONE",
            "behavior_launch": "NONE",
            "h19_or_later": "NONE",
            "official_hands": 0,
            "pass_next": "SEPARATELY_REGISTERED_FULL_ASSET_DESIGN_REVIEW_NO_AUTOMATIC_GENERATION",
            "nonpass_next": "SEPARATELY_REGISTERED_ROUTE_REVIEW030",
        },
        "path1_action": False,
        "strength_claim": "FORBIDDEN",
    }
    write_json_exclusive(result_path, result)
    print(canonical_json({"verdict": result["verdict"], "classification": result["classification"], "result": str(result_path)}))
    return 0 if passed else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration")
    parser.add_argument("--preregistration-audit")
    parser.add_argument("--implementation-audit")
    parser.add_argument("--implementation-audit-sha256")
    parser.add_argument("--output")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract-probe", action="store_true")
    args = parser.parse_args()
    if not args.self_test and not args.contract_probe and not all((args.preregistration, args.preregistration_audit, args.implementation_audit, args.implementation_audit_sha256, args.output)):
        parser.error("registered execution requires all identity and output arguments")
    return args


def main() -> int:
    args = parse_args()
    if args.contract_probe:
        return contract_probe()
    if args.self_test:
        self_test()
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
