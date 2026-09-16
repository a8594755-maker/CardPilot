import copy
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_continuation as run


@pytest.mark.parametrize('seed', [1, 3])
@pytest.mark.parametrize('stage', [1, 2])
def test_matched_commands(seed, stage):
    args = [run.training_command(seed, arm, stage, 'parent.pt', run.INITIAL_PHYSICAL[seed]) for arm in ('full', 'half')]
    for argv in args:
        for key in ('--run-dir', '--out', '--opponent-assignment-provenance-file'):
            argv[argv.index(key) + 1] = 'CELL'
        assert '--all-policy-heads-only-training' not in argv
        assert '--no-reset-optimizer' in argv and '--preserve-resumed-optimizer-lr' in argv
        assert '--reset-hand-counter' not in argv and '--reset-optimizer' not in argv
        assert argv[argv.index('--total-environment-hands') + 1] == str(run.INITIAL_PHYSICAL[seed] + run.DOSES[stage])
        assert argv[argv.index('--mini-batch-size') + 1] == '16384'
        assert argv[argv.index('--source-policy-reference-checkpoint') + 1] == str(run.HELPER.STANDARD)
    assert args[0] == args[1]


@pytest.mark.parametrize('seed', [1, 3])
@pytest.mark.parametrize('arm', ['full', 'half'])
def test_parent_lineage_and_no_old8m(seed, arm):
    parent = run.parent_path(seed, arm, 1)
    assert parent == (run.PARENTS[seed] if arm == 'full' else run.QUAL / f'derived/seed{seed}_half.pt')
    assert run.parent_path(seed, arm, 2) == run.directory(seed, arm, 1) / 'latest.pt'
    assert run.prior.BASE == run.PREVIOUS
    assert run.prior.INITIAL_PHYSICAL == run.INITIAL_PHYSICAL


@pytest.mark.parametrize('seed', [1, 3])
@pytest.mark.parametrize('stage', [1, 2])
def test_fresh_eval_seed_and_matched_parent(seed, stage):
    args = [run.evaluate_command(seed, arm, stage) for arm in ('full', 'half')]
    for argv in args:
        assert argv[argv.index('--seed') + 1] == str(20263900 + seed * 10 + stage)
        assert argv[argv.index('--control') + 1] == str(run.PARENTS[seed])
        assert argv[argv.index('--pairs-per-anchor') + 1] == '2048'
        for key in ('--treatment', '--out-dir'):
            argv[argv.index(key) + 1] = 'CELL'
    assert args[0] == args[1]


def summary(high=0):
    return {'by_anchor': {a: {'ci95_high_bb100': high} for a in run.execution.ANCHORS},
            'by_seat': {str(s): {'ci95_high_bb100': high} for s in (0, 1)}}


@pytest.mark.parametrize('where', ['contrast', 'full', 'half'])
def test_severe_gate_checks_each_route(where):
    contrast, endpoints = summary(), {'full': summary(), 'half': summary()}
    assert not run.collapse_gate(contrast, endpoints)
    if where == 'contrast':
        contrast = summary(-26)
    else:
        endpoints[where] = summary(-26)
    assert run.collapse_gate(contrast, endpoints)


def optimizer(step, lr):
    return {'optimizer': {'param_groups': [{'params': list(range(86)), 'lr': lr}],
        'state': {i: {'step': torch.tensor(float(step + (7070 if i >= 76 else 0))),
            'exp_avg': torch.tensor([.1]), 'exp_avg_sq': torch.tensor([.2])} for i in range(86)}}}


@pytest.mark.parametrize('lr', [9.999999999999996e-05, 4.999999999999998e-05])
def test_real_scope_individual_adam_clocks(lr):
    parent, final = optimizer(846, lr), optimizer(847, lr)
    result = run.prior.optimizer_step_audit(parent, final, True)
    assert not result['new_state_ids']
    assert all(row['delta'] == 1 for row in result['per_parameter_steps'].values())


@pytest.mark.parametrize('problem', ['reset', 'lr', 'missing'])
def test_reject_final_corruption(problem):
    parent, final = optimizer(846, 5e-5), optimizer(847, 5e-5)
    if problem == 'reset':
        final['optimizer']['state'][76]['step'].zero_()
    elif problem == 'lr':
        final['optimizer']['param_groups'][0]['lr'] = 1e-4
    else:
        del final['optimizer']['state'][0]
    with pytest.raises(ValueError):
        run.prior.optimizer_step_audit(parent, final, True)


def test_orders_and_log_owner():
    assert run.ORDERS[1] == ((1, 'full'), (1, 'half'), (3, 'half'), (3, 'full'))
    assert run.ORDERS[2] == ((3, 'full'), (3, 'half'), (1, 'half'), (1, 'full'))
    assert run.execution.logger_update is run.logger
