from alpha_holdem.v6_public_opponent_matched_policy_eval import mean_ci95


def test_mean_ci95_uses_pair_level_units():
    result = mean_ci95([0.0, 1.0, 2.0, 3.0])
    assert result["count"] == 4
    assert result["bb100"] == 150.0
    assert result["ci95_low_bb100"] < result["bb100"]
    assert result["ci95_high_bb100"] > result["bb100"]
