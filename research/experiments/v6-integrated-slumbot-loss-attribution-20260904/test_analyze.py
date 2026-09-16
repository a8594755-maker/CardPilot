from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


PATH = Path(__file__).with_name("analyze.py")
SPEC = spec_from_file_location("loss_attribution", PATH)
MODULE = module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_preflop_topology_counts_raises():
    assert MODULE.preflop_topology("cc/k") == "unraised"
    assert MODULE.preflop_topology("b200c/kk") == "single_raised"
    assert MODULE.preflop_topology("b200b800c/") == "three_bet"
    assert MODULE.preflop_topology("b200b800b2400c/") == "four_bet_plus"


def test_outcome_metrics_are_hand_level_and_complemented():
    rows = [
        {"winnings_bb": -2.0, "session": 5, "class_keys": ["x=a"]},
        {"winnings_bb": -1.0, "session": 6, "class_keys": ["x=a"]},
        {"winnings_bb": 1.0, "session": 5, "class_keys": ["x=b"]},
        {"winnings_bb": 2.0, "session": 6, "class_keys": ["x=b"]},
    ]
    result = MODULE.outcome_metrics(rows, "x=a")
    assert result["hands"] == 2
    assert result["bb100"] == -150.0
    assert result["complement_bb100"] == 150.0
    assert result["class_minus_complement_bb100"] == -300.0
    assert result["negative_sessions"] == 2


def test_proxy_metrics_use_only_admissible_rows():
    rows = [
        {"class_keys": ["x=a"], "teacher_admissible": True, "onpolicy_vs_teacher_consensus": True},
        {"class_keys": ["x=a"], "teacher_admissible": False, "onpolicy_vs_teacher_consensus": True},
        {"class_keys": ["x=b"], "teacher_admissible": True, "onpolicy_vs_teacher_consensus": False},
    ]
    result = MODULE.proxy_metrics(rows, "x=a")
    assert result["rows"] == 1
    assert result["complement_rows"] == 1
    assert result["disagreement_uplift"] == 1.0
