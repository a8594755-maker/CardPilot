"""Admission tests for fixed generic-greedy journaled execution."""

import os
from pathlib import Path
import sys
import tempfile
import uuid


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
GREEDY_FIXTURES = ROOT / "research/experiments/v6-actor-raw-greedy-fresh5k-slumbot-20260901"
CLIENT_FIXTURES = ROOT / "research/experiments/v6-journaled-client-readiness-20260831"
os.environ["JOURNAL_TEST_OUTPUT"] = str(
    Path(tempfile.gettempdir()) / f"cardpilot_source_kl_temperature_greedy_{uuid.uuid4().hex}"
)
sys.path[:0] = [str(BASE), str(GREEDY_FIXTURES), str(CLIENT_FIXTURES)]

from test_greedy_contract import *  # noqa: F401,F403,E402
from test_client import ClientTests  # noqa: F401,E402


def test_fixed_pilot_statistics_gate():
    from pilot_stats import summarize

    passing = summarize([[10] * 625 for _ in range(8)])
    failing = summarize([[-10] * 625 for _ in range(8)])
    assert passing["supports_separate_fresh20k"]
    assert not failing["supports_separate_fresh20k"]
