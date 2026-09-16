"""Fail-closed audit of policy-only counterfactual replay evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import torch


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def close(actual: float, expected: float, tolerance: float = 1e-9) -> bool:
    return math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--expected-final-iteration", type=int, required=True)
    parser.add_argument("--expected-dataset-sha256", required=True)
    parser.add_argument("--expected-training-rows", type=int, required=True)
    parser.add_argument("--expected-batch-size", type=int, required=True)
    parser.add_argument("--expected-policy-loss-coef", type=float, required=True)
    parser.add_argument("--expected-decay-hands", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    metric_path = run_dir / "h1_training_metrics.jsonl"
    manifest_path = run_dir / "run_manifest.json"
    checkpoint_path = run_dir / "latest.pt"
    for path in (metric_path, manifest_path, checkpoint_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    metrics = load_jsonl(metric_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    manifest_config = manifest.get("config") or {}
    checkpoint_config = checkpoint.get("config") or {}

    expected_iterations = list(range(1, args.expected_final_iteration + 1))
    iterations = [int(row["iteration"]) for row in metrics]
    if iterations != expected_iterations:
        raise RuntimeError("metric iterations are not exactly contiguous")
    if manifest.get("status") != "finished":
        raise RuntimeError("run manifest is not terminal finished")
    if int(manifest.get("iteration", -1)) != args.expected_final_iteration:
        raise RuntimeError("manifest iteration differs from preregistration")
    if int(checkpoint.get("iteration", -1)) != args.expected_final_iteration:
        raise RuntimeError("checkpoint iteration differs from preregistration")

    config_contract = {
        "action_q_advantage": False,
        "action_q_counterfactual_dataset_sha256": args.expected_dataset_sha256,
        "action_q_counterfactual_policy_loss_coef": args.expected_policy_loss_coef,
        "action_q_counterfactual_loss_coef": 0.0,
        "action_q_counterfactual_batch_size": args.expected_batch_size,
        "action_q_counterfactual_max_batches_per_update": 1,
        "action_q_counterfactual_stratify_trajectory_opponent": True,
        "action_q_counterfactual_loss_decay_hands": args.expected_decay_hands,
    }
    for label, config in (
        ("manifest", manifest_config),
        ("checkpoint", checkpoint_config),
    ):
        for key, expected in config_contract.items():
            if config.get(key) != expected:
                raise RuntimeError(f"{label} config contract mismatch: {key}")

    policy_losses: list[float] = []
    effective_coefficients: list[float] = []
    elapsed_hands: list[int] = []
    for iteration, row in zip(expected_iterations, metrics):
        if row.get("action_q_advantage") is not False:
            raise RuntimeError("Action-Q advantage head was enabled")
        if int(row.get("action_q_counterfactual_batches_applied", -1)) != 1:
            raise RuntimeError("counterfactual replay did not apply exactly one batch")
        if float(row.get("action_q_counterfactual_loss", math.nan)) != 0.0:
            raise RuntimeError("counterfactual Q loss is not identically zero")
        if float(row.get("action_q_counterfactual_loss_coef", math.nan)) != 0.0:
            raise RuntimeError("counterfactual Q coefficient is not identically zero")
        if int(row.get("action_q_counterfactual_batch_size", -1)) != args.expected_batch_size:
            raise RuntimeError("counterfactual batch size changed")
        if int(row.get("action_q_counterfactual_training_rows", -1)) != args.expected_training_rows:
            raise RuntimeError("counterfactual training split size changed")

        expected_draws = iteration * args.expected_batch_size
        draws = int(row.get("action_q_counterfactual_replay_total_draws", -1))
        if draws != expected_draws:
            raise RuntimeError("replay cursor draw count is not iteration-contiguous")
        epochs = float(row.get("action_q_counterfactual_replay_dataset_epochs", math.nan))
        if not close(epochs, draws / args.expected_training_rows):
            raise RuntimeError("reported replay epochs do not match cursor draws")

        elapsed = int(row.get("action_q_counterfactual_replay_elapsed_hands", -1))
        if elapsed < 0:
            raise RuntimeError("invalid replay elapsed-hand counter")
        expected_coefficient = args.expected_policy_loss_coef * max(
            0.0, 1.0 - elapsed / args.expected_decay_hands
        )
        coefficient = float(
            row.get("action_q_counterfactual_policy_loss_coef", math.nan)
        )
        if not close(coefficient, expected_coefficient):
            raise RuntimeError("effective policy coefficient violates hand decay")
        policy_loss = float(row.get("action_q_counterfactual_policy_loss", math.nan))
        if not math.isfinite(policy_loss) or policy_loss <= 0.0:
            raise RuntimeError("counterfactual policy loss is not finite and positive")
        policy_losses.append(policy_loss)
        effective_coefficients.append(coefficient)
        elapsed_hands.append(elapsed)

    if any(right <= left for left, right in zip(elapsed_hands, elapsed_hands[1:])):
        raise RuntimeError("replay elapsed-hand counter is not strictly increasing")
    if any(
        right > left + 1e-12
        for left, right in zip(effective_coefficients, effective_coefficients[1:])
    ):
        raise RuntimeError("effective counterfactual coefficient increased")

    result = {
        "schema": "cardpilot.counterfactual_policy_replay_session_audit.v1",
        "status": "PASS",
        "run_id": checkpoint.get("run_id"),
        "final_iteration": args.expected_final_iteration,
        "actual_environment_hands": int(checkpoint["total_hands"]),
        "policy_only": True,
        "metric_rows": len(metrics),
        "dataset_sha256": args.expected_dataset_sha256,
        "training_rows": args.expected_training_rows,
        "batch_size": args.expected_batch_size,
        "total_draws": int(metrics[-1]["action_q_counterfactual_replay_total_draws"]),
        "dataset_epochs": float(metrics[-1]["action_q_counterfactual_replay_dataset_epochs"]),
        "policy_loss": {
            "minimum": min(policy_losses),
            "maximum": max(policy_losses),
            "final": policy_losses[-1],
        },
        "effective_policy_loss_coefficient": {
            "initial": effective_coefficients[0],
            "final": effective_coefficients[-1],
        },
        "q_loss_identically_zero": True,
        "trajectory_opponent_stratification": True,
        "artifacts": {
            "checkpoint": {
                "path": str(checkpoint_path),
                "bytes": checkpoint_path.stat().st_size,
                "sha256": sha256_path(checkpoint_path),
            },
            "manifest": {
                "path": str(manifest_path),
                "bytes": manifest_path.stat().st_size,
                "sha256": sha256_path(manifest_path),
            },
            "metrics": {
                "path": str(metric_path),
                "bytes": metric_path.stat().st_size,
                "sha256": sha256_path(metric_path),
            },
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
