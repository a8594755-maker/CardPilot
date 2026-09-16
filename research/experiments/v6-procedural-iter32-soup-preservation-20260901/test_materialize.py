from pathlib import Path
import importlib.util

import pytest
import torch


SPEC = importlib.util.spec_from_file_location("materialize", Path(__file__).with_name("materialize.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_interpolation_is_exact_and_actor_only():
    parent = {"actor": torch.tensor([4.0]), "trunk": torch.tensor([7.0])}
    source = {"actor": torch.tensor([0.0]), "trunk": torch.tensor([-9.0])}
    result = MODULE.interpolate(parent, source, alpha=0.75, actor_names=("actor",))
    assert torch.equal(result["actor"], torch.tensor([1.0]))
    assert torch.equal(result["trunk"], parent["trunk"])


def test_fixed_alpha_and_weights():
    assert MODULE.ALPHA == 0.75
    assert 1.0 - MODULE.ALPHA == 0.25


def test_interpolation_rejects_invalid_alpha():
    values = {"actor": torch.tensor([1.0])}
    with pytest.raises(ValueError):
        MODULE.interpolate(values, values, alpha=1.01, actor_names=("actor",))
