import torch
from torch import nn

from scripts.alpha_holdem.contextual_residual_v6 import ContextualResidualPolicy, PosteriorCenteredResidualPolicy


class TinyBase(nn.Module):
    def forward(self, cards, actions, extras, legal):
        batch = cards.shape[0]
        return torch.arange(9, dtype=cards.dtype).repeat(batch, 1), torch.full((batch, 1), 3.0)


def inputs(batch=2):
    return (
        torch.zeros(batch, 6, 4, 13),
        torch.zeros(batch, 25, 4, 4),
        torch.zeros(batch, 2),
        torch.zeros(batch, 6, 4, 13),
        torch.zeros(batch, 25, 4, 5),
        torch.zeros(batch, 2),
        torch.ones(batch, 9),
        torch.ones(batch, 9),
    )


def test_zero_context_is_exact_base_even_after_residual_bias_changes():
    model = ContextualResidualPolicy(TinyBase(), hidden=16)
    with torch.no_grad():
        model.policy_delta.bias.fill_(0.2)
        model.value_delta.bias.fill_(0.4)
    logits, value = model(*inputs(), torch.zeros(2, 20))
    assert torch.equal(logits, torch.arange(9, dtype=torch.float32).repeat(2, 1))
    assert torch.equal(value, torch.full((2, 1), 3.0))


def test_active_context_respects_policy_delta_cap():
    model = ContextualResidualPolicy(TinyBase(), hidden=16, policy_delta_cap=0.25)
    with torch.no_grad():
        model.policy_delta.bias.fill_(100.0)
    logits, _ = model(*inputs(), torch.ones(2, 20))
    base = torch.arange(9, dtype=torch.float32).repeat(2, 1)
    assert torch.all((logits - base).abs() <= 0.250001)


def classifier():
    return {
        "weight": torch.stack((torch.ones(20), -torch.ones(20))),
        "bias": torch.zeros(2), "mean": torch.zeros(20), "std": torch.ones(20), "temperature": 1.0,
    }


def test_posterior_centered_policy_is_exact_for_zero_context_after_training():
    model = PosteriorCenteredResidualPolicy(TinyBase(), classifier(), hidden=16)
    with torch.no_grad():
        model.policy_heads.bias.copy_(torch.arange(18, dtype=torch.float32))
    logits, value = model(*inputs(), torch.zeros(2, 20))
    assert torch.equal(logits, torch.arange(9, dtype=torch.float32).repeat(2, 1))
    assert torch.equal(value, torch.full((2, 1), 3.0))


def test_posterior_centering_forces_uniform_context_to_zero_delta():
    spec = classifier()
    spec["weight"].zero_()
    model = PosteriorCenteredResidualPolicy(TinyBase(), spec, hidden=16)
    with torch.no_grad():
        model.policy_heads.bias.copy_(torch.arange(18, dtype=torch.float32))
    logits, _ = model(*inputs(), torch.ones(2, 20))
    assert torch.allclose(logits, torch.arange(9, dtype=torch.float32).repeat(2, 1))


def test_entropy_reliability_shrinks_nonuniform_posterior_delta():
    plain = PosteriorCenteredResidualPolicy(TinyBase(), classifier(), hidden=16, reliability_power=0)
    shrunk = PosteriorCenteredResidualPolicy(TinyBase(), classifier(), hidden=16, reliability_power=1)
    with torch.no_grad():
        plain.policy_heads.bias.copy_(torch.arange(18, dtype=torch.float32))
        shrunk.policy_heads.bias.copy_(plain.policy_heads.bias)
    context = torch.full((2, 20), 0.02)
    base = torch.arange(9, dtype=torch.float32).repeat(2, 1)
    plain_delta = (plain(*inputs(), context)[0] - base).abs().max()
    shrunk_delta = (shrunk(*inputs(), context)[0] - base).abs().max()
    assert 0 < shrunk_delta < plain_delta
