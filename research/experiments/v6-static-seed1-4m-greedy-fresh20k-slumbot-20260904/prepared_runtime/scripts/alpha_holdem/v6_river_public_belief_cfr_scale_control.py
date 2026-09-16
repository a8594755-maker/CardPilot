#!/usr/bin/env python3
"""Restartable deeper-dose control for immutable river belief-CFR cells."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import Event
from alpha_holdem.v6_history_consistent_hole_posterior import deck_for_holes
from alpha_holdem.v6_river_public_belief_cfr_feasibility import (
    RiverCFRSolver,
    compare_seed_strategies,
    parse_ints,
    sha256_path,
)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def reference_from_row(row: dict):
    holes0 = tuple(row["true_holes"][0])
    holes1 = tuple(row["true_holes"][1])
    board = tuple(row["board"])
    deck = deck_for_holes(
        candidate_seat=0,
        candidate_holes=holes0,
        opponent_holes=holes1,
        board=board,
    )
    from alpha_holdem.rules_v6 import ChipState

    state = ChipState.new(deck)
    for raw in row["history"]:
        event = Event(**raw)
        action = f"b{event.amount}" if event.kind == "b" else event.kind
        state = apply_incr(state, action)
    if (
        state.street != 3
        or state.terminal
        or state.actor != row["actor"]
        or state.board != board
        or list(state.holes[0]) != row["true_holes"][0]
        or list(state.holes[1]) != row["true_holes"][1]
    ):
        raise RuntimeError("state artifact did not reconstruct its exact river root")
    return state


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for attempt in range(10):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.05 * (attempt + 1))


def max_strategy_error(left: dict, right: dict) -> float:
    if set(left) != set(right):
        raise RuntimeError("replicated root strategy hand set differs from parent")
    return max(
        float(
            np.max(
                np.abs(
                    np.asarray(left[key], dtype=np.float64)
                    - np.asarray(right[key], dtype=np.float64)
                )
            )
        )
        for key in left
    )


def pooled_comparison(rows: list[dict], state_count: int) -> tuple[dict, list[dict]]:
    by_state = [
        sorted(
            [row for row in rows if row["state_index"] == state_index],
            key=lambda row: row["solver_seed"],
        )
        for state_index in range(state_count)
    ]
    state_comparisons = [compare_seed_strategies(cell) for cell in by_state]
    weights = [row["comparisons"] for row in state_comparisons]
    return (
        {
            "pooled_cross_seed_mean_total_variation": float(
                np.average(
                    [row["mean_total_variation"] for row in state_comparisons],
                    weights=weights,
                )
            ),
            "pooled_cross_seed_greedy_agreement": float(
                np.average(
                    [row["greedy_agreement"] for row in state_comparisons],
                    weights=weights,
                )
            ),
        },
        state_comparisons,
    )


def load_replication_cells(
    control_dir: Path,
    parent_iteration: int,
    expected_keys: set[tuple[int, int]],
) -> tuple[dict[tuple[int, int], dict], dict]:
    control_summary_path = control_dir / "summary.json"
    control_summary = json.loads(control_summary_path.read_text(encoding="utf-8"))
    manifest = control_summary.get("cell_manifest") or []
    if len(manifest) != len(expected_keys):
        raise RuntimeError("replication-control cell manifest is incomplete")
    parent_cells = {}
    verified_cells = []
    for artifact in manifest:
        path = Path(artifact["path"])
        if sha256_path(path) != artifact["sha256"]:
            raise RuntimeError(f"replication-control cell hash mismatch: {path}")
        cell = json.loads(path.read_text(encoding="utf-8"))
        matches = [
            row
            for row in cell["snapshots"]
            if row["iteration"] == parent_iteration
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"replication-control cell lacks iteration {parent_iteration}: {path}"
            )
        key = (cell["state_index"], cell["solver_seed"])
        if key in parent_cells:
            raise RuntimeError(f"duplicate replication-control cell: {key}")
        parent_cells[key] = matches[0]
        verified_cells.append(
            {"path": str(path.resolve()), "sha256": artifact["sha256"]}
        )
    if set(parent_cells) != expected_keys:
        raise RuntimeError("replication-control cells do not match the expected grid")
    metadata = {
        "summary": str(control_summary_path.resolve()),
        "summary_sha256": sha256_path(control_summary_path),
        "verified_cells": verified_cells,
    }
    return parent_cells, metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-run", type=Path, required=True)
    parser.add_argument(
        "--replication-control",
        type=Path,
        help="Optional prior scale-control run whose cell snapshots are replayed.",
    )
    parser.add_argument("--iterations", default="2048,8192")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    iterations = parse_ints(args.iterations, label="iterations")
    if sorted(set(iterations)) != iterations or len(iterations) < 2:
        parser.error("iterations must contain at least two strictly increasing doses")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cells_dir = args.output_dir / "cells"
    cells_dir.mkdir(exist_ok=True)
    summary_path = args.output_dir / "summary.json"
    if summary_path.exists():
        raise FileExistsError(summary_path)

    parent_summary_path = args.parent_run / "summary.json"
    parent_states_path = args.parent_run / "states.jsonl"
    parent_snapshots_path = args.parent_run / "solver_snapshots.jsonl"
    parent_summary = json.loads(parent_summary_path.read_text(encoding="utf-8"))
    if sha256_path(parent_states_path) != parent_summary["states_sha256"]:
        raise RuntimeError("parent states artifact hash mismatch")
    if sha256_path(parent_snapshots_path) != parent_summary["snapshots_sha256"]:
        raise RuntimeError("parent snapshot artifact hash mismatch")
    state_rows = load_jsonl(parent_states_path)
    parent_snapshots = load_jsonl(parent_snapshots_path)
    parent_iteration = iterations[0]
    solver_seeds = [int(seed) for seed in parent_summary["solver_seeds"]]
    expected_keys = {
        (state_index, seed)
        for state_index in range(len(state_rows))
        for seed in solver_seeds
    }
    replication_metadata = None
    if args.replication_control is None:
        parent_cells = {
            (row["state_index"], row["solver_seed"]): row
            for row in parent_snapshots
            if row["iteration"] == parent_iteration
        }
    else:
        parent_cells, replication_metadata = load_replication_cells(
            args.replication_control, parent_iteration, expected_keys
        )
    if set(parent_cells) != expected_keys:
        raise RuntimeError("parent replication grid is incomplete")

    results = []
    for state_index, state_row in enumerate(state_rows):
        reference = reference_from_row(state_row)
        ranges = (
            [tuple(hand) for hand in state_row["selected_ranges"][0]],
            [tuple(hand) for hand in state_row["selected_ranges"][1]],
        )
        for solver_seed in solver_seeds:
            cell_path = cells_dir / f"state{state_index:02d}_seed{solver_seed}.json"
            if cell_path.exists():
                cell = json.loads(cell_path.read_text(encoding="utf-8"))
                if (
                    cell.get("state_index") != state_index
                    or cell.get("solver_seed") != solver_seed
                    or cell.get("iterations") != iterations
                ):
                    raise RuntimeError(f"existing cell contract mismatch: {cell_path}")
                results.append(cell)
                print(f"reuse state={state_index} seed={solver_seed}", flush=True)
                continue

            solver = RiverCFRSolver(
                reference,
                ranges,
                solver_seed + state_index * 1_000_003,
            )
            cursor = 0
            snapshots = []
            for target in iterations:
                while cursor < target:
                    solver.step(cursor)
                    cursor += 1
                snapshot = solver.snapshot(target)
                snapshot.update(state_index=state_index, solver_seed=solver_seed)
                snapshots.append(snapshot)
            parent = parent_cells[(state_index, solver_seed)]
            replicated = snapshots[0]
            strategy_error = max_strategy_error(
                replicated["root_strategies"], parent["root_strategies"]
            )
            regret_error = abs(
                replicated["root_regret_proxy_bb"]
                - parent["root_regret_proxy_bb"]
            )
            replay_gate = {
                "root_strategy_max_abs_error_at_most_1e12": strategy_error <= 1e-12,
                "root_regret_abs_error_at_most_1e12": regret_error <= 1e-12,
                "infoset_count_exact": replicated["infosets"] == parent["infosets"],
                "terminal_node_count_exact": (
                    replicated["terminal_nodes"] == parent["terminal_nodes"]
                ),
            }
            if not all(replay_gate.values()):
                raise RuntimeError(
                    f"parent replay mismatch state={state_index} seed={solver_seed}: "
                    f"{replay_gate}"
                )
            cell = {
                "schema": "cardpilot.v6_river_public_belief_cfr_scale_cell.v1",
                "state_index": state_index,
                "solver_seed": solver_seed,
                "iterations": iterations,
                "parent_replay_strategy_max_abs_error": strategy_error,
                "parent_replay_regret_abs_error": regret_error,
                "parent_replay_gate": replay_gate,
                "snapshots": snapshots,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            atomic_json(cell_path, cell)
            results.append(cell)
            print(
                f"complete state={state_index} seed={solver_seed} "
                f"regret={snapshots[-1]['root_regret_proxy_bb']:.6f} "
                f"infosets={snapshots[-1]['infosets']}",
                flush=True,
            )

    final_rows = [cell["snapshots"][-1] for cell in results]
    parent_rows = [parent_cells[key] for key in sorted(parent_cells)]
    parent_pooled, parent_state = pooled_comparison(parent_rows, len(state_rows))
    final_pooled, final_state = pooled_comparison(final_rows, len(state_rows))
    state_deltas = []
    for state_index, (old, new) in enumerate(zip(parent_state, final_state)):
        state_deltas.append(
            {
                "state_index": state_index,
                "tv_delta": new["mean_total_variation"] - old["mean_total_variation"],
                "greedy_agreement_delta": (
                    new["greedy_agreement"] - old["greedy_agreement"]
                ),
                "parent": old,
                "final": new,
            }
        )
    cell_manifest = [
        {
            "path": str(path.resolve()),
            "sha256": sha256_path(path),
        }
        for path in sorted(cells_dir.glob("*.json"))
    ]
    gates = {
        "parent_raw_hashes_match": True,
        "all_2048_cells_replay_exact": all(
            all(cell["parent_replay_gate"].values()) for cell in results
        ),
        "all_final_root_ranges_covered": all(
            row["root_strategy_hands"] == parent_summary["range_hands_per_player"]
            for row in final_rows
        ),
        "all_terminal_payoffs_zero_sum": all(
            row["zero_sum_failures"] == 0 for row in final_rows
        ),
        "no_illegal_action_probability": all(
            row["illegal_probability_events"] == 0 for row in final_rows
        ),
        "pooled_tv_decreased": (
            final_pooled["pooled_cross_seed_mean_total_variation"]
            < parent_pooled["pooled_cross_seed_mean_total_variation"]
        ),
        "pooled_greedy_agreement_increased": (
            final_pooled["pooled_cross_seed_greedy_agreement"]
            > parent_pooled["pooled_cross_seed_greedy_agreement"]
        ),
        "no_state_tv_worsened_by_more_than_0p10": all(
            row["tv_delta"] <= 0.10 for row in state_deltas
        ),
        "no_state_agreement_dropped_by_more_than_0p10": all(
            row["greedy_agreement_delta"] >= -0.10 for row in state_deltas
        ),
    }
    output = {
        "schema": "cardpilot.v6_river_public_belief_cfr_scale_control.v1",
        "status": "COMPLETED",
        "parent_summary": str(parent_summary_path.resolve()),
        "parent_summary_sha256": sha256_path(parent_summary_path),
        "parent_states_sha256": sha256_path(parent_states_path),
        "parent_snapshots_sha256": sha256_path(parent_snapshots_path),
        "replication_control": replication_metadata,
        "states": len(state_rows),
        "solver_seeds": solver_seeds,
        "iterations": iterations,
        "solver_traversals": len(results) * iterations[-1] * 2,
        "parent_pooled": parent_pooled,
        "final_pooled": final_pooled,
        "state_deltas": state_deltas,
        "mean_final_root_regret_proxy_bb": float(
            np.mean([row["root_regret_proxy_bb"] for row in final_rows])
        ),
        "cell_manifest": cell_manifest,
        "gate_components": gates,
        "admit_32768_control": all(gates.values()),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    atomic_json(summary_path, output)
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
