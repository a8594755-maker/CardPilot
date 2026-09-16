#!/usr/bin/env python3
"""Independent raw-evidence audit for the drift and 2k-pair panel."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANDIDATES = ("parent", "iter04", "iter08", "iter12", "iter16")
ANCHORS = (
    "bridge_smoke",
    "procedural_soup",
    "raw_actor",
    "source_kl_temperature",
)
BONFERRONI_Z = 2.497705474412374


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def paired(values: list[float], z: float) -> dict:
    mean = statistics.fmean(values)
    se = statistics.stdev(values) / math.sqrt(len(values))
    return {
        "samples": len(values),
        "mean": mean,
        "ci": [mean - z * se, mean + z * se],
    }


def main() -> None:
    checks = {}
    drift_path = HERE / "curve_drift_analysis.json"
    drift_raw_path = HERE / "curve_drift_raw.jsonl.gz"
    drift = json.loads(drift_path.read_text(encoding="utf-8"))
    with gzip.open(drift_raw_path, "rt", encoding="utf-8") as handle:
        drift_rows = [json.loads(line) for line in handle]
    checks["drift_raw_hash"] = sha256_file(drift_raw_path) == drift["raw_sha256"]
    checks["drift_rows"] = len(drift_rows) == 50_000
    checks["drift_street_balance"] = all(
        sum(row["street"] == street for row in drift_rows) == 12_500
        for street in range(4)
    )
    drift_recomputed = {}
    for candidate in CANDIDATES[1:]:
        mean_tv = statistics.fmean(float(row[candidate]["tv"]) for row in drift_rows)
        disagreement = statistics.fmean(
            bool(row[candidate]["greedy_disagreement"]) for row in drift_rows
        )
        drift_recomputed[candidate] = {
            "mean_tv": mean_tv,
            "greedy_disagreement_rate": disagreement,
        }
        reported = drift["curve"][candidate]["overall"]
        checks[f"drift_summary_{candidate}"] = (
            abs(mean_tv - reported["mean_tv"]) < 1e-15
            and abs(disagreement - reported["greedy_disagreement_rate"]) < 1e-15
        )

    risk_path = HERE / "source_drift_analysis.json"
    risk_raw_path = HERE / "source_drift_raw.jsonl.gz"
    risk = json.loads(risk_path.read_text(encoding="utf-8"))
    checks["risk_raw_hash"] = sha256_file(risk_raw_path) == risk["raw_sha256"]
    with gzip.open(risk_raw_path, "rt", encoding="utf-8") as handle:
        risk_rows = [json.loads(line) for line in handle]
    checks["risk_rows"] = len(risk_rows) == 50_000
    checks["risk_high_rows"] = (
        sum(row["risk_band"] == "high_ge_30bb" for row in risk_rows)
        == risk["candidates"]["treatment"]["by_risk"]["high_ge_30bb"]["states"]
    )

    panel_path = HERE / "panel_analysis.json"
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    expected_pairs = int(panel["design"]["pairs_per_cell"])
    cell_rows = {}
    cell_hashes = {}
    for candidate in CANDIDATES:
        for anchor in ANCHORS:
            cell_dir = HERE / "panel" / f"{candidate}__{anchor}"
            raw_path = cell_dir / "pairs.jsonl"
            summary_path = cell_dir / "summary.json"
            rows = load_jsonl(raw_path)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            cell_rows[(candidate, anchor)] = rows
            cell_hashes[f"{candidate}__{anchor}/pairs.jsonl"] = sha256_file(raw_path)
            cell_hashes[f"{candidate}__{anchor}/summary.json"] = sha256_file(summary_path)
            checks[f"cell_{candidate}_{anchor}"] = (
                len(rows) == expected_pairs
                and [row["pair_index"] for row in rows]
                == list(range(expected_pairs))
                and all(len(row["candidate_rewards_bb"]) == 2 for row in rows)
                and sha256_file(raw_path) == summary["pairs_sha256"]
                and summary["candidate_sha256"]
                == panel["checkpoint_hashes"]["candidates"][candidate]
                and summary["anchor_sha256"]
                == panel["checkpoint_hashes"]["anchors"][anchor]
            )
    for anchor in ANCHORS:
        parent_decks = [row["deck"] for row in cell_rows[("parent", anchor)]]
        checks[f"common_decks_{anchor}"] = all(
            [row["deck"] for row in cell_rows[(candidate, anchor)]]
            == parent_decks
            for candidate in CANDIDATES[1:]
        )

    comparisons = {}
    for candidate in CANDIDATES[1:]:
        per_anchor = {}
        pooled_pair_deltas = []
        seat_deltas = [[], []]
        for anchor in ANCHORS:
            candidate_rows = cell_rows[(candidate, anchor)]
            parent_rows = cell_rows[("parent", anchor)]
            deltas = [
                100.0 * (
                    left["candidate_pair_average_bb"]
                    - right["candidate_pair_average_bb"]
                )
                for left, right in zip(candidate_rows, parent_rows, strict=True)
            ]
            per_anchor[anchor] = paired(deltas, 1.96)
            pooled_pair_deltas.extend(deltas)
            for seat in (0, 1):
                seat_deltas[seat].extend(
                    100.0 * (
                        left["candidate_rewards_bb"][seat]
                        - right["candidate_rewards_bb"][seat]
                    )
                    for left, right in zip(candidate_rows, parent_rows, strict=True)
                )
        pooled = paired(pooled_pair_deltas, BONFERRONI_Z)
        seats = {
            str(seat): paired(seat_deltas[seat], BONFERRONI_Z)
            for seat in (0, 1)
        }
        positive = sum(row["mean"] > 0.0 for row in per_anchor.values())
        passed = (
            positive >= 3
            and pooled["ci"][0] > 0.0
            and all(row["mean"] >= 0.0 for row in seats.values())
        )
        comparisons[candidate] = {
            "per_anchor": per_anchor,
            "pooled": pooled,
            "seats": seats,
            "positive_anchors": positive,
            "gate": "PASS" if passed else "FAIL",
        }
        reported = panel["comparisons_to_parent"][candidate]
        checks[f"panel_summary_{candidate}"] = (
            abs(
                pooled["mean"]
                - reported["pooled_bonferroni_98_75"]["mean_delta_bb100"]
            ) < 1e-12
            and all(
                abs(a - b) < 1e-12
                for a, b in zip(
                    pooled["ci"],
                    reported["pooled_bonferroni_98_75"]["ci"],
                )
            )
            and positive == reported["positive_anchors"]
            and all(
                abs(seats[str(seat)]["mean"] - reported["pooled_by_candidate_seat"][str(seat)]["mean_delta_bb100"]) < 1e-12
                for seat in (0, 1)
            )
        )
    eligible = [
        candidate for candidate, row in comparisons.items()
        if row["gate"] == "PASS"
    ]
    checks["selection"] = eligible == panel["eligible_candidates"] == [] and panel["selected_candidate"] is None

    result = {
        "schema": "cardpilot.risk_weighted_mixed_league_evidence_audit.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "drift_recomputed": drift_recomputed,
        "panel_comparisons_recomputed": comparisons,
        "eligible_candidates": eligible,
        "cell_artifact_sha256": cell_hashes,
        "drift_analysis_sha256": sha256_file(drift_path),
        "risk_analysis_sha256": sha256_file(risk_path),
        "panel_analysis_sha256": sha256_file(panel_path),
        "session_audit_sha256": sha256_file(HERE / "training/session_audit.json"),
    }
    (HERE / "evidence_audit.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
