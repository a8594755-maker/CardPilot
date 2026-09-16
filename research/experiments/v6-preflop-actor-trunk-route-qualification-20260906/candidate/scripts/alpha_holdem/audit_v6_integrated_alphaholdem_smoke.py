"""Audit the integrated replay/K-best/large-batch physical-v6 smoke."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_v5 import restore_group_assignment_rng_from_evidence


ARCHIVE_RE = re.compile(r"checkpoint_iter(?P<iteration>\d+)_hands(?P<hands>\d+)\.pt")
ALLOWED_CHANGED = {
    "policy_head.weight", "policy_head.bias",
    "preflop_policy_head.weight", "preflop_policy_head.bias",
    "value_head.0.weight", "value_head.0.bias",
    "value_head.2.weight", "value_head.2.bias",
    "value_head.4.weight", "value_head.4.bias",
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    run = args.run_dir.resolve()
    checkpoint_path = run / "latest.pt"
    manifest_path = run / "run_manifest.json"
    metrics_path = run / "h1_training_metrics.jsonl"
    assignments_path = run / "opponent_assignments.jsonl"
    log_path = run / "latest_train.log"
    for path in (checkpoint_path, manifest_path, metrics_path, assignments_path, log_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    base = torch.load(args.base, map_location="cpu", weights_only=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metrics = load_jsonl(metrics_path)
    assignments = load_jsonl(assignments_path)
    log_text = log_path.read_text(encoding="utf-8")
    logged_ratio_maxima = [float(value) for value in re.findall(r"rmax=([0-9.]+)", log_text)]
    config = checkpoint["config"]
    changed = sorted(
        name for name, value in base["model"].items()
        if name in checkpoint["model"] and torch.is_tensor(value)
        and not torch.equal(value, checkpoint["model"][name])
    )
    final_pool = checkpoint["pool_snapshots"]
    final_ids = [int(row["id"]) for row in final_pool]
    assignment_audit = restore_group_assignment_rng_from_evidence(
        assignments,
        metrics,
        rng=random.Random(0),
        seed=int(config["seed"]),
        worker_count=int(config["workers"]),
        pool_size=len(final_pool),
        pool_snapshot_ids=final_ids,
        group_count=int(config["opponent_groups"]),
        self_play_fraction=float(config["self_play_fraction"]),
        checkpoint_iteration=int(checkpoint["iteration"]),
        checkpoint_total_hands=int(checkpoint["total_hands"]),
    )
    replay_rows = [int(row["ppo_replay_rows"]) for row in metrics]
    replay_buffers = [int(row["ppo_replay_buffer_iterations"]) for row in metrics]
    env = checkpoint["environment_hand_accounting"]
    archive_rows = []
    for path in sorted((run / "checkpoints").glob("checkpoint_iter*_hands*.pt")):
        match = ARCHIVE_RE.fullmatch(path.name)
        if match:
            archive_rows.append({
                "iteration": int(match.group("iteration")),
                "hands": int(match.group("hands")),
                "path": str(path),
                "sha256": sha256_path(path),
            })
    optimizer_steps = []
    for state in checkpoint["optimizer"]["state"].values():
        step = state.get("step", 0)
        optimizer_steps.append(int(step.item() if hasattr(step, "item") else step))
    finite_fields = (
        "approx_kl", "reference_policy_kl", "preupdate_critic_mse",
        "entropy", "reward_per_hand",
    )
    gates = {
        "manifest_finished": manifest["status"] == "finished",
        "four_contiguous_updates": [row["iteration"] for row in metrics] == [1, 2, 3, 4],
        "checkpoint_manifest_metric_identity": (
            checkpoint["iteration"] == manifest["iteration"] == metrics[-1]["iteration"] == 4
            and checkpoint["total_hands"] == manifest["total_hands"] == metrics[-1]["hands"]
        ),
        "physical_environment_target_reached": (
            env["completed_hands"] >= 16_384 and env["prefix_complete"]
            and env["unknown_prefix_training_marker_hands"] == 0
        ),
        "all_12_workers_completed_hands": (
            len(env["session_worker_counts"]) == 12
            and all(row["completed_hands"] > 0 for row in env["session_worker_counts"])
        ),
        "fresh_replay_boundary_then_nonzero": replay_rows[0] == 0 and all(x > 0 for x in replay_rows[1:]),
        "replay_cumulative_exact": (
            sum(replay_rows) == checkpoint["ppo_replay_cumulative_rows"]
            and len(checkpoint["ppo_replay_entries"]) == 2
            and not checkpoint["ppo_replay_recovery_boundaries"]
            and set(replay_buffers) == {2}
        ),
        "dynamic_pool_grew_3_to_5": (
            len(final_pool) == 5 and final_ids == [0, 1, 2, 3, 4]
            and len(checkpoint["pool_candidate_history"]) == 5
        ),
        "assignment_rng_replay_exact": (
            assignment_audit["tail_iteration"] == 4
            and assignment_audit["pending_assignments"] is None
        ),
        "paper_batch_lr_and_recipe_exact": (
            config["mini_batch_size"] == 16_384
            and config["lr"] == 0.0003
            and config["ppo_replay_ratio"] == 0.5
            and config["ppo_replay_buffer_iterations"] == 2
            and config["k_best"] == 5
            and config["pool_strategy"] == "loss-kbest"
            and config["snapshot_every"] == 2
        ),
        "corrected_legacy_contract_bound": (
            checkpoint["env_version"] == "v6legacyv4obs"
            and checkpoint["legacy_weights_rebound_to_new_contract"] is True
            and checkpoint["observation_bridge_contract"]
            == "hunl_v6_physical_legacy_v4_observation_bridge_v1"
        ),
        "only_policy_and_value_heads_changed": set(changed) == ALLOWED_CHANGED,
        "optimizer_state_nonempty_and_synchronized": (
            len(optimizer_steps) == 10 and len(set(optimizer_steps)) == 1
            and optimizer_steps[0] > 0
        ),
        "finite_health_metrics": all(
            math.isfinite(float(row[key])) for row in metrics for key in finite_fields
        ),
        "trust_region_healthy": (
            max(abs(float(row["approx_kl"])) for row in metrics) < 0.01
            and max(float(row["reference_policy_kl"]) for row in metrics) < 0.01
            and not any(row["kl_early_stop_triggered"] for row in metrics)
        ),
        "importance_ratios_below_delta1": (
            len(logged_ratio_maxima) == 4 and max(logged_ratio_maxima) < 3.0
        ),
        "four_hash_bound_archives": [row["iteration"] for row in archive_rows] == [1, 2, 3, 4],
    }
    output = {
        "schema": "cardpilot.integrated_alphaholdem_contract_smoke_audit.v1",
        "checkpoint_sha256": sha256_path(checkpoint_path),
        "manifest_sha256": sha256_path(manifest_path),
        "metrics_sha256": sha256_path(metrics_path),
        "assignments_sha256": sha256_path(assignments_path),
        "log_sha256": sha256_path(log_path),
        "transition_hands": int(checkpoint["total_hands"]),
        "physical_environment_hands": int(env["completed_hands"]),
        "replay_rows_by_iteration": replay_rows,
        "replay_cumulative_rows": int(checkpoint["ppo_replay_cumulative_rows"]),
        "final_pool_ids": final_ids,
        "changed_tensors": changed,
        "max_approx_kl": max(abs(float(row["approx_kl"])) for row in metrics),
        "max_reference_policy_kl": max(float(row["reference_policy_kl"]) for row in metrics),
        "max_importance_ratio": max(logged_ratio_maxima),
        "assignment_audit": assignment_audit,
        "archives": archive_rows,
        "gates": gates,
        "passed": all(gates.values()),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, sort_keys=True))
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
