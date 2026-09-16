"""Nested-CV regularization and calibration control for frozen session features."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
import torch


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rows(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("session feature evidence is empty")
    return rows


def arrays(rows: list[dict], horizon: int, split: str, train_sessions: int) -> tuple[np.ndarray, np.ndarray]:
    selected = []
    for row in rows:
        if row["split"] != split:
            continue
        if split == "training" and ((row["session_index"] < train_sessions) != (train_sessions > 0)):
            continue
        selected.append(row)
    x = np.asarray([row["features"][str(horizon)] for row in selected], dtype=np.float32)
    y = np.asarray([row["policy_index"] for row in selected], dtype=np.int64)
    return x, y


def split_training_rows(rows: list[dict], train_sessions: int) -> tuple[list[dict], list[dict]]:
    train = [r for r in rows if r["split"] == "training" and r["session_index"] < train_sessions]
    test = [r for r in rows if r["split"] == "training" and r["session_index"] >= train_sessions]
    return train, test


def fit_linear(x: np.ndarray, y: np.ndarray, classes: int, l2: float) -> tuple[torch.nn.Linear, np.ndarray, np.ndarray]:
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std[std < 1e-6] = 1.0
    tx = torch.as_tensor((x - mean) / std, dtype=torch.float64)
    ty = torch.as_tensor(y, dtype=torch.long)
    model = torch.nn.Linear(x.shape[1], classes, dtype=torch.float64)
    with torch.no_grad():
        model.weight.zero_()
        model.bias.zero_()
    optimizer = torch.optim.LBFGS(
        model.parameters(), lr=0.5, max_iter=300, tolerance_grad=1e-11, tolerance_change=1e-13
    )

    def closure() -> torch.Tensor:
        optimizer.zero_grad(set_to_none=True)
        logits = model(tx)
        loss = torch.nn.functional.cross_entropy(logits, ty) + float(l2) * model.weight.square().mean()
        loss.backward()
        return loss

    optimizer.step(closure)
    return model, mean, std


def logits(model: torch.nn.Linear, mean: np.ndarray, std: np.ndarray, x: np.ndarray) -> np.ndarray:
    with torch.no_grad():
        tx = torch.as_tensor((x - mean) / std, dtype=torch.float64)
        return model(tx).cpu().numpy()


def classification_metrics(raw_logits: np.ndarray, y: np.ndarray, classes: int, temperature: float = 1.0) -> dict:
    scaled = raw_logits / float(temperature)
    scaled -= scaled.max(axis=1, keepdims=True)
    probabilities = np.exp(scaled)
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    predictions = probabilities.argmax(axis=1)
    per_class = [float(np.mean(predictions[y == label] == label)) for label in range(classes)]
    confidence = probabilities.max(axis=1)
    correct = predictions == y
    ece = 0.0
    for lower in np.linspace(0.0, 0.9, 10):
        mask = (confidence >= lower) & (confidence < lower + 0.1 + 1e-12)
        if np.any(mask):
            ece += float(mask.mean()) * abs(float(correct[mask].mean()) - float(confidence[mask].mean()))
    return {
        "accuracy": float(correct.mean()),
        "minimum_class_accuracy": float(min(per_class)),
        "per_class_accuracy": per_class,
        "nll": float(-np.log(np.maximum(probabilities[np.arange(len(y)), y], 1e-15)).mean()),
        "ece": ece,
        "mean_confidence": float(confidence.mean()),
    }


def nested_cv(
    train_rows: list[dict], horizon: int, classes: int, l2_grid: list[float], train_sessions: int
) -> tuple[float, float, list[dict], np.ndarray, np.ndarray]:
    y_all = np.asarray([r["policy_index"] for r in train_rows], dtype=np.int64)
    x_all = np.asarray([r["features"][str(horizon)] for r in train_rows], dtype=np.float32)
    candidates = []
    candidate_logits = []
    for l2 in l2_grid:
        oof = np.zeros((len(train_rows), classes), dtype=np.float64)
        for fold in range(train_sessions):
            fit_mask = np.asarray([r["session_index"] != fold for r in train_rows])
            valid_mask = ~fit_mask
            model, mean, std = fit_linear(x_all[fit_mask], y_all[fit_mask], classes, l2)
            oof[valid_mask] = logits(model, mean, std, x_all[valid_mask])
        metrics = classification_metrics(oof, y_all, classes)
        candidates.append({"l2": l2, **metrics})
        candidate_logits.append(oof)
    best_index = max(
        range(len(candidates)),
        key=lambda i: (
            candidates[i]["minimum_class_accuracy"],
            candidates[i]["accuracy"],
            -candidates[i]["nll"],
            l2_grid[i],
        ),
    )
    best_oof = candidate_logits[best_index]
    temperatures = np.geomspace(0.25, 16.0, 65)
    temperature_scores = [classification_metrics(best_oof, y_all, classes, float(t))["nll"] for t in temperatures]
    best_temperature = float(temperatures[int(np.argmin(temperature_scores))])
    return l2_grid[best_index], best_temperature, candidates, best_oof, y_all


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--expected-features-sha256", required=True)
    parser.add_argument("--train-sessions-per-policy", type=int, default=8)
    parser.add_argument("--horizons", type=int, nargs="+", default=[32, 64])
    parser.add_argument("--l2-grid", type=float, nargs="+", default=[0.0001, 0.001, 0.01, 0.1, 1.0, 10.0])
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    actual_sha = sha256_path(args.features)
    if actual_sha != args.expected_features_sha256:
        raise ValueError(f"feature evidence SHA mismatch: {actual_sha}")
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    started = time.time()
    rows = load_rows(args.features)
    training_rows, test_rows = split_training_rows(rows, args.train_sessions_per_policy)
    holdout_rows = [r for r in rows if r["split"] == "holdout"]
    classes = len({r["policy_index"] for r in training_rows})
    if classes != 6 or len(training_rows) != 48 or len(test_rows) != 24 or len(holdout_rows) != 12:
        raise ValueError("expected sealed 48-train/24-test/12-holdout six-class evidence")
    results = []
    saved = {}
    for horizon in args.horizons:
        selected_l2, temperature, candidates, oof_logits, oof_y = nested_cv(
            training_rows, horizon, classes, args.l2_grid, args.train_sessions_per_policy
        )
        train_x = np.asarray([r["features"][str(horizon)] for r in training_rows], dtype=np.float32)
        train_y = np.asarray([r["policy_index"] for r in training_rows], dtype=np.int64)
        test_x = np.asarray([r["features"][str(horizon)] for r in test_rows], dtype=np.float32)
        test_y = np.asarray([r["policy_index"] for r in test_rows], dtype=np.int64)
        holdout_x = np.asarray([r["features"][str(horizon)] for r in holdout_rows], dtype=np.float32)
        model, mean, std = fit_linear(train_x, train_y, classes, selected_l2)
        test_logits = logits(model, mean, std, test_x)
        test_metrics = classification_metrics(test_logits, test_y, classes, temperature)
        holdout_logits = logits(model, mean, std, holdout_x) / temperature
        holdout_logits -= holdout_logits.max(axis=1, keepdims=True)
        holdout_prob = np.exp(holdout_logits)
        holdout_prob /= holdout_prob.sum(axis=1, keepdims=True)
        holdout_entropy = -np.sum(holdout_prob * np.log(np.maximum(holdout_prob, 1e-15)), axis=1)
        results.append(
            {
                "horizon_hands": horizon,
                "selected_l2": selected_l2,
                "selected_temperature": temperature,
                "cv_candidates": candidates,
                "selected_oof_metrics": classification_metrics(oof_logits, oof_y, classes, temperature),
                "untouched_test_metrics": test_metrics,
                "holdout_mean_entropy": float(holdout_entropy.mean()),
                "holdout_mean_normalized_entropy": float(holdout_entropy.mean() / math.log(classes)),
                "holdout_mean_confidence": float(holdout_prob.max(axis=1).mean()),
                "holdout_nearest_training_class_counts": np.bincount(
                    holdout_prob.argmax(axis=1), minlength=classes
                ).tolist(),
            }
        )
        saved[str(horizon)] = {
            "weight": model.weight.detach().cpu(),
            "bias": model.bias.detach().cpu(),
            "mean": mean,
            "std": std,
            "temperature": temperature,
            "l2": selected_l2,
        }
    by_horizon = {row["horizon_hands"]: row for row in results}
    gates = {
        "features_sha_exact": sha256_path(args.features) == args.expected_features_sha256,
        "horizon32_accuracy_at_least_50pct": by_horizon[32]["untouched_test_metrics"]["accuracy"] >= 0.50,
        "horizon64_accuracy_at_least_75pct": by_horizon[64]["untouched_test_metrics"]["accuracy"] >= 0.75,
        "horizon64_minimum_class_accuracy_at_least_50pct": by_horizon[64]["untouched_test_metrics"]["minimum_class_accuracy"] >= 0.50,
        "horizon64_holdout_normalized_entropy_at_least_25pct": by_horizon[64]["holdout_mean_normalized_entropy"] >= 0.25,
    }
    admitted = all(gates.values())
    model_path = args.out_dir / "regularized_context_classifiers.pt"
    torch.save({"schema": "cardpilot.regularized_opponent_context.v1", "models": saved}, model_path)
    summary = {
        "schema": "cardpilot.opponent_context_regularization_control.v1",
        "status": "COMPLETED",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "claim_scope": "FROZEN_SESSION_FEATURE_READOUT_NOT_POLICY_STRENGTH",
        "features_path": str(args.features.resolve()),
        "features_sha256": actual_sha,
        "model_sha256": sha256_path(model_path),
        "new_environment_hands": 0,
        "offline_session_samples": len(rows),
        "sealed_split": {"model_selection": len(training_rows), "untouched_test": len(test_rows), "unseen_holdout": len(holdout_rows)},
        "results": results,
        "gates": gates,
        "admitted": admitted,
        "decision": "ADMIT_REGULARIZED_PUBLIC_SESSION_CONTEXT" if admitted else "REJECT_REGULARIZED_PUBLIC_SESSION_CONTEXT",
        "wall_time_seconds": time.time() - started,
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
