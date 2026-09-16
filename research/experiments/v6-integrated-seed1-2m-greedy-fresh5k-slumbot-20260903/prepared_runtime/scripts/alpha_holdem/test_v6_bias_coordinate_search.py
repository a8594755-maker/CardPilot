import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alpha_holdem.v6_bias_coordinate_search import (
    parse_keyed,
    robust_score,
    set_bias_offsets,
)


class TwoHeadModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.policy_head = torch.nn.Linear(2, 9)
        self.preflop_policy_head = torch.nn.Linear(2, 9)


def test_parse_keyed_rejects_duplicates():
    assert parse_keyed(['a=x', 'b=y=z'], option='--x') == {'a': 'x', 'b': 'y=z'}
    with pytest.raises(ValueError, match='duplicate'):
        parse_keyed(['a=x', 'a=y'], option='--x')


def test_robust_score_penalizes_dispersion():
    assert robust_score([2.0, 2.0], dispersion_weight=0.5) == pytest.approx(2.0)
    assert robust_score([0.0, 4.0], dispersion_weight=0.5) == pytest.approx(1.0)


def test_set_bias_offsets_changes_only_requested_heads():
    model = TwoHeadModel()
    before = {key: value.detach().clone() for key, value in model.state_dict().items()}
    source = {
        'policy_head.bias': before['policy_head.bias'],
        'preflop_policy_head.bias': before['preflop_policy_head.bias'],
    }
    offsets = np.arange(18, dtype=np.float64) / 100.0
    set_bias_offsets(model, source, offsets)
    assert torch.equal(model.policy_head.weight, before['policy_head.weight'])
    assert torch.equal(
        model.preflop_policy_head.weight, before['preflop_policy_head.weight']
    )
    assert torch.allclose(
        model.policy_head.bias,
        before['policy_head.bias'] + torch.tensor(offsets[:9], dtype=torch.float32),
    )
    assert torch.allclose(
        model.preflop_policy_head.bias,
        before['preflop_policy_head.bias'] + torch.tensor(offsets[9:], dtype=torch.float32),
    )
