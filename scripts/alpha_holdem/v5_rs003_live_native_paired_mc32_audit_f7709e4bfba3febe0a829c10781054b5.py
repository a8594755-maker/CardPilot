"""Independent content audit for the one frozen RS003 qualification result."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "f7709e4bfba3febe0a829c10781054b5"
IDENTITY = "f7709e4bfba3febe0a829c10781054b557ead7d419428dc06736316980679fdb"
PREREG = ROOT / "reports" / f"v5_rs003_live_native_paired_mc32_preregistration_{TOKEN}_20260722.json"
PREREG_SHA = "19a75a06e77919bf6cc9bc8bd871b70107a3ec2ee38cb3ccb8fad456788c706b"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs003_live_native_paired_mc32_preregistration_audit_{TOKEN}_20260722.json"
PREREG_AUDIT_SHA = "f411bd44f0aa96d5692c0469db7a61f464939d9a340d3b5b72062bda10a0744e"
RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs003_live_native_paired_mc32_{TOKEN}.py"
RUNNER_SHA = "0021463e9905a923d14f1c93f95ecd68f7294d907b963e016fb60b0f3eb1b334"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"
CHECKPOINT_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
QUAL_ROOT = ROOT / "reports" / f"v5_rs003_live_native_paired_mc32_qualification_{TOKEN}_20260722"
EXPECTED = {
    "invocation.json", "ledger_rows.jsonl.gz", "prefix_rows.jsonl.gz", "hero_live_interfaces.jsonl.gz",
    "synthetic_states.jsonl.gz", "resolution_rows.jsonl.gz", "repeat_rows.jsonl.gz", "fault_rows.jsonl.gz",
    "metrics.json", "result.json",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def write_exclusive(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        f.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--implementation-audit-sha256", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve(strict=False)
    if root != QUAL_ROOT.resolve(strict=False):
        raise RuntimeError("audit_root_identity_mismatch")
    output = root / "result_audit.json"
    if output.exists():
        raise RuntimeError("audit_output_already_exists")
    checks: dict[str, bool] = {}
    def check(name: str, value: bool) -> None:
        checks[name] = bool(value)

    check("prereg_sha", sha256_file(PREREG) == PREREG_SHA)
    check("prereg_audit_sha", sha256_file(PREREG_AUDIT) == PREREG_AUDIT_SHA)
    check("runner_sha", sha256_file(RUNNER) == RUNNER_SHA)
    check("checkpoint_sha", sha256_file(CHECKPOINT) == CHECKPOINT_SHA)
    present = {p.name for p in root.iterdir() if p.is_file()}
    check("files_exact_before_audit", present == EXPECTED)
    invocation = json.loads((root / "invocation.json").read_text(encoding="utf-8"))
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))
    metrics = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
    check("identity", invocation.get("identity_sha256") == IDENTITY == result.get("identity_sha256"))
    check("implementation_audit_sha", invocation.get("implementation_audit_sha256") == args.implementation_audit_sha256)
    check("network_forbidden", invocation.get("network") == "FORBIDDEN" and result.get("network_or_slumbot_hands") == 0)

    ledger = read_jsonl(root / "ledger_rows.jsonl.gz")
    prefixes = read_jsonl(root / "prefix_rows.jsonl.gz")
    interfaces = read_jsonl(root / "hero_live_interfaces.jsonl.gz")
    synthetic = read_jsonl(root / "synthetic_states.jsonl.gz")
    resolutions = read_jsonl(root / "resolution_rows.jsonl.gz")
    repeats = read_jsonl(root / "repeat_rows.jsonl.gz")
    faults = read_jsonl(root / "fault_rows.jsonl.gz")
    check("ledger_count", len(ledger) == 29878)
    check("ledger_all_exact", all(x.get("exact") is True for x in ledger))
    check("prefix_count", len(prefixes) == 584)
    check("prefix_all_exact", all(x.get("reencode_exact") is True for x in prefixes))
    check("interface_count", len(interfaces) == 6921)
    check("interface_all_exact", all(x.get("bit_exact") is True for x in interfaces))
    check("interface_forbidden_zero", all(x.get("forbidden_source_field_read_count") == 0 for x in interfaces))
    check("interface_increment_executable", all(x.get("baseline_increment") is not None and x.get("table9", [None] * 9)[int(x["baseline_slot"])] == x["baseline_increment"] for x in interfaces))
    check("synthetic_count", len(synthetic) == 8192)
    check("synthetic_all_exact", all(
        x.get("ledger_exact") is True
        and x.get("mirror_exact") is True
        and x.get("interface_exact") is True
        and isinstance(x.get("interface_sha256"), str)
        and len(x["interface_sha256"]) == 64
        and int(x.get("mask_sum", -1)) == len(x.get("legal_slots", []))
        for x in synthetic
    ))
    check("resolution_count", len(resolutions) == 1280)
    check("resolution_indices", [x.get("resolution_index") for x in resolutions] == list(range(1280)))
    nonfallback = [x for x in resolutions if not x.get("error_fallback")]
    check("resolution_distinct_pairs", all(x.get("determinizations", {}).get("distinct_pair_count") == 32 for x in nonfallback))
    check("resolution_live_increment", all(x.get("selected_increment") is not None and x.get("live_table9", [None] * 9)[int(x["selected_slot"])] == x["selected_increment"] for x in resolutions))
    check("resolution_illegal_zero", sum(float(x.get("illegal_selected_action_mass", 1)) for x in resolutions) == 0.0)
    check("repeat_count", len(repeats) == 192)
    check("repeat_all_exact", all(x.get("exact") is True for x in repeats))
    check("fault_count", len(faults) == 128)
    check("fault_all_baseline", all(x.get("baseline_exact") is True and x.get("error_fallback") is True for x in faults))

    expected_metrics = {
        "ledger_rows": 29878, "distinct_prefixes": 584, "adjacent_transitions": 24878,
        "hero_live_interfaces": 6921, "synthetic_states": 8192, "resolution_rows": 1280,
        "repeat_rows": 192, "repeat_exact": 192, "fault_rows": 128, "fault_baseline_exact": 128,
    }
    for key, value in expected_metrics.items():
        check("metric_" + key, metrics.get(key) == value)
    check("fallback_rate", math.isclose(metrics.get("qualified_fallback_rate", 99), sum(bool(x.get("error_fallback")) for x in resolutions) / 1280, rel_tol=0, abs_tol=1e-15) and metrics["qualified_fallback_rate"] <= .02)
    changes = sum(x.get("selected_slot") != x.get("baseline_slot") for x in nonfallback)
    check("action_change_rate", metrics.get("selected_slot_change_count") == changes and math.isclose(metrics.get("selected_slot_change_rate", -1), changes / max(1, len(nonfallback)), rel_tol=0, abs_tol=1e-15) and metrics["selected_slot_change_rate"] >= .01)
    latency = metrics.get("latency_seconds", {})
    check("latency", latency.get("p50", 99) <= 2.5 and latency.get("p95", 99) <= 8 and latency.get("p99", 99) <= 15 and latency.get("max", 99) <= 20)
    check("resources", metrics.get("projected_quick5k_hours", 99) <= 12 and metrics.get("model_cold_load_seconds", 99) <= 60 and metrics.get("wall_seconds", 99999) <= 10800 and metrics.get("process_rss_mib", 99999) <= 16384 and metrics.get("gpu_peak_allocated_mib", 99999) <= 11264)
    check("result_gate_count", result.get("check_count") == 21 and result.get("pass_count") == 21 and len(result.get("gates", {})) == 21 and all(result.get("gates", {}).values()))
    check("result_classification", result.get("classification") == "PASS / RS003_LIVE_NATIVE_QUALIFICATION_PASS")
    check("checkpoint_result", result.get("checkpoint_sha256") == CHECKPOINT_SHA)
    check("quick5k_pending_only", result.get("quick5k_authority") == "PENDING_INDEPENDENT_RESULT_AUDIT")
    total_bytes = sum(p.stat().st_size for p in root.iterdir() if p.is_file())
    check("output_bytes", total_bytes <= 5_368_709_120)

    passed = sum(checks.values())
    classification = "PASS / RS003_INDEPENDENT_RESULT_AUDIT_PASS_QUICK5K_ELIGIBLE" if passed == len(checks) else "FAIL_CLOSED / RS003_INDEPENDENT_RESULT_AUDIT_NONPASS_NO_QUICK5K"
    report = {
        "schema_version": "v5.rs003.qualification.result_audit.v1",
        "classification": classification,
        "identity_sha256": IDENTITY,
        "implementation_audit_sha256": args.implementation_audit_sha256,
        "checks": checks,
        "pass_count": passed,
        "check_count": len(checks),
        "fail_count": len(checks) - passed,
        "file_sha256": {name: sha256_file(root / name) for name in sorted(EXPECTED)},
        "counts": {"ledger": len(ledger), "prefixes": len(prefixes), "interfaces": len(interfaces), "synthetic": len(synthetic), "resolutions": len(resolutions), "repeats": len(repeats), "faults": len(faults)},
        "quick5k_authority": "ONE_COMPLETE_PREREGISTERED_DIRECTIONAL_WINDOW_NEXT_ONLY" if passed == len(checks) else "NONE",
        "strength": "L0",
        "network_or_slumbot_hands": 0,
    }
    write_exclusive(output, report)
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
