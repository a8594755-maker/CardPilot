"""Independent CI arithmetic and preserved greedy-evidence regression checks."""
import importlib.util
import json
import math
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('completed_analysis', BASE / 'analyze_completed_run.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def test_known_sample_mean_and_sample_standard_error():
    result = analysis.paired_statistics([0, 0, 0], [1, 2, 3])
    assert result['delta_bb100'] == 200
    assert result['ci95_half_width'] == pytest.approx(1.96 * 100 / math.sqrt(3))
    assert result['ci95_lower'] == pytest.approx(200 - result['ci95_half_width'])
    assert result['ci95_upper'] == pytest.approx(200 + result['ci95_half_width'])


def test_identical_crn_outcomes_cancel_exactly():
    values = [200, -200, 1, -0.5, 13]
    result = analysis.paired_statistics(values, values)
    assert result['pairs'] == 5
    for field in ['delta_bb100', 'ci95_half_width', 'ci95_lower', 'ci95_upper']:
        assert result[field] == 0


@pytest.mark.parametrize('control,treatment', [([], []), ([1], [1]),
    ([1, 2], [1]), ([0, 0], [0, float('nan')]), ([0, 0], [0, float('inf')])])
def test_invalid_evidence_rejected(control, treatment):
    with pytest.raises(ValueError):
        analysis.paired_statistics(control, treatment)


@pytest.mark.parametrize('label', ['early', 'mid', 'final'])
def test_completed_greedy_cells_independently_match_saved_pair_ci(label):
    source = json.loads((BASE / 'matrix/greedy_source.json').read_text())
    target = json.loads((BASE / 'matrix' / f'greedy_{label}.json').read_text())
    expected = json.loads((BASE / 'matrix' / f'greedy_{label}_delta.json').read_text())
    by_anchor = {row['anchor']: row for row in expected['anchors']}
    assert len(source['anchors']) == len(target['anchors']) == 3
    for control, treatment in zip(source['anchors'], target['anchors']):
        assert control['anchor'] == treatment['anchor']
        result = analysis.paired_statistics(control['paired_outcomes']['overall_bb_per_hand'],
                                            treatment['paired_outcomes']['overall_bb_per_hand'])
        assert result['pairs'] == 2048
        saved = by_anchor[control['anchor']]
        assert result['delta_bb100'] == pytest.approx(saved['treatment_minus_control_bb100'], abs=1e-9)
        assert result['ci95_half_width'] == pytest.approx(saved['paired_ci95_bb100'], abs=1e-9)
