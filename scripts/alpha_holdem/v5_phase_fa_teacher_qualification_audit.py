"""Independent fail-closed auditor for Phase FA Q001 qualification output."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any

DESIGN_ID = "PHASE_FA_Q001_EXACT_CFR_MAPPER_AND_MC32_QUALITY_QUALIFICATION"
DESIGN_SHA256 = "74b7aeda43d46c1ec84ea72f58f3795c32279b548fdc7674f8fa837e99669a82"
DESIGN_AUDIT_SHA256 = "ee245f813fc9fd4a301f6a9dfc92761b4e3db51becf7de5361cd59aa8fb0ba68"
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
CONTRACT_SHA256 = "5b7ed3ccd8acc12366f93537f4426eaacb273006b7b0bbaeeb907ece6be579e3"
DEVICE_MODE = "CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK"
CONTRACT_NONCE = "2029972201"
AUDIT_MARKER = "LAUNCHER_OWNED_ABSOLUTE_PATHS"

EXPECTED = {
    "root": r"C:\Users\a8594\CardPilot\reports\phase_fa_teacher_qualification_20260722",
    "design": r"C:\Users\a8594\CardPilot\reports\v5_phase_fa_full_teacher_asset_design_preregistration_20260722.json",
    "design_audit": r"C:\Users\a8594\CardPilot\reports\v5_phase_fa_full_teacher_asset_design_preregistration_audit_20260722.json",
    "implementation_audit": r"C:\Users\a8594\CardPilot\reports\v5_phase_fa_teacher_qualification_implementation_audit_20260722.json",
    "runner": r"C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_phase_fa_teacher_qualification.py",
    "launcher": r"C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_phase_fa_teacher_launch.ps1",
}
LINE_BUCKETS = (
    "ALLIN_RESPONSE_ONLY", "SHORT_SPR_FACING", "SHORT_SPR_UNOPENED", "FACING_DEEP_RERAISE",
    "FACING_FIRST_RAISE", "FACING_FIRST_BET", "CHECKED_TO_NO_BET", "OPEN_ACTION_NO_BET",
)
STREETS = ("PREFLOP", "FLOP", "TURN", "RIVER")
TEMPERATURES = (1.0, 5.0, 10.0, 25.0, 100.0)


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
    expected = canonical_path(EXPECTED["root"])
    relative = os.path.relpath(expected, Path.cwd())
    observed = canonical_path(relative)
    if observed != expected:
        raise RuntimeError("relative_absolute_canonicalization_mismatch")
    print(canonical_json({
        "schema_version": "v5.phase_fa.q001.path_self_test.v1",
        "design_id": DESIGN_ID,
        "canonical_function": "str(Path(value).resolve(strict=False))",
        "relative_root": relative,
        "canonical_relative_root": str(observed),
        "canonical_absolute_root": str(expected),
        "relative_matches_absolute": True,
        "files_written": 0,
    }))
    return 0


def audit(args: argparse.Namespace) -> int:
    raw = {
        "root": args.root,
        "design": args.design,
        "design_audit": args.design_audit,
        "implementation_audit": args.implementation_audit,
        "runner": args.runner,
        "launcher": args.launcher,
    }
    paths = {key: canonical_path(value) for key, value in raw.items()}
    root = paths["root"]
    result_path = root / "result.json"
    mapper_path = root / "mapper_candidates.jsonl"
    mc_path = root / "mc32_rows.jsonl"
    metrics_path = root / "raw_metrics.json"
    audit_path = root / "result_audit.json"
    if audit_path.exists():
        raise RuntimeError("immutable_audit_exists")

    result = json.loads(result_path.read_text(encoding="utf-8"))
    mapper = load_jsonl(mapper_path)
    mc = load_jsonl(mc_path)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    implementation = json.loads(paths["implementation_audit"].read_text(encoding="utf-8"))
    design = json.loads(paths["design"].read_text(encoding="utf-8"))
    design_audit = json.loads(paths["design_audit"].read_text(encoding="utf-8"))

    checks: dict[str, bool] = {}
    checks["schema_and_design_exact"] = result.get("schema_version") == "v5.phase_fa.q001.result.v1" and result.get("design_id") == DESIGN_ID
    checks["all_cli_paths_raw_absolute_exact"] = raw == EXPECTED and all(Path(x).is_absolute() for x in raw.values())
    checks["all_cli_paths_canonical_exact"] = paths == {key: canonical_path(value) for key, value in EXPECTED.items()}
    checks["launcher_owned_invocation_exact"] = os.environ.get("PHASE_FA_AUDIT_INVOCATION") == AUDIT_MARKER
    checks["design_hash_exact"] = sha256_file(paths["design"]) == DESIGN_SHA256 == result.get("design_sha256")
    checks["design_audit_hash_and_pass197"] = sha256_file(paths["design_audit"]) == DESIGN_AUDIT_SHA256 == result.get("design_audit_sha256") and design_audit.get("overall") == "PASS" and design_audit.get("checks_total") == 197
    checks["design_q001_contract_exact"] = design.get("qualification_window_contract", {}).get("next_design_id") == DESIGN_ID
    checks["implementation_audit_hash_pass"] = sha256_file(paths["implementation_audit"]) == args.implementation_audit_sha256 == result.get("implementation_audit_sha256") and implementation.get("overall") == "PASS"
    checks["implementation_two_contract_probes"] = len(implementation.get("contract_probes", [])) == 2 and all(x.get("exit_code") == 0 and x.get("files_written_check") == "NO_NEW_FILES" for x in implementation.get("contract_probes", []))
    checks["runner_hash_bound"] = sha256_file(paths["runner"]) == result.get("runner_sha256") == implementation.get("runner_sha256")
    checks["launcher_hash_bound"] = sha256_file(paths["launcher"]) == implementation.get("launcher_sha256")
    device = result.get("device_contract", {})
    checks["device_contract_exact"] = device.get("CUDA_VISIBLE_DEVICES") == "-1" and device.get("PHASE_FA_DEVICE_MODE") == DEVICE_MODE and device.get("PHASE_FA_CONTRACT_NONCE") == CONTRACT_NONCE and device.get("python_sha256") == PYTHON_SHA256 and device.get("contract_sha256") == CONTRACT_SHA256 and device.get("torch_in_sys_modules") is False
    checks["raw_file_hashes_exact"] = sha256_file(mapper_path) == result["files"]["mapper_candidates"]["sha256"] and sha256_file(mc_path) == result["files"]["mc32_rows"]["sha256"] and sha256_file(metrics_path) == result["files"]["raw_metrics"]["sha256"]
    checks["mapper_rows_12288"] = len(mapper) == 12_288 == result["files"]["mapper_candidates"]["rows"]
    mapper_counts = Counter(row.get("depth") for row in mapper)
    checks["mapper_depth_counts_exact"] = mapper_counts == Counter({"200bb": 4096, "100bb": 4096, "50bb": 4096})
    checks["mapper_candidate_ids_unique"] = len({row.get("candidate_id") for row in mapper}) == len(mapper)
    checks["mapper_training_forbidden"] = all(row.get("training_eligibility") == "FORBIDDEN_DIAGNOSTIC_ONLY" for row in mapper)
    accepted = [row for row in mapper if row.get("accepted") is True]
    checks["accepted_exact_identity_fields"] = all(len(row.get("state_payload_sha256", "")) == 64 and len(row.get("observation_identity_sha256", "")) == 64 for row in accepted)
    checks["accepted_no_semantic_loss"] = all(row.get("projection_drop_collision_or_renormalization") is False and len(row.get("source_action_to_slot", [])) == len(set(row.get("source_action_to_slot", []))) for row in accepted)
    checks["accepted_probabilities_exact"] = all(len(row.get("teacher_probs9", [])) == 9 and all(math.isfinite(float(x)) and float(x) >= 0 for x in row["teacher_probs9"]) and abs(sum(row["teacher_probs9"]) - 1.0) <= 1e-6 and sha256_obj(row["teacher_probs9"]) == row.get("teacher_probability_sha256") for row in accepted)
    checks["rejected_reason_nonempty"] = all(isinstance(row.get("rejection_reason"), str) and row["rejection_reason"] for row in mapper if not row.get("accepted"))
    checks["mapper_acceptance_recomputed"] = all(abs(result["measurements"]["mapper_acceptance"][depth] - sum(row.get("accepted") is True for row in mapper if row["depth"] == depth) / 4096) <= 1e-15 for depth in ("200bb", "100bb", "50bb"))
    checks["mc_rows_bound_and_file_count_exact"] = 0 < len(mc) <= 4096 and len(mc) == result["files"]["mc32_rows"]["rows"]
    checks["mc_row_ids_exact"] = [row.get("row_id") for row in mc] == list(range(len(mc)))
    checks["mc_schema_and_training_forbidden"] = all(row.get("schema_version") == "v5.phase_fa.q001.mc32_row.v1" and row.get("classification") == "FORBIDDEN_DIAGNOSTIC_ONLY" for row in mc)
    observed_streets = Counter(row.get("street") for row in mc)
    observed_cells = Counter((row.get("street"), row.get("state_line_bucket")) for row in mc)
    quota_shortfall = result["measurements"].get("mc32_quota_shortfall", {})
    recomputed_shortfall = {
        f"{street}:{bucket}": 128 - observed_cells[(street, bucket)]
        for street in STREETS for bucket in LINE_BUCKETS if observed_cells[(street, bucket)] < 128
    }
    checks["mc_street_counts_at_most_1024_and_gate_truth"] = all(observed_streets[street] <= 1024 for street in STREETS) and result["gates"]["mc32_street_balance_1024_each"] == (observed_streets == Counter({street: 1024 for street in STREETS}))
    checks["mc_cell_counts_at_most_128_shortfall_and_gate_truth"] = all(observed_cells[(street, bucket)] <= 128 for street in STREETS for bucket in LINE_BUCKETS) and quota_shortfall == recomputed_shortfall and result["gates"]["mc32_cell_balance_128_each"] == (not recomputed_shortfall and observed_cells == Counter({(street, bucket): 128 for street in STREETS for bucket in LINE_BUCKETS}))
    checks["mc_exact_4x8"] = all(row.get("rollouts_per_action_total") == 32 and len(row.get("batch_values", [])) == 4 and all(len(x) == 9 for x in row.get("batch_values", [])) for row in mc)
    checks["mc_exact_slot_shapes"] = all(len(row.get("legal_mask9", [])) == 9 and len(row.get("ordered_nonnull_slot_actions", [])) >= 1 and [x["slot"] for x in row["ordered_nonnull_slot_actions"]] == [x["slot"] for x in row["next_state_sha256_by_legal_slot"]] for row in mc)
    checks["mc_slots_unique_nonnull_legal"] = all(len({x["slot"] for x in row["ordered_nonnull_slot_actions"]}) == len(row["ordered_nonnull_slot_actions"]) and all(row["legal_mask9"][x["slot"]] == 1.0 and x.get("action") is not None for x in row["ordered_nonnull_slot_actions"]) for row in mc)
    checks["mc_temperature_candidates_exact"] = all(set(row.get("temperature_metrics", {})) == {str(x) for x in TEMPERATURES} and set(row.get("teacher_probs9_by_temperature", {})) == {str(x) for x in TEMPERATURES} for row in mc)
    checks["mc_teacher_probabilities_valid"] = all(all(len(probs) == 9 and all(math.isfinite(float(x)) and float(x) >= 0 for x in probs) and abs(sum(probs) - 1.0) <= 1e-12 for probs in row["teacher_probs9_by_temperature"].values()) for row in mc)
    checks["mc_illegal_mass_zero"] = all(row.get("illegal_positive_probability_mass") == 0.0 and all(sum(probs[i] for i in range(9) if row["legal_mask9"][i] == 0.0) == 0.0 for probs in row["teacher_probs9_by_temperature"].values()) for row in mc)
    checks["same_seed_repeat_zero"] = metrics.get("same_seed_repeat_failures") == 0 == result["measurements"]["same_seed_repeat_failures"]
    selected = metrics.get("selected_temperature")
    summary = metrics.get("temperature_summary", {})
    checks["temperature_summary_exact_candidates"] = set(summary) == {str(x) for x in TEMPERATURES}
    checks["selected_temperature_rule_exact"] = (
        (selected is None and not any(summary[str(x)]["passes"] for x in TEMPERATURES))
        or (selected in TEMPERATURES and summary[str(selected)]["passes"] is True and all(summary[str(x)]["passes"] is False for x in TEMPERATURES if x < selected))
    )
    checks["source_hashes_replay"] = all(sha256_file(canonical_path(item["path"])) == item["sha256"] for item in metrics.get("source_hashes_before_first_read", []))
    checks["runner_gates_exact23"] = len(result.get("gates", {})) == 23
    checks["runner_gate_truth_matches_verdict"] = all(result["gates"].values()) == (result.get("verdict") == "PASS")
    checks["classification_exact"] = result.get("classification") == ("PHASE_FA_Q001_PASS_EXACT_CFR_MAPPER_AND_MC32_QUALITY_QUALIFIED" if all(result["gates"].values()) else "PHASE_FA_Q001_NONPASS_FAIL_CLOSED_EXACT_MAPPER_OR_MC32_QUALITY_GATE")
    checks["resource_limits"] = result["measurements"]["wall_seconds"] <= 900.0 and result["measurements"]["peak_rss_mb"] <= 2048.0 and result["measurements"]["bundle_bytes_before_result_and_audit"] <= 2_000_000_000
    checks["scope_workers_cpu_gpu_exact"] = result["scope"]["workers"] == 8 and result["scope"]["gpu"] is False and result["scope"]["training_eligibility"] == "FORBIDDEN_DIAGNOSTIC_ONLY"
    checks["authority_exact"] = result["authority"] == {"training_eligibility": "FORBIDDEN", "full_asset_generation": "NONE", "behavior_launch": "NONE", "official_hands": 0, "pass_next": "SEPARATELY_REGISTERED_PHASE_FA_GENERATION_WINDOW_000_NO_AUTOMATIC_LAUNCH", "nonpass_next": "SEPARATELY_REGISTERED_PHASE_FA_DESIGN_REVIEW_002_OR_ROUTE_REVIEW031_AS_EXACTLY_JUDGED"}
    checks["path1_false_strength_l0"] = result.get("path1_action") is False and result.get("strength_claim") == "FORBIDDEN_L0"

    failed = [name for name, value in checks.items() if not value]
    if len(checks) != 44:
        raise RuntimeError(f"registered_check_count_mismatch:{len(checks)}")
    audit_result = {
        "schema_version": "v5.phase_fa.q001.result_audit.v1",
        "result_sha256": sha256_file(result_path),
        "invocation": {"marker": os.environ.get("PHASE_FA_AUDIT_INVOCATION"), "raw_argv": raw, "canonical_argv": {key: str(value) for key, value in paths.items()}},
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "terminal_classification": result.get("classification") if not failed else "PHASE_FA_Q001_FAIL_CLOSED_INDEPENDENT_AUDIT_GATE",
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
    parser.add_argument("--design")
    parser.add_argument("--design-audit")
    parser.add_argument("--implementation-audit")
    parser.add_argument("--implementation-audit-sha256")
    parser.add_argument("--runner")
    parser.add_argument("--launcher")
    parser.add_argument("--path-self-test", action="store_true")
    args = parser.parse_args()
    if not args.path_self_test and not all((args.root, args.design, args.design_audit, args.implementation_audit, args.implementation_audit_sha256, args.runner, args.launcher)):
        parser.error("audit requires every immutable identity argument")
    return args


def main() -> int:
    args = parse_args()
    return path_self_test() if args.path_self_test else audit(args)


if __name__ == "__main__":
    raise SystemExit(main())
