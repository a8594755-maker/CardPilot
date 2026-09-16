import numpy as np
import torch

from scripts.alpha_holdem.v6_decision_expert_gate_smoke import ExpertGate
from scripts.alpha_holdem.v6_decision_gate_gradient_conflict_audit import policy_gradient_matrix


def test_group_gradient_geometry_detects_opposition():
    gate = ExpertGate(2, hidden=2, initial_weight=0.5)
    features = np.asarray([[1, -1], [1, 1], [1, -1], [1, 1]], dtype=np.float32)
    p0 = np.tile(np.asarray([[0.8, 0.2]], dtype=np.float32), (4, 1))
    p1 = np.tile(np.asarray([[0.2, 0.8]], dtype=np.float32), (4, 1))
    arrays = {
        "features": features, "p0": p0, "p1": p1,
        "slots": np.asarray([0, 1, 0, 1], dtype=np.int16),
        "old_log_probs": np.log(np.asarray([0.5] * 4, dtype=np.float32)),
        "returns_bb": np.asarray([1, -1, -1, 1], dtype=np.float32),
        "groups": np.asarray([0, 0, 1, 1], dtype=np.int16),
    }
    matrix, report = policy_gradient_matrix(gate, arrays, groups=2, device="cpu")
    assert matrix.shape[0] == 2
    assert report["negative_pairwise_cosines"] == 1
    assert report["pairwise_cosine_minimum"] < 0
