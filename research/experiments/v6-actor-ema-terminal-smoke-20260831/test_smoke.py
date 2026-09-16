import importlib.util
from pathlib import Path
import sys

import pytest
import torch
from torch import nn


ROOT = Path(__file__).resolve().parents[3]
TRAINER = ROOT / "scripts/alpha_holdem/train_v5.py"
sys.path.insert(0, str(ROOT / "scripts/alpha_holdem"))
spec = importlib.util.spec_from_file_location("actor_ema_train_v5", TRAINER)
trainer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trainer)


class TinyActor(nn.Module):
    def __init__(self):
        super().__init__()
        self.trunk = nn.Linear(2, 3)
        self.policy_head = nn.Linear(3, 2)
        self.preflop_policy_head = nn.Linear(3, 2)
        self.value_head = nn.Linear(3, 1)


def test_actor_ema_initializes_exact_four_cpu_tensors():
    model = TinyActor()
    state = trainer.initialize_actor_ema(model)
    assert tuple(state) == (
        "policy_head.weight",
        "policy_head.bias",
        "preflop_policy_head.weight",
        "preflop_policy_head.bias",
    )
    parameters = dict(model.named_parameters())
    assert all(value.device.type == "cpu" for value in state.values())
    assert all(torch.equal(value, parameters[name]) for name, value in state.items())
    assert all(value.data_ptr() != parameters[name].data_ptr() for name, value in state.items())


def test_actor_ema_update_formula_and_scope():
    model = TinyActor()
    state = trainer.initialize_actor_ema(model)
    before = {name: value.clone() for name, value in state.items()}
    trunk_before = model.trunk.weight.detach().clone()
    with torch.no_grad():
        for name, parameter in model.named_parameters():
            if name in state:
                parameter.add_(2.0)
    trainer.update_actor_ema(model, state, 0.9)
    parameters = dict(model.named_parameters())
    for name in state:
        expected = before[name] * 0.9 + parameters[name].detach().cpu() * 0.1
        assert torch.allclose(state[name], expected, rtol=0, atol=1e-7)
    assert torch.equal(model.trunk.weight, trunk_before)


def test_actor_ema_rejects_invalid_decay_or_state():
    model = TinyActor()
    state = trainer.initialize_actor_ema(model)
    with pytest.raises(ValueError, match="decay"):
        trainer.update_actor_ema(model, state, 1.0)
    state.pop("policy_head.bias")
    with pytest.raises(ValueError, match="keys"):
        trainer.update_actor_ema(model, state, 0.9)


def test_trainer_serializes_restores_and_logs_ema_contract():
    source = TRAINER.read_text(encoding="utf-8")
    assert "payload['actor_ema_state']" in source
    assert "true actor-EMA resume requires serialized actor_ema_state" in source
    assert "actor-EMA resume decay mismatch" in source
    assert "update_actor_ema(" in source
    assert "'actor_ema_updates': int(actor_ema_updates)" in source
    assert source.index("update_actor_ema(", source.index("stats = trinal_clip_ppo_update(")) < source.index("torch.save(checkpoint_payload()", source.index("stats = trinal_clip_ppo_update("))
