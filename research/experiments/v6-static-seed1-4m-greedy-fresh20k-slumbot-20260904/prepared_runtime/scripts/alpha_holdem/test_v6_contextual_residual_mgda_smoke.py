import numpy as np

from scripts.alpha_holdem.v6_contextual_residual_mgda_smoke import summarize, update_counts


class State:
    street = 2


def test_update_counts_uses_public_street_and_action_bucket():
    counts = np.zeros((4, 4), dtype=np.int64)
    update_counts(counts, State(), "b125")
    assert counts[2].tolist() == [0, 0, 0, 1]


def test_summarize_keeps_training_and_holdout_separate():
    rows = [
        {"split": split, "hero_seat": seat, "correct_minus_base_bb": delta, "correct_minus_wrong_bb": delta / 2}
        for split, delta in (("training", 1.0), ("holdout", -1.0))
        for seat in (0, 1)
    ]
    result = summarize(rows)
    assert result["pooled_correct_minus_base"]["bb100"] == 0.0
    assert result["splits"]["training"]["correct_minus_base"]["bb100"] == 100.0
    assert result["splits"]["holdout"]["correct_minus_base"]["bb100"] == -100.0
