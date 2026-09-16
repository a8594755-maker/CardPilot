import torch

from scripts.alpha_holdem.v6_posterior_context_curve_geometry_replay import logical_digest, tensors_exact


def test_logical_digest_ignores_dictionary_key_order():
    assert logical_digest([{"a": 1, "b": 2}]) == logical_digest([{"b": 2, "a": 1}])


def test_tensors_exact_requires_identical_values_and_keys():
    assert tensors_exact({"x": torch.tensor([1])}, {"x": torch.tensor([1])})
    assert not tensors_exact({"x": torch.tensor([1])}, {"x": torch.tensor([2])})
