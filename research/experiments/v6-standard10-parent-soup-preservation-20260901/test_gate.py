from pathlib import Path
import importlib.util

import torch


SPEC = importlib.util.spec_from_file_location("soup_gate", Path(__file__).with_name("run_gate.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_interpolation_is_exact_and_actor_only():
    parent = {"policy_head.weight": torch.tensor([4.0]), "trunk.weight": torch.tensor([7.0])}
    source = {"policy_head.weight": torch.tensor([0.0]), "trunk.weight": torch.tensor([-9.0])}
    result = MODULE.interpolate(parent, source, actor_names=("policy_head.weight",))
    assert torch.equal(result["policy_head.weight"], torch.tensor([3.0]))
    assert torch.equal(result["trunk.weight"], parent["trunk.weight"])


def test_fixed_weights_sum_to_one():
    assert MODULE.PARENT_WEIGHT == 0.75
    assert MODULE.SOURCE_WEIGHT == 0.25
    assert MODULE.PARENT_WEIGHT + MODULE.SOURCE_WEIGHT == 1.0
