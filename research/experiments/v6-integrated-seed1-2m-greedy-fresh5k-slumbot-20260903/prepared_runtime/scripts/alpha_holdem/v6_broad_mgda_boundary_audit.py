"""Offline checkpoint-dose and paired-slope audit for broad MGDA."""
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

from alpha_holdem.dual_contract_residual_v6 import DualContractResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_broad_league_domain_feasibility import collect_balanced_states, sha256_path
from alpha_holdem.v6_broad_mgda_curve import source_preservation, summarize_evaluation
from alpha_holdem.v6_dual_contract_residual_training_smoke import mean_ci95


def paired_interval(rows: list[dict], first_chunk: int, last_chunk: int) -> list[dict]:
    lookup = {
        (row["seed_index"], row["holdout_label"], row["pair_index"], row["chunk_index"]): row
        for row in rows
    }
    result = []
    for key, first in lookup.items():
        seed, holdout, pair, chunk = key
        if chunk != first_chunk:
            continue
        last = lookup[(seed, holdout, pair, last_chunk)]
        result.append({
            "seed_index": seed,
            "holdout_label": holdout,
            "pair_index": pair,
            "delta_slope_bb": last["delta_bb"] - first["delta_bb"],
            "seat_slope_bb": [last["seat_delta_bb"][seat] - first["seat_delta_bb"][seat] for seat in (0, 1)],
        })
    return result


