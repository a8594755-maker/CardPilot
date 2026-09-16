import copy
import importlib.util
from pathlib import Path
import sys

import pytest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import run_pilot as run
import evaluate as evaluation


def values(command):
    return {key: command[i+1] for i, key in enumerate(command[:-1]) if key.startswith('--') and not command[i+1].startswith('--')}


def test_arms_differ_only_in_source_kl_and_output_identity():
    control, weak = values(run.make_command('control')), values(run.make_command('weak'))
    allowed = {'--source-policy-kl-coef', '--run-id', '--run-dir', '--out', '--opponent-assignment-provenance-file'}
    assert {key for key in control if control[key] != weak[key]} == allowed
    assert control['--mini-batch-size'] == weak['--mini-batch-size'] == '1024'
    assert control['--lr'] == weak['--lr'] == '0.00003'
    assert control['--source-policy-kl-coef'] == '1' and weak['--source-policy-kl-coef'] == '0.01'
    for config in [control, weak]:
        assert config['--hands-per-iter'] == '4096'
        assert config['--total-environment-hands'] == '262144'
        assert config['--seed'] == '20260907'
    assert '--reset-optimizer' in run.make_command('control')
    assert '--reset-optimizer' in run.make_command('weak')


def fixture():
    return dict(seed=evaluation.SEED, pairs=2, policy_mode=evaluation.MODE, action_rng_schema=evaluation.RNG,
        starting_stack=200., candidate={'sha256': 'candidate'}, execution={'status': 'COMPLETED'},
        anchors=[dict(anchor=name, anchor_sha256=run.DIGESTS[i], action_rng=dict(seed=evaluation.SEED+i*1000003, schema=evaluation.RNG),
                      pairs=2, hands=4, candidate_bb100=0., anchor_ood_valid=True,
                      paired_outcomes=dict(overall_bb_per_hand=[0., 0.], bb_bb_per_hand=[1., 2.], sb_bb_per_hand=[-1., -2.]))
                 for i, name in enumerate(evaluation.NAMES)])


def test_valid_raw_cell_and_zero_self_difference():
    doc = fixture()
    assert evaluation.validate(doc, {'status': 'COMPLETED'}, 'candidate', pairs=2) == 12
    for row in evaluation.compare(doc, doc):
        assert row['delta_bb100'] == row['ci95_half_width'] == 0


@pytest.mark.parametrize('kind', ['seed', 'rng', 'raw', 'count', 'identity'])
def test_rejects_misaligned_evidence(kind):
    doc = copy.deepcopy(fixture())
    if kind == 'seed': doc['seed'] += 1
    if kind == 'rng': doc['anchors'][0]['action_rng']['seed'] += 1
    if kind == 'raw': doc['anchors'][0]['paired_outcomes']['overall_bb_per_hand'][0] = float('inf')
    if kind == 'count': doc['anchors'][0]['hands'] = 3
    if kind == 'identity': doc['candidate']['sha256'] = 'other'
    with pytest.raises(ValueError): evaluation.validate(doc, {'status': 'COMPLETED'}, 'candidate', pairs=2)


def test_admission_requires_primary_gain_and_no_negative_source_points():
    rows = [dict(delta_bb100=1, ci95_lower=.1, bonferroni_lower=.01, ood_valid=True) for _ in range(3)]
    assert evaluation.admission(rows, rows)
    worse = copy.deepcopy(rows)
    worse[0]['delta_bb100'] = -.01
    assert not evaluation.admission(rows, worse)
    assert not evaluation.admission(worse, rows)
    flat = copy.deepcopy(rows)
    for row in flat: row['bonferroni_lower'] = -.1
    assert not evaluation.admission(flat, rows)
