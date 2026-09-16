import json
import math
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_pilot as pilot
import review_finish as review


def row(anchor=0, mean=10, low=1):
    return dict(anchor=anchor, bb_per_100=mean, ci_adjusted=[low, 20])


def test_only_learning_coefficient_and_identity_change():
    original = json.loads((pilot.PARENT/'execution.json').read_text())['children'][0]['command'][1:]
    cmd = pilot.training_command()
    restored = [value.replace(str(pilot.BASE), str(pilot.PARENT)) for value in cmd]
    restored[restored.index('--source-policy-kl-coef')+1] = original[original.index('--source-policy-kl-coef')+1]
    restored[restored.index('--run-id')+1] = original[original.index('--run-id')+1]
    assert restored == original
    assert cmd[cmd.index('--source-policy-kl-coef')+1] == '0.1'
    for flag, expected in [('--seed', '20260918'), ('--worker-seed-base', '2026091800'),
                           ('--total-environment-hands', '262144'), ('--workers', '12')]:
        assert cmd[cmd.index(flag)+1] == expected
    assert '--reset-optimizer' in cmd and '--reset-hand-counter' in cmd
    start = cmd.index('--fixed-opponent-checkpoints')+1
    pool = []
    for value in cmd[start:]:
        if value.startswith('--'): break
        pool.append(Path(value).name)
    assert pool == ['anchor0.pt', 'anchor1.pt', 'anchor2.pt']
    assert not any('weak_control' in value for value in cmd)


def test_joint_gate_needs_heldout_and_retention():
    rows = [row(a, low=(1 if a in [0, 1, 3] else -1)) for a in range(5)]
    assert pilot.gate(rows, row())
    assert not pilot.gate(rows, row(low=-1))
    assert not pilot.gate([row(a, low=(1 if a < 3 else -1)) for a in range(5)], row())
    assert not pilot.gate([row(a, low=(1 if a > 0 else -1)) for a in range(5)], row())


def test_gate_all_source_points_positive():
    rows = [row(a) for a in range(5)]
    rows[4] = row(4, mean=-1, low=-2)
    assert not pilot.gate(rows, row())


def test_gate_rejects_wrong_family_and_nonfinite():
    with pytest.raises(ValueError): pilot.gate([row()] * 4, row())
    with pytest.raises(ValueError): pilot.gate([row()] * 5, row())
    with pytest.raises(ValueError): pilot.gate([row(a) for a in range(5)], row(mean=math.nan))


def test_statistics_and_six_contrast_adjustment():
    out = pilot.estimate([1, 3])
    assert out['bb_per_100'] == 2 and out['standard_error'] == 1
    assert out['ci95'] == pytest.approx([.04, 3.96])
    assert out['ci_adjusted'][0] < 2-2.5758293035489004
    assert pilot.estimate([0, 0])['ci_adjusted'] == [0, 0]


@pytest.mark.parametrize('values', [[], [1], [0, math.nan], [0, math.inf]])
def test_statistics_reject_bad_pairs(values):
    with pytest.raises(ValueError): pilot.estimate(values)


def test_only_newline_complete_rows_count(tmp_path):
    path = tmp_path/'pairs.jsonl'
    assert pilot.raw_count(path) == 0
    path.write_bytes(b'{}\n{"x":1}\n{"partial":')
    assert pilot.raw_count(path) == 2


def test_independent_review_arithmetic_agrees():
    values = [-103.25, 15.5, 90.125, 0, 23.75]
    actual, expected = review.interval(values), pilot.estimate(values)
    assert actual['bb_per_100'] == pytest.approx(expected['bb_per_100'])
    assert actual['ci95'] == pytest.approx(expected['ci95'])
    assert actual['ci_adjusted'] == pytest.approx(expected['ci_adjusted'])


def test_review_raw_pair_structure_and_reward_bounds():
    rows = [dict(pair_index=i, deck=list(range(52)), rewards_bb=[1, -1], decisions=[2, 2]) for i in range(8192)]
    assert review.raw_values(rows) == [0]*8192
    with pytest.raises(ValueError): review.raw_values(rows[:-1])
    rows[0] = dict(rows[0], rewards_bb=[200.01, -200.01])
    with pytest.raises(AssertionError): review.raw_values(rows)
