#!/usr/bin/env python3
"""Matched-terminal-node opponent multisampling control for river belief CFR."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.v6_river_public_belief_cfr_feasibility import (
    RiverCFRSolver,
    compare_seed_strategies,
    sha256_path,
)
from alpha_holdem.v6_river_public_belief_cfr_scale_control import (
    atomic_json,
    load_replication_cells,
    reference_from_row,
)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def parse_states(raw: str) -> list[int]:
    try:
        values = [int(value) for value in raw.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("states must be comma-separated integers") from exc
    if not values or any(value < 0 for value in values):
        raise argparse.ArgumentTypeError("states must be nonnegative")
    return values


def aggregate(rows: list[dict], states: list[int]) -> tuple[dict, list[dict]]:
    by_state = [
        sorted(
            [row for row in rows if row["state_index"] == state],
            key=lambda row: row["solver_seed"],
        )
        for state in states
    ]
    comparisons = [compare_seed_strategies(cell) for cell in by_state]
    weights = [row["comparisons"] for row in comparisons]
    return (
        {
            "pooled_tv": float(
                np.average(
                    [row["mean_total_variation"] for row in comparisons],
                    weights=weights,
                )
            ),
            "pooled_greedy_agreement": float(
                np.average(
                    [row["greedy_agreement"] for row in comparisons],
                    weights=weights,
                )
            ),
        },
        comparisons,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-run", type=Path, required=True)
    parser.add_argument("--control-run", type=Path, required=True)
    parser.add_argument("--states", default="0,2,4")
    parser.add_argument("--opponent-samples", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    states = parse_states(args.states)
    if len(set(states)) != len(states):
        parser.error("states must be unique nonnegative integers")
    if args.opponent_samples < 2:
        parser.error("variance control requires opponent-samples >=2")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cells_dir = args.output_dir / "cells"
    cells_dir.mkdir(exist_ok=True)
    summary_path = args.output_dir / "summary.json"
    if summary_path.exists():
        raise FileExistsError(summary_path)

    source_summary_path = args.parent_run / "summary.json"
    source_states_path = args.parent_run / "states.jsonl"
    source_summary = json.loads(source_summary_path.read_text(encoding="utf-8"))
    if sha256_path(source_states_path) != source_summary["states_sha256"]:
        raise RuntimeError("source states artifact hash mismatch")
    state_rows = load_jsonl(source_states_path)
    solver_seeds = [int(seed) for seed in source_summary["solver_seeds"]]
    all_keys = {
        (state, seed)
        for state in range(len(state_rows))
        for seed in solver_seeds
    }
    control_cells, control_metadata = load_replication_cells(
        args.control_run, 8192, all_keys
    )
    selected_keys = {(state, seed) for state in states for seed in solver_seeds}
    control_rows = [control_cells[key] for key in sorted(selected_keys)]

    treatment_cells = []
    for state_index in states:
        state_row = state_rows[state_index]
        reference = reference_from_row(state_row)
        ranges = (
            [tuple(hand) for hand in state_row["selected_ranges"][0]],
            [tuple(hand) for hand in state_row["selected_ranges"][1]],
        )
        for solver_seed in solver_seeds:
            path = cells_dir / f"state{state_index:02d}_seed{solver_seed}.json"
            if path.exists():
                cell = json.loads(path.read_text(encoding="utf-8"))
                if (
                    cell.get("state_index") != state_index
                    or cell.get("solver_seed") != solver_seed
                    or cell.get("opponent_samples") != args.opponent_samples
                ):
                    raise RuntimeError(f"existing treatment cell mismatch: {path}")
                treatment_cells.append(cell)
                print(f"reuse state={state_index} seed={solver_seed}", flush=True)
                continue
            control = control_cells[(state_index, solver_seed)]
            terminal_target = int(control["terminal_nodes"])
            solver = RiverCFRSolver(
                reference,
                ranges,
                solver_seed + state_index * 1_000_003,
                opponent_samples=args.opponent_samples,
            )
            iteration = 0
            while solver.terminal_nodes < terminal_target:
                solver.step(iteration)
                iteration += 1
            snapshot = solver.snapshot(iteration)
            snapshot.update(state_index=state_index, solver_seed=solver_seed)
            overshoot = (solver.terminal_nodes - terminal_target) / terminal_target
            cell = {
                "schema": "cardpilot.v6_river_public_belief_cfr_multisample_cell.v1",
                "state_index": state_index,
                "solver_seed": solver_seed,
                "opponent_samples": args.opponent_samples,
                "iterations": iteration,
                "control_terminal_nodes": terminal_target,
                "treatment_terminal_nodes": solver.terminal_nodes,
                "terminal_overshoot_fraction": overshoot,
                "snapshot": snapshot,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            atomic_json(path, cell)
            treatment_cells.append(cell)
            print(
                f"complete state={state_index} seed={solver_seed} "
                f"iterations={iteration} terminals={solver.terminal_nodes} "
                f"regret={snapshot['root_regret_proxy_bb']:.6f}",
                flush=True,
            )

    treatment_rows = [cell["snapshot"] for cell in treatment_cells]
    control_pooled, control_state = aggregate(control_rows, states)
    treatment_pooled, treatment_state = aggregate(treatment_rows, states)
    state_deltas = []
    for state, control, treatment in zip(states, control_state, treatment_state):
        state_deltas.append(
            {
                "state_index": state,
                "control": control,
                "treatment": treatment,
                "tv_delta": (
                    treatment["mean_total_variation"]
                    - control["mean_total_variation"]
                ),
                "agreement_delta": (
                    treatment["greedy_agreement"] - control["greedy_agreement"]
                ),
            }
        )
    relative_tv_improvement = (
        control_pooled["pooled_tv"] - treatment_pooled["pooled_tv"]
    ) / control_pooled["pooled_tv"]
    cell_manifest = [
        {"path": str(path.resolve()), "sha256": sha256_path(path)}
        for path in sorted(cells_dir.glob("*.json"))
    ]
    gates = {
        "source_state_hash_matches": True,
        "control_cell_hashes_match": True,
        "all_terminal_overshoots_at_most_0p005": all(
            cell["terminal_overshoot_fraction"] <= 0.005
            for cell in treatment_cells
        ),
        "all_terminal_payoffs_zero_sum": all(
            row["zero_sum_failures"] == 0 for row in treatment_rows
        ),
        "no_illegal_action_probability": all(
            row["illegal_probability_events"] == 0 for row in treatment_rows
        ),
        "pooled_tv_relative_improvement_at_least_0p10": (
            relative_tv_improvement >= 0.10
        ),
        "pooled_greedy_agreement_increased": (
            treatment_pooled["pooled_greedy_agreement"]
            > control_pooled["pooled_greedy_agreement"]
        ),
        "no_state_tv_worsened_by_more_than_0p05": all(
            row["tv_delta"] <= 0.05 for row in state_deltas
        ),
    }
    output = {
        "schema": "cardpilot.v6_river_public_belief_cfr_multisample_control.v1",
        "status": "COMPLETED",
        "source_summary": str(source_summary_path.resolve()),
        "source_summary_sha256": sha256_path(source_summary_path),
        "source_states_sha256": sha256_path(source_states_path),
        "control": control_metadata,
        "states": states,
        "solver_seeds": solver_seeds,
        "opponent_samples": args.opponent_samples,
        "control_pooled": control_pooled,
        "treatment_pooled": treatment_pooled,
        "relative_tv_improvement": relative_tv_improvement,
        "state_deltas": state_deltas,
        "treatment_terminal_nodes": sum(
            cell["treatment_terminal_nodes"] for cell in treatment_cells
        ),
        "treatment_iterations": sum(
            cell["iterations"] for cell in treatment_cells
        ),
        "cell_manifest": cell_manifest,
        "gate_components": gates,
        "admit_multisample_solver": all(gates.values()),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    atomic_json(summary_path, output)
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
