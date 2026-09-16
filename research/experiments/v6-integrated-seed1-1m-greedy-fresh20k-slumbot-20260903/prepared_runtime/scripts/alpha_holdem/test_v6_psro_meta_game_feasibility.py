import numpy as np

from scripts.alpha_holdem.v6_psro_meta_game_feasibility import solve_zero_sum


def test_solve_zero_sum_recovers_rock_paper_scissors_uniform():
    matrix = np.asarray([[0.0, -1.0, 1.0], [1.0, 0.0, -1.0], [-1.0, 1.0, 0.0]])
    result = solve_zero_sum(matrix)
    assert np.allclose(result["weights"], [1 / 3] * 3, atol=1e-8)
    assert abs(result["value_bb100"]) < 1e-8
    assert result["support_at_1pct"] == 3


def test_solve_zero_sum_rejects_non_skew_matrix():
    try:
        solve_zero_sum(np.ones((2, 2)))
    except ValueError as error:
        assert "skew-symmetric" in str(error)
    else:
        raise AssertionError("non-zero-sum matrix was accepted")
