import importlib.util
from pathlib import Path
from scipy.stats import ttest_ind
import pytest

spec = importlib.util.spec_from_file_location('parent_transfer_tested', Path(__file__).with_name('compare_parent_transfer.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def moments(values):
    return dict(hands=len(values), sum_chips=sum(values), sum_squared_chips=sum(v*v for v in values))


@pytest.mark.parametrize('a,b', [([1,2,9,20], [-8,-3,4,8,10]),
    ([-20000,20000,0], [100,1000,200]), ([5]*8, [1,2,3,4,5])])
def test_moment_welch_matches_scipy_raw_samples(a,b):
    result = m.moment_welch(moments(a), moments(b))
    ci = ttest_ind(a,b,equal_var=False).confidence_interval()
    assert result['ci95'] == pytest.approx([ci.low,ci.high])
    assert result['exploratory_historical_not_contemporaneous']


@pytest.mark.parametrize('value', [dict(hands=1,sum_chips=0,sum_squared_chips=0),
    dict(hands=True,sum_chips=0,sum_squared_chips=0),
    dict(hands=2,sum_chips=100,sum_squared_chips=0),
    dict(hands=2,sum_chips=0,sum_squared_chips=800000001)])
def test_invalid_moments_rejected(value):
    with pytest.raises(ValueError): m.mean_variance(value)


def test_live_controller_blocks_before_current_outcomes(monkeypatch):
    monkeypatch.setattr(m.review,'readiness',lambda:{'ready':False})
    monkeypatch.setattr(m.r,'read',lambda p:pytest.fail('must not read outcomes or followthrough yet'))
    with pytest.raises(ValueError,match='not terminal'): m.terminal_guard()


def test_live_followthrough_blocks_before_report(monkeypatch):
    monkeypatch.setattr(m.review,'readiness',lambda:{'ready':True})
    def read(p):
        assert p.name == 'followthrough_execution.json'
        return dict(pid=58116,create_time=1788709462.2370713)
    monkeypatch.setattr(m.r,'read',read)
    monkeypatch.setattr(m.r,'live_identity',lambda p:True)
    with pytest.raises(ValueError,match='still live'): m.terminal_guard()


def test_zero_variance_explicit_not_success():
    value = m.moment_welch(moments([5]*8),moments([1]*8))
    assert value['empirical_zero_variance'] and value['degrees_of_freedom'] is None
    assert value['family_adjusted'] is False
