import numpy as np
import torch

import run_development as run


def test_parent_checkpoint_has_exact_resume_semantics():
    checkpoint = torch.load(run.PARENT / "latest.pt", map_location="cpu", weights_only=False)
    run.validate_parent_checkpoint(checkpoint)


def test_rng_reconstruction_advances_exactly_eight_permutations():
    expected = np.random.default_rng(run.parent.SEED)
    for _ in range(8):
        expected.permutation(31)
    assert np.array_equal(run.reconstructed_generator(31).permutation(31), expected.permutation(31))


def test_parent_curve_is_strictly_decreasing_by_epoch_mean():
    import json
    rows = [json.loads(line) for line in (run.PARENT / "training_metrics.jsonl").read_text().splitlines()]
    means = [np.mean([row["loss"] for row in rows if row["epoch"] == epoch]) for epoch in range(1, 9)]
    assert all(left > right for left, right in zip(means, means[1:]))
