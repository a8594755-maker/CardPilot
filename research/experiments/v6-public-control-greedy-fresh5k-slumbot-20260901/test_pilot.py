"""Live admission gate: greedy execution plus journal-client regression."""
import os
from pathlib import Path
import sys
import tempfile
import uuid

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
FIXTURES = ROOT / "research/experiments/v6-journaled-client-readiness-20260831"
os.environ["JOURNAL_TEST_OUTPUT"] = str(
    Path(tempfile.gettempdir()) / f"cardpilot_public_control_{uuid.uuid4().hex}"
)
sys.path[:0] = [str(BASE), str(FIXTURES)]

from test_greedy_contract import *  # noqa: F401,F403
from test_client import ClientTests  # noqa: F401
