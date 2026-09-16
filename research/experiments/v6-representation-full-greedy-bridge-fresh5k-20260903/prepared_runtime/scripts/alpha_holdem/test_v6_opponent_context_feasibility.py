import numpy as np
import pytest

from scripts.alpha_holdem.v6_opponent_context_feasibility import (
    action_bucket,
    context_features,
)


def test_action_bucket_maps_public_action_contract():
    assert action_bucket("f") == 0
    assert action_bucket("c") == 1
    assert action_bucket("k") == 2
    assert action_bucket("b125") == 3


def test_context_features_are_street_normalized_and_finite():
    counts = np.zeros((4, 4), dtype=np.int64)
    counts[0] = [1, 2, 1, 0]
    features = context_features(counts)
    assert features.shape == (20,)
    assert features[:4].tolist() == pytest.approx([0.25, 0.5, 0.25, 0.0])
    assert np.isfinite(features).all()
