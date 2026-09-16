import importlib.util
from pathlib import Path
import statistics

import pytest

spec = importlib.util.spec_from_file_location('phase_external_review_tests', Path(__file__).with_name('review_completed.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_live_owner_blocks_before_any_outcomes(monkeypatch):
    reads = []
    def read(path):
        reads.append(path.name)
        assert path.name == 'execution.json'
        return {'pid': 123, 'create_time': 456}
    monkeypatch.setattr(m.r, 'read', read)
    monkeypatch.setattr(m.r, 'live_identity', lambda row: True)
    assert m.readiness()['ready'] is False
    assert reads == ['execution.json']


def test_integer_moments_matches_independent_statistics():
    values = [-20000, -100, 0, 50, 1200, 20000]
    result = m.integer_moments(values)
    assert result['bb_per_100'] == statistics.mean(values)
    assert result['variance_chips2'] == pytest.approx(statistics.variance(values))
    assert result['sum_chips'] == sum(values)


@pytest.mark.parametrize('values', [[0], [0, float('nan')], [0, 20001], [True, 0]])
def test_moments_rejects_invalid_physical_chips(values):
    with pytest.raises(ValueError):
        m.integer_moments(values)
