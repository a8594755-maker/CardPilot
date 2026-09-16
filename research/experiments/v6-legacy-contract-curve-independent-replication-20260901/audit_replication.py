#!/usr/bin/env python3
"""Independent raw audit of the fresh-seed iter08/iter16 replication."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DISCOVERY = ROOT / "research/experiments/v6-legacy-contract-mixed-league-65k-pilot-20260901"
CANDIDATES = ("parent", "iter08", "iter16")
ANCHORS = ("bridge_smoke", "procedural_soup", "raw_actor", "source_kl_temperature")
Z = 2.241402727604947


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stats(values: list[float], z: float) -> dict:
    mean = statistics.fmean(values)
    se = statistics.stdev(values) / math.sqrt(len(values))
    return {"samples": len(values), "mean": mean, "ci": [mean - z * se, mean + z * se]}


def main() -> None:
    analysis = json.loads((HERE / "replication_analysis.json").read_text(encoding="utf-8"))
    checks = {}
    data = {}
    hashes = {}
    for candidate in CANDIDATES:
        for anchor in ANCHORS:
            cell = HERE / "replication" / f"{candidate}__{anchor}"
            raw_path = cell / "pairs.jsonl"
            summary_path = cell / "summary.json"
            raw = rows(raw_path)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            data[(candidate, anchor)] = raw
            hashes[f"{candidate}__{anchor}/pairs.jsonl"] = sha256_file(raw_path)
            hashes[f"{candidate}__{anchor}/summary.json"] = sha256_file(summary_path)
            checks[f"cell_{candidate}_{anchor}"] = (
                len(raw) == 4096
                and [row["pair_index"] for row in raw] == list(range(4096))
                and all(len(row["candidate_rewards_bb"]) == 2 for row in raw)
                and summary["pairs"] == 4096
                and summary["evaluation_hands"] == 8192
                and summary["pairs_sha256"] == sha256_file(raw_path)
                and summary["candidate_sha256"] == analysis["checkpoint_hashes"]["candidates"][candidate]
                and summary["anchor_sha256"] == analysis["checkpoint_hashes"]["anchors"][anchor]
            )
    for anchor in ANCHORS:
        parent_decks = [row["deck"] for row in data[("parent", anchor)]]
        checks[f"common_decks_{anchor}"] = all(
            [row["deck"] for row in data[(candidate, anchor)]] == parent_decks
            for candidate in CANDIDATES[1:]
        )
        discovery_decks = [
            row["deck"]
            for row in rows(DISCOVERY / "panel" / f"parent__{anchor}" / "pairs.jsonl")
        ]
        checks[f"fresh_from_discovery_{anchor}"] = not set(map(tuple, parent_decks)) & set(map(tuple, discovery_decks))

    comparisons = {}
    eligible = []
    for candidate in CANDIDATES[1:]:
        per_anchor = {}
        pooled = []
        seats = [[], []]
        for anchor in ANCHORS:
            candidate_rows = data[(candidate, anchor)]
            parent_rows = data[("parent", anchor)]
            deltas = [
                100.0 * (left["candidate_pair_average_bb"] - right["candidate_pair_average_bb"])
                for left, right in zip(candidate_rows, parent_rows, strict=True)
            ]
            per_anchor[anchor] = stats(deltas, 1.96)
            pooled.extend(deltas)
            for seat in (0, 1):
                seats[seat].extend(
                    100.0 * (left["candidate_rewards_bb"][seat] - right["candidate_rewards_bb"][seat])
                    for left, right in zip(candidate_rows, parent_rows, strict=True)
                )
        pooled_stats = stats(pooled, Z)
        seat_stats = {str(seat): stats(seats[seat], Z) for seat in (0, 1)}
        positive = sum(row["mean"] > 0 for row in per_anchor.values())
        passed = positive >= 3 and pooled_stats["ci"][0] > 0 and all(row["mean"] >= 0 for row in seat_stats.values())
        comparisons[candidate] = {
            "per_anchor": per_anchor,
            "pooled_bonferroni_97_5": pooled_stats,
            "pooled_by_candidate_seat": seat_stats,
            "positive_anchors": positive,
            "promotion_gate": "PASS" if passed else "FAIL",
        }
        reported = analysis["comparisons_to_parent"][candidate]
        checks[f"summary_{candidate}"] = (
            abs(pooled_stats["mean"] - reported["pooled_bonferroni_97_5"]["mean_delta_bb100"]) < 1e-12
            and all(abs(a - b) < 1e-12 for a, b in zip(pooled_stats["ci"], reported["pooled_bonferroni_97_5"]["ci"]))
            and positive == reported["positive_anchors"]
            and ("PASS" if passed else "FAIL") == reported["promotion_gate"]
        )
        if passed:
            eligible.append(candidate)
    selected = max(eligible, key=lambda label: comparisons[label]["pooled_bonferroni_97_5"]["ci"][0], default=None)
    checks["selection"] = eligible == analysis["eligible_candidates"] and selected == analysis["selected_candidate"] == "iter16"
    result = {
        "schema": "cardpilot.legacy_contract_curve_replication_audit.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "comparisons_recomputed": comparisons,
        "eligible_candidates": eligible,
        "selected_candidate": selected,
        "cell_artifact_sha256": hashes,
        "analysis_sha256": sha256_file(HERE / "replication_analysis.json"),
        "evaluation_hands": 98_304,
        "slumbot_hands": 0,
    }
    (HERE / "replication_audit.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
