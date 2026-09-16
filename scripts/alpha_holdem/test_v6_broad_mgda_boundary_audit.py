import numpy as np

from scripts.alpha_holdem.v6_broad_mgda_boundary_audit import paired_interval


def test_paired_interval_matches_seed_holdout_pair_keys():
    rows = []
    for seed in range(2):
        for holdout in ("a", "b"):
            for pair in range(3):
                rows.append({"seed_index": seed, "holdout_label": holdout, "pair_index": pair, "chunk_index": 2, "delta_bb": 1.0, "seat_delta_bb": [0.5, 1.5]})
                rows.append({"seed_index": seed, "holdout_label": holdout, "pair_index": pair, "chunk_index": 4, "delta_bb": 1.25, "seat_delta_bb": [1.0, 1.5]})
    result = paired_interval(rows, 2, 4)
    assert len(result) == 12
    assert all(np.isclose(row["delta_slope_bb"], 0.25) for row in result)
    assert all(row["seat_slope_bb"] == [0.5, 0.0] for row in result)
