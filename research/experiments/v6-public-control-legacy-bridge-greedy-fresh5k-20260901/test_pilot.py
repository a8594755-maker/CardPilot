from pathlib import Path
import hashlib
import sys

import run_pilot as pilot

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from alpha_holdem.legacy_observation_bridge_v6 import BRIDGE_CONTRACT, load_policy


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_frozen_source_bridge_load_and_fixed_commands():
    assert sha(pilot.SOURCE) == pilot.SOURCE_SHA
    policy = load_policy(pilot.SOURCE, "cpu")
    assert policy.sha256 == pilot.SOURCE_SHA
    assert BRIDGE_CONTRACT == "hunl_v6_physical_legacy_v4_observation_bridge_v1"
    commands = [pilot.session_command(i) for i in range(1, 9)]
    assert len({pilot.session_id(i) for i in range(1, 9)}) == 8
    assert len({pilot.session_seed(i) for i in range(1, 9)}) == 8
    assert all(command[-2:] == ["--observation-bridge", "legacy-v4"] for command in commands)
    assert all(command[command.index("--policy-mode") + 1] == "greedy" for command in commands)
    assert all(command[command.index("--hands") + 1] == "625" for command in commands)


def test_statistics_admission_is_not_qualification():
    result = pilot.summarize([[1] * 625 for _ in range(8)])
    assert result["supports_separate_fresh20k"]
    assert not result["goal_achieved"] and result["qualification_hands"] == 0
