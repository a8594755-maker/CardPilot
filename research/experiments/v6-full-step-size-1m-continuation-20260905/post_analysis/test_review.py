import copy
import importlib.util
import json
from pathlib import Path

import pytest
import torch

spec = importlib.util.spec_from_file_location('lr_terminal_review', Path(__file__).with_name('review.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def maps():
    full, half = {}, {}
    for i, anchor in enumerate(('a', 'b', 'c', 'd')):
        for pair in range(2):
            key = (anchor, 10 + i, pair)
            # Only compare_arms is tested here; permutation validity belongs to raw_map.
            full[key] = {'deck': [i, pair], 'control_rewards_bb': [1., -1.], 'treatment_rewards_bb': [2., -2.]}
            half[key] = {'deck': [i, pair], 'control_rewards_bb': [1., -1.], 'treatment_rewards_bb': [3., -3.]}
    return full, half


def test_contrast_direction_and_paired_decks():
    full, half = maps()
    saved = copy.deepcopy((full, half))
    decks = set()
    out = r.compare_arms(full, half, decks)
    assert len(decks) == 8
    assert out['half_minus_full']['pooled']['ci95'] == [0., 0.]
    assert out['half_minus_full']['by_seat']['0']['bb100'] == 100.
    assert out['half_minus_full']['by_seat']['1']['bb100'] == -100.
    assert not out['broad_collapse']
    assert (full, half) == saved


@pytest.mark.parametrize('corruption', ['key', 'deck', 'parent', 'earlier_deck'])
def test_reject_bad_pairing(corruption):
    full, half = maps()
    key = next(iter(half))
    decks = set()
    if corruption == 'key':
        del half[key]
    elif corruption == 'deck':
        half[key]['deck'] = [99]
    elif corruption == 'parent':
        half[key]['control_rewards_bb'][0] = 2.
    else:
        decks.add(tuple(full[key]['deck']))
    with pytest.raises(ValueError):
        r.compare_arms(full, half, decks)


def checkpoint(physical, transition, no_decision, replay):
    return {'environment_hand_accounting': {'completed_hands': physical, 'no_trainable_decision_hands': no_decision},
            'total_hands': transition, 'ppo_replay_cumulative_rows': replay}


def test_physical_counters_not_replay_or_inherited_hands():
    out = r.counter_deltas(checkpoint(1000, 800, 195, 2000), checkpoint(1500, 1200, 285, 4000))
    assert out == {'new_physical_hands': 500, 'new_transition_hands': 400, 'new_no_decision_hands': 90,
                   'residual_worker_tail_hands': 10, 'new_replay_rows': 2000}


@pytest.mark.parametrize('bad', [(999, 801, 195, 2100), (1500, 800, 195, 2100),
                                (1500, 1300, 200, 2100), (1500, 1200, 285, 1999)])
def test_reject_invalid_accounting(bad):
    with pytest.raises(ValueError):
        r.counter_deltas(checkpoint(1000, 800, 195, 2000), checkpoint(*bad))


def optimizer(step):
    return {'optimizer': {'param_groups': [{'params': list(range(86)), 'lr': 5e-5}],
        'state': {i: {'step': torch.tensor(float(step + (7070 if i >= 76 else 0))),
            'exp_avg': torch.tensor([.1]), 'exp_avg_sq': torch.tensor([.2])} for i in range(86)}}}


def adam_fixture():
    parent, final = optimizer(800), optimizer(805)
    report = {'new_state_ids': [], 'per_parameter_steps': {str(i):
        {'before': int(parent['optimizer']['state'][i]['step']), 'after': int(final['optimizer']['state'][i]['step']),
         'delta': 5} for i in range(86)}}
    return parent, final, report


def test_realized_clocks_use_actual_parent_per_parameter():
    assert set(r.adam_steps(*adam_fixture(), 5e-5).values()) == {5}


@pytest.mark.parametrize('corruption', ['wrong_before', 'changed_lr', 'missing_state', 'reset_step'])
def test_reject_optimizer_report_corruption(corruption):
    parent, final, reported = adam_fixture()
    if corruption == 'wrong_before':
        reported['per_parameter_steps']['76']['before'] = 0
    elif corruption == 'changed_lr':
        final['optimizer']['param_groups'][0]['lr'] = 1e-4
    elif corruption == 'missing_state':
        del final['optimizer']['state'][0]
    else:
        final['optimizer']['state'][76]['step'].zero_()
    with pytest.raises(ValueError):
        r.adam_steps(parent, final, reported, 5e-5)


def test_terminal_review_rejects_live_owner_before_work(tmp_path, monkeypatch):
    (tmp_path / 'ownership.json').write_text(json.dumps({'pid': 12, 'create_time': 123}), encoding='utf-8')
    monkeypatch.setattr(r, 'live', lambda *_: True)
    with pytest.raises(ValueError, match='controller still live'):
        r.main(tmp_path)
    assert not (tmp_path / 'post_terminal_review.json').exists()


@pytest.mark.parametrize('affected', ['half', 'both'])
def test_severe_endpoint_regression_is_not_hidden_by_relative_tie(affected):
    full, half = maps()
    for row in half.values():
        row['treatment_rewards_bb'] = [-20., -20.]
    if affected == 'both':
        for row in full.values():
            row['treatment_rewards_bb'] = [-20., -20.]
    out = r.compare_arms(full, half, set())
    assert out['broad_collapse']
    if affected == 'both':
        assert out['half_minus_full']['pooled']['bb100'] == 0
