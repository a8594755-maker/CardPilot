#!/usr/bin/env python3
"""Independent raw parity evidence audit."""
from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    analysis = json.loads((HERE / "analysis.json").read_text(encoding="utf-8"))
    raw = HERE / "raw_parity.jsonl.gz"
    counts: Counter[str] = Counter()
    streets: Counter[int] = Counter()
    last_row = -1
    with gzip.open(raw, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["row"] != last_row + 1:
                raise AssertionError("non-contiguous raw rows")
            last_row = row["row"]
            counts["states"] += 1
            streets[int(row["street"])] += 1
            for key in (
                "exact_action_parity", "exact_legacy_slot_parity", "exact_v6_legality"
            ):
                counts[key] += int(bool(row[key]))
    checks = {
        "raw_sha_matches": sha256_file(raw) == analysis["raw_parity_sha256"],
        "counts_match": dict(counts) == analysis["counts"],
        "street_quota_match": [streets[i] for i in range(4)] == analysis["design"]["street_quotas"],
        "all_exact": all(counts[key] == counts["states"] for key in (
            "exact_action_parity", "exact_legacy_slot_parity", "exact_v6_legality"
        )),
        "no_training_hands": analysis["environment_training_hands"] == 0,
        "no_slumbot_hands": analysis["slumbot_hands"] == 0,
    }
    result = {
        "schema": "cardpilot.legacy_observation_bridge_parity_audit.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "counts": dict(counts),
        "raw_sha256": sha256_file(raw),
    }
    (HERE / "evidence_audit.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
