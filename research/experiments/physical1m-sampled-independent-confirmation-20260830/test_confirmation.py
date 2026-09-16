import copy
import importlib.util
import math
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('confirmation', Path(__file__).with_name('run_confirmation.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def cell():
    return dict(seed=m.SEED, pairs=2, starting_stack=200.0, policy_mode=m.MODE, action_rng_schema=m.RNG,
                candidate={'sha256': 'candidate'}, execution={'status': 'COMPLETED'},
                anchors=[dict(anchor=name, anchor_sha256=digest, pairs=2, hands=4, candidate_bb100=0,
                              action_rng={'schema': m.RNG, 'seed': m.SEED+i*1000003},
                              paired_outcomes={'overall_bb_per_hand': [0., 0.],
                                               'bb_bb_per_hand': [1., 2.], 'sb_bb_per_hand': [-1., -2.]})
                         for i, (name, _, digest) in enumerate(m.ANCHORS)])


def test_complete_valid_cell():
    assert m.validate_cell(cell(), {'status': 'COMPLETED'}, 'candidate', pairs=2) == 12


@pytest.mark.parametrize('kind', ['seed', 'rng', 'identity', 'count', 'raw', 'score', 'status'])
def test_bad_evidence_rejected(kind):
    doc = copy.deepcopy(cell())
    if kind == 'seed': doc['seed'] += 1
    if kind == 'rng': doc['anchors'][1]['action_rng']['seed'] += 1
    if kind == 'identity': doc['candidate']['sha256'] = 'changed'
    if kind == 'count': doc['anchors'][0]['hands'] -= 1
    if kind == 'raw': doc['anchors'][0]['paired_outcomes']['overall_bb_per_hand'][0] = float('nan')
    if kind == 'score': doc['anchors'][0]['candidate_bb100'] = 1
    if kind == 'status': doc['execution']['status'] = 'RUNNING'
    with pytest.raises(ValueError): m.validate_cell(doc, {'status': 'COMPLETED'}, 'candidate', pairs=2)


def test_paired_statistics_and_multiplicity():
    stats = m.paired_stats([0, 0, 0], [1, 2, 3])
    assert stats['delta_bb100'] == 200
    assert stats['ci95_half_width'] == pytest.approx(1.96*100/math.sqrt(3))
    assert stats['bonferroni98p333_lower'] < stats['ci95_lower']
    assert stats['bonferroni98p333_upper'] > stats['ci95_upper']


def test_self_control_zero_ci():
    stats = m.paired_stats([1, -200, 200], [1, -200, 200])
    assert stats['delta_bb100'] == stats['ci95_half_width'] == stats['bonferroni98p333_lower'] == 0


def test_gate_nominal_and_adjusted_are_distinct():
    rows = [dict(ood_valid=True, delta_bb100=1, ci95_lower=0.1, bonferroni98p333_lower=-0.1) for _ in range(3)]
    assert m.classify(rows)['nominal_replication_gate']
    assert not m.classify(rows)['multiplicity_adjusted_secondary_gate']
    rows[0]['delta_bb100'] = -1
    assert not m.classify(rows)['nominal_replication_gate']


def test_all_three_valid_anchors_required():
    rows = [dict(ood_valid=True, delta_bb100=1, ci95_lower=0.1, bonferroni98p333_lower=0.01) for _ in range(3)]
    assert m.classify(rows)['multiplicity_adjusted_secondary_gate']
    rows[0]['ood_valid'] = False
    assert not m.classify(rows)['nominal_replication_gate']
    assert not m.classify(rows[1:])['nominal_replication_gate']


def test_parent_shell_is_not_a_duplicate_evaluator():
    info = dict(pid=5, name='powershell.exe', cmdline=['powershell', '-Command',
                f'python research/experiments/{m.ID}/run_confirmation.py'])
    assert not m.is_other_evaluation_process(info, own_pid=6)
    info['name'] = 'python.exe'
    assert m.is_other_evaluation_process(info, own_pid=6)
    assert not m.is_other_evaluation_process(info, own_pid=5)
