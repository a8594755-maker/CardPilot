import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alpha_holdem.v6_posterior_counterfactual_reliability import (
    sample_disjoint_holes,
)


def test_sample_disjoint_holes_is_reproducible_and_disjoint():
    support = [[index, index + 20] for index in range(20)]
    dev, confirm = sample_disjoint_holes(
        support, dev=4, confirm=5, rng=random.Random(11)
    )
    assert len(dev) == 4 and len(confirm) == 5
    assert set(dev).isdisjoint(confirm)
    assert (dev, confirm) == sample_disjoint_holes(
        support, dev=4, confirm=5, rng=random.Random(11)
    )


def test_sample_disjoint_holes_rejects_small_support():
    with pytest.raises(ValueError, match='too small'):
        sample_disjoint_holes([[1, 2]], dev=1, confirm=1, rng=random.Random(1))
