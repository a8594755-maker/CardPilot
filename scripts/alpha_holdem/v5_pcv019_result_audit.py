"""Independent fail-closed auditor for the immutable PCV019 bounded smoke.

Every path is canonicalized with Path.resolve(strict=False) before access, hashing, or
identity comparison. Registered execution is launcher-owned and absolute end-to-end.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any

PREREG_SHA256 = "9664243c6d0042c73935086e332afc63342cdfcc00ce8b3431400db92c5ae3f2"
PREREG_AUDIT_SHA256 = "94644c8b6d6d855fe07d80b6bbac009efc970ba5ac4309c1cdfd793d1b7300b1"
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
CONTRACT_SHA256 = "cee64165a651a0ca0ee99e2350859d567468c7b8e5ad9e70e01fce9253be6937"
CONTRACT_NONCE = "2027972093"
DEVICE_MODE = "CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK"
AUDIT_INVOCATION = "LAUNCHER_OWNED_ABSOLUTE_PATHS"

EXPECTED_ROOT = r"C:\Users\a8594\CardPilot\reports\pcv019_exact_v55_teacher_smoke_20260722"
EXPECTED_PREREG = r"C:\Users\a8594\CardPilot\reports\v5_pcv019_preregistration_20260722.json"
EXPECTED_PREREG_AUDIT = r"C:\Users\a8594\CardPilot\reports\v5_pcv019_preregistration_audit_20260722.json"
EXPECTED_IMPLEMENTATION_AUDIT = r"C:\Users\a8594\CardPilot\reports\v5_pcv019_implementation_audit_20260722.json"
EXPECTED_RUNNER = r"C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_pcv019_exact_v55_teacher_smoke.py"
EXPECTED_LAUNCHER = r"C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_pcv019_launch.ps1"


def canonical_path(value: str | Path) -> Path:
    return Path(value).resolve(strict=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with canonical_path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_obj(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with canonical_path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_json_exclusive(path: Path, value: Any) -> None:
    with canonical_path(path).open("x", encoding="utf-8", newline="\n") as fh:
        json.dump(value, fh, indent=2, ensure_ascii=False, allow_nan=False)
        fh.write("\n")


def path_self_test() -> int:
    expected = canonical_path(EXPECTED_ROOT)
    relative = os.path.relpath(expected, Path.cwd())
    observed = canonical_path(relative)
    if observed != expected:
        raise RuntimeError("relative_absolute_canonicalization_mismatch")
    payload = {
        "schema_version": "v5.pcv019.path_self_test.v1",
        "design_id": "PCV019",
        "canonical_function": "str(Path(value).resolve(strict=False))",
        "relative_root": relative,
        "canonical_relative_root": str(observed),
        "canonical_absolute_root": str(expected),
        "relative_matches_absolute": True,
        "files_written": 0,
    }
    print(canonical_json(payload))
    return 0


def audit(args: argparse.Namespace) -> int:
    raw_argv = {
        "root": args.root,
        "preregistration": args.preregistration,
        "preregistration_audit": args.preregistration_audit,
        "implementation_audit": args.implementation_audit,
        "runner": args.runner,
        "launcher": args.launcher,
    }
    paths = {key: canonical_path(value) for key, value in raw_argv.items()}
    canonical_argv = {key: str(value) for key, value in paths.items()}

    root = paths["root"]
    result_path = canonical_path(root / "result.json")
    rows_path = canonical_path(root / "teacher_rows.jsonl")
    probes_path = canonical_path(root / "terminal_probes.jsonl")
    metrics_path = canonical_path(root / "raw_metrics.json")
    audit_path = canonical_path(root / "result_audit.json")
    if audit_path.exists():
        raise RuntimeError("immutable_audit_exists")

    result = json.loads(result_path.read_text(encoding="utf-8"))
    rows = load_jsonl(rows_path)
    probes = load_jsonl(probes_path)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    prereg = json.loads(paths["preregistration"].read_text(encoding="utf-8"))
    implementation_audit = json.loads(paths["implementation_audit"].read_text(encoding="utf-8"))

    checks: dict[str, bool] = {}
    checks["result_schema_and_design"] = result.get("schema_version") == "v5.pcv019.result.v1" and result.get("design_id") == "PCV019"
    checks["preregistration_hash"] = sha256_file(paths["preregistration"]) == PREREG_SHA256 == result.get("preregistration_sha256")
    checks["preregistration_audit_hash"] = sha256_file(paths["preregistration_audit"]) == PREREG_AUDIT_SHA256 == result.get("preregistration_audit_sha256")
    checks["implementation_audit_hash"] = sha256_file(paths["implementation_audit"]) == args.implementation_audit_sha256 == result.get("implementation_audit_sha256")
    checks["implementation_audit_pass_with_two_exact_contract_probes"] = (
        implementation_audit.get("overall") == "PASS"
        and len(implementation_audit.get("contract_probes", [])) == 2
        and all(
            probe.get("exit_code") == 0
            and probe.get("files_written_check") == "NO_NEW_FILES"
            and probe.get("stdout_json", {}).get("CUDA_VISIBLE_DEVICES") == "-1"
            and probe.get("stdout_json", {}).get("PCV019_DEVICE_MODE") == DEVICE_MODE
            and probe.get("stdout_json", {}).get("PCV019_CONTRACT_NONCE") == CONTRACT_NONCE
            and probe.get("stdout_json", {}).get("python_sha256") == PYTHON_SHA256
            and probe.get("stdout_json", {}).get("contract_sha256") == CONTRACT_SHA256
            and probe.get("stdout_json", {}).get("torch_in_sys_modules") is False
            and probe.get("stdout_json", {}).get("files_written") == 0
            for probe in implementation_audit.get("contract_probes", [])
        )
    )
    checks["runner_hash"] = sha256_file(paths["runner"]) == result.get("runner_sha256") == implementation_audit.get("runner_sha256")
    checks["launcher_hash_matches_implementation_audit"] = sha256_file(paths["launcher"]) == implementation_audit.get("launcher_sha256")
    checks["device_contract_exact"] = (
        result.get("device_contract", {}).get("CUDA_VISIBLE_DEVICES") == "-1"
        and result.get("device_contract", {}).get("PCV019_DEVICE_MODE") == DEVICE_MODE
        and result.get("device_contract", {}).get("PCV019_CONTRACT_NONCE") == CONTRACT_NONCE
        and result.get("device_contract", {}).get("python_sha256") == PYTHON_SHA256
        and result.get("device_contract", {}).get("contract_sha256") == CONTRACT_SHA256
        and result.get("device_contract", {}).get("torch_in_sys_modules") is False
    )
    checks["input_hashes_31_of_31"] = (
        len(result.get("verified_inputs", [])) == 31
        and len(prereg["frozen_existing_inputs"]) == 31
        and all(sha256_file(canonical_path(x["path"])) == x["sha256"] for x in result["verified_inputs"])
        and {(str(canonical_path(x["path"])), x["sha256"]) for x in result["verified_inputs"]}
        == {(str(canonical_path(x["path"])), x["sha256"]) for x in prereg["frozen_existing_inputs"]}
    )
    checks["raw_file_hashes"] = (
        sha256_file(rows_path) == result["files"]["teacher_rows"]["sha256"]
        and sha256_file(probes_path) == result["files"]["terminal_probes"]["sha256"]
        and sha256_file(metrics_path) == result["files"]["raw_metrics"]["sha256"]
    )
    checks["teacher_rows_64"] = len(rows) == 64 == result["scope"]["decision_rows"]
    checks["row_ids_exact"] = [row.get("row_id") for row in rows] == list(range(64))
    checks["row_schema_exact"] = all(row.get("schema_version") == "v5.pcv019.teacher_row.smoke.v1" for row in rows)
    checks["street_counts"] = Counter(row.get("street") for row in rows) == Counter({"PREFLOP": 16, "FLOP": 16, "TURN": 16, "RIVER": 16})
    checks["teacher_rows_forbidden_training"] = all(row.get("classification") == "FORBIDDEN_TRAINING_SMOKE_ONLY" for row in rows)
    checks["nine_slot_vectors"] = all(len(row.get("legal_mask", [])) == 9 and len(row.get("teacher_probabilities", [])) == 9 for row in rows)
    checks["probabilities_finite_nonnegative_sum1"] = all(
        all(math.isfinite(float(x)) and float(x) >= 0 for x in row["teacher_probabilities"])
        and abs(sum(float(x) for x in row["teacher_probabilities"]) - 1.0) <= 1e-12
        for row in rows
    )
    checks["zero_illegal_mass"] = all(
        sum(float(row["teacher_probabilities"][i]) for i in range(9) if float(row["legal_mask"][i]) == 0.0) == 0.0
        and row.get("illegal_positive_probability_mass") == 0.0
        for row in rows
    )
    checks["teacher_probability_hashes"] = all(sha256_obj(row["teacher_probabilities"]) == row.get("teacher_probability_sha256") for row in rows)
    checks["ordered_slots_unique_legal_and_nonnull"] = all(
        len({x["slot"] for x in row["ordered_slot_actions"]}) == len(row["ordered_slot_actions"])
        and all(float(row["legal_mask"][x["slot"]]) == 1.0 and x.get("action") is not None for x in row["ordered_slot_actions"])
        for row in rows
    )
    checks["next_state_hashes_match_slots"] = all(
        [x["slot"] for x in row["next_state_hashes"]] == [x["slot"] for x in row["ordered_slot_actions"]]
        and all(len(x["next_state_sha256"]) == 64 for x in row["next_state_hashes"])
        for row in rows
    )
    checks["identity_hash_shapes"] = all(
        all(len(str(row.get(k, ""))) == 64 for k in ("state_sha256", "observation_sha256", "legal_mask_sha256", "teacher_probability_sha256"))
        for row in rows
    )
    checks["two_value_batches"] = all(len(row.get("batch_a_values", [])) == 9 and len(row.get("batch_b_values", [])) == 9 for row in rows)
    checks["batch_l1_matches_raw"] = [float(row["batch_l1"]) for row in rows] == [float(x) for x in metrics["batch_l1"]]
    checks["row_times_match_raw"] = [float(row["row_wall_seconds"]) for row in rows] == [float(x) for x in metrics["row_wall_seconds"]]
    observed_max_steps = max(int(row["max_rollout_steps"]) for row in rows)
    checks["max_rollout_steps"] = observed_max_steps <= 128 and observed_max_steps == int(result["measurements"]["max_rollout_steps"])
    probe_counts = Counter(row.get("terminal_class") for row in probes)
    checks["terminal_probes_48"] = len(probes) == 48
    checks["probe_schema_exact"] = all(row.get("schema_version") == "v5.pcv019.terminal_probe.v1" for row in probes)
    checks["terminal_classes_16_each"] = probe_counts == Counter({"FOLD_AFTER_EXACT_SIZED_ACTION": 16, "ALLIN_CALL_SHOWDOWN": 16, "PASSIVE_RIVER_SHOWDOWN": 16})
    checks["terminal_probes_terminal_zero_sum"] = all(row.get("terminal") is True and abs(float(row["payoff0"]) + float(row["payoff1"])) <= 1e-9 for row in probes)
    checks["terminal_probe_hashes"] = all(sha256_obj({k: v for k, v in row.items() if k != "probe_sha256"}) == row.get("probe_sha256") for row in probes)
    checks["scope_seeds_and_counts"] = (
        result["scope"]["deal_seed"] == 2026072093
        and result["scope"]["rollout_seed"] == 2026972093
        and result["scope"]["contract_nonce_seed"] == 2027972093
        and result["scope"]["deals"] == 16
        and result["scope"]["rollouts_per_action_per_batch"] == 4
        and result["scope"]["teacher_batches"] == 2
        and result["scope"]["teacher_temperature"] == 100.0
    )
    checks["cpu_only_gpu_false"] = result["scope"]["cpu_workers"] == 1 and result["scope"]["gpu"] is False and result["gates"]["gpu_visible_or_used_false"] is True
    checks["same_seed_repeat_zero"] = result["measurements"]["same_seed_repeat_hash_failures"] == 0
    checks["batch_l1_gates"] = result["measurements"]["batch_l1_mean"] <= 0.75 and result["measurements"]["batch_l1_max"] <= 1.75
    checks["wall_rss_bundle_row_gates"] = (
        result["measurements"]["wall_seconds"] <= 180.0
        and result["measurements"]["peak_rss_mb"] <= 2048.0
        and result["measurements"]["bundle_bytes_before_result_and_audit"] <= 26_214_400
        and result["measurements"]["row_wall_seconds_p95"] <= 2.0
    )
    checks["extrapolation_rule"] = (
        result["extrapolation"]["target_rows"] == 1_000_000
        and result["extrapolation"]["serial_wall_seconds_from_p95"] == result["measurements"]["row_wall_seconds_p95"] * 1_000_000
        and result["extrapolation"]["storage_bytes_from_payload_ceiling"] == result["extrapolation"]["bytes_per_row_ceiling"] * 1_000_000
        and result["extrapolation"]["serial_wall_seconds_from_p95"] <= 2_592_000.0
        and result["extrapolation"]["storage_bytes_from_payload_ceiling"] <= 53_687_091_200
        and result["extrapolation"]["authority"] == "PLANNING_BOUND_ONLY_NOT_FULL_ASSET_RUNTIME_CLAIM"
    )
    checks["all_runner_gates_true"] = all(result.get("gates", {}).values())
    checks["result_pass_classification_exact"] = result.get("verdict") == "PASS" and result.get("classification") == "PCV019_PASS_INVOCATION_ROBUST_EXACT_V55_INTERFACE_AND_BOUNDED_CPU_SMOKE"
    checks["training_full_asset_behavior_authority_none"] = (
        result["authority"]["training_eligibility"] == "FORBIDDEN"
        and result["authority"]["full_asset_generation"] == "NONE"
        and result["authority"]["behavior_launch"] == "NONE"
        and result["authority"]["h19_or_later"] == "NONE"
        and result["authority"]["nonpass_next"] == "SEPARATELY_REGISTERED_ROUTE_REVIEW031"
        and result["authority"]["pass_next"] == "SEPARATELY_REGISTERED_FULL_TEACHER_ASSET_DESIGN_REVIEW_NO_AUTOMATIC_GENERATION"
    )
    checks["path1_false_official_zero_strength_forbidden"] = result.get("path1_action") is False and result["authority"]["official_hands"] == 0 and result.get("strength_claim") == "FORBIDDEN"
    checks["preregistered_outputs_resolved_exact"] = all(
        canonical_path(root / name) == canonical_path(prereg["immutable_outputs"][key])
        for name, key in (
            ("teacher_rows.jsonl", "teacher_rows"),
            ("terminal_probes.jsonl", "terminal_probes"),
            ("raw_metrics.json", "raw_metrics"),
            ("result.json", "result"),
            ("result_audit.json", "result_audit"),
        )
    )
    expected_raw = {
        "root": EXPECTED_ROOT,
        "preregistration": EXPECTED_PREREG,
        "preregistration_audit": EXPECTED_PREREG_AUDIT,
        "implementation_audit": EXPECTED_IMPLEMENTATION_AUDIT,
        "runner": EXPECTED_RUNNER,
        "launcher": EXPECTED_LAUNCHER,
    }
    checks["all_cli_paths_absolute_and_canonical_exact"] = (
        raw_argv == expected_raw
        and all(Path(value).is_absolute() for value in raw_argv.values())
        and canonical_argv == {key: str(canonical_path(value)) for key, value in expected_raw.items()}
        and canonical_argv["root"] == str(canonical_path(prereg["immutable_outputs"]["root"]))
        and canonical_argv["implementation_audit"] == str(canonical_path(prereg["planned_new_implementation"]["implementation_audit_path"]))
    )
    checks["launcher_owned_audit_invocation_exact"] = os.environ.get("PCV019_AUDIT_INVOCATION") == AUDIT_INVOCATION

    failed = [name for name, passed in checks.items() if not passed]
    if len(checks) != 44:
        raise RuntimeError(f"registered_check_count_mismatch:{len(checks)}")
    audit_result = {
        "schema_version": "v5.pcv019.result_audit.v1",
        "checked_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "result_sha256": sha256_file(result_path),
        "invocation": {
            "marker": os.environ.get("PCV019_AUDIT_INVOCATION"),
            "raw_argv": raw_argv,
            "canonical_argv": canonical_argv,
            "canonical_function": "str(Path(value).resolve(strict=False))",
        },
        "checks": checks,
        "checks_passed": sum(bool(x) for x in checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "terminal_classification": result.get("classification") if not failed else "PCV019_FAIL_CLOSED_INVOCATION_DEVICE_INTERFACE_OR_BOUNDED_CPU_SMOKE_GATE",
        "full_asset_generation_authority": "NONE",
        "behavior_launch_authority": "NONE",
        "official_hands": 0,
    }
    write_json_exclusive(audit_path, audit_result)
    print(canonical_json({"overall": audit_result["overall"], "checks": f"{audit_result['checks_passed']}/{audit_result['checks_total']}", "audit": str(audit_path)}))
    return 0 if not failed else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--preregistration")
    parser.add_argument("--preregistration-audit")
    parser.add_argument("--implementation-audit")
    parser.add_argument("--implementation-audit-sha256")
    parser.add_argument("--runner")
    parser.add_argument("--launcher")
    parser.add_argument("--path-self-test", action="store_true")
    args = parser.parse_args()
    if not args.path_self_test and not all(
        (
            args.root,
            args.preregistration,
            args.preregistration_audit,
            args.implementation_audit,
            args.implementation_audit_sha256,
            args.runner,
            args.launcher,
        )
    ):
        parser.error("registered audit requires all identity arguments")
    return args


def main() -> int:
    args = parse_args()
    if args.path_self_test:
        return path_self_test()
    return audit(args)


if __name__ == "__main__":
    raise SystemExit(main())
