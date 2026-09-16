"""Exact deterministic replay of curve training to recover omitted MGDA geometry."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.contextual_residual_v6 import PosteriorCenteredResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_broad_mgda_curve import load_frozen_policy
from alpha_holdem.v6_contextual_residual_mgda_smoke import (
    collect_learning_rounds,
    initialize_training_groups,
    train_mgda,
)
from alpha_holdem.v6_dual_contract_mgda_matched_smoke import residual_state
from alpha_holdem.v6_dual_contract_residual_training_smoke import sha256_path


def read_gz(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def logical_digest(rows: list[dict]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def tensors_exact(left: dict, right: dict) -> bool:
    return left.keys() == right.keys() and all(torch.equal(left[key].detach().cpu(), right[key].detach().cpu()) for key in left)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--context-classifier", type=Path, required=True)
    parser.add_argument("--expected-context-classifier-sha256", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--group-batch-size", type=int, default=32)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    classifier_sha = sha256_path(args.context_classifier)
    if classifier_sha != args.expected_context_classifier_sha256:
        raise ValueError("classifier SHA mismatch")
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    classifier = torch.load(args.context_classifier, map_location="cpu", weights_only=False)["models"]["64"]
    base_policy = load_policy(args.base_checkpoint, args.device)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    training = [load_frozen_policy(row, args.device) for row in spec["training_policies"]]
    endpoints = (128, 512)
    steps = (32, 96)
    seed_results = []
    replay_hands = 0
    for seed_index in range(args.seeds):
        run_seed = args.seed + seed_index * 10_007
        torch.manual_seed(run_seed)
        model = PosteriorCenteredResidualPolicy(base_policy.model, classifier, reliability_power=0).to(args.device).eval()
        groups, warmup_rows = initialize_training_groups(base_policy, training, seed=run_seed, warmup_hands=64)
        saved_warmup = read_gz(args.run_dir / f"seed{seed_index}_warmup_hands.jsonl.gz")
        warmup_exact = logical_digest(warmup_rows) == logical_digest(saved_warmup)
        replay_hands += len(warmup_rows)
        optimizer = None
        previous = 0
        stage_results = []
        for endpoint_index, (endpoint, stage_steps) in enumerate(zip(endpoints, steps)):
            transitions, generated_rows = collect_learning_rounds(
                model, base_policy, groups, seed=run_seed, round_start=previous,
                round_count=endpoint - previous, device=args.device,
            )
            saved_rows = read_gz(args.run_dir / f"seed{seed_index}_endpoint{endpoint}_learning_hands.jsonl.gz")
            trajectory_exact = logical_digest(generated_rows) == logical_digest(saved_rows)
            replay_hands += len(generated_rows)
            optimizer, geometry, schedules, update_l2, support = train_mgda(
                model, transitions, steps=stage_steps, group_batch_size=args.group_batch_size,
                seed=run_seed + endpoint_index * 20_003, device=args.device, optimizer=optimizer,
            )
            generated_schedules = [{"step": i, "indices": [x.tolist() for x in schedule]} for i, schedule in enumerate(schedules)]
            saved_schedules = read_gz(args.run_dir / f"seed{seed_index}_endpoint{endpoint}_schedule.jsonl.gz")
            schedule_exact = logical_digest(generated_schedules) == logical_digest(saved_schedules)
            checkpoint = torch.load(args.run_dir / f"seed{seed_index}_endpoint{endpoint}.pt", map_location=args.device, weights_only=False)
            checkpoint_exact = tensors_exact(residual_state(model), checkpoint["residual_state_dict"])
            stage_results.append({
                "endpoint_learning_hands_per_group": endpoint, "warmup_exact": warmup_exact,
                "trajectory_exact": trajectory_exact, "schedule_exact": schedule_exact,
                "checkpoint_tensors_exact": checkpoint_exact, "group_decision_support": support,
                "conditioning_parameter_update_l2": update_l2,
                "positive_worst_alignment_fraction": float(np.mean([row["applied_worst_alignment"] > 0 for row in geometry])),
                "minimum_applied_worst_alignment": float(min(row["applied_worst_alignment"] for row in geometry)),
                "minimum_ordinary_worst_alignment": float(min(row["ordinary_worst_alignment"] for row in geometry)),
                "steps": len(geometry),
            })
            print(json.dumps({"seed": seed_index, "endpoint": endpoint, "trajectory_exact": trajectory_exact, "schedule_exact": schedule_exact, "checkpoint_exact": checkpoint_exact, "positive_geometry": stage_results[-1]["positive_worst_alignment_fraction"]}), flush=True)
            previous = endpoint
        seed_results.append({"seed_index": seed_index, "seed": run_seed, "stages": stage_results})
    all_stages = [stage for seed in seed_results for stage in seed["stages"]]
    gates = {
        "replay_hands_exact": replay_hands == args.seeds * 12 * (64 + 512),
        "all_warmups_exact": all(stage["warmup_exact"] for stage in all_stages),
        "all_trajectories_exact": all(stage["trajectory_exact"] for stage in all_stages),
        "all_schedules_exact": all(stage["schedule_exact"] for stage in all_stages),
        "all_checkpoint_tensors_exact": all(stage["checkpoint_tensors_exact"] for stage in all_stages),
        "all_geometry_positive_at_least_75pct": all(stage["positive_worst_alignment_fraction"] >= 0.75 for stage in all_stages),
        "all_optimizer_states_nonempty": all(bool(torch.load(args.run_dir / f"seed{seed['seed_index']}_endpoint{stage['endpoint_learning_hands_per_group']}.pt", map_location="cpu", weights_only=False)["optimizer"]["state"]) for seed in seed_results for stage in seed["stages"]),
    }
    admitted = all(gates.values())
    summary = {
        "schema": "cardpilot.posterior_context_curve_geometry_replay.v1", "status": "COMPLETED",
        "claim_scope": "EXACT_REPLAY_OF_EXISTING_HANDS_NOT_NEW_ENVIRONMENT_TRAINING",
        "new_environment_hands": 0, "replayed_existing_hands": replay_hands,
        "seed_results": seed_results, "gates": gates, "admitted": admitted,
        "decision": "RESTORE_CURVE_GEOMETRY_PROVENANCE" if admitted else "CURVE_REPLAY_MISMATCH",
        "wall_time_seconds": time.time() - started, "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"replayed_hands": replay_hands, "gates": gates, "decision": summary["decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
