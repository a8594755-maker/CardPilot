import torch

from scripts.alpha_holdem.v6_mgda_source_boundary_audit import distribution_metrics


def test_distribution_metrics_are_zero_for_identical_legal_logits():
    logits = torch.tensor([[1.0, 2.0, 50.0]])
    legal = torch.tensor([[1.0, 1.0, 0.0]])
    agreement, kl, mean_delta, max_delta = distribution_metrics(
        logits, logits.clone(), legal
    )
    assert agreement.item()
    assert abs(kl.item()) < 1e-7
    assert mean_delta.item() == 0.0
    assert max_delta.item() == 0.0


def test_distribution_metrics_ignore_illegal_logit_changes():
    base = torch.tensor([[2.0, 1.0, 0.0]])
    candidate = torch.tensor([[2.0, 1.0, 1000.0]])
    legal = torch.tensor([[1.0, 1.0, 0.0]])
    agreement, kl, mean_delta, max_delta = distribution_metrics(
        base, candidate, legal
    )
    assert agreement.item()
    assert abs(kl.item()) < 1e-7
    assert mean_delta.item() == 0.0
    assert max_delta.item() == 0.0
