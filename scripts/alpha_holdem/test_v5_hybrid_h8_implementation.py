from __future__ import annotations

import copy

import numpy as np
import torch
from torch import nn

from scripts.alpha_holdem.train_mp3_hybrid_h1 import trinal_clip_ppo_update


class TinyPolicy(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.trunk = nn.Linear(2, 8)
        self.policy_head = nn.Linear(8, 9)
        self.value_head = nn.Linear(8, 1)
        self.register_buffer("audit_buffer", torch.tensor([3.0, 7.0]))

    def forward(self, cards, actions, extras, masks):
        hidden = torch.tanh(self.trunk(extras))
        logits = self.policy_head(hidden).masked_fill(masks <= 0, -1e9)
        return logits, self.value_head(hidden)


def transitions(model: TinyPolicy, count: int = 24) -> list[tuple]:
    rows = []
    model.eval()
    for index in range(count):
        card = np.zeros((6, 4, 13), np.float32)
        action = np.zeros((25, 4, 5), np.float32)
        extra = np.array(
            [1.0 + (index % 5) * 0.2, 0.5 + (index % 3) * 0.3],
            np.float32,
        )
        mask = np.ones(9, np.float32)
        selected = index % 4 + 1
        with torch.no_grad():
            logits, value = model(
                torch.tensor(card).unsqueeze(0),
                torch.tensor(action).unsqueeze(0),
                torch.tensor(extra).unsqueeze(0),
                torch.tensor(mask).unsqueeze(0),
            )
            old_lp = torch.log_softmax(logits, dim=-1)[0, selected].item()
        done = 1.0 if index % 6 == 5 else 0.0
        reward = float((index % 7) - 3) if done else 0.0
        rows.append(
            (
                card,
                action,
                extra,
                mask,
                selected,
                old_lp,
                reward,
                float(value.item()),
                done,
                200.0,
                200.0,
                1.0 if done else 0.0,
            )
        )
    return rows


def run_update(initial: TinyPolicy, data: list[tuple], *, catchup: bool):
    model = copy.deepcopy(initial)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.02)
    torch.manual_seed(2026071803)
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
        value_head_catchup=catchup,
    )
    return model, optimizer, stats


def named_optimizer_state(model: nn.Module, optimizer: torch.optim.Optimizer) -> dict:
    result = {}
    for name, parameter in model.named_parameters():
        state = optimizer.state.get(parameter, {})
        result[name] = {
            key: value.detach().clone() if torch.is_tensor(value) else copy.deepcopy(value)
            for key, value in state.items()
        }
    return result


def assert_state_equal(left: dict, right: dict) -> None:
    assert left.keys() == right.keys()
    for key in left:
        if torch.is_tensor(left[key]):
            assert torch.equal(left[key], right[key]), key
        else:
            assert left[key] == right[key], key


def test_forced_h8_catchup_changes_only_value_head_and_its_optimizer_state() -> None:
    torch.manual_seed(2026071803)
    initial = TinyPolicy()
    data = transitions(initial)
    control, control_optimizer, control_stats = run_update(initial, data, catchup=False)
    treatment, treatment_optimizer, treatment_stats = run_update(initial, data, catchup=True)

    assert control_stats["kl_early_stop_triggered"]
    assert treatment_stats["kl_early_stop_triggered"]
    assert control_stats["ppo_epochs_completed"] == treatment_stats["ppo_epochs_completed"] < 4
    assert treatment_stats["value_head_catchup_epochs"] == 4 - treatment_stats["ppo_epochs_completed"]
    assert treatment_stats["value_head_catchup_minibatches"] > 0
    assert treatment_stats["value_head_catchup_actor_state_unchanged"]

    for name, control_tensor in control.state_dict().items():
        treatment_tensor = treatment.state_dict()[name]
        if name.startswith("value_head."):
            assert not torch.equal(control_tensor, treatment_tensor), name
        else:
            assert torch.equal(control_tensor, treatment_tensor), name

    control_optimizer_state = named_optimizer_state(control, control_optimizer)
    treatment_optimizer_state = named_optimizer_state(treatment, treatment_optimizer)
    for name in control_optimizer_state:
        if not name.startswith("value_head."):
            assert_state_equal(control_optimizer_state[name], treatment_optimizer_state[name])
    assert any(
        not torch.equal(
            control_optimizer_state[name]["exp_avg"],
            treatment_optimizer_state[name]["exp_avg"],
        )
        for name in control_optimizer_state
        if name.startswith("value_head.")
    )
    assert torch.equal(control.audit_buffer, treatment.audit_buffer)


def test_disabled_flag_is_bitwise_and_rng_equivalent() -> None:
    torch.manual_seed(2026071804)
    initial = TinyPolicy()
    data = transitions(initial)

    model_a = copy.deepcopy(initial)
    optimizer_a = torch.optim.Adam(model_a.parameters(), lr=0.02)
    torch.manual_seed(2026071805)
    stats_a = trinal_clip_ppo_update(
        model_a,
        optimizer_a,
        data,
        "cpu",
        epochs=4,
        mini_batch_size=6,
        entropy_coef=0.0,
        target_kl=1e-12,
    )
    rng_a = torch.random.get_rng_state().clone()

    model_b = copy.deepcopy(initial)
    optimizer_b = torch.optim.Adam(model_b.parameters(), lr=0.02)
    torch.manual_seed(2026071805)
    stats_b = trinal_clip_ppo_update(
        model_b,
        optimizer_b,
        data,
        "cpu",
        epochs=4,
        mini_batch_size=6,
        entropy_coef=0.0,
        target_kl=1e-12,
        value_head_catchup=False,
    )
    rng_b = torch.random.get_rng_state().clone()

    for name, tensor_a in model_a.state_dict().items():
        assert torch.equal(tensor_a, model_b.state_dict()[name]), name
    for name in named_optimizer_state(model_a, optimizer_a):
        assert_state_equal(
            named_optimizer_state(model_a, optimizer_a)[name],
            named_optimizer_state(model_b, optimizer_b)[name],
        )
    assert torch.equal(rng_a, rng_b)
    assert stats_a == stats_b
    assert not stats_b["value_head_catchup_enabled"]
    assert stats_b["value_head_catchup_epochs"] == 0
