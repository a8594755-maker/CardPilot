import math
from pathlib import Path
import statistics
import pytest
import curve_contract as contract
import run_curve as run


def test_training_command_preserves_qualified_control_learning_settings():
    old = next(r for r in run.read(run.PARENT/'execution.json')['children'] if r['role'] == 'train_control3')['command'][1:]
    cmd = run.training_command()
    changed = {'--total-environment-hands', '--run-id', '--run-dir', '--out',
               '--opponent-assignment-provenance-file', '--seed', '--worker-seed-base', '--max-runtime-seconds'}
    normalized = [v.replace(str(run.PARENT), str(run.BASE)) for v in old]
    for flag in changed: normalized[normalized.index(flag)+1] = cmd[cmd.index(flag)+1]
    assert normalized == cmd
    expected = {'--total-environment-hands': '1048576', '--seed': '20260930', '--worker-seed-base': '2026093000',
                '--rollout-mode': 'multi', '--rollout-envs-per-worker': '8', '--workers': '12',
                '--source-policy-kl-coef': '.01', '--self-play-fraction': '.25', '--max-runtime-seconds': '7200',
                '--resume': str(run.SOURCE), '--out': str(run.BASE/'production/latest.pt')}
    for flag, value in expected.items(): assert cmd[cmd.index(flag)+1] == value
    assert all(f in cmd for f in ['--reset-optimizer', '--reset-hand-counter', '--validate-stream', '--v6-rebind-legacy-weights'])
    start = cmd.index('--fixed-opponent-checkpoints')+1
    end = next(i for i in range(start, len(cmd)) if cmd[i].startswith('--'))
    assert [Path(v).name for v in cmd[start:end]] == ['anchor0.pt', 'anchor1.pt', 'anchor2.pt']
    assert not any('control3.pt' in v or 'diverse5.pt' in v for v in cmd)


def rows():
    return [dict(iteration=i, environment_hand_accounting=dict(completed_hands=i*50000)) for i in range(1, 23)]


def test_selection_is_first_scheduled_counter_crossing():
    r = rows()
    result = contract.choose_curve(r, {i: None for i in [4, 8, 12, 16, 20]})
    assert result['mid262']['iteration'] == 8 and result['mid524']['iteration'] == 12


@pytest.mark.parametrize('kind', ['missing_iteration', 'nonmonotonic', 'missing_archive', 'extra_archive', 'no_crossing'])
def test_selection_rejects_incomplete_evidence(kind):
    r, archives = rows(), {i: None for i in [4, 8, 12, 16, 20]}
    if kind == 'missing_iteration': r.pop(2)
    if kind == 'nonmonotonic': r[4]['environment_hand_accounting']['completed_hands'] = 100
    if kind == 'missing_archive': archives.pop(8)
    if kind == 'extra_archive': archives[21] = None
    if kind == 'no_crossing':
        r = r[:4]
        archives = {4: None}
    with pytest.raises(ValueError): contract.choose_curve(r, archives)


def row(anchor=0, mean=5, low=1): return dict(anchor=anchor, bb_per_100=mean, ci_adjusted=[low, 10])


def test_joint_gate_requires_growth_breadth_source_and_heldout():
    valid = [row(a, low=1 if a in [0, 1, 3] else -1) for a in range(5)]
    assert contract.gate(valid, row())
    assert not contract.gate(valid, row(low=0))
    assert not contract.gate([row(a, low=1 if a < 3 else -1) for a in range(5)], row())
    assert not contract.gate([row(a, mean=-1 if a == 4 else 5) for a in range(5)], row())
    assert not contract.gate([row(a, low=-1 if a == 0 else 1) for a in range(5)], row())
    with pytest.raises(ValueError): contract.gate(valid[:-1], row())
    with pytest.raises(ValueError): contract.gate(valid, row(mean=math.nan))


@pytest.mark.parametrize('values', [[], [1], [0, math.nan], [math.inf, 1]])
def test_statistics_fail_closed(values):
    with pytest.raises(ValueError): contract.estimate(values)


def test_units_family_and_fixed_hand_budget(tmp_path):
    result = contract.estimate([1, 3])
    z = statistics.NormalDist().inv_cdf((1+(1-.05/6))/2)
    assert result['bb_per_100'] == 2 and result['standard_error'] == 1
    assert result['ci95'] == pytest.approx([.04, 3.96])
    assert result['ci_adjusted'] == pytest.approx([2-z, 2+z])
    path = tmp_path/'raw.jsonl'
    path.write_bytes(b'{}\n{}\n{"partial":')
    assert contract.raw_count(path) == 2 and contract.raw_count(tmp_path/'missing') == 0
    assert contract.EVAL_HANDS == 327680 and contract.EVAL_SEED == 20261001


def test_independent_arithmetic_agrees():
    from review_finish import independent_interval
    values = [-925.25, 0, 885.125, 319.5, -122]
    a, b = contract.estimate(values), independent_interval(values)
    assert a['bb_per_100'] == pytest.approx(b['bb_per_100'])
    assert a['ci_adjusted'] == pytest.approx(b['ci_adjusted'])
