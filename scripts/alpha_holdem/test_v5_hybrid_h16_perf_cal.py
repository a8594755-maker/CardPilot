from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/alpha_holdem/v5_hybrid_h16_perf_cal.py"
SPEC = importlib.util.spec_from_file_location("h16_perf", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_registered_gate_constants_are_frozen() -> None:
    assert MODULE.THROUGHPUT_RATIO_MIN == 0.85
    assert MODULE.MSE_STABILITY_RATIO_MIN == 0.95
    assert MODULE.SOURCE_ITERATION == 35051
    assert MODULE.SOURCE_HANDS == 576021901


def test_full_update_kwargs_freeze_only_catchup_loss_variable() -> None:
    mse = MODULE.update_kwargs("mse", 1024, 4, 1e-12)
    smooth = MODULE.update_kwargs("smooth_l1", 1024, 4, 1e-12)
    assert mse["value_head_catchup"] is True
    assert mse["epochs"] == 4
    assert mse["mini_batch_size"] == 1024
    assert mse["target_kl"] == 1e-12
    assert mse["action_prior_coef"] == 0.02
    assert mse["preflop_action_prior_coef"] == 0.01
    differing = {key for key in mse if mse[key] != smooth[key]}
    assert differing == {"value_head_catchup_loss"}


def test_transition_hash_is_deterministic_and_content_sensitive() -> None:
    base = (
        np.zeros((6, 4, 13), np.float32),
        np.zeros((25, 4, 5), np.float32),
        np.zeros(2, np.float32),
        np.ones(9, np.float32),
        1, -1.5, 0.0, 2.0, 1.0, 200.0, 200.0, 1.0,
    )
    assert MODULE.transition_sha256([base]) == MODULE.transition_sha256([base])
    changed = list(base)
    changed[4] = 2
    assert MODULE.transition_sha256([base]) != MODULE.transition_sha256([tuple(changed)])
