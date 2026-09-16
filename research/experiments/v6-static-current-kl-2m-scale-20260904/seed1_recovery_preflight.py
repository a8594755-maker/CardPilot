"""Bind the seed1 launcher-log-conflict recovery to exact uncommitted state."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts/alpha_holdem"))
from train_v5 import restore_group_assignment_rng_from_evidence


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_equal(left, right) -> bool:
    if torch.is_tensor(left) or torch.is_tensor(right):
        if not (torch.is_tensor(left) and torch.is_tensor(right)):
            return False
        left_cpu, right_cpu = left.cpu(), right.cpu()
        if left_cpu.shape != right_cpu.shape or left_cpu.dtype != right_cpu.dtype:
            return False
        if left_cpu.is_floating_point():
            return bool(torch.all((left_cpu == right_cpu) | (torch.isnan(left_cpu) & torch.isnan(right_cpu))))
        return torch.equal(left_cpu, right_cpu)
    if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
        return isinstance(left, np.ndarray) and isinstance(right, np.ndarray) and np.array_equal(left, right, equal_nan=True)
    if isinstance(left, dict) or isinstance(right, dict):
        return isinstance(left, dict) and isinstance(right, dict) and set(left) == set(right) and all(exact_equal(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)) or isinstance(right, (list, tuple)):
        return type(left) is type(right) and len(left) == len(right) and all(exact_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, float) and isinstance(right, float) and math.isnan(left) and math.isnan(right):
        return True
    return left == right


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    parent_path = REPO / "research/experiments/v6-static-current-kl-1m-scale-20260903/seed1/latest.pt"
    current_path = REPO / "research/experiments/v6-static-current-kl-2m-scale-20260904/seed1/latest.pt"
    metrics_path = current_path.with_name("h1_training_metrics.jsonl")
    assignments_path = current_path.with_name("opponent_assignments.jsonl")
    failure_log = current_path.with_name("launcher_conflict_failure.log")
    parent = torch.load(parent_path, map_location="cpu", weights_only=False)
    current = torch.load(current_path, map_location="cpu", weights_only=False)
    metrics = load_jsonl(metrics_path)
    assignments = load_jsonl(assignments_path)
    config = current["config"]
    pool_ids = [int(row["id"]) for row in current["pool_snapshots"]]
    restored = restore_group_assignment_rng_from_evidence(
        assignments,
        metrics,
        rng=random.Random(0),
        seed=int(config["seed"]),
        worker_count=int(config["workers"]),
        pool_size=len(pool_ids),
        pool_snapshot_ids=pool_ids,
        group_count=int(config["opponent_groups"]),
        self_play_fraction=float(config["self_play_fraction"]),
        checkpoint_iteration=int(current["iteration"]),
        checkpoint_total_hands=int(current["total_hands"]),
    )
    state_keys = (
        "model", "optimizer", "ppo_replay_entries", "ppo_replay_rng_state",
        "ppo_replay_cumulative_rows", "pool_snapshots", "pool_strategy",
        "pool_active_metadata", "pool_candidate_history",
        "adaptive_opponent_ema_rewards", "adaptive_opponent_weights",
        "adaptive_opponent_observations", "iteration", "total_hands", "run_id",
    )
    last_assignment = assignments[-1]
    gates = {
        "current_checkpoint_expected_hash": sha256_path(current_path) == "4c70b801b2743c323b5b8f90322ce95a06c0a8785c31ec8350fc262c5b7d7205",
        "parent_checkpoint_expected_hash": sha256_path(parent_path) == "1fdc7ebc2560888938cc55bbf6c9eef05deb2e5c9270fbebb123d3143357dbe3",
        "metrics_unchanged_at_parent_boundary": (
            sha256_path(metrics_path) == "43f339c7b17d6aac4fb68fdc4e3a07f45d7693be04f4d1c2b2522973985cbf49"
            and len(metrics) == 221 and int(metrics[-1]["iteration"]) == 221
            and int(metrics[-1]["hands"]) == 910278
        ),
        "assignment_has_exact_pending_iter222": (
            sha256_path(assignments_path) == "9b266e53c6c8fba07c1443f316362674f877cd5231752b210991c5441cd0e779"
            and len(assignments) == 222
            and int(last_assignment["applies_to_iteration"]) == 222
            and int(last_assignment["total_hands_before_iteration"]) == 910278
            and last_assignment["record_sha256"] == "268ae0c9f81e9aa5ada7b59f9f3badeddeae90e47ced56f6f064039fea76a587"
        ),
        "assignment_restore_finds_pending": (
            restored["tail_iteration"] == 222
            and restored["pending_assignments"] is not None
        ),
        "all_committed_training_state_equals_parent": all(exact_equal(current[key], parent[key]) for key in state_keys),
        "physical_counter_still_parent": (
            int(current["environment_hand_accounting"]["completed_hands"]) == 1052694
            and int(current["iteration"]) == 221
            and int(current["total_hands"]) == 910278
        ),
        "serialized_replay_intact": (
            len(current["ppo_replay_entries"]) == 2
            and current.get("ppo_replay_rng_state") is not None
            and int(current["ppo_replay_cumulative_rows"]) == 1602078
        ),
        "failure_log_preserved": sha256_path(failure_log) == "a5db11baef59ff6abb8f55bfd2415840c80dea3c7608fc9003c3d173bd06163c",
        "same_replay_deal_start": int(config["fixed_training_deal_start_index"]) == 33300000,
    }
    output = {
        "schema": "cardpilot.static_current_kl_2m_seed1_log_conflict_recovery.v1",
        "passed": all(gates.values()),
        "gates": gates,
        "checkpoint": {"path": str(current_path), "sha256": sha256_path(current_path)},
        "parent": {"path": str(parent_path), "sha256": sha256_path(parent_path)},
        "metrics_sha256": sha256_path(metrics_path),
        "assignments_sha256": sha256_path(assignments_path),
        "failure_log_sha256": sha256_path(failure_log),
        "assignment_restore": restored,
        "recovery_semantics": "repeat_same_uncommitted_iter222_worker_deals_and_pending_assignment",
        "command": [sys.executable, *sys.argv],
    }
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, sort_keys=True))
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
