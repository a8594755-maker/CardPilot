"""Independent result auditor for the identity-bound RS002 qualification."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "81b61579f99755eb755d8c3c1905c22f"
QUAL_ROOT = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_qualification_{TOKEN}_20260722"
PREREG = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_preregistration_{TOKEN}_20260722.json"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_preregistration_audit_{TOKEN}_20260722.json"
IMPL_AUDIT = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_implementation_audit_{TOKEN}_20260722.json"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"
CHECKPOINT_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
PREREG_SHA256 = "93316de07812e6801cd6c83ddb7082b21841b981115a11c42ec3215c6b4563c7"
PREREG_AUDIT_SHA256 = "e346a5b56ed4b5dd7239e6726ed2f5082d9e7a8e711cf26f2bd14e85661ea4bd"
QUALIFICATION_NONCE = "RS002_QUALIFICATION_2036972294"
LCB_Z = 1.6448536269514722
FORBIDDEN_KEYS = {"opp_hole", "action_move", "action_amount", "winnings_hero", "showdown"}
EXPECTED_PREAUDIT_FILES = {
    "invocation.json",
    "interface_states.jsonl.gz",
    "witnessed_reconstruction.jsonl.gz",
    "resolution_rows.jsonl.gz",
    "repeat_rows.jsonl.gz",
    "fault_rows.jsonl.gz",
    "metrics.json",
    "result.json",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_gzip_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            try:
                rows.append(json.loads(line))
            except Exception as exc:
                raise RuntimeError(f"invalid_jsonl:{path.name}:{number}:{exc}") from exc
    return rows


def forbidden_paths(value: Any, at: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                found.append(f"{at}.{key}")
            found.extend(forbidden_paths(child, f"{at}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(forbidden_paths(child, f"{at}[{index}]"))
    return found


def exact_float(left: float, right: float, tolerance: float = 1e-12) -> bool:
    return math.isfinite(float(left)) and math.isfinite(float(right)) and abs(float(left) - float(right)) <= tolerance


def write_exclusive(path: Path, value: dict[str, Any]) -> None:
    data = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(data)


def audit(root: Path, implementation_audit_sha256: str) -> tuple[dict[str, Any], bool]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    check("root_exact", root.resolve(strict=False) == QUAL_ROOT.resolve(strict=False), str(root.resolve(strict=False)))
    check("prereg_hash_exact", PREREG.is_file() and sha256_file(PREREG) == PREREG_SHA256)
    check("prereg_audit_hash_exact", PREREG_AUDIT.is_file() and sha256_file(PREREG_AUDIT) == PREREG_AUDIT_SHA256)
    check("implementation_audit_hash_exact", IMPL_AUDIT.is_file() and sha256_file(IMPL_AUDIT) == implementation_audit_sha256)
    impl = read_json(IMPL_AUDIT)
    check("implementation_audit_pass", impl.get("classification") == "PASS / RS002_IMPLEMENTATION_AUDIT_PASS_ONE_QUALIFICATION_READY_ONLY")
    files = {path.name for path in root.iterdir() if path.is_file()} if root.is_dir() else set()
    check("preaudit_file_set_exact", files == EXPECTED_PREAUDIT_FILES, sorted(files))
    invocation = read_json(root / "invocation.json")
    metrics = read_json(root / "metrics.json")
    result = read_json(root / "result.json")
    interface = read_gzip_rows(root / "interface_states.jsonl.gz")
    witness = read_gzip_rows(root / "witnessed_reconstruction.jsonl.gz")
    resolution = read_gzip_rows(root / "resolution_rows.jsonl.gz")
    repeats = read_gzip_rows(root / "repeat_rows.jsonl.gz")
    faults = read_gzip_rows(root / "fault_rows.jsonl.gz")
    check("invocation_nonce_exact", invocation.get("nonce") == QUALIFICATION_NONCE)
    check("invocation_root_exact", Path(invocation.get("root", "")).resolve(strict=False) == QUAL_ROOT.resolve(strict=False))
    check("invocation_authority_exact", invocation.get("preregistration_sha256") == PREREG_SHA256 and invocation.get("preregistration_audit_sha256") == PREREG_AUDIT_SHA256 and invocation.get("implementation_audit_sha256") == implementation_audit_sha256)
    check("invocation_frozen_inputs_19", invocation.get("frozen_inputs_exact") == 19)
    check("invocation_no_network", invocation.get("network_or_slumbot_calls") == 0)
    check("checkpoint_before_exact", invocation.get("checkpoint_sha256_before") == CHECKPOINT_SHA256)
    check("checkpoint_current_exact", sha256_file(CHECKPOINT) == CHECKPOINT_SHA256)
    check("row_counts_exact", [len(interface), len(witness), len(resolution), len(repeats), len(faults)] == [8192, 6921, 1280, 192, 128], [len(interface), len(witness), len(resolution), len(repeats), len(faults)])
    interface_cells = Counter((row.get("street"), row.get("hero_player"), row.get("pot_band")) for row in interface if row.get("street") != "preflop")
    check("interface_preflop_2048", sum(row.get("street") == "preflop" for row in interface) == 2048)
    check("interface_24_cells_256", len(interface_cells) == 24 and set(interface_cells.values()) == {256}, dict(sorted((str(key), value) for key, value in interface_cells.items())))
    line_coverage = Counter(label for row in interface for label in row.get("line_labels", []))
    required_lines = {"UNOPENED_OR_CHECKED_TO", "FACING_BET", "AFTER_BET_CALL", "FACING_RAISE", "MULTIRAISE_BELOW_ALLIN", "FACING_ALLIN_WHEN_LEGAL"}
    check("line_coverage_complete", required_lines.issubset(line_coverage), dict(line_coverage))
    witness_counts = Counter((row.get("street"), row.get("hero_player")) for row in witness)
    check("witness_street_position_coverage", set(witness_counts) == {(street, player) for street in ("flop", "turn", "river") for player in (0, 1)}, dict(sorted((str(key), value) for key, value in witness_counts.items())))
    unsafe = []
    for group_name, rows in (("interface", interface), ("witness", witness), ("resolution", resolution), ("repeat", repeats), ("fault", faults)):
        for index, row in enumerate(rows):
            found = forbidden_paths(row)
            if found:
                unsafe.append({"group": group_name, "index": index, "paths": found[:5]})
                if len(unsafe) >= 10:
                    break
    check("zero_forbidden_keys", not unsafe, unsafe)
    mapping_violations = 0
    illegal_mass = 0.0
    distinct_failures = 0
    common_failures = 0
    statistics_failures: list[str] = []
    selection_failures: list[str] = []
    error_fallbacks = 0
    changes = 0
    nonfallback = 0
    for index, row in enumerate(resolution):
        legal = [int(slot) for slot in row.get("legal_slots", [])]
        baseline = int(row.get("baseline_slot", -1))
        selected = int(row.get("selected_slot", -1))
        if baseline not in legal or selected not in legal:
            selection_failures.append(f"illegal:{index}")
        mapping_violations += int(row.get("root_mapping_violation_count", 0))
        illegal_mass += float(row.get("illegal_selected_action_mass", 0.0))
        if row.get("error_fallback"):
            error_fallbacks += 1
            if selected != baseline:
                selection_failures.append(f"fallback_not_baseline:{index}")
            continue
        nonfallback += 1
        if selected != baseline:
            changes += 1
        det = row.get("determinizations", {})
        if det.get("sample_count") != 32 or det.get("distinct_pair_count") != 32 or len(det.get("pair_commitments_sha256", [])) != 32 or len(set(det.get("pair_commitments_sha256", []))) != 32:
            distinct_failures += 1
        if row.get("common_determinizations_across_root_actions") is not True:
            common_failures += 1
        stats = row.get("paired_statistics_by_slot", {})
        eligible: list[int] = []
        for slot in legal:
            stat = stats.get(str(slot))
            if not isinstance(stat, dict):
                statistics_failures.append(f"missing:{index}:{slot}")
                continue
            differences = [float(value) for value in stat.get("paired_differences_bb", [])]
            if len(differences) != 32:
                statistics_failures.append(f"n32:{index}:{slot}")
                continue
            mean = statistics.fmean(differences)
            sd = statistics.stdev(differences)
            se = sd / math.sqrt(32)
            lcb = mean - LCB_Z * se
            if not all((exact_float(mean, stat.get("mean_difference_bb", math.nan)), exact_float(sd, stat.get("sample_sd_bb", math.nan)), exact_float(se, stat.get("standard_error_bb", math.nan)), exact_float(lcb, stat.get("lcb95_bb", math.nan)))):
                statistics_failures.append(f"math:{index}:{slot}")
            if slot != baseline and lcb > 0.0:
                eligible.append(slot)
        if eligible:
            expected = max(eligible, key=lambda slot: (float(stats[str(slot)]["mean_difference_bb"]), float(stats[str(slot)]["lcb95_bb"]), -slot))
            if selected != expected or row.get("selection_reason") != "POSITIVE_PAIRED_LCB95":
                selection_failures.append(f"positive_rule:{index}:{selected}:{expected}")
        elif selected != baseline or row.get("selection_reason") != "LCB_NO_CHANGE":
            selection_failures.append(f"nochange_rule:{index}")
    check("all32_distinct_pairs", distinct_failures == 0, distinct_failures)
    check("common_determinizations_all_actions", common_failures == 0, common_failures)
    check("paired_statistics_recomputed_exact", not statistics_failures, statistics_failures[:20])
    check("selection_rule_recomputed_exact", not selection_failures, selection_failures[:20])
    check("zero_mapping_violations", mapping_violations == 0, mapping_violations)
    check("zero_illegal_selected_mass", illegal_mass == 0.0, illegal_mass)
    repeat_failures: list[str] = []
    repeat_fields = ("state_identity_sha256", "baseline_slot", "selected_slot", "selection_reason", "paired_statistics_by_slot", "rollout_trace_sha256", "decision_trace_sha256")
    for row in repeats:
        source_index = int(row.get("source_resolution_index", -1))
        if not 0 <= source_index < len(resolution):
            repeat_failures.append("source_index")
            continue
        source = resolution[source_index]
        if row.get("exact_repeat_match") is not True or any(row.get(key) != source.get(key) for key in repeat_fields):
            repeat_failures.append(str(source_index))
    check("repeats_192_bit_exact", len(repeats) == 192 and not repeat_failures, repeat_failures[:20])
    fault_failures = [index for index, row in enumerate(faults) if row.get("baseline_returned_exact") is not True or row.get("selected_slot") != row.get("baseline_slot")]
    check("faults_128_baseline_exact", len(faults) == 128 and not fault_failures, fault_failures[:20])
    latency = metrics.get("decision_latency_seconds", {})
    output_bytes = sum(path.stat().st_size for path in root.iterdir() if path.is_file())
    recomputed_gates = {
        "synthetic_interface_8192_exact": len(interface) == 8192,
        "synthetic_preflop_2048_exact": sum(row.get("street") == "preflop" for row in interface) == 2048,
        "synthetic_postflop_6144_exact": sum(row.get("street") != "preflop" for row in interface) == 6144,
        "witness_public_reconstruction_6921_exact": len(witness) == 6921,
        "zero_forbidden_output_keys": not unsafe,
        "resolution_rows_1280_exact": len(resolution) == 1280,
        "all32_distinct_pairs": distinct_failures == 0,
        "common_determinizations_all_actions": common_failures == 0,
        "zero_root_mapping_violations": mapping_violations == 0,
        "zero_illegal_selected_mass": illegal_mass == 0.0,
        "same_seed_repeats_192_exact": len(repeats) == 192 and not repeat_failures,
        "fault_fallbacks_128_baseline_exact": len(faults) == 128 and not fault_failures,
        "fallback_rate_le_0_02": error_fallbacks / max(1, len(resolution)) <= 0.02,
        "action_change_rate_ge_0_01": changes / max(1, nonfallback) >= 0.01,
        "checkpoint_hash_unchanged": metrics.get("checkpoint_sha256_before") == metrics.get("checkpoint_sha256_after") == CHECKPOINT_SHA256 and sha256_file(CHECKPOINT) == CHECKPOINT_SHA256,
        "cold_load_le_60": float(metrics.get("model_cold_load_seconds", math.inf)) <= 60.0,
        "latency_p50_le_2_5": float(latency.get("p50", math.inf)) <= 2.5,
        "latency_p95_le_8": float(latency.get("p95", math.inf)) <= 8.0,
        "latency_p99_le_15": float(latency.get("p99", math.inf)) <= 15.0,
        "latency_max_le_20": float(latency.get("max", math.inf)) <= 20.0,
        "quick5k_projection_le_12h": float(metrics.get("projected_quick5k_resolver_compute_hours", math.inf)) <= 12.0,
        "qualification_wall_le_10800": float(metrics.get("qualification_wall_seconds", math.inf)) <= 10800.0,
        "rss_le_16384": float(metrics.get("process_rss_mib", math.inf)) <= 16384.0,
        "gpu_peak_le_11264": float(metrics.get("gpu_peak_allocated_mib", math.inf)) <= 11264.0,
        "output_le_5gib": output_bytes <= 5368709120,
    }
    check("registered_gates_exact", result.get("gates") == recomputed_gates, {"registered": result.get("gates"), "recomputed": recomputed_gates})
    expected_overall = "PASS" if all(recomputed_gates.values()) else "NONPASS"
    check("overall_classification_exact", result.get("overall") == expected_overall and result.get("pass_count") == sum(recomputed_gates.values()) and result.get("gate_count") == len(recomputed_gates), expected_overall)
    check("metrics_counts_exact", [metrics.get("interface_rows"), metrics.get("witness_rows"), metrics.get("resolution_rows"), metrics.get("repeat_rows"), metrics.get("fault_rows")] == [8192, 6921, 1280, 192, 128])
    check("metrics_rates_exact", exact_float(metrics.get("qualified_error_fallback_rate", math.nan), error_fallbacks / 1280) and exact_float(metrics.get("selected_slot_change_rate_nonfallback", math.nan), changes / max(1, nonfallback)))
    check("result_metrics_hash_exact", result.get("metrics_sha256") == sha256_file(root / "metrics.json"))
    manifest = result.get("output_manifest_before_result", {})
    manifest_ok = set(manifest) == EXPECTED_PREAUDIT_FILES - {"result.json"}
    if manifest_ok:
        for name, item in manifest.items():
            path = root / name
            manifest_ok = manifest_ok and path.stat().st_size == item.get("bytes") and sha256_file(path) == item.get("sha256")
    check("pre_result_manifest_exact", manifest_ok)
    check("result_no_network_or_quick5k", result.get("network_or_slumbot_calls") == 0 and result.get("quick5k_launched") is False and result.get("strength_claim") == "FORBIDDEN")
    passed = all(item["pass"] for item in checks)
    audit_result = {
        "schema_version": "v5.rs002.qualification_result_audit.v1",
        "classification": (
            f"PASS / RS002_RESULT_AUDIT_PASS_QUALIFICATION_{expected_overall}_EXACT_JUDGMENT_READY"
            if passed else "FAIL_CLOSED / RS002_RESULT_AUDIT_INTEGRITY_FAILURE_NO_QUICK5K"
        ),
        "overall": "PASS" if passed else "FAIL_CLOSED",
        "qualification_judgment": expected_overall if passed else "UNTRUSTED",
        "root": str(root.resolve(strict=False)),
        "implementation_audit_sha256": implementation_audit_sha256,
        "result_sha256": sha256_file(root / "result.json"),
        "checks": checks,
        "check_count": len(checks),
        "pass_count": sum(item["pass"] for item in checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "recomputed_gates": recomputed_gates,
        "quick5k_eligibility": "ELIGIBLE_LATER_ONLY" if passed and expected_overall == "PASS" else "FORBIDDEN",
        "quick5k_launched": False,
        "official_hands": 0,
        "strength": "L0",
    }
    return audit_result, passed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--implementation-audit-sha256", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    audit_path = root / "result_audit.json"
    if audit_path.exists():
        raise RuntimeError("result_audit_already_exists")
    try:
        value, passed = audit(root, args.implementation_audit_sha256)
    except Exception as exc:
        value = {
            "schema_version": "v5.rs002.qualification_result_audit.v1",
            "classification": "FAIL_CLOSED / RS002_RESULT_AUDIT_EXCEPTION_NO_QUICK5K",
            "overall": "FAIL_CLOSED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "quick5k_eligibility": "FORBIDDEN",
        }
        passed = False
    write_exclusive(audit_path, value)
    print(canonical_json({"classification": value["classification"], "pass_count": value.get("pass_count", 0), "check_count": value.get("check_count", 0)}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
