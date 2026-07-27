"""Independent fail-closed output auditor for Revision006 Q006."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
from typing import Any, Iterable


DESIGN_ID = "PHASE_FA_TRAJECTORY_NATIVE_REACHABLE_INFOSET_MC32_TEACHER_ASSET_20M_DESIGN_REVISION006_V1"
QUALIFICATION_ID = "PHASE_FA_REVISION006_Q006_TRAJECTORY_SUPPORT_MC32_QUALITY_AND_RESOURCE_QUALIFICATION"
DESIGN_SHA256 = "c7f3645b7c1f763bd37ab99149c72f2b697868199735e80ebc36be4df16efd42"
DESIGN_AUDIT_SHA256 = "976c2721545f8aef7cc69167c9328531f55edc566f134fe31c741112b5d891b0"
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
DEVICE_MODE = "CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK"
CONTRACT_NONCE = "2031972206"
AUDIT_MARKER = "LAUNCHER_OWNED_ABSOLUTE_PATHS"

EXPECTED = {
    "root": r"C:\Users\a8594\CardPilot\reports\v5_phase_fa_revision006_q006_20260722",
    "design": r"C:\Users\a8594\CardPilot\reports\v5_phase_fa_design_revision006_preregistration_20260722.json",
    "design_audit": r"C:\Users\a8594\CardPilot\reports\v5_phase_fa_design_revision006_preregistration_audit_20260722.json",
    "implementation_audit": r"C:\Users\a8594\CardPilot\reports\v5_phase_fa_revision006_q006_implementation_audit_20260722.json",
    "runner": r"C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_phase_fa_revision006_q006.py",
    "launcher": r"C:\Users\a8594\CardPilot\scripts\alpha_holdem\launch_v5_phase_fa_revision006_q006.ps1",
}
DEPTHS = (200, 100, 50)
STREETS = ("PREFLOP", "FLOP", "TURN", "RIVER")
LINE_BUCKETS = (
    "ALLIN_RESPONSE_ONLY", "SHORT_SPR_FACING", "SHORT_SPR_UNOPENED", "FACING_DEEP_RERAISE",
    "FACING_FIRST_RAISE", "FACING_FIRST_BET", "CHECKED_TO_NO_BET", "OPEN_ACTION_NO_BET",
)
TEMPERATURES = (1.0, 5.0, 10.0, 25.0, 100.0)
EXPECTED_BASE_KEYS = {f"{depth}bb:{street}:P{player}" for depth in DEPTHS for street in STREETS for player in (0, 1)}


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


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with canonical_path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise RuntimeError(f"jsonl_parse_failure:{path}:{line_number}") from error


def percentile(values: Iterable[float], q: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile_requires_values")
    return ordered[min(len(ordered) - 1, math.floor((len(ordered) - 1) * q))]


def aggregate_quality(rows: list[dict[str, Any]]) -> tuple[float | None, dict[str, Any]]:
    slices: dict[str, list[dict[str, Any]]] = {"GLOBAL": rows}
    for depth in DEPTHS:
        slices[f"{depth}bb"] = [row for row in rows if row.get("depth_bb") == depth]
    summary: dict[str, Any] = {}
    selected: float | None = None
    for temperature in TEMPERATURES:
        key = str(temperature)
        slice_summary: dict[str, Any] = {}
        all_pass = True
        for name, subset in slices.items():
            if not subset:
                metrics = {"batch_distribution_l1_mean": None, "batch_distribution_l1_p95": None, "states_top_action_agreement_ge_0_75_fraction": None, "passes": False}
            else:
                l1 = [float(row["temperature_metrics"][key]["batch_l1_mean"]) for row in subset]
                top = [float(row["temperature_metrics"][key]["top_action_agreement_fraction"]) for row in subset]
                metrics = {
                    "batch_distribution_l1_mean": statistics.fmean(l1),
                    "batch_distribution_l1_p95": percentile(l1, 0.95),
                    "states_top_action_agreement_ge_0_75_fraction": sum(value >= 0.75 for value in top) / len(top),
                }
                metrics["passes"] = (
                    metrics["batch_distribution_l1_mean"] <= 0.20
                    and metrics["batch_distribution_l1_p95"] <= 0.50
                    and metrics["states_top_action_agreement_ge_0_75_fraction"] >= 0.70
                )
            slice_summary[name] = metrics
            all_pass = all_pass and metrics["passes"]
        summary[key] = {"slices": slice_summary, "passes_all_required_slices": all_pass}
        if selected is None and all_pass:
            selected = temperature
    return selected, summary


def recursively_has_key(value: Any, forbidden: set[str]) -> bool:
    if isinstance(value, dict):
        return any(key in forbidden or recursively_has_key(item, forbidden) for key, item in value.items())
    if isinstance(value, list):
        return any(recursively_has_key(item, forbidden) for item in value)
    return False


def write_json_exclusive(path: Path, value: Any) -> None:
    with canonical_path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def path_self_test() -> int:
    expected = canonical_path(EXPECTED["root"])
    relative = os.path.relpath(expected, Path.cwd())
    if canonical_path(relative) != expected:
        raise RuntimeError("relative_absolute_canonicalization_mismatch")
    print(canonical_json({
        "schema_version": "v5.phase_fa.revision006.q006.path_self_test.v1",
        "qualification_id": QUALIFICATION_ID,
        "canonical_function": "str(Path(value).resolve(strict=False))",
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
    if raw != EXPECTED or not all(Path(value).is_absolute() for value in raw.values()):
        raise RuntimeError("raw_absolute_path_identity_mismatch")
    if paths != {key: canonical_path(value) for key, value in EXPECTED.items()}:
        raise RuntimeError("canonical_path_identity_mismatch")
    root = paths["root"]
    result_path = root / "result.json"
    support_path = root / "support_states.jsonl"
    quality_path = root / "mc32_quality_rows.jsonl"
    repeat_path = root / "same_seed_repeats.jsonl"
    metrics_path = root / "raw_metrics.json"
    audit_path = root / "result_audit.json"
    if audit_path.exists():
        raise RuntimeError("immutable_audit_exists")

    result = json.loads(result_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    design = json.loads(paths["design"].read_text(encoding="utf-8"))
    design_audit = json.loads(paths["design_audit"].read_text(encoding="utf-8"))
    implementation = json.loads(paths["implementation_audit"].read_text(encoding="utf-8"))

    support_count = 0
    support_ordinals_exact = True
    support_identities: set[str] = set()
    base_counts: Counter[str] = Counter()
    line_counts: Counter[str] = Counter()
    public_replays: dict[str, set[str]] = defaultdict(set)
    legal_slots_seen: set[int] = set()
    support_schema_exact = True
    support_training_forbidden = True
    support_no_hidden_payload = True
    for row in iter_jsonl(support_path):
        support_ordinals_exact = support_ordinals_exact and row.get("global_ordinal") == support_count
        support_count += 1
        identity = row.get("state_identity_sha256")
        if isinstance(identity, str):
            support_identities.add(identity)
        base = f"{row.get('depth_bb')}bb:{row.get('street')}:P{row.get('acting_player')}"
        line = f"{base}:{row.get('line_bucket')}"
        base_counts[base] += 1
        line_counts[line] += 1
        public_replays[line].add(row.get("public_replay_identity_sha256"))
        legal_slots_seen.update(int(slot) for slot in row.get("legal_slots", []))
        support_schema_exact = support_schema_exact and row.get("schema_version") == "v5.phase_fa.revision006.q006.support_state.v1"
        support_training_forbidden = support_training_forbidden and row.get("training_eligibility") == "FORBIDDEN_DIAGNOSTIC_ONLY"
        support_no_hidden_payload = support_no_hidden_payload and not recursively_has_key(row, {"opponent_hole_cards", "unrevealed_deck", "deck"})

    eligible_lines = {
        key for key, count in line_counts.items()
        if count >= 256 and len(public_replays[key]) >= 64
    }
    line_diversity_by_depth = {
        depth: len({key.rsplit(":", 1)[1] for key in eligible_lines if key.startswith(f"{depth}bb:")})
        for depth in DEPTHS
    }
    global_line_diversity = len({key.rsplit(":", 1)[1] for key in eligible_lines})

    quality = list(iter_jsonl(quality_path))
    repeats = list(iter_jsonl(repeat_path))
    quality_base_counts = Counter(f"{row.get('depth_bb')}bb:{row.get('street')}:P{row.get('acting_player')}" for row in quality)
    quality_ids = [row.get("state_identity_sha256") for row in quality]
    quality_schema_exact = all(row.get("schema_version") == "v5.phase_fa.revision006.q006.mc32_quality_row.v1" for row in quality)
    quality_training_forbidden = all(row.get("training_eligibility") == "FORBIDDEN_DIAGNOSTIC_ONLY" for row in quality)
    quality_no_hidden_payload = all(not recursively_has_key(row, {"opponent_hole_cards", "unrevealed_deck", "deck"}) for row in quality)
    quality_shapes_exact = all(
        len(row.get("legal_mask9", [])) == 9
        and len(row.get("batch_action_values9", [])) == 4
        and all(len(batch) == 9 for batch in row.get("batch_action_values9", []))
        and row.get("rollouts_per_action_total") == 32
        and row.get("determinizations_total") == 32
        and len(row.get("determinization_identity_sha256s", [])) == 32
        for row in quality
    )
    quality_temperature_exact = all(
        set(row.get("temperature_metrics", {})) == {str(value) for value in TEMPERATURES}
        and set(row.get("teacher_probs9_by_temperature", {})) == {str(value) for value in TEMPERATURES}
        for row in quality
    )
    quality_probabilities_valid = all(
        all(
            len(probabilities) == 9
            and all(math.isfinite(float(value)) and float(value) >= 0 for value in probabilities)
            and abs(sum(float(value) for value in probabilities) - 1.0) <= 1e-6
            and sum(float(probabilities[index]) for index, mask in enumerate(row["legal_mask9"]) if float(mask) == 0.0) == 0.0
            for probabilities in row.get("teacher_probs9_by_temperature", {}).values()
        )
        for row in quality
    )
    quality_hard_failures_zero = all(
        row.get("source_hidden_information_read_count") == 0
        and row.get("information_leakage_failures") == 0
        and row.get("determinization_replay_failures") == 0
        and row.get("card_collision_failures") == 0
        and row.get("action_identity_failures") == 0
        and row.get("illegal_positive_probability_mass") == 0.0
        and int(row.get("max_rollout_steps", 129)) <= 128
        for row in quality
    )
    selected_temperature, quality_summary = aggregate_quality(quality) if quality else (None, {})

    repeat_schema_exact = all(row.get("schema_version") == "v5.phase_fa.revision006.q006.same_seed_repeat.v1" for row in repeats)
    repeat_matches = all(
        row.get("matches") is True
        and row.get("expected_identity_sha256") == row.get("observed_identity_sha256")
        and row.get("training_eligibility") == "FORBIDDEN_DIAGNOSTIC_ONLY"
        for row in repeats
    )

    checks: dict[str, bool] = {}
    checks["schema_design_qualification_exact"] = result.get("schema_version") == "v5.phase_fa.revision006.q006.result.v1" and result.get("design_id") == DESIGN_ID and result.get("qualification_id") == QUALIFICATION_ID
    checks["all_cli_paths_raw_absolute_exact"] = raw == EXPECTED and all(Path(value).is_absolute() for value in raw.values())
    checks["all_cli_paths_canonical_exact"] = paths == {key: canonical_path(value) for key, value in EXPECTED.items()}
    checks["launcher_owned_audit_invocation_exact"] = os.environ.get("REV006_AUDIT_INVOCATION") == AUDIT_MARKER
    checks["design_hash_exact"] = sha256_file(paths["design"]) == DESIGN_SHA256 == result.get("design_sha256")
    checks["design_id_exact"] = design.get("design_id") == DESIGN_ID
    checks["design_audit_hash_pass267_classification_exact"] = sha256_file(paths["design_audit"]) == DESIGN_AUDIT_SHA256 == result.get("design_audit_sha256") and design_audit.get("overall") == "PASS" and design_audit.get("checks_total") == 267 and design_audit.get("classification") == "PHASE_FA_DESIGN_REVISION006_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_Q006_IMPLEMENTATION_READY_ONLY"
    checks["implementation_audit_hash_pass"] = sha256_file(paths["implementation_audit"]) == args.implementation_audit_sha256 == result.get("implementation_audit_sha256") and implementation.get("overall") == "PASS"
    checks["implementation_authorization_exact"] = implementation.get("authorization") == "EXACTLY_ONE_LATER_Q006_QUALIFICATION_THROUGH_EXACT_LAUNCHER_NO_AUTOMATIC_LAUNCH"
    checks["runner_hash_bound"] = sha256_file(paths["runner"]) == result.get("runner_sha256") == implementation.get("runner_sha256")
    checks["launcher_hash_bound"] = sha256_file(paths["launcher"]) == implementation.get("launcher_sha256")
    device = result.get("device_contract", {})
    checks["device_contract_exact"] = device.get("CUDA_VISIBLE_DEVICES") == "-1" and device.get("REV006_DEVICE_MODE") == DEVICE_MODE and device.get("REV006_CONTRACT_NONCE") == CONTRACT_NONCE and device.get("python_sha256") == PYTHON_SHA256 and device.get("torch_in_sys_modules") is False
    checks["verified_frozen_inputs_12_rehash"] = len(result.get("verified_design_inputs", [])) == 12 and all(sha256_file(canonical_path(item["path"])) == item["sha256"] for item in result.get("verified_design_inputs", []))
    checks["raw_file_hashes_exact"] = sha256_file(support_path) == result["files"]["support_states"]["sha256"] and sha256_file(quality_path) == result["files"]["mc32_quality_rows"]["sha256"] and sha256_file(repeat_path) == result["files"]["same_seed_repeats"]["sha256"] and sha256_file(metrics_path) == result["files"]["raw_metrics"]["sha256"]
    checks["raw_file_row_counts_exact"] = support_count == result["files"]["support_states"]["rows"] and len(quality) == result["files"]["mc32_quality_rows"]["rows"] and len(repeats) == result["files"]["same_seed_repeats"]["rows"]
    checks["support_count_bounded_and_gate_truth"] = support_count <= 300_000 and result["gates"]["support_states_exact_300000"] == (support_count == 300_000)
    checks["support_ordinals_exact"] = support_ordinals_exact
    checks["support_identities_unique"] = len(support_identities) == support_count
    checks["support_schema_exact"] = support_schema_exact
    checks["support_training_forbidden"] = support_training_forbidden
    checks["support_no_hidden_payload"] = support_no_hidden_payload
    checks["support_base_counts_recomputed"] = dict(sorted(base_counts.items())) == metrics.get("base_support_counts") == result["measurements"].get("base_support_counts")
    checks["support_line_counts_recomputed"] = dict(sorted(line_counts.items())) == metrics.get("line_support_counts")
    checks["support_public_replays_recomputed"] = {key: len(public_replays[key]) for key in sorted(line_counts)} == metrics.get("line_public_replay_counts")
    checks["eligible_lines_recomputed"] = sorted(eligible_lines) == metrics.get("eligible_lines") == result["measurements"].get("eligible_lines")
    checks["eligible_lines_meet_256_64"] = all(line_counts[key] >= 256 and len(public_replays[key]) >= 64 for key in eligible_lines)
    checks["absent_ineligible_lines_not_promoted"] = all(key in eligible_lines or line_counts[key] < 256 or len(public_replays[key]) < 64 for key in line_counts)
    checks["base_24_gate_truth"] = result["gates"]["support_all_24_depth_street_actual_actor_base_cells_ge_256"] == all(base_counts[key] >= 256 for key in EXPECTED_BASE_KEYS)
    checks["line_diversity_recomputed"] = {f"{depth}bb": line_diversity_by_depth[depth] for depth in DEPTHS} == metrics.get("line_diversity_by_depth") and global_line_diversity == metrics.get("global_line_diversity")
    checks["line_diversity_gate_truth"] = result["gates"]["line_diversity_each_depth_ge_6_and_global_all_8"] == (all(value >= 6 for value in line_diversity_by_depth.values()) and global_line_diversity == 8)
    checks["legal_slots_recomputed"] = sorted(legal_slots_seen) == metrics.get("legal_slots_seen") == result["measurements"].get("legal_slots_seen")
    checks["legal_slots_gate_truth"] = result["gates"]["all_executable_v55_slots_observed"] == (legal_slots_seen == set(range(9)))
    checks["quality_count_bounded_and_gate_truth"] = len(quality) <= 6_144 and result["gates"]["quality_states_exact_6144"] == (len(quality) == 6_144)
    checks["quality_ids_unique"] = len(set(quality_ids)) == len(quality)
    checks["quality_schema_exact"] = quality_schema_exact
    checks["quality_training_forbidden"] = quality_training_forbidden
    checks["quality_no_hidden_payload"] = quality_no_hidden_payload
    checks["quality_base_balance_gate_truth"] = result["gates"]["quality_256_per_each_24_base_cells"] == (len(quality) == 6_144 and quality_base_counts == Counter({key: 256 for key in EXPECTED_BASE_KEYS}))
    checks["quality_shapes_exact"] = quality_shapes_exact
    checks["quality_temperatures_exact"] = quality_temperature_exact
    checks["quality_probabilities_valid_no_illegal_mass"] = quality_probabilities_valid
    checks["quality_hard_failures_zero"] = quality_hard_failures_zero
    checks["quality_summary_independently_recomputed"] = quality_summary == metrics.get("quality_summary") == result["measurements"].get("quality_summary")
    checks["selected_temperature_independently_recomputed"] = selected_temperature == metrics.get("selected_temperature") == result["measurements"].get("selected_temperature")
    checks["selected_temperature_lowest_passing_rule"] = selected_temperature is None or all(not quality_summary[str(value)]["passes_all_required_slices"] for value in TEMPERATURES if value < selected_temperature)
    checks["repeat_count_bounded_and_gate_truth"] = len(repeats) <= 768 and result["gates"]["same_seed_repeats_exact_768"] == (len(repeats) == 768)
    checks["repeat_schema_exact"] = repeat_schema_exact
    checks["repeat_identity_matches"] = repeat_matches
    checks["repeat_failure_count_zero_recomputed"] = sum(not bool(row.get("matches")) for row in repeats) == metrics.get("same_seed_repeat_failures") == result["measurements"].get("same_seed_repeat_failures")
    checks["resource_projection_values_finite_or_none"] = all(value is None or (math.isfinite(float(value)) and float(value) >= 0) for value in (metrics.get("max_sampling_p99"), metrics.get("max_mc32_p99"), metrics.get("serialization_gzip_p99_seconds"), metrics.get("projected_eight_worker_20m_wall_seconds")))
    checks["resource_projection_bound_gate_truth"] = result["gates"]["projected_eight_worker_20m_wall_le_168h"] == (metrics.get("projected_eight_worker_20m_wall_seconds") is not None and metrics["projected_eight_worker_20m_wall_seconds"] <= 604_800)
    checks["asset_row_size_gates_truth"] = result["gates"]["uncompressed_asset_row_p99_le_8192"] == (metrics.get("uncompressed_asset_row_p99_bytes") is not None and metrics["uncompressed_asset_row_p99_bytes"] <= 8_192) and result["gates"]["gzip_asset_row_p99_le_5000"] == (metrics.get("gzip_asset_row_p99_bytes") is not None and metrics["gzip_asset_row_p99_bytes"] <= 5_000)
    checks["runtime_resource_gates_truth"] = result["gates"]["qualification_wall_seconds_le_43200"] == (result["measurements"]["wall_seconds"] <= 43_200) and result["gates"]["qualification_peak_rss_mb_le_4096"] == (result["measurements"]["peak_rss_mb"] <= 4_096) and result["gates"]["qualification_output_bytes_le_10gb"] == (result["measurements"]["bundle_bytes_before_result_and_audit"] <= 10_000_000_000)
    checks["quota_manifest_not_created"] = metrics.get("quota_manifest_created") is False and result["gates"]["quota_manifest_not_created"] is True
    checks["runner_gate_count_exact29"] = len(result.get("gates", {})) == 29
    checks["runner_gate_truth_matches_verdict"] = all(result["gates"].values()) == (result.get("verdict") == "PASS")
    expected_classification = "PHASE_FA_REVISION006_Q006_PASS_TRAJECTORY_SUPPORT_MC32_QUALITY_AND_RESOURCE_QUALIFIED" if all(result["gates"].values()) else "PHASE_FA_REVISION006_Q006_NONPASS_FAIL_CLOSED_SUPPORT_MC32_QUALITY_OR_RESOURCE_GATE"
    checks["classification_exact"] = result.get("classification") == expected_classification
    checks["authority_training_asset_behavior_slumbot_none"] = result.get("authority", {}).get("training_eligibility") == "FORBIDDEN" and result["authority"].get("quota_manifest") == "NONE_UNTIL_SEPARATE_PASS_TRANSITION" and result["authority"].get("asset_generation") == "NONE" and result["authority"].get("behavior_launch") == "NONE" and result["authority"].get("slumbot") == "NONE_NO_NEW_CHECKPOINT"
    checks["pass_nonpass_next_exact"] = result.get("authority", {}).get("pass_next") == "SEPARATELY_CREATE_AND_AUDIT_ONE_IMMUTABLE_PILOT_DERIVED_QUOTA_MANIFEST" and result["authority"].get("nonpass_next") == "FREEZE_AND_RUN_SCIENTIFIC_ROUTE_REVIEW_NO_RERUN_EXTENSION_OR_THRESHOLD_RELAXATION"
    checks["path1_false_official_zero_strength_l0"] = result.get("path1_action") is False and result.get("authority", {}).get("official_hands") == 0 and result.get("strength_claim") == "FORBIDDEN_L0"

    failed = [name for name, passed in checks.items() if not passed]
    audit_result = {
        "schema_version": "v5.phase_fa.revision006.q006.result_audit.v1",
        "result_sha256": sha256_file(result_path),
        "invocation": {
            "marker": os.environ.get("REV006_AUDIT_INVOCATION"),
            "raw_argv": raw,
            "canonical_argv": {key: str(path) for key, path in paths.items()},
        },
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "terminal_classification": result.get("classification") if not failed else "PHASE_FA_REVISION006_Q006_FAIL_CLOSED_INDEPENDENT_AUDIT_GATE",
        "quota_manifest_authority": "NONE",
        "asset_generation_authority": "NONE",
        "training_authority": "NONE",
        "behavior_launch_authority": "NONE",
        "slumbot_authority": "NONE",
        "official_hands": 0,
        "strength": "L0",
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
