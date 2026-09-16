import numpy as np

from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_river_public_belief_cfr_feasibility import (
    RiverCFRSolver,
    compare_seed_strategies,
    regret_matching,
)


def river_root():
    state = ChipState.new(tuple(range(52)))
    for action in ("c", "k", "k", "k", "k", "k"):
        state = apply_incr(state, action)
    assert state.street == 3 and not state.terminal and state.actor == 0
    return state


def test_regret_matching_is_legal_and_uniform_without_positive_regret():
    mask = np.asarray([1, 1, 0, 1, 0, 0, 0, 0, 0], dtype=np.float64)
    strategy = regret_matching(np.asarray([-2, -1, 9, -3, 0, 0, 0, 0, 0]), mask)
    assert np.allclose(strategy[[0, 1, 3]], 1 / 3)
    assert strategy[2] == 0
    positive = regret_matching(np.asarray([0, 2, 99, 1, 0, 0, 0, 0, 0]), mask)
    assert np.allclose(positive[[0, 1, 3]], [0, 2 / 3, 1 / 3])


def test_small_river_solver_preserves_integrity_and_exposes_root_strategies():
    root = river_root()
    ranges = (
        [tuple(sorted(root.holes[0])), (10, 11)],
        [tuple(sorted(root.holes[1])), (12, 13)],
    )
    solver = RiverCFRSolver(root, ranges, seed=17)
    for iteration in range(12):
        solver.step(iteration)
    snapshot = solver.snapshot(12)
    assert snapshot["terminal_nodes"] > 0
    assert snapshot["zero_sum_failures"] == 0
    assert snapshot["illegal_probability_events"] == 0
    assert snapshot["root_strategy_hands"] == 2
    for strategy in snapshot["root_strategies"].values():
        assert np.isclose(sum(strategy), 1.0)


def test_opponent_multisampling_increases_terminal_work_per_step():
    root = river_root()
    ranges = (
        [tuple(sorted(root.holes[0])), (10, 11)],
        [tuple(sorted(root.holes[1])), (12, 13)],
    )
    single = RiverCFRSolver(root, ranges, seed=23, opponent_samples=1)
    multi = RiverCFRSolver(root, ranges, seed=23, opponent_samples=2)
    single.step(0)
    multi.step(0)
    assert multi.terminal_nodes > single.terminal_nodes
    assert multi.zero_sum_failures == multi.illegal_probability_events == 0


def test_seed_comparison_identity_has_zero_tv():
    snapshot = {
        "root_strategies": {
            "0-1": [0.0, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        }
    }
    result = compare_seed_strategies([snapshot, snapshot])
    assert result["mean_total_variation"] == 0.0
    assert result["greedy_agreement"] == 1.0
