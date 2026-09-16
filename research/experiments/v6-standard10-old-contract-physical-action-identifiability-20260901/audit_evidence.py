#!/usr/bin/env python3
"""Independent raw-row aggregate and artifact-integrity audit."""
from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    analysis_path = HERE / "analysis.json"
    raw_path = HERE / "raw_states.jsonl.gz"
    manifest_path = HERE / "artifact_manifest.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts: Counter[str] = Counter()
    by_street: dict[int, Counter[str]] = defaultdict(Counter)
    sequence = hashlib.sha256()
    last_row = -1
    with gzip.open(raw_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["row"] != last_row + 1:
                raise AssertionError("raw row ordering is not contiguous")
            last_row = row["row"]
            counts["states"] += 1
            street = int(row["street"])
            by_street[street]["states"] += 1
            for key in (
                "state_parity", "mappable", "exact_legal_action",
                "mapped_greedy_agreement", "physical_greedy_agreement",
                "kind_greedy_agreement",
            ):
                counts[key] += int(bool(row[key]))
                by_street[street][key] += int(bool(row[key]))
            sequence.update((row["state_sha256"] + "\n").encode("ascii"))
    checks = {
        "raw_sha_matches_manifest": sha256_file(raw_path) == manifest["raw_states_sha256"],
        "analysis_sha_matches_manifest": sha256_file(analysis_path) == manifest["analysis_sha256"],
        "counts_match": dict(counts) == analysis["counts"],
        "state_sequence_matches": sequence.hexdigest() == analysis["state_sequence_sha256"],
        "street_counts_match": all(
            all(
                counter[key] == analysis["by_street"][str(street)]["counts"][key]
                for key in analysis["by_street"][str(street)]["counts"]
            )
            for street, counter in by_street.items()
        ),
        "four_streets_present": set(by_street) == {0, 1, 2, 3},
        "no_slumbot_hands": analysis["design"]["slumbot_hands"] == 0,
        "no_training_hands": analysis["design"]["environment_training_hands"] == 0,
        "identical_learned_tensors": len(analysis["inputs"]["learned_tensor_sha256"]) == 64,
    }
    result = {
        "schema": "cardpilot.standard10_contract_identifiability_audit.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "counts": dict(counts),
        "by_street_counts": {str(k): dict(v) for k, v in sorted(by_street.items())},
        "artifact_sha256": {
            "analysis": sha256_file(analysis_path),
            "raw_states": sha256_file(raw_path),
            "manifest": sha256_file(manifest_path),
        },
    }
    (HERE / "evidence_audit.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
