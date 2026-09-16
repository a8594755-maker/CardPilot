"""Three-seed 128-to-512 posterior-context learning curve with frozen endpoints."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.contextual_residual_v6 import PosteriorCenteredResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_broad_league_domain_feasibility import collect_balanced_states
from alpha_holdem.v6_broad_mgda_curve import load_frozen_policy
from alpha_holdem.v6_contextual_residual_mgda_smoke import (
    active_preservation,
    collect_learning_rounds,
    evaluate,
    initialize_training_groups,
    summarize,
    train_mgda,
    write_jsonl_gz,
)
from alpha_holdem.v6_dual_contract_gradient_conflict_audit import residual_state_digest
from alpha_holdem.v6_dual_contract_mgda_matched_smoke import residual_state
from alpha_holdem.v6_dual_contract_residual_training_smoke import sha256_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--context-classifier", type=Path, required=True)
    parser.add_argument("--expected-context-classifier-sha256", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--warmup-hands", type=int, default=64)
    parser.add_argument("--first-learning-hands-per-group", type=int, default=128)
    parser.add_argument("--final-learning-hands-per-group", type=int, default=512)
    parser.add_argument("--first-steps", type=int, default=32)
    parser.add_argument("--additional-steps", type=int, default=96)
    parser.add_argument("--group-batch-size", type=int, default=32)
    parser.add_argument("--pairs-per-policy", type=int, default=64)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    if args.seeds < 3 or args.warmup_hands != 64 or args.first_learning_hands_per_group != 128 or args.final_learning_hands_per_group != 512:
        parser.error("curve requires at least three seeds and fixed 64/128/512 geometric endpoints")
    classifier_sha = sha256_path(args.context_classifier)
    if classifier_sha != args.expected_context_classifier_sha256:
        raise ValueError("context classifier SHA mismatch")
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    classifier = torch.load(args.context_classifier, map_location="cpu", weights_only=False)["models"]["64"]
    base_sha = sha256_path(args.base_checkpoint)
    base_policy = load_policy(args.base_checkpoint, args.device)
    base_state = {name: tensor.detach().cpu().clone() for name, tensor in base_policy.model.state_dict().items()}
    training = [load_frozen_policy(row, args.device) for row in spec["training_policies"]]
    holdouts = [load_frozen_policy(row, args.device) for row in spec["holdout_policies"]]
    if len(training) != 6 or len(holdouts) != 3 or not {p.sha256 for p in training}.isdisjoint({p.sha256 for p in holdouts}):
        raise ValueError("expected six training and three SHA-disjoint holdout policies")
    states = collect_balanced_states(2048, int(spec["seed"]) + 2777)
    endpoints = [args.first_learning_hands_per_group, args.final_learning_hands_per_group]
    endpoint_steps = [args.first_steps, args.additional_steps]
    seed_results = []
    artifacts = []
    actual_training_hands = 0
    evaluation_hands = 0
    for seed_index in range(args.seeds):
        run_seed = args.seed + seed_index * 10_007
        torch.manual_seed(run_seed)
        model = PosteriorCenteredResidualPolicy(base_policy.model, classifier, reliability_power=0).to(args.device).eval()
        initial_sha = residual_state_digest(model)
        optimizer = None
        groups, warmup_rows = initialize_training_groups(base_policy, training, seed=run_seed, warmup_hands=args.warmup_hands)
        warmup_path = args.out_dir / f"seed{seed_index}_warmup_hands.jsonl.gz"
        write_jsonl_gz(warmup_path, warmup_rows)
        artifacts.append(warmup_path)
        actual_training_hands += len(warmup_rows)
        previous = 0
        endpoint_rows = []
        for endpoint_index, (endpoint, steps) in enumerate(zip(endpoints, endpoint_steps)):
            transitions, learning_rows = collect_learning_rounds(
                model, base_policy, groups, seed=run_seed, round_start=previous,
                round_count=endpoint - previous, device=args.device,
            )
            training_path = args.out_dir / f"seed{seed_index}_endpoint{endpoint}_learning_hands.jsonl.gz"
            write_jsonl_gz(training_path, learning_rows)
            artifacts.append(training_path)
            actual_training_hands += len(learning_rows)
            optimizer, geometry, schedules, update_l2, group_support = train_mgda(
                model, transitions, steps=steps, group_batch_size=args.group_batch_size,
                seed=run_seed + endpoint_index * 20_003, device=args.device, optimizer=optimizer,
            )
            schedule_path = args.out_dir / f"seed{seed_index}_endpoint{endpoint}_schedule.jsonl.gz"
            write_jsonl_gz(schedule_path, [{"step": i, "indices": [x.tolist() for x in schedule]} for i, schedule in enumerate(schedules)])
            checkpoint_path = args.out_dir / f"seed{seed_index}_endpoint{endpoint}.pt"
            torch.save({
                "schema": "cardpilot.posterior_context_curve_checkpoint.v1", "seed": run_seed,
                "seed_index": seed_index, "learning_hands_per_group": endpoint,
                "completed_environment_training_hands": args.warmup_hands * 12 + endpoint * 12,
                "base_sha256": base_sha, "classifier_sha256": classifier_sha,
                "initial_residual_sha256": initial_sha, "residual_state_dict": residual_state(model),
                "optimizer": optimizer.state_dict(), "group_counts": [group["counts"].tolist() for group in groups],
                "training_evidence_sha256": sha256_path(training_path), "schedule_sha256": sha256_path(schedule_path),
            }, checkpoint_path)
            artifacts.extend([schedule_path, checkpoint_path])
            deployment = PosteriorCenteredResidualPolicy(base_policy.model, classifier, reliability_power=1).to(args.device).eval()
            missing, unexpected = deployment.load_state_dict(residual_state(model), strict=False)
            if unexpected or any(not name.startswith("base.") for name in missing):
                raise ValueError("failed to construct reliability-shrunk frozen endpoint")
            policies = [("training", row) for row in training] + [("holdout", row) for row in holdouts]
            eval_rows, eval_warmup, max_delta, contexts = evaluate(
                deployment, base_policy, policies,
                seed=run_seed + 80_000_003 + endpoint_index * 9_000_001,
                warmup_hands=args.warmup_hands, pairs_per_policy=args.pairs_per_policy, device=args.device,
            )
            eval_path = args.out_dir / f"seed{seed_index}_endpoint{endpoint}_evaluation.jsonl.gz"
            write_jsonl_gz(eval_path, eval_warmup + eval_rows)
            artifacts.append(eval_path)
            endpoint_eval_hands = len(eval_warmup) + 3 * len(eval_rows)
            evaluation_hands += endpoint_eval_hands
            preservation = active_preservation(deployment, base_policy, states, contexts, args.device)
            endpoint_rows.append({
                "endpoint_learning_hands_per_group": endpoint,
                "cumulative_environment_training_hands": args.warmup_hands * 12 + endpoint * 12,
                "stage_environment_training_hands": len(learning_rows), "stage_transition_rows": len(transitions),
                "stage_steps": steps, "group_decision_support": group_support,
                "conditioning_parameter_update_l2": update_l2,
                "positive_worst_alignment_fraction": float(np.mean([row["applied_worst_alignment"] > 0 for row in geometry])),
                "evaluation_environment_hands": endpoint_eval_hands, "evaluation": summarize(eval_rows),
                "preservation": preservation, "maximum_evaluation_delta": max_delta,
                "checkpoint_sha256": sha256_path(checkpoint_path),
                "training_evidence_sha256": sha256_path(training_path), "schedule_sha256": sha256_path(schedule_path),
                "evaluation_evidence_sha256": sha256_path(eval_path),
            })
            print(json.dumps({"seed": seed_index, "endpoint": endpoint, "delta": endpoint_rows[-1]["evaluation"]["pooled_correct_minus_base"]["bb100"], "holdout": endpoint_rows[-1]["evaluation"]["splits"]["holdout"]["correct_minus_base"]["bb100"]}), flush=True)
            previous = endpoint
        slope = endpoint_rows[-1]["evaluation"]["pooled_correct_minus_base"]["bb100"] - endpoint_rows[0]["evaluation"]["pooled_correct_minus_base"]["bb100"]
        holdout_slope = endpoint_rows[-1]["evaluation"]["splits"]["holdout"]["correct_minus_base"]["bb100"] - endpoint_rows[0]["evaluation"]["splits"]["holdout"]["correct_minus_base"]["bb100"]
        seed_results.append({"seed_index": seed_index, "seed": run_seed, "endpoints": endpoint_rows, "pooled_slope_bb100": slope, "holdout_slope_bb100": holdout_slope})
    final_rows = [row["endpoints"][-1] for row in seed_results]
    positive_slopes = sum(row["pooled_slope_bb100"] > 0 for row in seed_results)
    final_holdouts = [row["evaluation"]["splits"]["holdout"]["correct_minus_base"]["bb100"] for row in final_rows]
    final_seats = [row["evaluation"]["seats"][str(seat)]["bb100"] for row in final_rows for seat in (0, 1)]
    gates = {
        "training_hands_exact": actual_training_hands == args.seeds * 12 * (args.warmup_hands + args.final_learning_hands_per_group),
        "evaluation_hands_exact": evaluation_hands == args.seeds * len(endpoints) * (9 * 2 * args.warmup_hands + 9 * 2 * args.pairs_per_policy * 3),
        "positive_slope_in_at_least_two_of_three_seeds": positive_slopes >= math.ceil(2 * args.seeds / 3),
        "median_final_holdout_delta_nonnegative": float(np.median(final_holdouts)) >= 0,
        "median_final_seat_delta_nonnegative": float(np.median(final_seats)) >= 0,
        "median_final_correct_context_beats_wrong": float(np.median([row["evaluation"]["pooled_correct_minus_wrong"]["bb100"] for row in final_rows])) > 0,
        "all_geometry_positive_at_least_75pct": all(endpoint["positive_worst_alignment_fraction"] >= 0.75 for row in seed_results for endpoint in row["endpoints"]),
        "all_source_agreement_at_least_95pct": all(row["preservation"]["overall_agreement"] >= 0.95 for row in final_rows),
        "all_source_partitions_at_least_90pct": all(row["preservation"]["minimum_partition_agreement"] >= 0.90 for row in final_rows),
        "all_zero_context_exact": all(row["preservation"]["zero_context_exact"] for row in final_rows),
        "base_state_unchanged": all(torch.equal(base_state[name], tensor.detach().cpu()) for name, tensor in base_policy.model.state_dict().items()),
        "base_file_hash_unchanged": sha256_path(args.base_checkpoint) == base_sha,
    }
    admitted = all(gates.values())
    summary = {
        "schema": "cardpilot.posterior_context_geometric_curve.v1", "status": "COMPLETED",
        "claim_scope": "GEOMETRIC_BROAD_LEAGUE_CURVE_NOT_SLUMBOT_STRENGTH",
        "base_sha256": base_sha, "classifier_sha256": classifier_sha,
        "actual_environment_training_hands": actual_training_hands, "evaluation_hands": evaluation_hands,
        "seed_results": seed_results, "positive_seed_slopes": positive_slopes,
        "median_final_holdout_delta_bb100": float(np.median(final_holdouts)),
        "median_final_seat_delta_bb100": float(np.median(final_seats)),
        "gates": gates, "admitted": admitted,
        "decision": "ADMIT_POSTERIOR_CONTEXT_NEXT_GEOMETRIC_SCALE" if admitted else "HOLD_POSTERIOR_CONTEXT_CURVE",
        "artifact_sha256": {path.name: sha256_path(path) for path in artifacts},
        "wall_time_seconds": time.time() - started, "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"training_hands": actual_training_hands, "evaluation_hands": evaluation_hands, "gates": gates, "decision": summary["decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
