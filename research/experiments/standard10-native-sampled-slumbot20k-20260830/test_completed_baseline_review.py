import importlib.util
import math
from pathlib import Path
import sys

import pytest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
spec = importlib.util.spec_from_file_location('external_baseline_review', BASE/'review_completed_baseline.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def test_chip_units_and_sample_variance():
    result = review.chip_statistics([-100, 100])
    assert result['bb_per_100'] == 0
    assert math.isclose(result['ci95_bb_per_100'], 196.)
    assert math.isclose(result['std_bb_per_hand'], math.sqrt(2))
    constant = review.chip_statistics([50]*20000)
    assert constant['bb_per_100'] == 50. and constant['ci95_bb_per_100'] == 0
    assert review.decision(constant) == 'ADMIT_SEPARATE_FRESH100K'


@pytest.mark.parametrize('values', [[1], [True, 0], [0., 1], [20001, 0], [0, float('nan')]])
def test_invalid_chip_evidence_rejected(values):
    with pytest.raises(ValueError): review.chip_statistics(values)


def test_no_optional_extension_or_small_sample_admission():
    with pytest.raises(ValueError): review.decision(dict(hands=19999, bb_per_100=50))
    assert review.decision(dict(hands=20000, bb_per_100=0)) == 'SAMPLED_BASELINE_NONPOSITIVE'
    assert review.decision(dict(hands=20000, bb_per_100=-.01)) == 'SAMPLED_BASELINE_NONPOSITIVE'


def test_prefix_comparison_flags_aligned_and_shifted_streams():
    from check_initial_prefixes import compare_initial
    left = {i: f'card_fingerprint_{i}' for i in range(100)}
    assert compare_initial(left, left)['gross_replay_detected']
    shifted = {i: left[i+10] for i in range(90)}
    assert compare_initial(left, shifted)['gross_replay_detected']
    assert not compare_initial(left, {i: f'other_{i}' for i in range(100)})['gross_replay_detected']
