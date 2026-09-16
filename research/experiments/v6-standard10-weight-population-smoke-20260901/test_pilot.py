from pathlib import Path
import importlib.util

import torch


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("weight_population_runner", HERE / "run_pilot.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def tiny_state():
    return {
        "trunk.weight": torch.arange(12, dtype=torch.float32).reshape(3, 4),
        "policy_head.weight": torch.arange(12, dtype=torch.float32).reshape(3, 4) / 10,
        "policy_head.bias": torch.tensor([-0.2, 0.0, 0.3]),
        "preflop_policy_head.weight": torch.arange(12, dtype=torch.float32).reshape(3, 4) / 20,
        "preflop_policy_head.bias": torch.tensor([0.1, -0.1, 0.2]),
    }


def test_perturbation_is_deterministic_and_actor_only():
    base = tiny_state()
    first = MODULE.perturb_actor_state(base, 0.5, 1234)
    second = MODULE.perturb_actor_state(base, 0.5, 1234)
    third = MODULE.perturb_actor_state(base, 0.5, 1235)
    assert all(torch.equal(first[key], second[key]) for key in base)
    assert torch.equal(first["trunk.weight"], base["trunk.weight"])
    assert all(torch.isfinite(value).all() for value in first.values())
    assert any(not torch.equal(first[key], base[key]) for key in MODULE.ACTOR_NAMES)
    assert any(not torch.equal(first[key], third[key]) for key in MODULE.ACTOR_NAMES)


def test_scale_selection_uses_only_tv_target():
    rows = {0.25: [0.02, 0.03, 0.04], 0.5: [0.10, 0.12, 0.14], 1.0: [0.20, 0.22, 0.24]}
    assert MODULE.select_scale(rows, target=0.12) == 0.5


def test_fixed_seed_partitions_are_disjoint():
    assert set(MODULE.CALIBRATION_SEEDS).isdisjoint(MODULE.TRAIN_SEEDS)
    assert set(MODULE.CALIBRATION_SEEDS).isdisjoint(MODULE.EVAL_SEEDS)
    assert set(MODULE.TRAIN_SEEDS).isdisjoint(MODULE.EVAL_SEEDS)
    assert MODULE.TARGET_PHYSICAL - MODULE.START_PHYSICAL == 65536
