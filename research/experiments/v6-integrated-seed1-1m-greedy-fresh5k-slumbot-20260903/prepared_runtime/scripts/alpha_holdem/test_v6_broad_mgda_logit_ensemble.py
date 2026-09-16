import numpy as np
import torch
from torch import nn

from scripts.alpha_holdem.v6_broad_mgda_logit_ensemble import LogitEnsemble, paired_ensemble_gain


class _Member(nn.Module):
    def __init__(self, logit, value):
        super().__init__()
        self.base = nn.Identity()
        self.logit = torch.as_tensor(logit, dtype=torch.float32)
        self.value = torch.as_tensor([value], dtype=torch.float32)

    def forward(self, batch):
        size = batch.shape[0]
        return self.logit.expand(size, -1), self.value.expand(size, -1)


def test_logit_ensemble_averages_outputs_not_parameters():
    ensemble = LogitEnsemble([
        _Member([1.0, 3.0], 2.0),
        _Member([3.0, 5.0], 4.0),
        _Member([5.0, 7.0], 6.0),
    ])
    logits, values = ensemble(torch.zeros(2, 1))
    assert torch.equal(logits, torch.tensor([[3.0, 5.0], [3.0, 5.0]]))
    assert torch.equal(values, torch.tensor([[4.0], [4.0]]))


def test_logit_ensemble_preserves_shared_large_mask_sentinel():
    sentinel = -1_000_000_000.0
    members = [
        _Member([sentinel, 1.0 + offset], 0.0)
        for offset in (0.0, 0.1, -0.1)
    ]
    ensemble = LogitEnsemble(members)
    logits, _ = ensemble(torch.zeros(1, 1))
    assert logits[0, 0].item() == members[0].logit[0].item()
    assert np.isclose(logits[0, 1].item(), 1.0)


def test_paired_ensemble_gain_uses_common_deal_constituent_mean():
    rows = []
    for pair in range(3):
        for seed, delta in enumerate((0.0, 0.3, 0.6)):
            rows.append({
                "dose_hands": 65536,
                "candidate_label": f"seed{seed}",
                "holdout_label": "a",
                "pair_index": pair,
                "delta_bb": delta,
                "seat_delta_bb": [delta, delta],
            })
        rows.append({
            "dose_hands": 65536,
            "candidate_label": "ensemble",
            "holdout_label": "a",
            "pair_index": pair,
            "delta_bb": 0.5,
            "seat_delta_bb": [0.5, 0.5],
        })
    result = paired_ensemble_gain(rows, 65536)
    assert result["pairs"] == 3
    assert np.isclose(result["gain_vs_mean_constituent_bb100"], 20.0)
    assert all(np.isclose(row["gain_bb100"], 20.0) for row in result["seats"])
