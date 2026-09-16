import numpy as np

from scripts.alpha_holdem.v6_broad_mgda_curve import research_admission, summarize_evaluation


def test_summarize_evaluation_preserves_holdout_and_seat_breadth():
    rows = [
        {"holdout_label": "a", "delta_bb": 1.0, "seat_delta_bb": [2.0, 0.0]},
        {"holdout_label": "b", "delta_bb": -0.5, "seat_delta_bb": [-1.0, 0.0]},
        {"holdout_label": "a", "delta_bb": 0.5, "seat_delta_bb": [0.0, 1.0]},
        {"holdout_label": "b", "delta_bb": 0.0, "seat_delta_bb": [0.0, 0.0]},
    ]
    result = summarize_evaluation(rows)
    assert np.isclose(result["pooled_delta_bb100"], 25.0)
    assert [row["label"] for row in result["holdouts"]] == ["a", "b"]
    assert np.isclose(result["seats"][0]["delta_bb100"], 25.0)
    assert np.isclose(result["seats"][1]["delta_bb100"], 25.0)


def test_research_admission_requires_reproduced_slope_and_median_breadth():
    curve = []
    for seed in range(3):
        curve.append({
            "seed_index": seed,
            "chunk_index": 8,
            "holdouts": [{"delta_bb100": value} for value in (-1.0, 2.0, 3.0)],
            "seats": [{"delta_bb100": -0.5}, {"delta_bb100": 1.0}],
        })
    slopes = [
        {"seed_index": 0, "slope_bb100": 2.0},
        {"seed_index": 1, "slope_bb100": 1.0},
        {"seed_index": 2, "slope_bb100": -1.0},
    ]
    result = research_admission(curve, slopes, final_chunk=8, seeds=3)
    assert result["positive_slope_in_at_least_two_thirds_seeds"]
    assert result["median_final_seed_holdout_delta_nonnegative"]
    assert result["median_final_seed_seat_delta_nonnegative"]
