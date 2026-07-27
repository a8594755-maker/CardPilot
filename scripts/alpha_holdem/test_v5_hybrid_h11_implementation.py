from __future__ import annotations

import copy

import torch

from scripts.alpha_holdem.test_v5_hybrid_h8_implementation import (
    TinyPolicy,
    assert_state_equal,
    named_optimizer_state,
    transitions,
)
from scripts.alpha_holdem.train_mp3_hybrid_h1 import trinal_clip_ppo_update


def run_update(initial: TinyPolicy, data: list[tuple], *, loss_mode: str):
    model = copy.deepcopy(initial)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.02)
    torch.manual_seed(2026071901)
    stats = trinal_clip_ppo_update(
        model,
        optimizer,
        data,
        "cpu",
        epochs=4,
        mini_batch_size=6,
        entropy_coef=0.0,
        action_prior_coef=0.0,
        preflop_action_prior_coef=0.0,
        target_kl=1e-12,
        value_head_catchup=True,
        value_head_catchup_loss=loss_mode,
        value_head_catchup_smooth_l1_beta=1.0,
    )
    return model, optimizer, stats, torch.random.get_rng_state().clone()


def test_h11_mse_mode_is_bitwise_equivalent_to_h8_catchup_default() -> None:
    torch.manual_seed(2026071900)
    initial = TinyPolicy()
    data = transitions(initial)

    explicit, explicit_optimizer, explicit_stats, explicit_rng = run_update(
        initial, data, loss_mode="mse"
    )

    legacy = copy.deepcopy(initial)
    legacy_optimizer = torch.optim.Adam(legacy.parameters(), lr=0.02)
    torch.manual_seed(2026071901)
    legacy_stats = trinal_clip_ppo_update(
        legacy,
        legacy_optimizer,
        data,
        "cpu",
        epochs=4,
        mini_batch_size=6,
        entropy_coef=0.0,
        action_prior_coef=0.0,
        preflop_action_prior_coef=0.0,
        target_kl=1e-12,
        value_head_catchup=True,
    )
    legacy_rng = torch.random.get_rng_state().clone()

    for name, tensor in explicit.state_dict().items():
        assert torch.equal(tensor, legacy.state_dict()[name]), name
    explicit_opt = named_optimizer_state(explicit, explicit_optimizer)
    legacy_opt = named_optimizer_state(legacy, legacy_optimizer)
    for name in explicit_opt:
        assert_state_equal(explicit_opt[name], legacy_opt[name])
    assert explicit_stats == legacy_stats
    assert torch.equal(explicit_rng, legacy_rng)
    assert explicit_stats["value_head_catchup_loss_mode"] == "mse"


def test_h11_smooth_l1_changes_only_value_head_catchup_effect() -> None:
    torch.manual_seed(2026071902)
    initial = TinyPolicy()
    data = transitions(initial)
    control, control_optimizer, control_stats, control_rng = run_update(
        initial, data, loss_mode="mse"
    )
    treatment, treatment_optimizer, treatment_stats, treatment_rng = run_update(
        initial, data, loss_mode="smooth_l1"
    )

    assert control_stats["kl_early_stop_epoch"] == treatment_stats["kl_early_stop_epoch"]
    assert control_stats["value_head_catchup_epochs"] == treatment_stats["value_head_catchup_epochs"]
    assert control_stats["value_head_catchup_minibatches"] == treatment_stats["value_head_catchup_minibatches"]
    assert treatment_stats["value_head_catchup_loss_mode"] == "smooth_l1"
    assert treatment_stats["value_head_catchup_smooth_l1_beta"] == 1.0
    assert treatment_stats["value_head_catchup_actor_state_unchanged"]
    assert torch.equal(control_rng, treatment_rng)

    for name, control_tensor in control.state_dict().items():
        treatment_tensor = treatment.state_dict()[name]
        if name.startswith("value_head."):
            assert not torch.equal(control_tensor, treatment_tensor), name
        else:
            assert torch.equal(control_tensor, treatment_tensor), name

    control_opt = named_optimizer_state(control, control_optimizer)
    treatment_opt = named_optimizer_state(treatment, treatment_optimizer)
    for name in control_opt:
        if not name.startswith("value_head."):
            assert_state_equal(control_opt[name], treatment_opt[name])
    assert torch.equal(control.audit_buffer, treatment.audit_buffer)


def test_h11_cli_contract_is_fail_closed_in_source() -> None:
    source = open("scripts/alpha_holdem/train_v5.py", encoding="utf-8").read()
    required = (
        "--h11-window-arm",
        "--h11-catchup-loss",
        "--h11-catchup-smooth-l1-beta",
        "H11 arm run_id or fixed endpoint mismatch",
        "H11 exact canonical source checkpoint identity/hash mismatch",
        "H11 forbidden H9/H10/CAL source path",
        "H11 arms require target-KL0.03 and value-head catch-up enabled",
    )
    for token in required:
        assert token in source
