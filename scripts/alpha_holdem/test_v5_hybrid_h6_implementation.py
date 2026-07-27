import copy

import torch

from scripts.alpha_holdem.v5_hybrid_h6_implementation_audit import TinyPolicy, equal_state, run_update, transitions


def test_disabled_and_unreachable_threshold_are_bitwise_equivalent() -> None:
    torch.manual_seed(7)
    initial = TinyPolicy()
    data = transitions(initial)
    disabled_model, disabled = run_update(initial, data, 0.0)
    high_model, high = run_update(initial, data, 1e9)
    assert equal_state(disabled_model, high_model)
    assert disabled["ppo_epochs_completed"] == high["ppo_epochs_completed"] == 4
    assert not disabled["kl_early_stop_triggered"]
    assert not high["kl_early_stop_triggered"]


def test_forced_threshold_stops_only_after_a_completed_epoch() -> None:
    torch.manual_seed(8)
    initial = TinyPolicy()
    data = transitions(initial)
    before = copy.deepcopy(initial)
    model, stats = run_update(initial, data, 1e-12)
    assert stats["kl_early_stop_triggered"]
    assert 1 <= stats["kl_early_stop_epoch"] == stats["ppo_epochs_completed"] < 4
    assert not equal_state(model, before)
