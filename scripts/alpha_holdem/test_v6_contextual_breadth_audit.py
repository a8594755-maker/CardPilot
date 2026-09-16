from scripts.alpha_holdem.v6_contextual_breadth_audit import deck_units, mean_ci95


def test_deck_units_pair_both_seats_before_inference():
    rows = [
        {"seed_index": 0, "opponent_label": "x", "pair_index": 0, "hero_seat": seat,
         "deck": [1, 2], "split": "holdout", "correct_minus_base_bb": value,
         "correct_minus_wrong_bb": value * 2}
        for seat, value in ((0, 1.0), (1, -0.5))
    ]
    units = deck_units(rows)
    assert len(units) == 1
    assert units[0]["correct_minus_base_bb"] == 0.25


def test_mean_ci95_uses_bb100_units():
    result = mean_ci95([1.0, -1.0])
    assert result["bb100"] == 0.0
    assert result["ci95_half_bb100"] > 0
