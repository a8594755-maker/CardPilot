from scripts.alpha_holdem.v6_proxy_alignment_meta_audit import external_score, first_number


def test_first_number_respects_preferred_metric_order():
    assert first_number({"b": 2, "a": 1}, ("a", "b")) == 1.0
    assert first_number({"a": "x", "b": 2}, ("a", "b")) == 2.0
    assert first_number({}, ("a",)) is None


def test_external_score_reads_current_ci_metric_names():
    record = {
        "metrics": {
            "bb_per_100": -24.5,
            "ci95_lower_bb_per_100": -42.8,
            "ci95_upper_bb_per_100": -6.3,
        }
    }
    assert external_score(record) == (-24.5, -42.8, -6.3)


def test_external_score_falls_back_to_compact_summary_ci():
    record = {
        "id": "summary-only",
        "metrics": {},
        "result": {"summary": "Exactly20k: -137.7392bb/100; raw95%CI[-183.1154, -92.3630]."},
    }
    assert external_score(record) == (-137.7392, -183.1154, -92.363)
