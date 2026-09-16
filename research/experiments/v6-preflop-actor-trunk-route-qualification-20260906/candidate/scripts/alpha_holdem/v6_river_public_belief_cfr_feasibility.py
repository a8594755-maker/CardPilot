#!/usr/bin/env python3
"""Feasibility gate for posterior-range CFR on exact-terminal river subgames.

This experiment changes no learned weights.  It samples public river prefixes
reached by frozen Standard10, reconstructs each player's deterministic-policy
private-hand support, and runs tabular external-sampling CFR over the resulting
river game.  Independent solver seeds must agree before any target distillation
is considered.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
from pathlib import Path
import random
import sys
from typing import Iterable

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.physical_v6_cfr import legal_slot_actions
from alpha_holdem.policy_contract_v6 import action_table, apply_incr
from alpha_holdem.rules_v6 import BB, ChipState, Event
from alpha_holdem.v5_mirror_eval import init_model, read_checkpoint
from alpha_holdem.v6_elo_eval import greedy_action
from alpha_holdem.v6_history_consistent_hole_posterior import deck_for_holes


MAX_ACTIONS = 9


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def event_action(event: Event) -> str:
    return f"b{event.amount}" if event.kind == "b" else event.kind


def replay_public_prefix(
    reference: ChipState,
    holes0: tuple[int, int],
    holes1: tuple[int, int],
) -> ChipState:
    deck = deck_for_holes(
        candidate_seat=0,
        candidate_holes=holes0,
        opponent_holes=holes1,
        board=reference.board,
    )
    state = ChipState.new(deck, initial=reference.initial)
    for event in reference.history:
        state = apply_incr(state, event_action(event))
    public_fields = (
        "initial", "stacks", "bets", "pot", "board", "street", "actor",
        "pending", "last_full_raise", "history", "terminal", "folded",
    )
    if any(getattr(state, name) != getattr(reference, name) for name in public_fields):
        raise RuntimeError("private-hand replay changed the public river state")
    return state


def _placeholder_holes(
    candidate: tuple[int, int], board: tuple[int, ...]
) -> tuple[int, int]:
    excluded = set(candidate) | set(board)
    available = [card for card in range(52) if card not in excluded]
    return available[0], available[1]


def hand_matches_history(
    reference: ChipState,
    seat: int,
    holes: tuple[int, int],
    policy,
    device: str,
) -> bool:
    other = _placeholder_holes(holes, reference.board)
    if seat == 0:
        state = replay_public_prefix_start(reference, holes, other)
    else:
        state = replay_public_prefix_start(reference, other, holes)
    for event in reference.history:
        observed = event_action(event)
        if event.player == seat:
            predicted = greedy_action(
                policy, state, observation_style="legacy_v4", device=device
            )
            if predicted != observed:
                return False
        state = apply_incr(state, observed)
    return True


def replay_public_prefix_start(
    reference: ChipState,
    holes0: tuple[int, int],
    holes1: tuple[int, int],
) -> ChipState:
    deck = deck_for_holes(
        candidate_seat=0,
        candidate_holes=holes0,
        opponent_holes=holes1,
        board=reference.board,
    )
    return ChipState.new(deck, initial=reference.initial)


def deterministic_subset(
    support: list[tuple[int, int]],
    true_holes: tuple[int, int],
    count: int,
    seed: int,
) -> list[tuple[int, int]]:
    true_holes = tuple(sorted(true_holes))
    if true_holes not in support:
        raise RuntimeError("true private hand is absent from inferred support")
    ranked = sorted(
        support,
        key=lambda hand: hashlib.sha256(
            f"{seed}:{hand[0]}:{hand[1]}".encode("ascii")
        ).digest(),
    )
    selected = ranked[:count]
    if true_holes not in selected:
        selected[-1] = true_holes
    return sorted(set(selected))


def infer_range(
    reference: ChipState,
    seat: int,
    policy,
    device: str,
    count: int,
    seed: int,
) -> tuple[list[tuple[int, int]], int]:
    available = [card for card in range(52) if card not in set(reference.board)]
    support = [
        tuple(hand)
        for hand in combinations(available, 2)
        if hand_matches_history(reference, seat, tuple(hand), policy, device)
    ]
    if len(support) < count:
        raise RuntimeError(
            f"seat{seat} history-consistent support {len(support)} is below {count}"
        )
    selected = deterministic_subset(
        support, tuple(reference.holes[seat]), count, seed + seat * 1_000_003
    )
    if len(selected) != count:
        raise RuntimeError("deterministic range subset lost a hand")
    return selected, len(support)


def collect_river_states(policy, states: int, seed: int, device: str) -> tuple[list[ChipState], int]:
    quotas = {0: states // 2, 1: states - states // 2}
    rng = random.Random(seed)
    rows: list[ChipState] = []
    hands = 0
    while any(quotas.values()) and hands < 50_000:
        deck = list(range(52))
        rng.shuffle(deck)
        state = ChipState.new(deck)
        seen_prefixes: set[tuple[Event, ...]] = set()
        while not state.terminal:
            if state.street == 3 and quotas[state.actor] > 0 and state.history not in seen_prefixes:
                rows.append(state)
                quotas[state.actor] -= 1
                seen_prefixes.add(state.history)
            action = greedy_action(
                policy, state, observation_style="legacy_v4", device=device
            )
            state = apply_incr(state, action)
        hands += 1
    if any(quotas.values()):
        raise RuntimeError(f"failed to fill balanced river-state quotas: {quotas}")
    return rows, hands


@dataclass
class InfoSet:
    regrets: np.ndarray = field(
        default_factory=lambda: np.zeros(MAX_ACTIONS, dtype=np.float64)
    )
    strategy_sum: np.ndarray = field(
        default_factory=lambda: np.zeros(MAX_ACTIONS, dtype=np.float64)
    )
    regret_updates: int = 0
    average_updates: int = 0


def regret_matching(regrets: np.ndarray, legal_mask: np.ndarray) -> np.ndarray:
    legal = legal_mask > 0
    positive = np.maximum(regrets, 0.0) * legal_mask
    strategy = np.zeros(MAX_ACTIONS, dtype=np.float64)
    if float(positive.sum()) > 0.0:
        strategy = positive / positive.sum()
    else:
        strategy[legal] = 1.0 / int(legal.sum())
    return strategy


class RiverCFRSolver:
    def __init__(
        self,
        reference: ChipState,
        ranges: tuple[list[tuple[int, int]], list[tuple[int, int]]],
        seed: int,
        opponent_samples: int = 1,
    ) -> None:
        if reference.street != 3 or reference.terminal:
            raise ValueError("river CFR requires a live river state")
        self.reference = reference
        self.root_history_len = len(reference.history)
        self.ranges = ranges
        self.opponent_samples = int(opponent_samples)
        if self.opponent_samples < 1:
            raise ValueError("opponent_samples must be positive")
        self.rng = np.random.default_rng(seed)
        self.infosets: dict[tuple, InfoSet] = {}
        self.terminal_nodes = 0
        self.illegal_probability_events = 0
        self.zero_sum_failures = 0
        self.max_depth = 0
        self.valid_deals: list[ChipState] = []
        for holes0 in ranges[0]:
            for holes1 in ranges[1]:
                if set(holes0).isdisjoint(holes1):
                    self.valid_deals.append(
                        replay_public_prefix(reference, holes0, holes1)
                    )
        if not self.valid_deals:
            raise RuntimeError("river ranges contain no compatible private-hand pair")
        order = self.rng.permutation(len(self.valid_deals))
        self.deal_order = [int(index) for index in order]

    def _key(self, state: ChipState) -> tuple:
        suffix = tuple(event_action(event) for event in state.history[self.root_history_len :])
        return state.actor, tuple(sorted(state.holes[state.actor])), suffix

    def _record_and_strategy(self, state: ChipState) -> tuple[InfoSet, np.ndarray, np.ndarray]:
        mask, _ = action_table(state)
        record = self.infosets.setdefault(self._key(state), InfoSet())
        strategy = regret_matching(record.regrets, mask.astype(np.float64))
        if (
            not np.isfinite(strategy).all()
            or np.any(strategy < 0)
            or np.any(strategy[mask <= 0] != 0)
            or not np.isclose(float(strategy.sum()), 1.0, atol=1e-10)
        ):
            self.illegal_probability_events += 1
            raise RuntimeError("CFR generated an invalid physical action distribution")
        return record, strategy, mask

    def _traverse(self, state: ChipState, traverser: int, depth: int = 0) -> float:
        self.max_depth = max(self.max_depth, depth)
        if state.terminal:
            self.terminal_nodes += 1
            payoffs = state.payoffs()
            if sum(payoffs) != 0:
                self.zero_sum_failures += 1
                raise RuntimeError("terminal payoff is not zero-sum")
            return payoffs[traverser] / BB
        record, strategy, _ = self._record_and_strategy(state)
        actions = legal_slot_actions(state)
        if state.actor == traverser:
            values = np.zeros(MAX_ACTIONS, dtype=np.float64)
            for slot, action in actions:
                values[slot] = self._traverse(
                    apply_incr(state, action), traverser, depth + 1
                )
            node_value = float(np.dot(strategy, values))
            legal_mask, _ = action_table(state)
            record.regrets += (values - node_value) * legal_mask
            record.regret_updates += 1
            return node_value

        record.strategy_sum += strategy
        record.average_updates += 1
        slots = np.asarray([slot for slot, _ in actions], dtype=np.int64)
        probabilities = strategy[slots]
        probabilities = probabilities / probabilities.sum()
        values = []
        for _ in range(self.opponent_samples):
            selected = int(self.rng.choice(len(actions), p=probabilities))
            values.append(
                self._traverse(
                    apply_incr(state, actions[selected][1]), traverser, depth + 1
                )
            )
        return float(np.mean(values))

    def step(self, iteration: int) -> None:
        if iteration > 0 and iteration % len(self.deal_order) == 0:
            self.deal_order = [
                int(index) for index in self.rng.permutation(len(self.valid_deals))
            ]
        state = self.valid_deals[self.deal_order[iteration % len(self.deal_order)]]
        self._traverse(state, 0)
        self._traverse(state, 1)

    def root_strategies(self) -> dict[str, list[float]]:
        actor = self.reference.actor
        root_suffix: tuple[str, ...] = ()
        output = {}
        root_mask, _ = action_table(self.reference)
        for holes in self.ranges[actor]:
            key = actor, tuple(sorted(holes)), root_suffix
            record = self.infosets.get(key)
            if record is None:
                continue
            if record.average_updates > 0:
                strategy = record.strategy_sum / record.average_updates
                strategy = strategy * root_mask
                strategy = strategy / strategy.sum()
            else:
                strategy = regret_matching(record.regrets, root_mask)
            output[f"{holes[0]}-{holes[1]}"] = strategy.tolist()
        return output

    def root_regret_proxy(self) -> float:
        actor = self.reference.actor
        values = []
        for holes in self.ranges[actor]:
            record = self.infosets.get((actor, tuple(sorted(holes)), ()))
            if record is not None and record.regret_updates > 0:
                values.append(
                    float(np.maximum(record.regrets, 0.0).sum())
                    / record.regret_updates
                )
        return float(np.mean(values)) if values else float("inf")

    def snapshot(self, iteration: int) -> dict:
        root = self.root_strategies()
        return {
            "iteration": iteration,
            "infosets": len(self.infosets),
            "valid_deals": len(self.valid_deals),
            "terminal_nodes": self.terminal_nodes,
            "max_depth": self.max_depth,
            "illegal_probability_events": self.illegal_probability_events,
            "zero_sum_failures": self.zero_sum_failures,
            "root_regret_proxy_bb": self.root_regret_proxy(),
            "root_strategy_hands": len(root),
            "root_strategies": root,
        }


def compare_seed_strategies(snapshots: list[dict]) -> dict:
    televisions: list[float] = []
    agreements: list[float] = []
    for left_index in range(len(snapshots)):
        for right_index in range(left_index + 1, len(snapshots)):
            left = snapshots[left_index]["root_strategies"]
            right = snapshots[right_index]["root_strategies"]
            keys = sorted(set(left) & set(right))
            if not keys:
                raise RuntimeError("solver seeds have no common root information sets")
            for key in keys:
                a = np.asarray(left[key], dtype=np.float64)
                b = np.asarray(right[key], dtype=np.float64)
                televisions.append(float(np.abs(a - b).sum() / 2.0))
                agreements.append(float(int(np.argmax(a) == np.argmax(b))))
    return {
        "comparisons": len(televisions),
        "mean_total_variation": float(np.mean(televisions)),
        "max_total_variation": float(np.max(televisions)),
        "greedy_agreement": float(np.mean(agreements)),
    }


def parse_ints(raw: str, *, label: str) -> list[int]:
    try:
        values = [int(value) for value in raw.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{label} must be comma-separated integers") from exc
    if not values or any(value <= 0 for value in values):
        raise argparse.ArgumentTypeError(f"{label} values must be positive")
    return values


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standard10", type=Path, required=True)
    parser.add_argument("--states", type=int, default=6)
    parser.add_argument("--range-hands", type=int, default=48)
    parser.add_argument("--iterations", default="128,512,2048")
    parser.add_argument("--trajectory-seed", type=int, required=True)
    parser.add_argument("--solver-seeds", required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    iterations = parse_ints(args.iterations, label="iterations")
    solver_seeds = parse_ints(args.solver_seeds, label="solver seeds")
    if sorted(set(iterations)) != iterations:
        parser.error("iterations must be strictly increasing")
    if args.states < 2 or args.states % 2:
        parser.error("states must be a positive even number")
    if args.range_hands < 4 or len(solver_seeds) < 2:
        parser.error("range-hands must be >=4 and at least two solver seeds are required")
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)

    checkpoint = args.standard10.resolve()
    checkpoint_sha = sha256_path(checkpoint)
    policy = init_model(read_checkpoint(checkpoint), args.device).eval()
    references, trajectory_hands = collect_river_states(
        policy, args.states, args.trajectory_seed, args.device
    )

    state_rows = []
    snapshot_rows = []
    final_by_state: list[list[dict]] = [[] for _ in references]
    all_initial_regrets = []
    all_final_regrets = []
    for state_index, reference in enumerate(references):
        ranges = []
        full_support = []
        for seat in (0, 1):
            selected, support_count = infer_range(
                reference,
                seat,
                policy,
                args.device,
                args.range_hands,
                args.trajectory_seed + state_index * 10_007,
            )
            ranges.append(selected)
            full_support.append(support_count)
        state_rows.append(
            {
                "state_index": state_index,
                "actor": reference.actor,
                "board": list(reference.board),
                "history": [asdict(event) for event in reference.history],
                "true_holes": [list(reference.holes[0]), list(reference.holes[1])],
                "full_support": full_support,
                "selected_ranges": [
                    [list(hand) for hand in ranges[0]],
                    [list(hand) for hand in ranges[1]],
                ],
            }
        )
        for solver_seed in solver_seeds:
            solver = RiverCFRSolver(
                reference,
                (ranges[0], ranges[1]),
                solver_seed + state_index * 1_000_003,
            )
            cursor = 0
            for target in iterations:
                while cursor < target:
                    solver.step(cursor)
                    cursor += 1
                snapshot = solver.snapshot(target)
                snapshot.update(state_index=state_index, solver_seed=solver_seed)
                snapshot_rows.append(snapshot)
                if target == iterations[0]:
                    all_initial_regrets.append(snapshot["root_regret_proxy_bb"])
                if target == iterations[-1]:
                    all_final_regrets.append(snapshot["root_regret_proxy_bb"])
                    final_by_state[state_index].append(snapshot)
            print(
                f"state={state_index} seed={solver_seed} "
                f"regret={all_final_regrets[-1]:.6f} "
                f"infosets={len(solver.infosets)}",
                flush=True,
            )

    comparisons = [compare_seed_strategies(rows) for rows in final_by_state]
    pooled_tv = float(
        np.average(
            [row["mean_total_variation"] for row in comparisons],
            weights=[row["comparisons"] for row in comparisons],
        )
    )
    pooled_agreement = float(
        np.average(
            [row["greedy_agreement"] for row in comparisons],
            weights=[row["comparisons"] for row in comparisons],
        )
    )
    initial_regret = float(np.mean(all_initial_regrets))
    final_regret = float(np.mean(all_final_regrets))
    integrity = {
        "checkpoint_unchanged": sha256_path(checkpoint) == checkpoint_sha,
        "all_terminal_payoffs_zero_sum": all(
            row["zero_sum_failures"] == 0 for row in snapshot_rows
        ),
        "no_illegal_action_probability": all(
            row["illegal_probability_events"] == 0 for row in snapshot_rows
        ),
        "all_final_root_ranges_covered": all(
            row["root_strategy_hands"] == args.range_hands
            for row in snapshot_rows
            if row["iteration"] == iterations[-1]
        ),
    }
    gates = {
        **integrity,
        "mean_root_regret_proxy_decreased": final_regret < initial_regret,
        "pooled_cross_seed_mean_tv_at_most_0p10": pooled_tv <= 0.10,
        "pooled_cross_seed_greedy_agreement_at_least_0p80": pooled_agreement >= 0.80,
    }
    states_path = args.output_dir / "states.jsonl"
    snapshots_path = args.output_dir / "solver_snapshots.jsonl"
    write_jsonl(states_path, state_rows)
    write_jsonl(snapshots_path, snapshot_rows)
    summary = {
        "schema": "cardpilot.v6_river_public_belief_cfr_feasibility.v1",
        "status": "COMPLETED",
        "standard10": str(checkpoint),
        "standard10_sha256": checkpoint_sha,
        "states": len(references),
        "trajectory_hands": trajectory_hands,
        "range_hands_per_player": args.range_hands,
        "iterations": iterations,
        "solver_seeds": solver_seeds,
        "solver_traversals": len(references) * len(solver_seeds) * iterations[-1] * 2,
        "mean_initial_root_regret_proxy_bb": initial_regret,
        "mean_final_root_regret_proxy_bb": final_regret,
        "root_regret_proxy_ratio": final_regret / initial_regret,
        "pooled_cross_seed_mean_total_variation": pooled_tv,
        "pooled_cross_seed_greedy_agreement": pooled_agreement,
        "state_comparisons": comparisons,
        "gate_components": gates,
        "admit_target_distillation": all(gates.values()),
        "states_sha256": sha256_path(states_path),
        "snapshots_sha256": sha256_path(snapshots_path),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
