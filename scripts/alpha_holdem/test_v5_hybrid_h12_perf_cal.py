from __future__ import annotations

import importlib.util
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/alpha_holdem/v5_hybrid_h12_perf_cal.py"
SPEC = importlib.util.spec_from_file_location("h12_perf", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_deterministic_batch_and_hash() -> None:
    left = MODULE.deterministic_batch(2026071601, 8)
    right = MODULE.deterministic_batch(2026071601, 8)
    assert MODULE.tensor_sha256(left) == MODULE.tensor_sha256(right)
    assert left["cards"].shape == (8, 6, 4, 13)
    assert left["actions"].shape == (8, 25, 4, 5)
    assert left["masks"].shape == (8, 9)


def test_value_head_only_step_does_not_change_actor() -> None:
    model = MODULE.AlphaHoldemNet(num_actions=9, critic_contract=MODULE.CRITIC_V1)
    batch = MODULE.deterministic_batch(7, 2)
    model(batch["cards"], batch["actions"], batch["extras"], batch["masks"])
    model.eval()
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    before = {
        name: value.detach().clone()
        for name, value in model.state_dict().items()
        if not name.startswith("value_head.")
    }
    for name, parameter in model.named_parameters():
        parameter.requires_grad_(name.startswith("value_head."))
    MODULE.one_step(model, optimizer, batch, "smooth_l1")
    after = model.state_dict()
    assert all(torch.equal(value, after[name]) for name, value in before.items())


def test_gate_constants_are_frozen() -> None:
    assert MODULE.LOSS_RATIO_MIN == 0.95
    assert MODULE.COMMON_BASELINE_RATIO_MIN == 0.95
