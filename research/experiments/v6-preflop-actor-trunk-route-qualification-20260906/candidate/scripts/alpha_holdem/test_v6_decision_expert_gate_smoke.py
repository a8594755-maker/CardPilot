import numpy as np
import torch

from scripts.alpha_holdem.v6_decision_expert_gate_smoke import (
    ExpertGate,
    align_physical_probabilities,
    gate_update_report,
    gate_choice,
    summarize,
    union_physical_probabilities,
)


def test_gate_initializes_to_requested_constant_weight():
    gate = ExpertGate(7, hidden=4, initial_weight=0.05)
    values = gate(torch.randn(11, 7))
    assert torch.allclose(values, torch.full_like(values, 0.05), atol=1e-7)


def test_gate_choice_mixes_detached_expert_probabilities():
    gate = ExpertGate(2, hidden=2, initial_weight=0.25)
    slot, log_prob, weight = gate_choice(
        gate, np.asarray([0.0, 1.0], dtype=np.float32),
        np.asarray([0.8, 0.2], dtype=np.float32),
        np.asarray([0.0, 1.0], dtype=np.float32), device="cpu", uniform=None,
    )
    assert slot == 0
    assert abs(weight - 0.25) < 1e-6
    assert abs(np.exp(log_prob) - 0.6) < 1e-6


def test_physical_action_alignment_handles_legacy_min_raise_slot():
    source = ("f", "c", "b200", None, "b300")
    target = ("f", "c", None, "b200", "b300")
    aligned = align_physical_probabilities(
        np.asarray([0.1, 0.2, 0.3, 0.0, 0.4], dtype=np.float32), source, target,
    )
    assert np.allclose(aligned, [0.1, 0.2, 0.0, 0.3, 0.4])


def test_physical_action_union_preserves_distinct_legal_bet_sizes():
    p0, p1, table = union_physical_probabilities(
        np.asarray([0.2, 0.8, 0.0]), ("c", "b200", None),
        np.asarray([0.1, 0.3, 0.6]), ("c", "b250", "b400"), width=5,
    )
    assert table == ("c", "b200", "b250", "b400", None)
    assert np.allclose(p0, [0.2, 0.8, 0.0, 0.0, 0.0])
    assert np.allclose(p1, [0.1, 0.0, 0.3, 0.6, 0.0])


def test_paired_summary_uses_delta_and_decision_counts():
    rows = [
        {"delta_bb": 1.0, "hero_decisions": 2, "greedy_disagreements": 1, "mean_alternate_weight": 0.1},
        {"delta_bb": -0.5, "hero_decisions": 3, "greedy_disagreements": 0, "mean_alternate_weight": 0.3},
    ]
    report = summarize(rows)
    assert report["pairs"] == 2
    assert report["delta_bb100"] == 25.0
    assert report["greedy_disagreement"] == 0.2
    assert report["mean_alternate_weight"] == 0.2


def test_gate_update_report_detects_material_output_change():
    torch.manual_seed(9)
    gate = ExpertGate(5, hidden=3)
    initial = {key: value.detach().clone() for key, value in gate.state_dict().items()}
    with torch.no_grad():
        gate.network[-1].bias.add_(0.5)
    report = gate_update_report(initial, gate, 5)
    assert report["parameter_delta_l2"] > 0
    assert report["probe_max_abs_output_delta"] > 0.01


def test_mgda_gate_training_reports_positive_worst_alignment():
    torch.manual_seed(4)
    gate = ExpertGate(2, hidden=2, initial_weight=0.5)
    optimizer = torch.optim.Adam(gate.parameters(), lr=1e-3)
    transitions = []
    for group, returns in enumerate(((1.0, -1.0), (-1.0, 1.0))):
        for index, value in enumerate(returns):
            transitions.append({
                "features": np.asarray([1.0, float(index * 2 - 1)], dtype=np.float32),
                "p0": np.asarray([0.8, 0.2], dtype=np.float32),
                "p1": np.asarray([0.2, 0.8], dtype=np.float32),
                "slot": index, "old_log_prob": float(np.log(0.5)),
                "return_bb": value, "group": group,
            })
    from scripts.alpha_holdem.v6_decision_expert_gate_smoke import train_gate
    metrics = train_gate(
        gate, optimizer, transitions, epochs=1, groups=2, device="cpu",
        reference_kl_coef=0.1, robust_mgda=True,
    )
    assert metrics[0]["robust_mgda"] is True
    assert metrics[0]["applied_worst_alignment"] >= -1e-8
