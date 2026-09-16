from scripts.alpha_holdem.v6_greedy_es_sigma_calibration import choose_sigma


def test_choose_sigma_targets_small_nonzero_disagreement():
    rows = [
        {"sigma": 0.1, "minimum_disagreement": 0.0, "median_disagreement": 0.0, "maximum_abs_residual_logit": 0.1},
        {"sigma": 0.2, "minimum_disagreement": 0.01, "median_disagreement": 0.02, "maximum_abs_residual_logit": 0.2},
        {"sigma": 0.3, "minimum_disagreement": 0.02, "median_disagreement": 0.03, "maximum_abs_residual_logit": 0.25},
        {"sigma": 0.4, "minimum_disagreement": 0.03, "median_disagreement": 0.04, "maximum_abs_residual_logit": 0.25001},
    ]
    assert choose_sigma(rows) == 0.3


def test_choose_sigma_rejects_no_activation():
    rows = [
        {"sigma": 0.1, "minimum_disagreement": 0.0, "median_disagreement": 0.0, "maximum_abs_residual_logit": 0.1}
    ]
    assert choose_sigma(rows) is None
