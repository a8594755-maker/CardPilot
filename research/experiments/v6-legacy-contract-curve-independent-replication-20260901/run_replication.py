#!/usr/bin/env python3
"""Fresh-seed confirmatory replication of the frozen iter08/iter16 curve points."""
from __future__ import annotations

import importlib.util
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DISCOVERY = ROOT / "research/experiments/v6-legacy-contract-mixed-league-65k-pilot-20260901"
SPEC = importlib.util.spec_from_file_location("legacy_panel", DISCOVERY / "evaluate_panel.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load frozen panel implementation")
panel = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = panel
SPEC.loader.exec_module(panel)

PAIRS = 4096
BASE_SEED = 2_026_090_301
BONFERRONI_Z = 2.241402727604947  # two-sided 97.5%; two frozen candidates
CANDIDATES = {
    "parent": ROOT / "models/baseline/standard10/latest.pt",
    "iter08": DISCOVERY / "training/checkpoints/checkpoint_iter000008_hands000000033016.pt",
    "iter16": DISCOVERY / "training/checkpoints/checkpoint_iter000016_hands000000065966.pt",
}
ANCHORS = dict(panel.ANCHORS)


def paired(values: list[float], z: float) -> dict:
    mean = statistics.fmean(values)
    se = statistics.stdev(values) / math.sqrt(len(values))
    return {"samples": len(values), "mean_delta_bb100": mean, "ci": [mean - z * se, mean + z * se]}


def main() -> None:
    if sys.argv[1:]:
        raise SystemExit("This preregistered replication takes no arguments")
    if (HERE / "replication").exists():
        raise FileExistsError(HERE / "replication")
    started = time.time()
    panel.PAIRS = PAIRS
    torch.set_num_threads(8)
    device = "cuda"
    candidates = {label: panel.load_auto(path, device) for label, path in CANDIDATES.items()}
    anchors = {label: panel.load_auto(path, device) for label, path in ANCHORS.items()}
    cells = {}
    for anchor_index, (anchor_label, anchor) in enumerate(anchors.items()):
        rng = np.random.default_rng(BASE_SEED + anchor_index * 1_000_003)
        decks = [rng.permutation(52).astype(int).tolist() for _ in range(PAIRS)]
        for candidate_label, candidate in candidates.items():
            print(json.dumps({"candidate": candidate_label, "anchor": anchor_label, "status": "RUNNING"}), flush=True)
            cells[(candidate_label, anchor_label)] = panel.cell(
                candidate,
                anchor,
                decks,
                HERE / "replication" / f"{candidate_label}__{anchor_label}",
            )
    comparisons = {}
    eligible = []
    for candidate_label in ("iter08", "iter16"):
        per_anchor = {}
        pooled_pair_deltas = []
        pooled_seat_deltas = [[], []]
        for anchor_label in anchors:
            candidate_rows = [
                json.loads(line)
                for line in (HERE / "replication" / f"{candidate_label}__{anchor_label}" / "pairs.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            parent_rows = [
                json.loads(line)
                for line in (HERE / "replication" / f"parent__{anchor_label}" / "pairs.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            pair_deltas = [
                100.0 * (left["candidate_pair_average_bb"] - right["candidate_pair_average_bb"])
                for left, right in zip(candidate_rows, parent_rows, strict=True)
            ]
            per_anchor[anchor_label] = paired(pair_deltas, 1.96)
            pooled_pair_deltas.extend(pair_deltas)
            for seat in (0, 1):
                pooled_seat_deltas[seat].extend(
                    100.0 * (left["candidate_rewards_bb"][seat] - right["candidate_rewards_bb"][seat])
                    for left, right in zip(candidate_rows, parent_rows, strict=True)
                )
        pooled = paired(pooled_pair_deltas, BONFERRONI_Z)
        seats = {str(seat): paired(pooled_seat_deltas[seat], BONFERRONI_Z) for seat in (0, 1)}
        positive_anchors = sum(row["mean_delta_bb100"] > 0 for row in per_anchor.values())
        passed = positive_anchors >= 3 and pooled["ci"][0] > 0 and all(row["mean_delta_bb100"] >= 0 for row in seats.values())
        comparisons[candidate_label] = {
            "per_anchor": per_anchor,
            "pooled_bonferroni_97_5": pooled,
            "pooled_by_candidate_seat": seats,
            "positive_anchors": positive_anchors,
            "promotion_gate": "PASS" if passed else "FAIL",
        }
        if passed:
            eligible.append(candidate_label)
    selected = max(
        eligible,
        key=lambda label: comparisons[label]["pooled_bonferroni_97_5"]["ci"][0],
        default=None,
    )
    result = {
        "schema": "cardpilot.legacy_contract_curve_independent_replication.v1",
        "status": "PASS",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "design": {
            "pairs_per_cell": PAIRS,
            "candidates": list(CANDIDATES),
            "anchors": list(ANCHORS),
            "base_seed": BASE_SEED,
            "fresh_from_discovery": True,
            "policy_mode": "greedy",
            "promotion_rule": "at least 3/4 positive anchors, pooled two-comparison Bonferroni 97.5% lower >0, and both seat points nonnegative",
            "selection_rule": "highest adjusted lower bound among passing candidates",
        },
        "checkpoint_hashes": {
            "candidates": {label: policy.sha256 for label, policy in candidates.items()},
            "anchors": {label: policy.sha256 for label, policy in anchors.items()},
        },
        "comparisons_to_parent": comparisons,
        "eligible_candidates": eligible,
        "selected_candidate": selected,
        "evaluation_hands": len(candidates) * len(anchors) * PAIRS * 2,
        "slumbot_hands": 0,
        "wall_time_seconds": time.time() - started,
    }
    (HERE / "replication_analysis.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
