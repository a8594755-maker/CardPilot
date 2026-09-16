import numpy as np
import pytest

from scripts.alpha_holdem.v6_broad_mgda_matched_dose_audit import align_evidence, summarize_matches


def _row(seed, holdout, pair, chunk, delta, seat_delta):
    return {
        "seed_index": seed,
        "holdout_label": holdout,
        "holdout_index": 0,
        "holdout_sha256": "same",
        "pair_index": pair,
        "chunk_index": chunk,
        "deck": list(range(52)),
        "control_rewards_bb": [1.0, -1.0],
        "delta_bb": delta,
        "seat_delta_bb": seat_delta,
    }


def test_align_evidence_matches_exact_paired_deals():
    half = [_row(0, "a", pair, 8, 1.0 + pair, [0.5 + pair, 1.5 + pair]) for pair in range(3)]
    full = [_row(0, "a", pair, 4, 0.75 + pair, [0.0 + pair, 1.5 + pair]) for pair in range(3)]
    matched = align_evidence(half, full)
    assert len(matched) == 3
    assert all(np.isclose(row["half_minus_full_bb"], 0.25) for row in matched)
    assert all(row["seat_half_minus_full_bb"] == [0.5, 0.0] for row in matched)


def test_align_evidence_rejects_control_mismatch():
    half = [_row(0, "a", 0, 8, 1.0, [0.5, 1.5])]
    full = [_row(0, "a", 0, 4, 0.75, [0.0, 1.5])]
    full[0]["control_rewards_bb"] = [2.0, -2.0]
    with pytest.raises(ValueError, match="control_rewards_bb differs"):
        align_evidence(half, full)


def test_summarize_matches_requires_uniform_seed_improvement():
    rows = []
    for seed, difference in enumerate((0.1, 0.2, -0.3)):
        for holdout in ("a", "b", "c"):
            for pair in range(2):
                rows.append({
                    "seed_index": seed,
                    "holdout_label": holdout,
                    "pair_index": pair,
                    "half_minus_full_bb": difference,
                    "seat_half_minus_full_bb": [difference, difference],
                })
    summary = summarize_matches(rows)
    assert summary["positive_seed_point_estimates"] == 2
    assert not summary["uniform_improvement_gates"]["all_three_seed_point_estimates_nonnegative"]
    assert not summary["uniform_improvement"]
