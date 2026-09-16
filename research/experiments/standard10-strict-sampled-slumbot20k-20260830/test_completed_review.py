import importlib.util
from pathlib import Path
import sys

import pytest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
spec = importlib.util.spec_from_file_location('strict_completed_review', BASE/'review_completed_baseline.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def test_chip_unit_statistics():
    result = review.chip_statistics([-100, 100, -100, 100])
    assert result['bb_per_100'] == 0 and result['total_chips'] == 0
    assert result['std_bb_per_hand'] == pytest.approx((4/3)**.5)
    assert result['upper_bound_bb_per_100'] == pytest.approx(1.96*100*(4/3)**.5/2)


@pytest.mark.parametrize('values', [[1], [True, 2], [1., 2], [-20001, 1]])
def test_invalid_chip_evidence(values):
    with pytest.raises(ValueError):
        review.chip_statistics(values)


def test_only_complete_20k_can_admit():
    for n in (4168, 19999, 20001):
        with pytest.raises(ValueError):
            review.decision(dict(hands=n, bb_per_100=1))
    assert review.decision(dict(hands=20000, bb_per_100=1)) == 'ADMIT_SEPARATE_FRESH100K'
    assert review.decision(dict(hands=20000, bb_per_100=0)) == 'SAMPLED_BASELINE_NONPOSITIVE'
