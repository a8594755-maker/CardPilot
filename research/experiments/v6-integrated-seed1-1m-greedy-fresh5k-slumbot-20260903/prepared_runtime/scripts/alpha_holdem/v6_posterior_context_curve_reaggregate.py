"""Recover a completed geometric curve from immutable stage artifacts only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
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
from alpha_holdem.v6_contextual_residual_mgda_smoke import active_preservation, summarize
from alpha_holdem.v6_contextual_residual_sensitivity_audit import final_group_contexts
from alpha_holdem.v6_dual_contract_residual_training_smoke import sha256_path


def read_rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def group_support(rows: list[dict]) -> dict:
    support = {index: 0 for index in range(12)}
    for row in rows:
        support[int(row["group_index"])] += len(row["hero_decisions"])
    return {f"group{index:02d}": value for index, value in support.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--context-classifier", type=Path, required=True)
    parser.add_argument("--expected-context-classifier-sha256", required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--states", type=int, default=2048)
    parser.add_argument("--state-seed", type=int, required=True)
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
    base_sha = sha256_path(args.base_checkpoint)
    states = collect_balanced_states(args.states, args.state_seed)
    endpoints = (128, 512)
    seed_results = []
    artifact_hashes = {}
    actual_training_hands = 0
    evaluation_hands = 0
    for seed_index in range(args.seeds):
        warmup_path = args.run_dir / f"seed{seed_index}_warmup_hands.jsonl.gz"
        warmup_rows = read_rows(warmup_path)
        actual_training_hands += len(warmup_rows)
        artifact_hashes[warmup_path.name] = sha256_path(warmup_path)
        endpoint_rows = []
        for endpoint in endpoints:
            training_path = args.run_dir / f"seed{seed_index}_endpoint{endpoint}_learning_hands.jsonl.gz"
            schedule_path = args.run_dir / f"seed{seed_index}_endpoint{endpoint}_schedule.jsonl.gz"
            checkpoint_path = args.run_dir / f"seed{seed_index}_endpoint{endpoint}.pt"
            eval_path = args.run_dir / f"seed{seed_index}_endpoint{endpoint}_evaluation.jsonl.gz"
            training_rows = read_rows(training_path)
            eval_all = read_rows(eval_path)
            eval_rows = [row for row in eval_all if "correct_minus_base_bb" in row]
            eval_warmup = [row for row in eval_all if "correct_minus_base_bb" not in row]
            actual_training_hands += len(training_rows)
            evaluation_hands += len(eval_warmup) + 3 * len(eval_rows)
            payload = torch.load(checkpoint_path, map_location=args.device, weights_only=False)
            if payload["base_sha256"] != base_sha or payload["classifier_sha256"] != classifier_sha:
                raise ValueError("checkpoint frozen parent mismatch")
            if payload["training_evidence_sha256"] != sha256_path(training_path) or payload["schedule_sha256"] != sha256_path(schedule_path):
                raise ValueError("checkpoint stage evidence mismatch")
            model = PosteriorCenteredResidualPolicy(base_policy.model, classifier, reliability_power=1).to(args.device).eval()
            missing, unexpected = model.load_state_dict(payload["residual_state_dict"], strict=False)
            if unexpected or any(not name.startswith("base.") for name in missing):
                raise ValueError("invalid endpoint residual keys")
            contexts_array = final_group_contexts(training_path)
            contexts = {(index // 2, index % 2): contexts_array[index] for index in range(12)}
            # Preservation only needs a diverse context map; keys are not opponent identities.
            preservation = active_preservation(model, base_policy, states, contexts, args.device)
            endpoint_rows.append({
                "endpoint_learning_hands_per_group": endpoint,
                "cumulative_environment_training_hands": 12 * (64 + endpoint),
                "stage_environment_training_hands": len(training_rows),
                "stage_transition_rows": sum(len(row["hero_decisions"]) for row in training_rows),
                "group_decision_support": group_support(training_rows),
                "evaluation_environment_hands": len(eval_warmup) + 3 * len(eval_rows),
                "evaluation": summarize(eval_rows), "preservation": preservation,
                "checkpoint_sha256": sha256_path(checkpoint_path),
                "training_evidence_sha256": sha256_path(training_path),
                "schedule_sha256": sha256_path(schedule_path), "evaluation_evidence_sha256": sha256_path(eval_path),
                "geometry_evidence_available": False,
            })
            for path in (training_path, schedule_path, checkpoint_path, eval_path):
                artifact_hashes[path.name] = sha256_path(path)
        seed_results.append({
            "seed_index": seed_index, "endpoints": endpoint_rows,
            "pooled_slope_bb100": endpoint_rows[1]["evaluation"]["pooled_correct_minus_base"]["bb100"] - endpoint_rows[0]["evaluation"]["pooled_correct_minus_base"]["bb100"],
            "holdout_slope_bb100": endpoint_rows[1]["evaluation"]["splits"]["holdout"]["correct_minus_base"]["bb100"] - endpoint_rows[0]["evaluation"]["splits"]["holdout"]["correct_minus_base"]["bb100"],
        })
    final_rows = [row["endpoints"][-1] for row in seed_results]
    final_holdouts = [row["evaluation"]["splits"]["holdout"]["correct_minus_base"]["bb100"] for row in final_rows]
    final_seats = [row["evaluation"]["seats"][str(seat)]["bb100"] for row in final_rows for seat in (0, 1)]
    positive_slopes = sum(row["pooled_slope_bb100"] > 0 for row in seed_results)
    gates = {
        "training_hands_exact": actual_training_hands == args.seeds * 12 * (64 + 512),
        "evaluation_hands_exact": evaluation_hands == args.seeds * 2 * (9 * 2 * 64 + 9 * 2 * 64 * 3),
        "all_stage_hash_chains_match": True,
        "positive_slope_in_at_least_two_of_three_seeds": positive_slopes >= 2,
        "median_final_holdout_delta_nonnegative": float(np.median(final_holdouts)) >= 0,
        "median_final_seat_delta_nonnegative": float(np.median(final_seats)) >= 0,
        "median_final_correct_context_beats_wrong": float(np.median([row["evaluation"]["pooled_correct_minus_wrong"]["bb100"] for row in final_rows])) > 0,
        "all_source_agreement_at_least_95pct": all(row["preservation"]["overall_agreement"] >= 0.95 for row in final_rows),
        "all_source_partitions_at_least_90pct": all(row["preservation"]["minimum_partition_agreement"] >= 0.90 for row in final_rows),
        "all_zero_context_exact": all(row["preservation"]["zero_context_exact"] for row in final_rows),
        "per_step_geometry_evidence_available": False,
    }
    summary = {
        "schema": "cardpilot.posterior_context_geometric_curve_reaggregate.v1", "status": "COMPLETED",
        "claim_scope": "POSTPROCESS_RECOVERY_NOT_NEW_ENVIRONMENT_WORK",
        "new_environment_hands": 0, "recovered_training_hands": actual_training_hands,
        "recovered_evaluation_hands": evaluation_hands, "seed_results": seed_results,
        "positive_seed_slopes": positive_slopes, "median_final_holdout_delta_bb100": float(np.median(final_holdouts)),
        "median_final_seat_delta_bb100": float(np.median(final_seats)), "gates": gates,
        "admitted": False,
        "decision": "HOLD_CURVE_FOR_MISSING_GEOMETRY_PROVENANCE",
        "artifact_sha256": artifact_hashes,
        "wall_time_seconds": time.time() - started, "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"recovered_training_hands": actual_training_hands, "recovered_evaluation_hands": evaluation_hands, "positive_seed_slopes": positive_slopes, "median_final_holdout": summary["median_final_holdout_delta_bb100"], "gates": gates, "decision": summary["decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
