import numpy as np
import pytest

from scripts.alpha_holdem.v6_opponent_context_regularization_control import (
    classification_metrics,
    split_training_rows,
)


def test_split_training_rows_keeps_selection_and_test_sealed():
    rows = [
        {"split": "training", "session_index": index, "policy_index": 0}
        for index in range(12)
    ] + [{"split": "holdout", "session_index": 0, "policy_index": 0}]
    train, test = split_training_rows(rows, 8)
    assert [row["session_index"] for row in train] == list(range(8))
    assert [row["session_index"] for row in test] == list(range(8, 12))


def test_classification_metrics_reports_balanced_breadth_and_calibration():
    logits = np.asarray([[4.0, 0.0], [3.0, 0.0], [0.0, 4.0], [0.0, 3.0]])
    labels = np.asarray([0, 0, 1, 1])
    metrics = classification_metrics(logits, labels, classes=2, temperature=2.0)
    assert metrics["accuracy"] == 1.0
    assert metrics["minimum_class_accuracy"] == 1.0
    assert metrics["nll"] > 0.0
    assert 0.0 <= metrics["ece"] <= 1.0
    assert metrics["mean_confidence"] == pytest.approx(
        0.5 * (1 / (1 + np.exp(-2)) + 1 / (1 + np.exp(-1.5)))
    )
