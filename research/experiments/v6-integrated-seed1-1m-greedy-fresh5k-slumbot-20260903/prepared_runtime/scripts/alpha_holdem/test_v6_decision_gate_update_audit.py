from pathlib import Path

import torch

from scripts.alpha_holdem.v6_decision_expert_gate_smoke import ExpertGate
from scripts.alpha_holdem.v6_decision_gate_update_audit import audit_checkpoint


def test_exact_seed_reconstruction_detects_small_nonzero_update(tmp_path: Path):
    seed = 1234
    torch.manual_seed(seed)
    gate = ExpertGate(5, hidden=3)
    with torch.no_grad():
        gate.network[-1].bias.add_(0.001)
    path = tmp_path / "gate.pt"
    torch.save({
        "schema": "cardpilot.decision_expert_gate.v1", "seed": seed,
        "feature_dim": 5, "hidden": 3, "state_dict": gate.state_dict(),
    }, path)
    report = audit_checkpoint(path)
    assert report["parameter_delta_l2"] > 0
    assert abs(report["parameter_delta_max_abs"] - 0.001) < 1e-6
    assert 0 < report["probe_max_abs_output_delta"] < 0.01
