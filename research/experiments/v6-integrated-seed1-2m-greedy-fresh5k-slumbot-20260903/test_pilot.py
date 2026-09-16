from pathlib import Path
import hashlib

import run_pilot as pilot


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_frozen_source_and_fixed_commands():
    assert sha(pilot.SOURCE) == pilot.SOURCE_SHA
    commands = [pilot.session_command(i) for i in range(1, 9)]
    assert len({pilot.session_id(i) for i in range(1, 9)}) == 8
    assert len({pilot.session_seed(i) for i in range(1, 9)}) == 8
    assert all(command[-2:] == ["--observation-bridge", "legacy-v4"] for command in commands)
    assert all(command[command.index("--policy-mode") + 1] == "greedy" for command in commands)
    assert all(command[command.index("--hands") + 1] == "625" for command in commands)


def test_scale_gate_is_preregistered_not_qualification():
    promising = [[-1010 if i % 2 == 0 else 990 for i in range(625)] for _ in range(8)]
    result = pilot.summarize(promising)
    assert result["supports_separate_fresh20k"]
    assert not result["goal_achieved"] and result["qualification_hands"] == 0


def test_scale_gate_rejects_clear_negative_or_incomplete_evidence():
    clear_negative = [[-100] * 625 for _ in range(8)]
    assert not pilot.summarize(clear_negative)["supports_separate_fresh20k"]
    try:
        pilot.summarize(clear_negative[:-1])
    except ValueError:
        pass
    else:
        raise AssertionError("Incomplete sessions must fail")