def summarize_interval(rows: list[dict], first_chunk: int, last_chunk: int) -> dict:
    paired = paired_interval(rows, first_chunk, last_chunk)
    seeds = []
    for seed in sorted({row["seed_index"] for row in paired}):
        selected = [row for row in paired if row["seed_index"] == seed]
        mean, half = mean_ci95([row["delta_slope_bb"] for row in selected])
        holdouts = []
        for label in sorted({row["holdout_label"] for row in selected}):
            local = [row for row in selected if row["holdout_label"] == label]
            local_mean, local_half = mean_ci95([row["delta_slope_bb"] for row in local])
            holdouts.append({"label": label, "slope_bb100": local_mean * 100.0, "slope_ci95_half_bb100": local_half * 100.0})
        seats = []
        for seat in (0, 1):
            local_mean, local_half = mean_ci95([row["seat_slope_bb"][seat] for row in selected])
            seats.append({"seat": seat, "slope_bb100": local_mean * 100.0, "slope_ci95_half_bb100": local_half * 100.0})
        seeds.append({"seed_index": seed, "pairs": len(selected), "slope_bb100": mean * 100.0, "slope_ci95_half_bb100": half * 100.0, "holdouts": holdouts, "seats": seats})
    return {
        "first_chunk": first_chunk,
        "last_chunk": last_chunk,
        "first_hands": first_chunk * 8192,
        "last_hands": last_chunk * 8192,
        "positive_seed_slopes": sum(row["slope_bb100"] > 0 for row in seeds),
        "seeds": seeds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    run_dir = args.run_dir.resolve()
    spec_path = args.spec.resolve()
    base_path = args.base_checkpoint.resolve()
    prior = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if prior["base_sha256"] != sha256_path(base_path) or prior["spec_sha256"] != sha256_path(spec_path):
        raise ValueError("source run identity mismatch")
    base_policy = load_policy(base_path, args.device)
    states = collect_balanced_states(4096, int(spec["seed"]) + 991)
    preservation_curve = []
    for checkpoint_row in sorted(prior["checkpoints"], key=lambda row: (row["seed_index"], row["chunk_index"])):
        path = Path(checkpoint_row["path"])
        if sha256_path(path) != checkpoint_row["sha256"]:
            raise ValueError(f"checkpoint hash mismatch: {path}")
        checkpoint = torch.load(path, map_location=args.device, weights_only=False)
        model = DualContractResidualPolicy(base_policy.model, hidden=128, policy_delta_cap=0.25).to(args.device).eval()
        model.load_state_dict(checkpoint["residual_state_dict"], strict=False)
        metrics = source_preservation(model, base_policy, states, args.device)
        preservation_curve.append({
            "seed_index": checkpoint_row["seed_index"],
            "chunk_index": checkpoint_row["chunk_index"],
            "hands": checkpoint_row["hands"],
            "checkpoint_sha256": checkpoint_row["sha256"],
            **metrics,
        })
        print(f"seed={checkpoint_row['seed_index']} chunk={checkpoint_row['chunk_index']} agreement={metrics['overall_agreement']:.6f} min_partition={metrics['minimum_partition_agreement']:.6f} max_delta={metrics['max_abs_residual_logit']:.6f}", flush=True)
        del model
    evidence_path = run_dir / "evaluation_pairs.jsonl.gz"
    if sha256_path(evidence_path) != prior["evaluation_evidence_sha256"]:
        raise ValueError("evaluation evidence hash mismatch")
    with gzip.open(evidence_path, "rt", encoding="utf-8") as handle:
        evaluation_rows = [json.loads(line) for line in handle]
    intervals = [summarize_interval(evaluation_rows, first, last) for first, last in ((2, 4), (4, 8), (2, 8))]
    dose_results = []
    for chunk in (2, 4, 8):
        seed_rows = []
        for seed in range(3):
            selected = [row for row in evaluation_rows if row["chunk_index"] == chunk and row["seed_index"] == seed]
            seed_rows.append({"seed_index": seed, **summarize_evaluation(selected)})
        holdout_points = [cell["delta_bb100"] for row in seed_rows for cell in row["holdouts"]]
        seat_points = [cell["delta_bb100"] for row in seed_rows for cell in row["seats"]]
        source_rows = [row for row in preservation_curve if row["chunk_index"] == chunk]
        dose_results.append({
            "chunk_index": chunk,
            "hands": chunk * 8192,
            "seeds": seed_rows,
            "positive_seed_pooled_deltas": sum(row["pooled_delta_bb100"] > 0 for row in seed_rows),
            "median_seed_holdout_delta_bb100": float(np.median(holdout_points)),
            "median_seed_seat_delta_bb100": float(np.median(seat_points)),
            "all_seed_source_overall_at_least_95pct": all(row["overall_agreement"] >= 0.95 for row in source_rows),
            "all_seed_source_partitions_at_least_90pct": all(row["minimum_partition_agreement"] >= 0.90 for row in source_rows),
        })
    per_seed_boundaries = []
    for seed in range(3):
        rows = [row for row in preservation_curve if row["seed_index"] == seed]
        safe = [row for row in rows if row["overall_agreement"] >= 0.95 and row["minimum_partition_agreement"] >= 0.90]
        saturated = [row for row in rows if row["max_abs_residual_logit"] >= 0.249]
        per_seed_boundaries.append({
            "seed_index": seed,
            "last_preservation_safe_hands": max((row["hands"] for row in safe), default=0),
            "first_cap_saturation_hands": min((row["hands"] for row in saturated), default=None),
        })
    dose32 = next(row for row in dose_results if row["chunk_index"] == 4)
    slope16_32 = next(row for row in intervals if row["first_chunk"] == 2 and row["last_chunk"] == 4)
    gates = {
        "all_24_checkpoint_hashes_match": len(preservation_curve) == 24,
        "evaluation_hash_matches": True,
        "dose32_all_seed_source_overall_at_least_95pct": dose32["all_seed_source_overall_at_least_95pct"],
        "dose32_all_seed_source_partitions_at_least_90pct": dose32["all_seed_source_partitions_at_least_90pct"],
        "dose16_to_32_positive_slope_at_least_2_of_3_seeds": slope16_32["positive_seed_slopes"] >= 2,
        "dose32_median_holdout_nonnegative": dose32["median_seed_holdout_delta_bb100"] >= 0,
        "dose32_median_seat_nonnegative": dose32["median_seed_seat_delta_bb100"] >= 0,
    }
    admitted = all(gates.values())
    result = {
        "schema": "cardpilot.broad_mgda_boundary_audit.v1",
        "status": "COMPLETED",
        "source_run": str(run_dir),
        "source_summary_sha256": sha256_path(run_dir / "summary.json"),
        "evaluation_evidence_sha256": sha256_path(evidence_path),
        "preservation_states": len(states),
        "preservation_queries": len(states) * len(preservation_curve),
        "preservation_curve": preservation_curve,
        "paired_intervals": intervals,
        "dose_results": dose_results,
        "per_seed_boundaries": per_seed_boundaries,
        "gates": gates,
        "admitted_lower_update_dose_curve": admitted,
        "decision": "ADMIT_HALF_UPDATE_DOSE_65K_REPLICATION" if admitted else "CLOSE_CURRENT_BROAD_MGDA_SCHEDULE",
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"gates": gates, "boundaries": per_seed_boundaries, "decision": result["decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
