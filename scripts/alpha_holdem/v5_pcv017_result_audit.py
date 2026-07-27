"""Independent fail-closed auditor for the immutable PCV017 bounded smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

PREREG_SHA256 = "63249c1ab2a8fcd5d4b7701eae22f3177b48db48d648abc46ce21589460a7522"
PREREG_AUDIT_SHA256 = "aa711438b6d92acdead4a0d1c4d0f1ac1b03a90eaea773a5ad51bed34e37d11d"


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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_json_exclusive(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as fh:
        json.dump(value, fh, indent=2, ensure_ascii=False, allow_nan=False)
        fh.write("\n")


def audit(args: argparse.Namespace) -> int:
    root = Path(args.root)
    result_path = root / "result.json"
    rows_path = root / "teacher_rows.jsonl"
    probes_path = root / "terminal_probes.jsonl"
    metrics_path = root / "raw_metrics.json"
    audit_path = root / "result_audit.json"
    if audit_path.exists():
        raise RuntimeError("immutable_audit_exists")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    rows = load_jsonl(rows_path)
    probes = load_jsonl(probes_path)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    prereg = json.loads(Path(args.preregistration).read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    checks["result_schema_and_design"] = result.get("schema_version") == "v5.pcv017.result.v1" and result.get("design_id") == "PCV017"
    checks["preregistration_hash"] = sha256_file(Path(args.preregistration)) == PREREG_SHA256 == result.get("preregistration_sha256")
    checks["preregistration_audit_hash"] = sha256_file(Path(args.preregistration_audit)) == PREREG_AUDIT_SHA256 == result.get("preregistration_audit_sha256")
    checks["implementation_audit_hash"] = sha256_file(Path(args.implementation_audit)) == args.implementation_audit_sha256 == result.get("implementation_audit_sha256")
    checks["runner_hash"] = sha256_file(Path(args.runner)) == result.get("runner_sha256")
    checks["input_hashes_8_of_8"] = len(result.get("verified_inputs", [])) == 8 and all(sha256_file(Path(x["path"])) == x["sha256"] for x in result["verified_inputs"])
    checks["raw_file_hashes"] = (
        sha256_file(rows_path) == result["files"]["teacher_rows"]["sha256"]
        and sha256_file(probes_path) == result["files"]["terminal_probes"]["sha256"]
        and sha256_file(metrics_path) == result["files"]["raw_metrics"]["sha256"]
    )
    checks["teacher_rows_64"] = len(rows) == 64 == result["scope"]["decision_rows"]
    checks["row_ids_exact"] = [row.get("row_id") for row in rows] == list(range(64))
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
    checks["terminal_classes_16_each"] = probe_counts == Counter({"FOLD_AFTER_EXACT_SIZED_ACTION": 16, "ALLIN_CALL_SHOWDOWN": 16, "PASSIVE_RIVER_SHOWDOWN": 16})
    checks["terminal_probes_terminal_zero_sum"] = all(row.get("terminal") is True and abs(float(row["payoff0"]) + float(row["payoff1"])) <= 1e-9 for row in probes)
    checks["terminal_probe_hashes"] = all(sha256_obj({k: v for k, v in row.items() if k != "probe_sha256"}) == row.get("probe_sha256") for row in probes)
    checks["scope_seeds_and_counts"] = (
        result["scope"]["deal_seed"] == 2026072091
        and result["scope"]["rollout_seed"] == 2026972091
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
    checks["result_pass_classification_exact"] = result.get("verdict") == "PASS" and result.get("classification") == "PCV017_PASS_EXACT_V55_INTERFACE_AND_BOUNDED_CPU_SMOKE"
    checks["training_full_asset_behavior_authority_none"] = (
        result["authority"]["training_eligibility"] == "FORBIDDEN"
        and result["authority"]["full_asset_generation"] == "NONE"
        and result["authority"]["behavior_launch"] == "NONE"
        and result["authority"]["h19_or_later"] == "NONE"
    )
    checks["path1_false_official_zero_strength_forbidden"] = result.get("path1_action") is False and result["authority"]["official_hands"] == 0 and result.get("strength_claim") == "FORBIDDEN"
    checks["preregistered_outputs_exact"] = all(str(root / name) == prereg["immutable_outputs"][key] for name, key in (("teacher_rows.jsonl", "teacher_rows"), ("terminal_probes.jsonl", "terminal_probes"), ("raw_metrics.json", "raw_metrics"), ("result.json", "result"), ("result_audit.json", "audit")))
    failed = [name for name, passed in checks.items() if not passed]
    audit_result = {
        "schema_version": "v5.pcv017.result_audit.v1",
        "checked_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "result_sha256": sha256_file(result_path),
        "checks": checks,
        "checks_passed": sum(bool(x) for x in checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "terminal_classification": result.get("classification") if not failed else "PCV017_FAIL_CLOSED_RESULT_AUDIT",
        "full_asset_generation_authority": "NONE",
        "behavior_launch_authority": "NONE",
        "official_hands": 0,
    }
    write_json_exclusive(audit_path, audit_result)
    print(canonical_json({"overall": audit_result["overall"], "checks": f"{audit_result['checks_passed']}/{audit_result['checks_total']}", "audit": str(audit_path)}))
    return 0 if not failed else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--preregistration", required=True)
    parser.add_argument("--preregistration-audit", required=True)
    parser.add_argument("--implementation-audit", required=True)
    parser.add_argument("--implementation-audit-sha256", required=True)
    parser.add_argument("--runner", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(audit(parse_args()))
