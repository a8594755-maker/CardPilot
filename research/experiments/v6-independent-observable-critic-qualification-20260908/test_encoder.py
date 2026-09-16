"""Actual frozen hybrid encoder tests, not production-path qualification."""
import copy
import importlib.util
from pathlib import Path
import sys

import pytest
import torch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from observable_critic import attach_encoder

SOURCE = BASE.parent / 'v6-preflop-actor-trunk-route-qualification-20260906/candidate/scripts/alpha_holdem/network_hybrid_h1.py'
spec = importlib.util.spec_from_file_location('frozen_encoder_network', SOURCE)
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)


def inputs(street):
    rng = torch.Generator().manual_seed(202609080 + street)
    cards = torch.rand(2, 6, 4, 13, generator=rng)
    cards[:, 4] = 0
    if street:
        cards[:, 4, 0, :street+2] = 1
    actions = torch.rand(2, 25, 4, 5, generator=rng)
    extra = torch.rand(2, 3, generator=rng)
    extra[:, 2] = torch.tensor([0., 1.])
    return cards, actions, extra


@pytest.fixture
def model():
    torch.set_num_threads(1)
    torch.manual_seed(202609081)
    model = network.AlphaHoldemNet(norm_layer='gn', critic_contract='critic_v2',
        separate_preflop_head=True, preflop_trunk_gradient=True)
    with torch.no_grad():
        model(*inputs(0))
    return model.eval()


@pytest.mark.parametrize('street', range(4))
def test_initial_forward_and_storage_parity(model, street):
    args = inputs(street)
    old_parameters = dict(model.named_parameters())
    with torch.no_grad():
        logits, value = model(*args)
    rng = torch.get_rng_state().clone()
    encoder = attach_encoder(model)
    assert torch.equal(rng, torch.get_rng_state())
    current = dict(model.named_parameters())
    assert all(current[name] is parameter for name, parameter in old_parameters.items())
    with torch.no_grad():
        assert torch.equal(model.value_head(encoder(*args)), value)
        assert torch.equal(model(*args)[0], logits)
    for name, parameter in encoder.named_parameters():
        assert torch.equal(parameter, old_parameters[name])
        assert parameter.data_ptr() != old_parameters[name].data_ptr()


@pytest.mark.parametrize('street', range(4))
def test_value_update_has_no_actor_gradient(model, street):
    encoder = attach_encoder(model)
    args = inputs(street)
    before = {n: p.detach().clone() for n, p in model.named_parameters()}
    logits = model(*args)[0].detach().clone()
    optimizer = torch.optim.Adam(list(encoder.parameters()) + list(model.value_head.parameters()), lr=1e-4)
    (model.value_head(encoder(*args)) - 0.5).square().mean().backward()
    for name, parameter in model.named_parameters():
        if not name.startswith(('observable_value_encoder.', 'value_head.')):
            assert parameter.grad is None
    assert any(p.grad is not None and p.grad.abs().sum() > 0 for p in encoder.parameters())
    optimizer.step()
    assert any(not torch.equal(p, before[n]) for n, p in model.named_parameters()
               if n.startswith('observable_value_encoder.'))
    for name, parameter in model.named_parameters():
        if not name.startswith(('observable_value_encoder.', 'value_head.')):
            assert torch.equal(parameter, before[name])
    assert torch.equal(model(*args)[0], logits)


def test_actor_gradient_does_not_reach_encoder(model):
    encoder = attach_encoder(model)
    logits, _ = model(*inputs(1))
    (logits[:, 1] - logits[:, 2]).sum().backward()
    assert all(p.grad is None for p in encoder.parameters())


def test_roundtrip_and_duplicate_guard(model):
    attach_encoder(model)
    other = copy.deepcopy(model)
    with torch.no_grad():
        next(other.observable_value_encoder.parameters()).add_(1)
    other.load_state_dict(model.state_dict(), strict=True)
    assert all(torch.equal(a, b) for a, b in zip(model.state_dict().values(), other.state_dict().values()))
    with pytest.raises(ValueError, match='already attached'):
        attach_encoder(model)
