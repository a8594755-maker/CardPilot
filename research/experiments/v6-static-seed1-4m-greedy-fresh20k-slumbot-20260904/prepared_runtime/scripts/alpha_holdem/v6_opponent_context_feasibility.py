"""Test whether public cross-hand action context identifies broad opponent styles."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.legacy_observation_bridge_v6 import decide as legacy_decide, load_policy
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_broad_mgda_curve import frozen_decide, load_frozen_policy


ACTION_BUCKETS = {"f": 0, "c": 1, "k": 2, "b": 3}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def action_bucket(action: str) -> int:
    key = "b" if action.startswith("b") else action
    if key not in ACTION_BUCKETS:
        raise ValueError(f"unknown public action {action!r}")
    return ACTION_BUCKETS[key]


def context_features(counts: np.ndarray) -> np.ndarray:
    counts = np.asarray(counts, dtype=np.float64)
    if counts.shape != (4, 4) or np.any(counts < 0):
        raise ValueError("context counts must have shape [4,4] and be nonnegative")
    totals = counts.sum(axis=1, keepdims=True)
    rates = counts / np.maximum(totals, 1.0)
    activity = np.log1p(totals[:, 0]) / math.log(65.0)
    return np.concatenate((rates.reshape(-1), activity)).astype(np.float32)


def fit_classifier(
    train_x: np.ndarray,
    train_y: np.ndarray,
    test_x: np.ndarray,
    test_y: np.ndarray,
    classes: int,
    seed: int,
) -> tuple[dict, torch.nn.Module, np.ndarray, np.ndarray]:
    mean = train_x.mean(axis=0)
    std = train_x.std(axis=0)
    std[std < 1e-6] = 1.0
    x_train = torch.as_tensor((train_x - mean) / std, dtype=torch.float32)
    y_train = torch.as_tensor(train_y, dtype=torch.long)
    x_test = torch.as_tensor((test_x - mean) / std, dtype=torch.float32)
    torch.manual_seed(seed)
    model = torch.nn.Linear(train_x.shape[1], classes)
    optimizer = torch.optim.LBFGS(
        model.parameters(), lr=0.5, max_iter=200, tolerance_grad=1e-9, tolerance_change=1e-11
    )

    def closure():
        optimizer.zero_grad(set_to_none=True)
        loss = torch.nn.functional.cross_entropy(model(x_train), y_train)
        loss.backward()
        return loss

    optimizer.step(closure)
    with torch.no_grad():
        train_predictions = model(x_train).argmax(dim=1).numpy()
        test_logits = model(x_test)
        test_predictions = test_logits.argmax(dim=1).numpy()
        test_probabilities = test_logits.softmax(dim=1).numpy()
    per_class = []
    for label in range(classes):
        selected = test_y == label
        per_class.append(float(np.mean(test_predictions[selected] == label)))
    metrics = {
        "train_accuracy": float(np.mean(train_predictions == train_y)),
        "test_accuracy": float(np.mean(test_predictions == test_y)),
        "minimum_test_class_accuracy": float(min(per_class)),
        "per_class_test_accuracy": per_class,
    }
    return metrics, model, mean, std


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--sessions-per-training-policy", type=int, default=12)
    parser.add_argument("--sessions-per-holdout-policy", type=int, default=4)
    parser.add_argument("--hands-per-session", type=int, default=64)
    parser.add_argument("--train-sessions-per-policy", type=int, default=8)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    horizons = (8, 16, 32, 64)
    if args.hands_per_session != 64 or not 0 < args.train_sessions_per_policy < args.sessions_per_training_policy:
        parser.error("this feasibility requires 64-hand sessions and a nonempty session split")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    spec_path = args.spec.resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    training = [load_frozen_policy(row, args.device) for row in spec["training_policies"]]
    holdouts = [load_frozen_policy(row, args.device) for row in spec["holdout_policies"]]
    if len(training) != 6 or len(holdouts) != 3:
        raise ValueError("context feasibility requires six training and three holdout policies")
    if not {row.sha256 for row in training}.isdisjoint({row.sha256 for row in holdouts}):
        raise ValueError("training and holdout policy identities overlap")
    base_path = args.base_checkpoint.resolve()
    base_sha = sha256_path(base_path)
    base_policy = load_policy(base_path, args.device)

    session_rows = []
    hand_rows = []
    all_policies = [("training", index, row) for index, row in enumerate(training)] + [
        ("holdout", index, row) for index, row in enumerate(holdouts)
    ]
    for split, policy_index, opponent in all_policies:
        session_count = (
            args.sessions_per_training_policy
            if split == "training"
            else args.sessions_per_holdout_policy
        )
        for session_index in range(session_count):
            counts = np.zeros((4, 4), dtype=np.int64)
            snapshots = {}
            for hand_index in range(args.hands_per_session):
                seed = (
                    args.seed
                    + (0 if split == "training" else 900_000_007)
                    + policy_index * 10_000_019
                    + session_index * 100_003
                    + hand_index * 101
                )
                deck_rng = random.Random(seed)
                deck = list(range(52))
                deck_rng.shuffle(deck)
                state = ChipState.new(deck)
                hero_seat = hand_index % 2
                public_actions = []
                while not state.terminal:
                    if state.actor == hero_seat:
                        action, _ = legacy_decide(
                            base_policy, state, uniform=0.0, policy_mode="greedy"
                        )
                    else:
                        action = frozen_decide(opponent, state, uniform=None)
                        bucket = action_bucket(action)
                        counts[state.street, bucket] += 1
                        public_actions.append(
                            {"street": int(state.street), "action": action, "bucket": bucket}
                        )
                    state = apply_incr(state, action)
                hand_rows.append(
                    {
                        "split": split,
                        "policy_index": policy_index,
                        "policy_label": opponent.label,
                        "policy_sha256": opponent.sha256,
                        "session_index": session_index,
                        "hand_index": hand_index,
                        "seed": seed,
                        "deck": deck,
                        "hero_seat": hero_seat,
                        "opponent_actions": public_actions,
                    }
                )
                completed = hand_index + 1
                if completed in horizons:
                    snapshots[str(completed)] = context_features(counts).tolist()
            session_rows.append(
                {
                    "split": split,
                    "policy_index": policy_index,
                    "policy_label": opponent.label,
                    "policy_sha256": opponent.sha256,
                    "session_index": session_index,
                    "final_counts": counts.tolist(),
                    "features": snapshots,
                }
            )
        print(f"{split} policy={policy_index + 1} sessions={session_count}", flush=True)
    evidence_path = args.out_dir / "session_hands.jsonl.gz"
    with gzip.open(evidence_path, "xt", encoding="utf-8", newline="\n") as handle:
        for row in hand_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    sessions_path = args.out_dir / "session_features.jsonl"
    sessions_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in session_rows),
        encoding="utf-8",
    )

    results = []
    classifiers = {}
    for horizon in horizons:
        train_rows = [
            row
            for row in session_rows
            if row["split"] == "training"
            and row["session_index"] < args.train_sessions_per_policy
        ]
        test_rows = [
            row
            for row in session_rows
            if row["split"] == "training"
            and row["session_index"] >= args.train_sessions_per_policy
        ]
        train_x = np.asarray([row["features"][str(horizon)] for row in train_rows])
        train_y = np.asarray([row["policy_index"] for row in train_rows])
        test_x = np.asarray([row["features"][str(horizon)] for row in test_rows])
        test_y = np.asarray([row["policy_index"] for row in test_rows])
        metrics, classifier, mean, std = fit_classifier(
            train_x, train_y, test_x, test_y, len(training), args.seed + horizon
        )
        holdout_rows = [row for row in session_rows if row["split"] == "holdout"]
        holdout_x = torch.as_tensor(
            (np.asarray([row["features"][str(horizon)] for row in holdout_rows]) - mean) / std,
            dtype=torch.float32,
        )
        with torch.no_grad():
            probabilities = classifier(holdout_x).softmax(dim=1).numpy()
        entropy = -np.sum(probabilities * np.log(np.maximum(probabilities, 1e-12)), axis=1)
        results.append(
            {
                "horizon_hands": horizon,
                **metrics,
                "holdout_mean_entropy": float(np.mean(entropy)),
                "holdout_nearest_training_class_counts": np.bincount(
                    probabilities.argmax(axis=1), minlength=len(training)
                ).tolist(),
            }
        )
        classifiers[str(horizon)] = {
            "weight": classifier.weight.detach().cpu(),
            "bias": classifier.bias.detach().cpu(),
            "feature_mean": torch.as_tensor(mean),
            "feature_std": torch.as_tensor(std),
        }
    classifier_path = args.out_dir / "context_classifiers.pt"
    torch.save(
        {
            "schema": "cardpilot.opponent_context_classifiers.v1",
            "training_policy_sha256": [row.sha256 for row in training],
            "feature_schema": "street_x_fold_call_check_bet_rates_plus_log_activity_v1",
            "classifiers": classifiers,
        },
        classifier_path,
    )
    result32 = next(row for row in results if row["horizon_hands"] == 32)
    result64 = next(row for row in results if row["horizon_hands"] == 64)
    gates = {
        "training_hands_exact": len(
            [row for row in hand_rows if row["split"] == "training"]
        )
        == len(training) * args.sessions_per_training_policy * args.hands_per_session,
        "holdout_hands_exact": len([row for row in hand_rows if row["split"] == "holdout"])
        == len(holdouts) * args.sessions_per_holdout_policy * args.hands_per_session,
        "horizon32_test_accuracy_at_least_50pct": result32["test_accuracy"] >= 0.50,
        "horizon64_test_accuracy_at_least_75pct": result64["test_accuracy"] >= 0.75,
        "horizon64_minimum_class_accuracy_at_least_50pct": result64[
            "minimum_test_class_accuracy"
        ]
        >= 0.50,
        "base_file_hash_unchanged": sha256_path(base_path) == base_sha,
    }
    admitted = all(gates.values())
    output = {
        "schema": "cardpilot.opponent_context_feasibility.v1",
        "status": "COMPLETED",
        "claim_scope": "PUBLIC_SESSION_CONTEXT_REPRESENTATION_NOT_POLICY_STRENGTH",
        "base_sha256": base_sha,
        "spec_sha256": sha256_path(spec_path),
        "training_policies": [{"label": row.label, "sha256": row.sha256} for row in training],
        "holdout_policies": [{"label": row.label, "sha256": row.sha256} for row in holdouts],
        "feature_width": 20,
        "results": results,
        "environment_training_hands": len(
            [row for row in hand_rows if row["split"] == "training" and row["session_index"] < args.train_sessions_per_policy]
        ),
        "evaluation_hands": len(hand_rows)
        - len([row for row in hand_rows if row["split"] == "training" and row["session_index"] < args.train_sessions_per_policy]),
        "evidence_sha256": sha256_path(evidence_path),
        "session_features_sha256": sha256_path(sessions_path),
        "classifiers_sha256": sha256_path(classifier_path),
        "gates": gates,
        "admitted": admitted,
        "decision": (
            "ADMIT_CONTEXT_CONDITIONED_POLICY_MECHANISM_SMOKE"
            if admitted
            else "REJECT_PUBLIC_SESSION_CONTEXT_AS_INSUFFICIENT"
        ),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
