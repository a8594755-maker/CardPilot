import torch
from torch import nn

from scripts.alpha_holdem.dual_contract_residual_v6 import DualContractResidualPolicy


class TinyBase(nn.Module):
    def __init__(self):
        super().__init__()
        self.policy = nn.Linear(2, 9)
        self.value = nn.Linear(2, 1)

    def forward(self, cards, actions, extras, mask):
        return self.policy(extras[:, :2]), self.value(extras[:, :2])


def inputs(batch=4):
    return (
        torch.randn(batch, 6, 4, 13), torch.randn(batch, 25, 4, 5),
        torch.randn(batch, 2), torch.randn(batch, 6, 4, 13),
        torch.randn(batch, 25, 4, 5), torch.randn(batch, 2),
        torch.ones(batch, 9), torch.ones(batch, 9),
    )


def test_zero_residual_is_exact_and_base_is_frozen():
    base = TinyBase().eval()
    model = DualContractResidualPolicy(base, hidden=16)
    values = inputs()
    expected = base(values[0], values[1], values[2], values[6])
    actual = model(*values)
    assert torch.equal(actual[0], expected[0])
    assert torch.equal(actual[1], expected[1])
    assert all(not parameter.requires_grad for parameter in model.base.parameters())


def test_update_changes_only_residual_parameters():
    model = DualContractResidualPolicy(TinyBase(), hidden=16)
    values = inputs()
    before = {name: value.detach().clone() for name, value in model.base.state_dict().items()}
    logits, value = model(*values)
    loss = torch.nn.functional.cross_entropy(logits, torch.tensor([0, 1, 2, 3])) + value.square().mean()
    loss.backward()
    assert any(parameter.grad is not None and parameter.grad.abs().sum() > 0 for parameter in model.trainable_parameters())
    assert all(parameter.grad is None for parameter in model.base.parameters())
    torch.optim.Adam(model.trainable_parameters(), lr=1e-3).step()
    assert all(torch.equal(before[name], tensor) for name, tensor in model.base.state_dict().items())
