import copy

import pytest
import torch

from scripts.alpha_holdem.train_mp3_hybrid_h1 import component_gradient_diagnostics


class TinyModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.policy_head = torch.nn.Linear(2, 1, bias=False)
        self.value_head = torch.nn.Linear(2, 1, bias=False)
        self.unused = torch.nn.Parameter(torch.ones(1))


def objectives(model):
    ppo = model.policy_head.weight.sum()
    kl = -0.5 * ppo
    critic = 10 * model.value_head.weight.sum()
    return {'ppo': ppo, 'source_kl': kl, 'entropy': ppo * 0,
            'critic': critic, 'actor': ppo + kl, 'total': ppo + kl + critic}


def test_exact_component_geometry_and_unused_parameters():
    model = TinyModel()
    result = component_gradient_diagnostics(model, objectives(model))
    policy = result['groups']['policy_head']
    assert policy['norms']['ppo'] == pytest.approx(2**0.5)
    assert policy['norms']['source_kl'] == pytest.approx(0.5 * 2**0.5)
    assert policy['cosines']['ppo_vs_source_kl'] == pytest.approx(-1)
    assert policy['cosines']['ppo_vs_critic'] is None
    assert result['groups']['unused']['norms']['total'] == 0
    assert result['groups']['all_trainable']['hypothetical_clip_scale'] < 0.04


def test_probe_preserves_rng_existing_grads_and_adam_update():
    torch.manual_seed(100)
    left = TinyModel()
    right = copy.deepcopy(left)
    opts = [torch.optim.Adam(m.parameters(), lr=0.01) for m in (left, right)]
    for _ in range(3):
        for index, (model, opt) in enumerate(zip((left, right), opts)):
            losses = objectives(model)
            if index == 1:
                before_rng = torch.get_rng_state().clone()
                before_grads = [None if p.grad is None else p.grad.clone() for p in model.parameters()]
                component_gradient_diagnostics(model, losses)
                assert torch.equal(before_rng, torch.get_rng_state())
                for previous, p in zip(before_grads, model.parameters()):
                    assert p.grad is None if previous is None else torch.equal(previous, p.grad)
            opt.zero_grad()
            losses['total'].backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 0.5)
            opt.step()
        for a, b in zip(left.parameters(), right.parameters()):
            assert torch.equal(a, b)
    for a, b in zip(opts[0].state.values(), opts[1].state.values()):
        for key in a:
            assert torch.equal(a[key], b[key])


def test_constant_objective_is_supported():
    model = TinyModel()
    result = component_gradient_diagnostics(model, {'ppo': torch.tensor(0.), 'total': torch.tensor(0.)})
    assert result['groups']['all_trainable']['norms']['total'] == 0


def test_no_trainable_parameters_rejected():
    model = TinyModel().requires_grad_(False)
    with pytest.raises(ValueError, match='trainable'):
        component_gradient_diagnostics(model, {})
