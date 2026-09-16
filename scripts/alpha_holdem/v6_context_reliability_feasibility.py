"""Outcome-blind feasibility of entropy shrinkage for unseen opponent contexts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.v6_dual_contract_residual_training_smoke import sha256_path


def normalized_reliability(probabilities: np.ndarray) -> np.ndarray:
    probabilities = np.asarray(probabilities, dtype=np.float64)
    entropy = -np.sum(probabilities * np.log(np.maximum(probabilities, 1e-15)), axis=1)
    return 1.0 - entropy / math.log(probabilities.shape[1])


def auc_higher_positive(positive: np.ndarray, negative: np.ndarray) -> float:
    return float(np.mean(positive[:, None] > negative[None, :]) + 0.5 * np.mean(positive[:, None] == negative[None, :]))


def describe(values: np.ndarray) -> dict:
    return {
        "count": len(values), "mean": float(np.mean(values)), "median": float(np.median(values)),
        "minimum": float(np.min(values)), "maximum": float(np.max(values)),
        "q25": float(np.quantile(values, 0.25)), "q75": float(np.quantile(values, 0.75)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--expected-features-sha256", required=True)
    parser.add_argument("--classifier", type=Path, required=True)
    parser.add_argument("--expected-classifier-sha256", required=True)
    parser.add_argument("--train-sessions-per-policy", type=int, default=8)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    feature_sha = sha256_path(args.features)
    classifier_sha = sha256_path(args.classifier)
    if feature_sha != args.expected_features_sha256 or classifier_sha != args.expected_classifier_sha256:
        raise ValueError("frozen artifact SHA mismatch")
    args.out_dir.mkdir(parents=True)
    started = time.time()
    rows = [json.loads(line) for line in args.features.read_text(encoding="utf-8").splitlines() if line.strip()]
    classifier = torch.load(args.classifier, map_location="cpu", weights_only=False)["models"]["64"]
    weight = np.asarray(classifier["weight"], dtype=np.float64)
    bias = np.asarray(classifier["bias"], dtype=np.float64)
    mean = np.asarray(classifier["mean"], dtype=np.float64)
    std = np.asarray(classifier["std"], dtype=np.float64)
    temperature = float(classifier["temperature"])

    def posterior(selected):
        x = np.asarray([row["features"]["64"] for row in selected], dtype=np.float64)
        logits = ((x - mean) / std) @ weight.T + bias
        logits /= temperature
        logits -= logits.max(axis=1, keepdims=True)
        probabilities = np.exp(logits)
        return probabilities / probabilities.sum(axis=1, keepdims=True)

    selection = [r for r in rows if r["split"] == "training" and r["session_index"] < args.train_sessions_per_policy]
    seen_test = [r for r in rows if r["split"] == "training" and r["session_index"] >= args.train_sessions_per_policy]
    unseen = [r for r in rows if r["split"] == "holdout"]
    if (len(selection), len(seen_test), len(unseen)) != (48, 24, 12):
        raise ValueError("expected sealed 48/24/12 split")
    selection_reliability = normalized_reliability(posterior(selection))
    seen_reliability = normalized_reliability(posterior(seen_test))
    unseen_reliability = normalized_reliability(posterior(unseen))
    auc = auc_higher_positive(seen_reliability, unseen_reliability)
    seen = describe(seen_reliability)
    holdout = describe(unseen_reliability)
    gates = {
        "artifact_hashes_exact": True,
        "seen_median_reliability_at_least_40pct": seen["median"] >= 0.40,
        "holdout_median_reliability_at_most_40pct": holdout["median"] <= 0.40,
        "seen_minus_holdout_mean_at_least_15pct": seen["mean"] - holdout["mean"] >= 0.15,
        "seen_vs_holdout_auc_at_least_75pct": auc >= 0.75,
    }
    admitted = all(gates.values())
    summary = {
        "schema": "cardpilot.context_reliability_feasibility.v1", "status": "COMPLETED",
        "claim_scope": "OUTCOME_BLIND_OOD_SHRINKAGE_NOT_POLICY_STRENGTH", "new_environment_hands": 0,
        "features_sha256": feature_sha, "classifier_sha256": classifier_sha,
        "selection_reliability": describe(selection_reliability), "seen_test_reliability": seen,
        "unseen_holdout_reliability": holdout, "seen_vs_holdout_auc": auc,
        "proposed_delta_multiplier": "1 - posterior_entropy/log(6)", "gates": gates, "admitted": admitted,
        "decision": "ADMIT_ENTROPY_SHRINKAGE_FRESH_CONTROL" if admitted else "REJECT_ENTROPY_AS_OOD_GATE",
        "wall_time_seconds": time.time() - started, "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
