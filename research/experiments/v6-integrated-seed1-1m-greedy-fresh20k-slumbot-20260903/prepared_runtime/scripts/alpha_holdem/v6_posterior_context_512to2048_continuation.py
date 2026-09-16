"""Restart-safe three-seed continuation from 512 to 2,048 learning hands/group."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
from alpha_holdem.v6_broad_league_domain_feasibility import collect_balanced_states
from alpha_holdem.v6_broad_mgda_curve import load_frozen_policy
from alpha_holdem.v6_contextual_residual_mgda_smoke import (
    active_preservation, collect_learning_rounds, evaluate, summarize, train_mgda, write_jsonl_gz,
)
from alpha_holdem.v6_dual_contract_mgda_matched_smoke import residual_state
from alpha_holdem.v6_dual_contract_residual_training_smoke import sha256_path


def atomic_torch_save(payload: dict, path: Path):
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)


def make_groups(training, counts):
    groups = []
    for opponent_index, opponent in enumerate(training):
        for seat in (0, 1):
            index = opponent_index * 2 + seat
            groups.append({"opponent": opponent, "opponent_index": opponent_index, "hero_seat": seat, "counts": np.asarray(counts[index], dtype=np.int64)})
    return groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-run-dir", type=Path, required=True)
    parser.add_argument("--parent-aggregate-summary", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--context-classifier", type=Path, required=True)
    parser.add_argument("--expected-context-classifier-sha256", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--stage-rounds", type=int, default=384)
    parser.add_argument("--stages", type=int, default=4)
    parser.add_argument("--steps-per-stage", type=int, default=96)
    parser.add_argument("--group-batch-size", type=int, default=32)
    parser.add_argument("--warmup-hands", type=int, default=64)
    parser.add_argument("--pairs-per-policy", type=int, default=128)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.seeds != 3 or args.stage_rounds * args.stages != 1536 or args.warmup_hands != 64:
        parser.error("continuation requires three seeds and exact 512-to-2048 staging")
    classifier_sha = sha256_path(args.context_classifier)
    if classifier_sha != args.expected_context_classifier_sha256:
        raise ValueError("classifier SHA mismatch")
    base_sha = sha256_path(args.base_checkpoint)
    parent_checkpoints = [args.parent_run_dir / f"seed{seed}_endpoint512.pt" for seed in range(args.seeds)]
    parent_shas = [sha256_path(path) for path in parent_checkpoints]
    config = {
        "schema": "cardpilot.posterior_context_512to2048_manifest.v1", "base_sha256": base_sha,
        "classifier_sha256": classifier_sha, "parent_checkpoint_sha256": parent_shas,
        "seed": args.seed, "seeds": args.seeds, "stage_rounds": args.stage_rounds,
        "stages": args.stages, "steps_per_stage": args.steps_per_stage,
        "group_batch_size": args.group_batch_size, "pairs_per_policy": args.pairs_per_policy,
    }
    config_sha = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out_dir / "run_manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8"))["config_sha256"] != config_sha:
            raise ValueError("resume manifest configuration mismatch")
    else:
        manifest_path.write_text(json.dumps({**config, "config_sha256": config_sha, "created_at": datetime.now(timezone.utc).isoformat()}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    classifier = torch.load(args.context_classifier, map_location="cpu", weights_only=False)["models"]["64"]
    base_policy = load_policy(args.base_checkpoint, args.device)
    base_state = {name: tensor.detach().cpu().clone() for name, tensor in base_policy.model.state_dict().items()}
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    training = [load_frozen_policy(row, args.device) for row in spec["training_policies"]]
    holdouts = [load_frozen_policy(row, args.device) for row in spec["holdout_policies"]]
    states = collect_balanced_states(4096, int(spec["seed"]) + 3777)
    parent_aggregate = json.loads(args.parent_aggregate_summary.read_text(encoding="utf-8"))
    seed_results = []
    resumed_stages = 0
    for seed_index in range(args.seeds):
        seed_summary_path = args.out_dir / f"seed{seed_index}_summary.json"
        if seed_summary_path.exists():
            seed_results.append(json.loads(seed_summary_path.read_text(encoding="utf-8")))
            continue
        run_seed = args.seed + seed_index * 10_007
        parent = torch.load(parent_checkpoints[seed_index], map_location=args.device, weights_only=False)
        if parent["base_sha256"] != base_sha or parent["classifier_sha256"] != classifier_sha:
            raise ValueError("parent checkpoint contract mismatch")
        model = PosteriorCenteredResidualPolicy(base_policy.model, classifier, reliability_power=0).to(args.device).eval()
        model.load_state_dict(parent["residual_state_dict"], strict=False)
        optimizer = torch.optim.Adam(model.trainable_parameters(), lr=3e-4)
        optimizer.load_state_dict(parent["optimizer"])
        groups = make_groups(training, parent["group_counts"])
        completed = 512
        stage_results = []
        for stage_index in range(args.stages):
            endpoint = 512 + (stage_index + 1) * args.stage_rounds
            checkpoint_path = args.out_dir / f"seed{seed_index}_endpoint{endpoint}.pt"
            evidence_path = args.out_dir / f"seed{seed_index}_endpoint{endpoint}_learning_hands.jsonl.gz"
            schedule_path = args.out_dir / f"seed{seed_index}_endpoint{endpoint}_schedule.jsonl.gz"
            if checkpoint_path.exists():
                saved = torch.load(checkpoint_path, map_location=args.device, weights_only=False)
                if saved["config_sha256"] != config_sha or saved["endpoint_learning_hands_per_group"] != endpoint:
                    raise ValueError("invalid resume checkpoint")
                if sha256_path(evidence_path) != saved["training_evidence_sha256"] or sha256_path(schedule_path) != saved["schedule_sha256"]:
                    raise ValueError("resume stage evidence mismatch")
                model.load_state_dict(saved["residual_state_dict"], strict=False)
                optimizer.load_state_dict(saved["optimizer"])
                groups = make_groups(training, saved["group_counts"])
                stage_results.append(saved["stage_summary"])
                completed = endpoint
                resumed_stages += 1
                continue
            transitions, rows = collect_learning_rounds(
                model, base_policy, groups, seed=run_seed, round_start=completed,
                round_count=args.stage_rounds, device=args.device,
            )
            write_jsonl_gz(evidence_path, rows)
            optimizer, geometry, schedules, update_l2, support = train_mgda(
                model, transitions, steps=args.steps_per_stage, group_batch_size=args.group_batch_size,
                seed=run_seed + (stage_index + 2) * 20_003, device=args.device, optimizer=optimizer,
            )
            write_jsonl_gz(schedule_path, [{"step": i, "indices": [x.tolist() for x in schedule]} for i, schedule in enumerate(schedules)])
            stage_summary = {
                "stage_index": stage_index, "start_learning_hands_per_group": completed,
                "endpoint_learning_hands_per_group": endpoint, "environment_training_hands": len(rows),
                "transition_rows": len(transitions), "group_decision_support": support,
                "conditioning_parameter_update_l2": update_l2, "steps": len(geometry),
                "positive_worst_alignment_fraction": float(np.mean([row["applied_worst_alignment"] > 0 for row in geometry])),
                "minimum_applied_worst_alignment": float(min(row["applied_worst_alignment"] for row in geometry)),
                "training_evidence_sha256": sha256_path(evidence_path), "schedule_sha256": sha256_path(schedule_path),
            }
            atomic_torch_save({
                "schema": "cardpilot.posterior_context_512to2048_checkpoint.v1", "config_sha256": config_sha,
                "seed_index": seed_index, "seed": run_seed, "endpoint_learning_hands_per_group": endpoint,
                "base_sha256": base_sha, "classifier_sha256": classifier_sha,
                "parent_checkpoint_sha256": parent_shas[seed_index], "residual_state_dict": residual_state(model),
                "optimizer": optimizer.state_dict(), "group_counts": [group["counts"].tolist() for group in groups],
                "training_evidence_sha256": sha256_path(evidence_path), "schedule_sha256": sha256_path(schedule_path),
                "step_geometry": geometry, "stage_summary": stage_summary,
            }, checkpoint_path)
            stage_results.append(stage_summary)
            completed = endpoint
            print(json.dumps({"seed": seed_index, "endpoint": endpoint, "hands": len(rows), "positive_geometry": stage_summary["positive_worst_alignment_fraction"]}), flush=True)
        deployment = PosteriorCenteredResidualPolicy(base_policy.model, classifier, reliability_power=1).to(args.device).eval()
        deployment.load_state_dict(residual_state(model), strict=False)
        policies = [("training", row) for row in training] + [("holdout", row) for row in holdouts]
        eval_rows, eval_warmup, max_delta, contexts = evaluate(
            deployment, base_policy, policies, seed=run_seed + 140_000_009,
            warmup_hands=args.warmup_hands, pairs_per_policy=args.pairs_per_policy, device=args.device,
        )
        eval_path = args.out_dir / f"seed{seed_index}_endpoint2048_evaluation.jsonl.gz"
        write_jsonl_gz(eval_path, eval_warmup + eval_rows)
        evaluation = summarize(eval_rows)
        preservation = active_preservation(deployment, base_policy, states, contexts, args.device)
        parent_row = parent_aggregate["seed_results"][seed_index]["endpoints"][-1]
        result = {
            "seed_index": seed_index, "seed": run_seed, "parent_checkpoint_sha256": parent_shas[seed_index],
            "stage_results": stage_results, "new_environment_training_hands": sum(row["environment_training_hands"] for row in stage_results),
            "evaluation_environment_hands": len(eval_warmup) + 3 * len(eval_rows),
            "evaluation": evaluation, "evaluation_evidence_sha256": sha256_path(eval_path),
            "preservation": preservation, "maximum_evaluation_delta": max_delta,
            "pooled_slope_bb100": evaluation["pooled_correct_minus_base"]["bb100"] - parent_row["evaluation"]["pooled_correct_minus_base"]["bb100"],
            "holdout_slope_bb100": evaluation["splits"]["holdout"]["correct_minus_base"]["bb100"] - parent_row["evaluation"]["splits"]["holdout"]["correct_minus_base"]["bb100"],
        }
        seed_summary_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        seed_results.append(result)
        print(json.dumps({"seed": seed_index, "endpoint": 2048, "delta": evaluation["pooled_correct_minus_base"]["bb100"], "holdout": evaluation["splits"]["holdout"]["correct_minus_base"]["bb100"], "slope": result["pooled_slope_bb100"]}), flush=True)
    new_training_hands = sum(row["new_environment_training_hands"] for row in seed_results)
    evaluation_hands = sum(row["evaluation_environment_hands"] for row in seed_results)
    final_holdouts = [row["evaluation"]["splits"]["holdout"]["correct_minus_base"]["bb100"] for row in seed_results]
    final_seats = [row["evaluation"]["seats"][str(seat)]["bb100"] for row in seed_results for seat in (0, 1)]
    gates = {
        "new_training_hands_exact": new_training_hands == args.seeds * 12 * 1536,
        "evaluation_hands_exact": evaluation_hands == args.seeds * (9 * 2 * 64 + 9 * 2 * args.pairs_per_policy * 3),
        "positive_slope_in_at_least_two_seeds": sum(row["pooled_slope_bb100"] > 0 for row in seed_results) >= 2,
        "at_least_two_final_holdout_seeds_nonnegative": sum(value >= 0 for value in final_holdouts) >= 2,
        "median_final_holdout_nonnegative": float(np.median(final_holdouts)) >= 0,
        "median_final_seat_nonnegative": float(np.median(final_seats)) >= 0,
        "median_correct_context_beats_wrong": float(np.median([row["evaluation"]["pooled_correct_minus_wrong"]["bb100"] for row in seed_results])) > 0,
        "all_stage_geometry_positive_at_least_75pct": all(stage["positive_worst_alignment_fraction"] >= 0.75 for row in seed_results for stage in row["stage_results"]),
        "all_source_agreement_at_least_95pct": all(row["preservation"]["overall_agreement"] >= 0.95 for row in seed_results),
        "all_source_partitions_at_least_90pct": all(row["preservation"]["minimum_partition_agreement"] >= 0.90 for row in seed_results),
        "all_zero_context_exact": all(row["preservation"]["zero_context_exact"] for row in seed_results),
        "base_state_unchanged": all(torch.equal(base_state[name], tensor.detach().cpu()) for name, tensor in base_policy.model.state_dict().items()),
        "base_file_hash_unchanged": sha256_path(args.base_checkpoint) == base_sha,
    }
    admitted = all(gates.values())
    summary = {
        "schema": "cardpilot.posterior_context_512to2048_continuation.v1", "status": "COMPLETED",
        "claim_scope": "GEOMETRIC_BROAD_LEAGUE_CONTINUATION_NOT_SLUMBOT_STRENGTH",
        "config_sha256": config_sha, "new_environment_training_hands": new_training_hands,
        "lineage_environment_training_hands": args.seeds * 12 * (64 + 2048), "evaluation_hands": evaluation_hands,
        "resumed_stages": resumed_stages, "seed_results": seed_results,
        "median_final_holdout_bb100": float(np.median(final_holdouts)), "median_final_seat_bb100": float(np.median(final_seats)),
        "gates": gates, "admitted": admitted,
        "decision": "ADMIT_POSTERIOR_CONTEXT_NEXT_GEOMETRIC_SCALE" if admitted else "HOLD_POSTERIOR_CONTEXT_AT_2048",
        "wall_time_seconds": time.time() - started, "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"new_training_hands": new_training_hands, "evaluation_hands": evaluation_hands, "gates": gates, "decision": summary["decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
