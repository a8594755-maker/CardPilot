import importlib.util
from pathlib import Path
import statistics

import pytest

spec = importlib.util.spec_from_file_location('seed3_external_review_tests', Path(__file__).with_name('review_completed.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def execution():
    return {'pid': 123, 'create_time': 456, 'status': 'COMPLETED_PENDING_REVIEW',
        'children': [{'pid': 200 + i, 'create_time': 456, 'exit_code': 0} for i in range(37)],
        'evaluation_hands': 80000, 'slumbot_hands': 80000,
        'waves': [{'finished_at': '2026-09-05T15:00:00+00:00'} for _ in range(4)]}


def test_live_owner_blocks_before_any_outcomes(monkeypatch):
    reads = []
    def read(path):
        reads.append(path.name)
        assert path.name == 'execution.json'
        return {'pid': 123, 'create_time': 456}
    monkeypatch.setattr(m.r, 'read', read)
    monkeypatch.setattr(m.r, 'live_identity', lambda row: True)
    assert m.readiness()['ready'] is False
    with pytest.raises(ValueError, match='not ready'):
        m.build_report()
    assert reads == ['execution.json', 'execution.json']


def test_live_child_blocks(monkeypatch):
    monkeypatch.setattr(m.r, 'read', lambda path: execution())
    monkeypatch.setattr(m.r, 'live_identity', lambda row: row['pid'] == 200)
    assert m.readiness()['ready'] is False


def test_failed_execution_blocks(monkeypatch):
    value = execution()
    value['status'] = 'FAILED_PRESERVED'
    monkeypatch.setattr(m.r, 'read', lambda path: value)
    monkeypatch.setattr(m.r, 'live_identity', lambda row: False)
    assert m.readiness()['ready'] is False


@pytest.mark.parametrize('bad', ['jobs', 'exit', 'hands', 'slumbot', 'waves', 'wave_end'])
def test_incomplete_evidence_rejected(monkeypatch, bad):
    value = execution()
    if bad == 'jobs':
        value['children'].pop()
    elif bad == 'exit':
        value['children'][0]['exit_code'] = 1
    elif bad == 'hands':
        value['evaluation_hands'] -= 1
    elif bad == 'slumbot':
        value['slumbot_hands'] -= 1
    elif bad == 'waves':
        value['waves'].pop()
    else:
        value['waves'][0]['finished_at'] = None
    monkeypatch.setattr(m.r, 'read', lambda path: value)
    monkeypatch.setattr(m.r, 'live_identity', lambda row: False)
    with pytest.raises(ValueError):
        m.readiness()


def test_exact_terminal_evidence_ready(monkeypatch):
    monkeypatch.setattr(m.r, 'read', lambda path: execution())
    monkeypatch.setattr(m.r, 'live_identity', lambda row: False)
    assert m.readiness() == {'ready': True}


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


def test_weighted_contrast_equals_two_sample_welch():
    treatment, control = [1, 5, 9, 12], [-3, 2, 8]
    result = m.weighted_independent_means([treatment, control], [1, -1])
    expected = m.r.protocol.welch(treatment, control)
    for key in ('bb_per_100', 'standard_error', 'degrees_of_freedom', 'ci'):
        assert result[key] == pytest.approx(expected[key])


def test_equal_seed_mean_uses_both_uncertainties():
    a, b = [0, 20, 40], [100, 140, 200, 300]
    result = m.weighted_independent_means([a, b], [.5, .5])
    assert result['bb_per_100'] == pytest.approx(.5 * statistics.mean(a) + .5 * statistics.mean(b))
    expected_variance = .25 * (statistics.variance(a) / len(a) + statistics.variance(b) / len(b))
    assert result['standard_error'] ** 2 == pytest.approx(expected_variance)
    adjusted = m.weighted_independent_means([a, b], [.5, .5], 1 - .05 / 3)
    assert adjusted['ci'][0] < result['ci'][0] < result['ci'][1] < adjusted['ci'][1]


def test_empirical_zero_variance_is_explicit():
    result = m.weighted_independent_means([[1, 1], [2, 2]], [.5, .5])
    assert result['empirical_zero_variance'] is True
    assert result['degrees_of_freedom'] is None


@pytest.mark.parametrize('samples,weights,confidence', [([], [], .95), ([[1, 2]], [], .95),
    ([[1, 2]], [float('nan')], .95), ([[1, 2]], [True], .95), ([[1, 2]], [0], .95),
    ([[1]], [1], .95), ([[1, 2]], [1], 1)])
def test_invalid_weighted_contrast_rejected(samples, weights, confidence):
    with pytest.raises(ValueError):
        m.weighted_independent_means(samples, weights, confidence)


def test_synthesis_preserves_scope_and_balanced_wave_covariance():
    groups = {seed: {arm: [[100 * wave + shift + (j % 3) for j in range(2500)]
        for wave in range(4) for _ in range(4)] for arm, shift in (('static', offset), ('moving256', offset + 7))}
        for seed, offset in (('seed1', -40), ('seed3', 20))}
    result = m.synthesis(groups)
    assert result['training_seed_population_interval'] is False
    assert result['not_confirmatory_alpha_guarantees'] is True
    assert result['final_qualification_hands'] == 0
    for unit in result['conditional_equal_seed_sampling_intervals'].values():
        assert unit['moving_minus_static']['nominal']['bb_per_100'] == pytest.approx(7)
    wave = result['conditional_equal_seed_sampling_intervals']['balanced_wave_means']
    assert wave['moving_minus_static']['nominal']['empirical_zero_variance'] is True
    assert wave['static_absolute']['nominal']['standard_error'] > 0
    with pytest.raises(ValueError):
        m.synthesis({'seed1': groups['seed1']})
