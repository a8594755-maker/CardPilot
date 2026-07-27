"""Independent result auditor for the immutable FA002 Q01 qualification bundle."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

PROJECT = Path(__file__).resolve().parents[2]
PROGRAM_ID = "FA002_61e5047f8820e9df19733e57c257a04a"
QUALIFICATION_ID = "FA002_Q01_61e5047f8820e9df19733e57c257a04a"
PREREG_SHA256 = "18765838ce043a6f560162770aeeb665eebac6a42b53f580934f6c69d6d849a7"
PREREG_AUDIT_SHA256 = "004090c0ab90388c9e494cf503f572a463fda38eaf65e6a41af886846db6e5f7"
EXPECTED_PREREG = PROJECT / "reports" / "v5_fa002_unified_candidate_preregistration_61e5047f8820e9df19733e57c257a04a_20260722.json"
EXPECTED_PREREG_AUDIT = PROJECT / "reports" / "v5_fa002_unified_candidate_preregistration_audit_61e5047f8820e9df19733e57c257a04a_20260722.json"
EXPECTED_IMPLEMENTATION_AUDIT = PROJECT / "reports" / "v5_fa002_q01_implementation_audit_61e5047f8820e9df19733e57c257a04a_20260722.json"
EXPECTED_ROOT = PROJECT / "reports" / "v5_fa002_q01_61e5047f8820e9df19733e57c257a04a_20260722"
EXPECTED_RUNNER = PROJECT / "scripts" / "alpha_holdem" / "v5_fa002_q01_61e5047f8820e9df19733e57c257a04a.py"
EXPECTED_LAUNCHER = PROJECT / "scripts" / "alpha_holdem" / "v5_fa002_q01_launcher_61e5047f8820e9df19733e57c257a04a.ps1"

DEPTHS = (200, 100, 50)
STREETS = ("PREFLOP", "FLOP", "TURN", "RIVER")
CONTEXTS = tuple(f"{depth}bb|{street}|actor{actor}" for depth in DEPTHS for street in STREETS for actor in (0, 1))
ACCEPTED_TOTAL = 120_000
ACCEPTED_PER_DEPTH = 40_000
QUALITY_TOTAL = 6_144
QUALITY_PER_CONTEXT = 256
REPEATS_TOTAL = 768
QUALITY_L1_MEAN_MAX = 0.20
QUALITY_L1_P95_MAX = 0.50
QUALITY_TOP_FRACTION_MIN = 0.70


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
    return ordered[min(len(ordered) - 1, math.floor((len(ordered) - 1) * q))]


def quality_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    slices: dict[str, list[dict[str, Any]]] = {"GLOBAL": rows}
    for depth in DEPTHS:
        slices[f"{depth}bb"] = [row for row in rows if int(row["depth_bb"]) == depth]
    summary: dict[str, Any] = {}
    for name, subset in slices.items():
        l1 = [float(row["batch_distribution_l1_mean"]) for row in subset]
        tops = [float(row["batch_top_action_agreement_fraction"]) for row in subset]
        metrics = {
            "rows": len(subset),
            "batch_distribution_l1_mean": float(statistics.fmean(l1)),
            "batch_distribution_l1_p95": percentile(l1, 0.95),
            "states_top_action_agreement_ge_0_75_fraction": sum(value >= 0.75 for value in tops) / len(tops),
        }
        metrics["passes"] = (
            metrics["batch_distribution_l1_mean"] <= QUALITY_L1_MEAN_MAX
            and metrics["batch_distribution_l1_p95"] <= QUALITY_L1_P95_MAX
            and metrics["states_top_action_agreement_ge_0_75_fraction"] >= QUALITY_TOP_FRACTION_MIN
        )
        summary[name] = metrics
    return summary


def close_float(left: float, right: float, tolerance: float = 1e-12) -> bool:
    return math.isfinite(float(left)) and math.isfinite(float(right)) and abs(float(left) - float(right)) <= tolerance


def write_json_exclusive(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def self_test() -> dict[str, Any]:
    synthetic: list[dict[str, Any]] = []
    for depth in DEPTHS:
        for index in range(10):
            synthetic.append({
                "depth_bb": depth,
                "batch_distribution_l1_mean": 0.1 + index * 0.001,
                "batch_top_action_agreement_fraction": 1.0,
            })
    summary = quality_summary(synthetic)
    checks = {
        "percentile_nearest_rank": percentile([1, 2, 3, 4], 0.95) == 3.0,
        "summary_slices_exact": set(summary) == {"GLOBAL", "200bb", "100bb", "50bb"},
        "summary_rows_exact": summary["GLOBAL"]["rows"] == 30,
        "summary_passes": all(value["passes"] for value in summary.values()),
        "close_float_exact": close_float(0.2, 0.2),
        "close_float_rejects": not close_float(0.2, 0.3),
        "contexts24": len(CONTEXTS) == 24 and len(set(CONTEXTS)) == 24,
    }
    if not all(checks.values()):
        raise RuntimeError("auditor_self_test_failure")
    return {"checks": checks, "check_count": len(checks), "pass_count": sum(checks.values())}


def audit(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    checks: dict[str, bool] = {}

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)

    paths = {
        "root": canonical_path(args.root),
        "prereg": canonical_path(args.preregistration),
        "prereg_audit": canonical_path(args.preregistration_audit),
        "implementation_audit": canonical_path(args.implementation_audit),
    }
    expected = {
        "root": canonical_path(EXPECTED_ROOT),
        "prereg": canonical_path(EXPECTED_PREREG),
        "prereg_audit": canonical_path(EXPECTED_PREREG_AUDIT),
        "implementation_audit": canonical_path(EXPECTED_IMPLEMENTATION_AUDIT),
    }
    check("paths_exact", paths == expected)
    check("raw_paths_absolute", all(Path(value).is_absolute() for value in (args.root, args.preregistration, args.preregistration_audit, args.implementation_audit)))
    check("prereg_hash", sha256_file(paths["prereg"]) == PREREG_SHA256)
    check("prereg_audit_hash", sha256_file(paths["prereg_audit"]) == PREREG_AUDIT_SHA256)
    check("implementation_audit_hash", sha256_file(paths["implementation_audit"]) == args.implementation_audit_sha256)
    implementation_audit = json.loads(paths["implementation_audit"].read_text(encoding="utf-8"))
    check("implementation_audit_pass", implementation_audit.get("overall") == "PASS")
    check("implementation_classification", implementation_audit.get("classification") == "PASS / FA002_Q01_IMPLEMENTATION_AUDIT_PASS_ONE_QUALIFICATION_READY_ONLY")
    implementation = implementation_audit.get("implementation", {})
    check("runner_hash_bound", implementation.get("runner_sha256") == sha256_file(EXPECTED_RUNNER))
    check("launcher_hash_bound", implementation.get("launcher_sha256") == sha256_file(EXPECTED_LAUNCHER))
    check("auditor_hash_bound", implementation.get("auditor_sha256") == sha256_file(__file__))
    check("torch_absent", "torch" not in sys.modules)

    expected_names = {"invocation.json", "reached_states.jsonl.gz", "quality_rows.jsonl.gz", "metrics.json", "result.json"}
    observed_names = {path.name for path in paths["root"].iterdir() if path.is_file()}
    check("preaudit_files_exact", observed_names == expected_names)
    result = json.loads((paths["root"] / "result.json").read_text(encoding="utf-8"))
    metrics = json.loads((paths["root"] / "metrics.json").read_text(encoding="utf-8"))
    invocation = json.loads((paths["root"] / "invocation.json").read_text(encoding="utf-8"))
    check("program_id_exact", result.get("program_id") == PROGRAM_ID == metrics.get("program_id") == invocation.get("program_id"))
    check("qualification_id_exact", result.get("qualification_id") == QUALIFICATION_ID == metrics.get("qualification_id") == invocation.get("qualification_id"))
    check("attempt_one", invocation.get("attempt") == 1)
    check("diagnostic_only", result.get("training_eligibility") == "FORBIDDEN_DIAGNOSTIC_ONLY" == metrics.get("training_eligibility"))
    check("result_counts_nonbehavioral_zero", result.get("counts", {}).get("teacher_rows") == 0 and result.get("counts", {}).get("training_hands") == 0 and result.get("counts", {}).get("checkpoints") == 0 and result.get("counts", {}).get("official_hands") == 0)

    bundle = result.get("bundle", {})
    check("bundle_names_exact", set(bundle) == {"invocation.json", "reached_states.jsonl.gz", "quality_rows.jsonl.gz", "metrics.json"})
    bundle_ok = True
    for name, identity in bundle.items():
        path = paths["root"] / name
        bundle_ok = bundle_ok and path.stat().st_size == int(identity["bytes"]) and sha256_file(path) == identity["sha256"]
    check("bundle_hashes_and_bytes_exact", bundle_ok)

    support_count = 0
    support_ids: set[str] = set()
    support_depths: Counter[int] = Counter()
    support_contexts: Counter[str] = Counter()
    sample_times: dict[str, list[float]] = defaultdict(list)
    support_schema = True
    support_hidden_clean = True
    support_actions_valid = True
    with gzip.open(paths["root"] / "reached_states.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            support_count += 1
            identity = row.get("state_identity_sha256")
            if not isinstance(identity, str) or len(identity) != 64 or identity in support_ids:
                support_schema = False
            else:
                support_ids.add(identity)
            depth = int(row.get("depth_bb", -1))
            context = row.get("base_context")
            support_depths[depth] += 1
            support_contexts[context] += 1
            sample_times[context].append(float(row.get("sampling_seconds", math.nan)))
            support_schema = support_schema and row.get("schema_version") == "v5.fa002.q01.reached_state.v1" and row.get("training_eligibility") == "FORBIDDEN_DIAGNOSTIC_ONLY" and context in CONTEXTS
            support_hidden_clean = support_hidden_clean and row.get("source_opponent_cards_serialized") is False and row.get("source_unrevealed_deck_serialized") is False
            actions = row.get("ordered_nonnull_slot_actions", [])
            slots = row.get("legal_slots", [])
            support_actions_valid = support_actions_valid and len(actions) == len(slots) == len(set(slots)) and all(item.get("slot") in slots and item.get("action") is not None for item in actions)
    check("support_count_120000", support_count == ACCEPTED_TOTAL)
    check("support_ids_unique_120000", len(support_ids) == ACCEPTED_TOTAL)
    check("support_depths_40000_each", support_depths == Counter({depth: ACCEPTED_PER_DEPTH for depth in DEPTHS}))
    check("support_contexts24_min256", set(support_contexts) == set(CONTEXTS) and all(support_contexts[context] >= 256 for context in CONTEXTS))
    check("support_schema_and_context", support_schema)
    check("support_hidden_clean", support_hidden_clean)
    check("support_actions_valid", support_actions_valid)
    check("support_sampling_finite", all(math.isfinite(value) and value >= 0 for values in sample_times.values() for value in values))

    quality_rows: list[dict[str, Any]] = []
    quality_schema = True
    probability_valid = True
    batch_shape_valid = True
    recomputed_row_metrics = True
    projection_fields_valid = True
    with gzip.open(paths["root"] / "quality_rows.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            quality_rows.append(row)
            quality_schema = quality_schema and row.get("schema_version") == "v5.fa002.q01.mc32_quality_row.v1" and row.get("training_eligibility") == "FORBIDDEN_DIAGNOSTIC_ONLY" and row.get("base_context") in CONTEXTS
            mask = [float(value) for value in row.get("legal_mask9", [])]
            probs = [float(value) for value in row.get("teacher_probs9", [])]
            probability_valid = probability_valid and len(mask) == len(probs) == 9 and all(math.isfinite(value) and value >= 0 for value in probs) and abs(sum(probs) - 1.0) <= 1e-12 and sum(probs[index] for index in range(9) if mask[index] == 0.0) == 0.0 and row.get("teacher_probability_sha256") == sha256_obj(probs)
            distributions = row.get("batch_teacher_probs9", [])
            values = row.get("batch_action_values9", [])
            batch_shape_valid = batch_shape_valid and len(distributions) == len(values) == 4 and all(len(item) == 9 for item in distributions + values) and row.get("determinizations_total") == 32 and row.get("rollouts_per_action_total") == 32
            if len(distributions) == 4:
                pairwise = [sum(abs(float(left) - float(right)) for left, right in zip(distributions[a], distributions[b], strict=True)) for a in range(4) for b in range(a + 1, 4)]
                tops = [max(range(9), key=lambda slot: (float(distribution[slot]), -slot)) for distribution in distributions]
                top_fraction = Counter(tops).most_common(1)[0][1] / 4
                recomputed_row_metrics = recomputed_row_metrics and all(close_float(left, right) for left, right in zip(pairwise, row.get("pairwise_batch_l1", []), strict=True)) and close_float(statistics.fmean(pairwise), row.get("batch_distribution_l1_mean")) and close_float(top_fraction, row.get("batch_top_action_agreement_fraction"))
            projection_fields_valid = projection_fields_valid and int(row.get("asset_projection_uncompressed_bytes", -1)) > 0 and int(row.get("asset_projection_gzip_bytes", -1)) > 0 and math.isfinite(float(row.get("asset_projection_serialization_gzip_seconds", math.nan))) and float(row.get("asset_projection_serialization_gzip_seconds")) >= 0
    quality_contexts = Counter(row.get("base_context") for row in quality_rows)
    check("quality_count_6144", len(quality_rows) == QUALITY_TOTAL)
    check("quality_contexts_exact256", quality_contexts == Counter({context: QUALITY_PER_CONTEXT for context in CONTEXTS}))
    check("quality_schema", quality_schema)
    check("quality_probability_valid", probability_valid)
    check("quality_batch_shape_4x8", batch_shape_valid)
    check("quality_row_metrics_recomputed", recomputed_row_metrics)
    check("quality_projection_fields", projection_fields_valid)
    check("quality_hidden_diversity", all(int(row.get("unique_opponent_private_pairs", 0)) >= 28 for row in quality_rows))
    check("quality_hidden_clean", all(row.get("source_hidden_information_read_count") == 0 and row.get("source_opponent_cards_serialized") is False and row.get("source_unrevealed_deck_serialized") is False for row in quality_rows))
    check("quality_illegal_mass_zero", all(float(row.get("illegal_positive_probability_mass", math.nan)) == 0.0 for row in quality_rows))
    check("quality_terminal_within128", all(int(row.get("max_rollout_steps", 129)) <= 128 for row in quality_rows))

    recomputed_quality = quality_summary(quality_rows)
    registered_quality = metrics.get("quality", {})
    quality_exact = set(recomputed_quality) == set(registered_quality)
    for name in recomputed_quality:
        for key in ("rows", "batch_distribution_l1_mean", "batch_distribution_l1_p95", "states_top_action_agreement_ge_0_75_fraction", "passes"):
            if isinstance(recomputed_quality[name][key], bool):
                quality_exact = quality_exact and recomputed_quality[name][key] == registered_quality[name][key]
            else:
                quality_exact = quality_exact and close_float(recomputed_quality[name][key], registered_quality[name][key])
    check("quality_summary_recomputed_exact", quality_exact)
    check("quality_global_and_depth_gate", all(value["passes"] for value in recomputed_quality.values()) == bool(metrics.get("gates", {}).get("quality_global_and_each_depth")))

    repeats = metrics.get("same_seed_repeat_records", [])
    check("repeat_records_exact768", len(repeats) == REPEATS_TOTAL and len({int(item["row_id"]) for item in repeats}) == REPEATS_TOTAL)
    check("repeat_records_exact_match", all(item.get("matches") is True and item.get("original_same_seed_identity_sha256") == item.get("repeated_same_seed_identity_sha256") for item in repeats))
    check("repeat_counts_zero_failures", metrics.get("same_seed_repeats") == REPEATS_TOTAL and metrics.get("same_seed_failures") == 0)

    resource = metrics.get("resource", {})
    recomputed_sampling = {context: percentile(sample_times[context], 0.99) for context in CONTEXTS}
    recomputed_mc32 = {f"{depth}bb": percentile((row["row_wall_seconds"] for row in quality_rows if int(row["depth_bb"]) == depth), 0.99) for depth in DEPTHS}
    recomputed_serialization = percentile((row["asset_projection_serialization_gzip_seconds"] for row in quality_rows), 0.99)
    recomputed_uncompressed = percentile((row["asset_projection_uncompressed_bytes"] for row in quality_rows), 0.99)
    recomputed_gzip = percentile((row["asset_projection_gzip_bytes"] for row in quality_rows), 0.99)
    recomputed_projected_seconds = 1.25 * 20_000_000 / 8 * (max(recomputed_sampling.values()) + max(recomputed_mc32.values()) + recomputed_serialization)
    check("resource_sampling_p99_recomputed", all(close_float(recomputed_sampling[key], resource["context_sampling_p99_seconds"][key]) for key in CONTEXTS))
    check("resource_mc32_p99_recomputed", all(close_float(recomputed_mc32[key], resource["depth_mc32_p99_seconds"][key]) for key in recomputed_mc32))
    check("resource_serialization_p99_recomputed", close_float(recomputed_serialization, resource.get("serialization_gzip_p99_seconds")))
    check("resource_projected_seconds_recomputed", close_float(recomputed_projected_seconds, resource.get("projected_eight_worker_wall_seconds"), 1e-9))
    check("resource_projected_hours_recomputed", close_float(recomputed_projected_seconds / 3600.0, resource.get("projected_eight_worker_wall_hours"), 1e-12))
    check("resource_uncompressed_p99_recomputed", close_float(recomputed_uncompressed, resource.get("uncompressed_row_p99_bytes")))
    check("resource_gzip_p99_recomputed", close_float(recomputed_gzip, resource.get("gzip_row_p99_bytes")))
    check("resource_projected_compressed_recomputed", int(20_000_000 * recomputed_gzip) == int(resource.get("projected_compressed_bytes", -1)))
    check("resource_bounds", float(resource.get("projected_eight_worker_wall_hours", math.inf)) <= 168 and int(resource.get("projected_compressed_bytes", 10**20)) <= 100_000_000_000 and float(resource.get("uncompressed_row_p99_bytes", math.inf)) <= 8192 and float(resource.get("gzip_row_p99_bytes", math.inf)) <= 5000 and float(resource.get("qualification_wall_seconds", math.inf)) <= 21600 and float(resource.get("process_tree_peak_rss_mb", math.inf)) <= 4096)

    recomputed_gates = dict(metrics.get("gates", {}))
    check("gate_keys_exact", set(result.get("gates", {})) == set(recomputed_gates))
    check("result_and_metrics_gates_equal", result.get("gates") == recomputed_gates)
    expected_verdict = "PASS" if all(recomputed_gates.values()) else "NONPASS"
    check("verdict_exact", result.get("verdict") == expected_verdict)
    expected_classification = "FA002_Q01_PASS_COMBINED_REACHABILITY_MC32_QUALITY_RESOURCE" if expected_verdict == "PASS" else "FA002_Q01_NONPASS_COMBINED_REACHABILITY_MC32_QUALITY_RESOURCE"
    check("classification_exact", result.get("classification") == expected_classification)
    check("next_exact", result.get("next_if_pass") == "SEPARATE_ASSET_GENERATOR_IMPLEMENTATION_AND_INDEPENDENT_IMPLEMENTATION_AUDIT_ONLY" and result.get("next_if_nonpass") == "FA002_QUALIFICATION_SCIENTIFIC_NONPASS_RETURN_TO_ROUTE_RANKING_NO_CORRECTED_IDENTITY")
    check("strength_l0", result.get("strength") == "L0")

    failures = [name for name, passed in checks.items() if not passed]
    audit_result = {
        "schema_version": "v5.fa002.q01.result_audit.v1",
        "audited_at_epoch": time.time(),
        "program_id": PROGRAM_ID,
        "qualification_id": QUALIFICATION_ID,
        "overall": "PASS" if not failures else "FAIL_CLOSED",
        "classification": "FA002_Q01_RESULT_AUDIT_PASS" if not failures else "FA002_Q01_RESULT_AUDIT_FAIL_CLOSED",
        "qualification_verdict": result.get("verdict"),
        "result_path": str(paths["root"] / "result.json"),
        "result_sha256": sha256_file(paths["root"] / "result.json"),
        "implementation_audit_sha256": args.implementation_audit_sha256,
        "checks": checks,
        "check_count": len(checks),
        "pass_count": sum(checks.values()),
        "fail_count": len(failures),
        "failures": failures,
        "audit_wall_seconds": time.perf_counter() - started,
        "training_or_behavior_authority": "NONE_RESULT_JUDGMENT_REQUIRED",
        "official_hands": 0,
        "strength": "L0",
    }
    audit_path = paths["root"] / "result_audit.json"
    write_json_exclusive(audit_path, audit_result)
    print(canonical_json({"overall": audit_result["overall"], "audit": str(audit_path), "audit_sha256": sha256_file(audit_path), "checks": f"{audit_result['pass_count']}/{audit_result['check_count']}"}))
    return 0 if not failures else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--preregistration", required=True)
    parser.add_argument("--preregistration-audit", required=True)
    parser.add_argument("--implementation-audit", required=True)
    parser.add_argument("--implementation-audit-sha256", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return audit(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
