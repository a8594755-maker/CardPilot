import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alpha_holdem.v6_elo_eval import summarize_models


class PassiveModel(torch.nn.Module):
    def forward(self, cards, actions, extras, mask):
        logits = torch.arange(9, dtype=torch.float32, device=mask.device)
        logits = logits.unsqueeze(0).expand(mask.shape[0], -1).clone()
        logits = logits.masked_fill(mask <= 0, -1e9)
        return logits, torch.zeros((mask.shape[0], 1), device=mask.device)


@pytest.mark.parametrize('observation_style', ['v6', 'legacy_v4'])
def test_exact_v6_mirrored_self_match_cancels(observation_style):
    model = PassiveModel().eval()
    result = summarize_models(
        candidate=model,
        anchor=model,
        pairs=16,
        seed=20260901,
        starting_stack=200.0,
        observation_style=observation_style,
        device='cpu',
        include_pair_outcomes=True,
    )
    assert result['candidate_bb100'] == pytest.approx(0.0, abs=1e-12)
    assert result['candidate_ci95_bb100'] == pytest.approx(0.0, abs=1e-12)
    assert result['pair_draws'] == 16
    assert result['ood_nodes'] == {'candidate': 0, 'anchor': 0}
    assert len(result['paired_outcomes']) == 16
    assert all(len(row['deck']) == 52 for row in result['paired_outcomes'])


def test_exact_v6_mirrored_supports_per_policy_observation_contracts():
    model = PassiveModel().eval()
    result = summarize_models(
        candidate=model,
        anchor=model,
        pairs=8,
        seed=20260902,
        starting_stack=200.0,
        candidate_observation_style='legacy_v4',
        anchor_observation_style='v6',
        device='cpu',
    )
    assert result['candidate_observation_style'] == 'legacy_v4'
    assert result['anchor_observation_style'] == 'v6'
    assert result['evaluation_contract'] == (
        'physical_v6_candidate_legacy_v4_anchor_v6_v1'
    )


def test_exact_v6_mirrored_rejects_ambiguous_observation_contracts():
    model = PassiveModel().eval()
    with pytest.raises(ValueError, match='cannot be combined'):
        summarize_models(
            candidate=model,
            anchor=model,
            pairs=8,
            seed=20260903,
            starting_stack=200.0,
            observation_style='legacy_v4',
            candidate_observation_style='legacy_v4',
            anchor_observation_style='v6',
            device='cpu',
        )
