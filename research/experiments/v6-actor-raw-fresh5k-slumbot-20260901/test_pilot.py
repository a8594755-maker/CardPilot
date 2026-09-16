import importlib.util
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pilot_stats", BASE / "pilot_stats.py")
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)


def test_equal_session_statistics_and_gate():
    result = stats.summarize([[100] * 625 for _ in range(8)])
    assert result["hands"] == 5000 and result["bb_per_100"] == 100
    assert result["positive_sessions"] == 8
    assert result["supports_separate_fresh20k"] and not result["goal_achieved"]


def test_gate_requires_positive_point_and_four_sessions():
    sessions = [[100] * 625 for _ in range(3)] + [[-60] * 625 for _ in range(5)]
    result = stats.summarize(sessions)
    assert result["bb_per_100"] == 0 and not result["supports_separate_fresh20k"]


def test_rejects_incomplete_or_invalid_samples():
    with pytest.raises(ValueError):
        stats.summarize([[0] * 625 for _ in range(7)])
    bad = [[0] * 625 for _ in range(8)]
    bad[0][0] = 20001
    with pytest.raises(ValueError):
        stats.summarize(bad)
