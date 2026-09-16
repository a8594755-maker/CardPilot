from scripts.alpha_holdem.v6_dual_contract_mgda_fresh_curve import summarize_delta


def test_summarize_delta_preserves_anchor_and_seat_signs():
    rows = []
    for anchor in range(3):
        for pair in range(2):
            rows.append(
                {
                    "anchor_index": anchor,
                    "delta_bb": 0.01 * (anchor + 1),
                    "seat_delta_bb": [0.01, 0.02],
                }
            )
    result = summarize_delta(rows)
    assert result["pairs"] == 6
    assert [row["delta_bb100"] for row in result["anchors"]] == [1.0, 2.0, 3.0]
    assert [row["delta_bb100"] for row in result["seats"]] == [1.0, 2.0]
