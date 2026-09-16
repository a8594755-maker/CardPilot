"""Admission gate reusing the previously frozen greedy contract tests."""
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
    Path(tempfile.gettempdir()) / f"cardpilot_public_control_recovery_{uuid.uuid4().hex}"
)
sys.path[:0] = [str(BASE), str(GREEDY_FIXTURES), str(CLIENT_FIXTURES)]

from test_greedy_contract import *  # noqa: F401,F403
from test_client import ClientTests  # noqa: F401
