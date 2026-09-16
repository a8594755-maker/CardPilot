import numpy as np
import torch
from torch import nn

import run_development as run


class DummyBase(nn.Module):
    def __init__(self):
        super().__init__()
        self.trunk = nn.Linear(500, 256)
        self.policy = nn.Linear(256, 9)

    def forward(self, card, action, extra, mask):
        hidden = self.trunk(action.flatten(1))
        return self.policy(hidden), hidden[:, :1]


def test_zero_initialized_residual_exactly_preserves_base_logits():
    base = DummyBase()
    model = run.FlatSequenceResidual(base)
    action = torch.randn(4, 25, 4, 5)
    card = torch.zeros(4, 6, 4, 13)
    extra = torch.tensor([[0, 0, 0], [0, 0, 1], [0, 0, 0], [0, 0, 1]], dtype=torch.float32)
    mask = torch.ones(4, 9)
    with torch.no_grad():
        expected = base(card, action, extra, mask)[0]
        actual = model(card, action, extra, mask)[0]
    assert torch.equal(expected, actual)
    assert all(not parameter.requires_grad for parameter in model.base.parameters())
    assert len([parameter for name, parameter in model.named_parameters() if not name.startswith("base.")]) == 14


def test_development_gate_requires_all_three_conditions():
    source = np.full(128, 0.16)
    assert run.development_gate(np.full(128, 0.149), source)["passed"]
    assert not run.development_gate(np.full(128, 0.151), source)["passed"]


def test_parity_metrics_pass_only_fixed_thresholds():
    cpu = np.array([[0.6, 0.4], [0.2, 0.8]])
    gpu = cpu.copy()
    assert run.parity_metrics(cpu, gpu)["passed"]
    gpu[0] = [0.59997, 0.40003]
    assert not run.parity_metrics(cpu, gpu)["passed"]


def test_sampled_actions_is_deterministic_per_uniform():
    probabilities = np.array([[0.2, 0.3, 0.5], [0.0, 0.6, 0.4]])
    assert run.sampled_actions(probabilities, np.array([0.2, 0.9])).tolist() == [0, 2]
