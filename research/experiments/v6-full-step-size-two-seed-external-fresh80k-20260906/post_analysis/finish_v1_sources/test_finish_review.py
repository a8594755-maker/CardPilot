import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('four_policy_finish_tests', Path(__file__).with_name('finish_review.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def decision():
    return {'post_terminal_review_sha256': 'review_sha', 'result_summary_sha256': 'summary_sha',
            'goal_achieved': False, **{k: 'Substantive synthetic research reasoning only.'
             for k in ('summary', 'conclusion', 'decision', 'next_step')}}


def test_bound_substantive_decision_admitted():
    m.validate_decision(decision(), 'review_sha', 'summary_sha')


@pytest.mark.parametrize('fault', ['review', 'summary_sha', 'goal', 'summary', 'conclusion', 'decision', 'next_step'])
def test_wrong_or_missing_decision_refused(fault):
    value = decision()
    if fault == 'review': value['post_terminal_review_sha256'] = 'another'
    elif fault == 'summary_sha': value['result_summary_sha256'] = 'another'
    elif fault == 'goal': value['goal_achieved'] = True
    else: value[fault] = ''
    with pytest.raises(ValueError):
        m.validate_decision(value, 'review_sha', 'summary_sha')


def test_live_owner_cannot_trigger_any_logger_or_outcome_read(monkeypatch):
    monkeypatch.setattr(m.review, 'readiness', lambda: {'ready': False})
    monkeypatch.setattr(m.review.r, 'read', lambda path: pytest.fail('outcome read before terminal gate'))
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **k: pytest.fail('logger called before terminal gate'))
    with pytest.raises(ValueError, match='not ready'):
        m.finish()
