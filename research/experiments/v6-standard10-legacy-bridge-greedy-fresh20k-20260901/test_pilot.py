from pathlib import Path
import hashlib
import run_pilot as pilot


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_source_and_fixed_cohort():
    assert sha(pilot.SOURCE) == pilot.SOURCE_SHA
    commands = [pilot.session_command(i) for i in range(1, 9)]
    assert len({pilot.session_id(i) for i in range(1, 9)}) == 8
    assert len({pilot.session_seed(i) for i in range(1, 9)}) == 8
    assert all(command[command.index("--hands") + 1] == "2500" for command in commands)
    assert all(command[-2:] == ["--observation-bridge", "legacy-v4"] for command in commands)


def test_admission_requires_positive_point_and_session_breadth():
    positive = [[1] * 2500 for _ in range(8)]
    negative = [[-1] * 2500 for _ in range(8)]
    assert pilot.summarize(positive)["supports_separate_fresh100k"]
    assert not pilot.summarize(negative)["supports_separate_fresh100k"]
