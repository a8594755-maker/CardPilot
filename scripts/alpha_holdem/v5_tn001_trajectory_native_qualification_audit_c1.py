"""Focused fresh correction for the TN001 result-auditor gate/value conflation.

The immutable parent audit already passed 24/25 independent checks.  Its sole failed
check required a scientifically failed qualification gate to be true.  This checker
independently establishes that the raw 96-state/3-cell evidence exactly implies the
registered NONPASS and that every other parent integrity check passed.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot\reports\tn001_trajectory_native_qualification_20260722")
PARENT_AUDIT_SHA256 = "14949ba00598b4f1528a7ce427a73297c4a92155ec96cd9408368db529c6f739"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as fh:
        json.dump(value, fh, indent=2, ensure_ascii=False, allow_nan=False)
        fh.write("\n")


def main() -> int:
    output = ROOT / "result_audit_c1.json"
    if output.exists():
        raise RuntimeError("immutable_c1_audit_exists")
    parent_path = ROOT / "result_audit.json"
    result_path = ROOT / "result.json"
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    metrics = json.loads((ROOT / "raw_metrics.json").read_text(encoding="utf-8"))
    rows = load_jsonl(ROOT / "constructive_witnesses.jsonl")
    counts = Counter(row["cell"] for row in rows)
    raw_names = (
        "constructive_witnesses.jsonl", "discovery_states.jsonl", "quality_rows.jsonl",
        "hidden_invariance_pairs.jsonl", "raw_metrics.json", "input_manifest.json",
        "execution_manifest.json",
    )
    checks = {
        "parent_audit_hash_exact": sha256_file(parent_path) == PARENT_AUDIT_SHA256,
        "parent_audit_only_failed_gate_value_conflation": (
            parent["overall"] == "FAIL_CLOSED"
            and parent["checks_total"] == 25 and parent["checks_passed"] == 24
            and parent["checks_failed"] == ["constructive_768_24x32"]
            and all(value is True for name, value in parent["checks"].items() if name != "constructive_768_24x32")
        ),
        "result_hash_bound_by_parent": sha256_file(result_path) == parent["result_sha256"],
        "all_raw_hashes_still_match_result": all(
            sha256_file(ROOT / name) == result["files"][name.rsplit(".", 1)[0]]["sha256"]
            for name in raw_names
        ),
        "constructive_rows_independent_96": len(rows) == 96 == metrics["constructive_states"],
        "constructive_cells_independent_3x32": len(counts) == 3 and set(counts.values()) == {32}
                                                   and metrics["witness_cells"] == 3,
        "witness_failures_independent_positive": metrics["witness_failures"] == 2688,
        "runner_constructive_gate_false_exact": result["gates"]["constructive_states_768"] is False,
        "runner_witness_gate_false_exact": result["gates"]["witnesses_24_of_24"] is False,
        "temperature_gate_false_exact": (
            result["measurements"]["selected_temperature"] is None
            and result["gates"]["global_temperature_selected"] is False
        ),
        "runner_nonpass_exactly_implied": (
            result["verdict"] == "NONPASS"
            and result["classification"] == "TN001_NONPASS_TRAJECTORY_NATIVE_INFOSET_MC32_OR_BOUNDED_DISCOVERY_FEASIBILITY"
            and not all(result["gates"].values())
        ),
        "scientific_output_not_reexecuted": True,
        "exact_registered_judgment": result["authority"]["nonpass_next"] == "RERANK_TO_OPPONENT_LEAGUE_FAMILY",
    }
    failed = [name for name, value in checks.items() if not value]
    payload = {
        "schema_version": "v5.tn001.trajectory_native_qualification.result_audit_c1.v1",
        "classification": "TN001C1_RESULT_AUDIT_PASS_NONPASS_EXACT_JUDGMENT" if not failed else "TN001C1_RESULT_AUDIT_FAIL_CLOSED",
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "correction_scope": "CHECKER_ONLY_GATE_VALUE_CONFLATION_NO_SCIENTIFIC_REEXECUTION",
        "parent_audit_path": str(parent_path), "parent_audit_sha256": sha256_file(parent_path),
        "result_path": str(result_path), "result_sha256": sha256_file(result_path),
        "checks": checks, "checks_passed": sum(checks.values()), "checks_total": len(checks),
        "checks_failed": failed,
        "qualification_verdict": result["verdict"],
        "exact_judgment": "TN001_NONPASS_RERANK_TO_OPPONENT_LEAGUE_NO_REPAIR_OR_BOUND_EXTENSION" if not failed else "FAIL_CLOSED",
        "official_hands": 0, "strength": "L0",
    }
    write_json(output, payload)
    print(canonical_json({"overall": payload["overall"], "checks": f"{payload['checks_passed']}/{payload['checks_total']}",
                          "judgment": payload["exact_judgment"], "audit": str(output)}))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
