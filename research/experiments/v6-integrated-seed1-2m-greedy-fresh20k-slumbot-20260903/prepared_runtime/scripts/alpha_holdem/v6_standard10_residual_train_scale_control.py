"""Matched scale-1 versus preservation-scale residual-regret training control."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.v6_standard10_residual_regret_smoke import run as run_arm


def _arm_args(args, scale, output_dir):
    return argparse.Namespace(
        standard10=args.standard10,
        iterations=args.iterations,
        traversals_per_player=args.traversals_per_player,
        train_steps=args.train_steps,
        batch_size=args.batch_size,
        lr=args.lr,
        residual_scale=scale,
        eval_pairs=args.eval_pairs,
        node_limit=args.node_limit,
        seed=args.seed,
        output_dir=output_dir,
    )


def run(args):
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    scale1 = run_arm(_arm_args(args, 1.0, args.output_dir / "scale_1"))
    scale001 = run_arm(_arm_args(args, 0.01, args.output_dir / "scale_0.01"))
    control_cells = {cell["anchor"]: cell for cell in scale1["evaluations"]}
    treatment_cells = {cell["anchor"]: cell for cell in scale001["evaluations"]}
    per_anchor = []
    for anchor in control_cells:
        control = control_cells[anchor]
        treatment = treatment_cells[anchor]
        per_anchor.append({
            "anchor": anchor,
            "scale_1_delta_bb100": control["paired_delta_bb100"],
            "scale_0_01_delta_bb100": treatment["paired_delta_bb100"],
            "treatment_minus_control_bb100": (
                treatment["paired_delta_bb100"] - control["paired_delta_bb100"]
            ),
            "scale_1_disagreement": control["greedy_disagreement_from_base"],
            "scale_0_01_disagreement": treatment["greedy_disagreement_from_base"],
        })
    treatment_standard10 = treatment_cells["standard10"]
    control_standard10 = control_cells["standard10"]
    treatment_positive = sum(
        cell["paired_delta_bb100"] > 0 for cell in treatment_cells.values()
    )
    max_treatment_disagreement = max(
        cell["greedy_disagreement_from_base"] for cell in treatment_cells.values()
    )
    gates = {
        "matched_root_and_eval_budgets": (
            scale1["accounting"]["environment_training_hands"]
            == scale001["accounting"]["environment_training_hands"]
            and scale1["accounting"]["evaluation_hands"]
            == scale001["accounting"]["evaluation_hands"]
        ),
        "preservation_scale_max_disagreement_le_0_25": max_treatment_disagreement <= 0.25,
        "preservation_scale_standard10_point_positive": (
            treatment_standard10["paired_delta_bb100"] > 0
        ),
        "preservation_scale_improves_standard10_direction": (
            treatment_standard10["paired_delta_bb100"]
            > control_standard10["paired_delta_bb100"]
        ),
        "preservation_scale_at_least_three_anchor_points_positive": treatment_positive >= 3,
    }
    result = {
        "schema_version": 1,
        "config": {
            "seed": args.seed,
            "iterations": args.iterations,
            "traversals_per_player": args.traversals_per_player,
            "train_steps": args.train_steps,
            "eval_pairs": args.eval_pairs,
            "scales": [1.0, 0.01],
        },
        "accounting": {
            "environment_training_hands": (
                scale1["accounting"]["environment_training_hands"]
                + scale001["accounting"]["environment_training_hands"]
            ),
            "evaluation_hands": (
                scale1["accounting"]["evaluation_hands"]
                + scale001["accounting"]["evaluation_hands"]
            ),
            "decision_nodes": (
                scale1["accounting"]["decision_nodes"]
                + scale001["accounting"]["decision_nodes"]
            ),
        },
        "arms": {
            "scale_1": {
                "summary": "scale_1/summary.json",
                "checkpoint": scale1["checkpoint"],
                "evaluations": scale1["evaluations"],
            },
            "scale_0_01": {
                "summary": "scale_0.01/summary.json",
                "checkpoint": scale001["checkpoint"],
                "evaluations": scale001["evaluations"],
            },
        },
        "comparison": {
            "per_anchor": per_anchor,
            "preservation_scale_positive_anchor_points": treatment_positive,
            "preservation_scale_max_greedy_disagreement": max_treatment_disagreement,
            "preservation_scale_mean_delta_bb100": float(np.mean([
                cell["paired_delta_bb100"] for cell in treatment_cells.values()
            ])),
        },
        "gates": gates,
        "elapsed_seconds": time.time() - started,
    }
    result["admit_preservation_scale_training"] = all(gates.values())
    result["decision"] = (
        "ADMIT_PRESERVATION_SCALE_RESIDUAL_TRAINING"
        if result["admit_preservation_scale_training"]
        else "REJECT_STANDARD10_RESIDUAL_REGRET_ROUTE"
    )
    (args.output_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--standard10", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--traversals-per-player", type=int, default=2)
    parser.add_argument("--train-steps", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--eval-pairs", type=int, default=1024)
    parser.add_argument("--node-limit", type=int, default=250_000)
    parser.add_argument("--seed", type=int, default=60913)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(1)
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
