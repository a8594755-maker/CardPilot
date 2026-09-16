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
    assert all(command[command.index("--hands") + 1] == "2500" for command in commands)


def test_scale_gate_is_preregistered_not_qualification():
    promising = [[-900 if i % 2 == 0 else 902 for i in range(2500)] for _ in range(8)]
    result = pilot.summarize(promising)
    assert result["supports_separate_fresh100k"]
    assert not result["goal_achieved"] and result["qualification_hands"] == 0


def test_scale_gate_rejects_nonpositive_point_or_incomplete_evidence():
    nonpositive = [[-900 if i % 2 == 0 else 900 for i in range(2500)] for _ in range(8)]
    assert not pilot.summarize(nonpositive)["supports_separate_fresh100k"]
    try:
        pilot.summarize(nonpositive[:-1])
    except ValueError:
        pass
    else:
        raise AssertionError("Incomplete sessions must fail")


def test_batched_logger_preserves_all_artifacts_and_common_options():
    calls = []
    args = ["--count", "evaluation_hands=20000"]
    for index in range(100):
        args.extend(("--artifact", "x" * 400 + str(index)))
    pilot.batched_log(lambda *values: calls.append(values), *args)
    assert len(calls) > 1
    assert calls[0] == ("--count", "evaluation_hands=20000")
    recovered = [call[i + 1] for call in calls[1:] for i in range(0, len(call), 2)]
    assert recovered == ["x" * 400 + str(index) for index in range(100)]
