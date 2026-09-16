from scripts.alpha_holdem.v6_context_reliability_shrinkage_control import paired_units, summarize


def rows():
    return [
        {"opponent_label": "x", "pair_index": 0, "hero_seat": seat, "deck": [1, 2], "split": "training",
         "unshrunk_minus_base_bb": 1.0, "shrunk_minus_base_bb": 0.5,
         "shrunk_minus_unshrunk_bb": -0.5}
        for seat in (0, 1)
    ]


def test_paired_units_average_seats():
    units = paired_units(rows())
    assert len(units) == 1
    assert units[0]["shrunk_minus_base_bb"] == 0.5


def test_summarize_reports_paired_primary_units():
    result = summarize(rows() + [{**row, "opponent_label": "y", "split": "holdout"} for row in rows()])
    assert result["paired_deck_units"] == 2
    assert result["pooled"]["shrunk_minus_base_bb"]["bb100"] == 50.0


def test_paired_units_keep_seed_streams_independent():
    combined = []
    for seed in (0, 1):
        combined.extend([{**row, "seed_index": seed} for row in rows()])
    assert len(paired_units(combined)) == 2
