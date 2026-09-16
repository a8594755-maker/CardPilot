import numpy as np

from scripts.alpha_holdem.v6_posterior_context_512to2048_continuation import make_groups


class Policy:
    pass


def test_make_groups_restores_exact_opponent_seat_order_and_counts():
    policies = [Policy() for _ in range(6)]
    counts = [np.full((4, 4), index).tolist() for index in range(12)]
    groups = make_groups(policies, counts)
    assert len(groups) == 12
    assert groups[3]["opponent"] is policies[1]
    assert groups[3]["hero_seat"] == 1
    assert np.all(groups[3]["counts"] == 3)
