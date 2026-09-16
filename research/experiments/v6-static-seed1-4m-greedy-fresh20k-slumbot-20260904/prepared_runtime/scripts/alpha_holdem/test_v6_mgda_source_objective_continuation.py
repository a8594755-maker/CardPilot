import numpy as np

from scripts.alpha_holdem.v6_mgda_source_objective_continuation import (
    source_constrained_aggregate,
)


def test_source_constrained_aggregate_descends_rewards_and_source():
    rewards = np.asarray(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0],
         [0.5, 1.0, 0.0], [1.0, 0.5, 0.0], [0.8, 0.8, 0.0]],
        dtype=np.float64,
    )
    source = np.asarray([0.2, 0.2, 1.0], dtype=np.float64)
    aggregate, metrics = source_constrained_aggregate(
        rewards, np.full(6, 1.0 / 6.0), source
    )
    assert metrics["reward_worst_alignment"] > 0.0
    assert metrics["source_kl_alignment"] > 0.0
    assert np.linalg.norm(aggregate) > 0.0
