from datetime import datetime, timedelta, timezone

import pytest

from scripts.alpha_holdem.v5_hybrid_h2_protocol_abort_judgment import classify, first60_effective_hps


def metric_rows(step: int) -> list[dict]:
    start = datetime(2026, 7, 13, tzinfo=timezone.utc)
    return [
        {"recorded_at": (start + timedelta(seconds=i)).isoformat(), "hands": i * step}
        for i in range(61)
    ]


def test_first60_excludes_one_warmup_row() -> None:
    assert first60_effective_hps(metric_rows(100)) == 100.0


def test_registered_protocol_abort_classification() -> None:
    assert classify(100.0, 84.9, 0.85) == ("FAIL", "H2_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT")


def test_nonfailure_cannot_use_abort_path() -> None:
    with pytest.raises(ValueError):
        classify(100.0, 85.0, 0.85)
