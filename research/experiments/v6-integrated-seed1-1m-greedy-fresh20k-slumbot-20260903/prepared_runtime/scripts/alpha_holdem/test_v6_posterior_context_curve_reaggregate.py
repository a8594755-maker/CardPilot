from scripts.alpha_holdem.v6_posterior_context_curve_reaggregate import group_support


def test_group_support_counts_hero_decisions():
    rows = [
        {"group_index": 0, "hero_decisions": [{}, {}]},
        {"group_index": 0, "hero_decisions": [{}]},
        {"group_index": 1, "hero_decisions": [{}, {}, {}]},
    ]
    support = group_support(rows)
    assert support["group00"] == 3
    assert support["group01"] == 3
    assert support["group11"] == 0
