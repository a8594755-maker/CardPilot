#!/usr/bin/env python3
"""Independently recompute the paired drift summary from its raw evidence."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    analysis_path = HERE / "drift_analysis.json"
    raw_path = HERE / "drift_raw.jsonl.gz"
    session_audit_path = HERE / "training/session_audit.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    rows = []
    with gzip.open(raw_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            rows.append(json.loads(line))
    mean_tv = sum(row["tv"] for row in rows) / len(rows)
    disagreements = sum(bool(row["greedy_disagreement"]) for row in rows)
    street_counts = {
        str(street): sum(row["street"] == street for row in rows)
        for street in range(4)
    }
    raw_sha256 = sha256_file(raw_path)
    checks = {
        "raw_hash_matches": raw_sha256 == analysis["raw_sha256"],
        "row_count_matches": len(rows) == analysis["overall"]["states"],
        "mean_tv_matches": abs(mean_tv - analysis["overall"]["mean_tv"]) < 1e-15,
        "disagreements_match": disagreements == analysis["overall"]["greedy_disagreements"],
        "street_balance_matches": all(count == 12_500 for count in street_counts.values()),
        "analysis_passed": analysis["status"] == "PASS",
    }
    report = {
        "schema": "cardpilot.legacy_contract_ppo_drift_independent_audit.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "raw_sha256": raw_sha256,
        "rows": len(rows),
        "mean_tv": mean_tv,
        "greedy_disagreements": disagreements,
        "street_counts": street_counts,
        "analysis_sha256": sha256_file(analysis_path),
        "session_audit_sha256": sha256_file(session_audit_path),
    }
    (HERE / "drift_independent_audit.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
