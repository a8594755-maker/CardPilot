import copy

import pytest
import torch

import run_pilot as run


@pytest.mark.parametrize('seed', [1, 3])
@pytest.mark.parametrize('stage', [1, 2])
def test_matched_commands(seed, stage):
    full = run.training_command(seed, 'full', stage, 'parent.pt', 8000000, 16384)
    heads = run.training_command(seed, 'heads', stage, 'parent.pt', 8000000, 16384)
    heads.remove('--all-policy-heads-only-training')
    for key in ('--run-dir', '--out', '--opponent-assignment-provenance-file'):
        full[full.index(key) + 1] = heads[heads.index(key) + 1] = 'CELL'
    assert full == heads
    assert '--no-reset-optimizer' in full and '--preserve-resumed-optimizer-lr' in full
    assert full[full.index('--total-environment-hands') + 1] == str(run.INITIAL_PHYSICAL[seed] + run.DOSES[stage])
    assert full[full.index('--worker-seed-base') + 1] == str(2026300000 + seed * 100)
    assert full[full.index('--source-policy-reference-checkpoint') + 1] == str(run.HELPER.STANDARD)


def optimizer(full, initial=False):
    ids = range(86) if full else range(10)
    states = range(76, 86) if full and initial else ids
    return {'optimizer': {'param_groups': [{'params': list(ids), 'lr': 1e-4}],
            'state': {i: {'step': torch.tensor(7070. if initial else (1. if full and i < 76 else 7071.)),
                         'exp_avg': torch.tensor([0.1]), 'exp_avg_sq': torch.tensor([0.2])} for i in states}}}


@pytest.mark.parametrize('full', [False, True])
def test_steps_use_each_parameters_own_history(full):
    result = run.optimizer_step_audit(optimizer(full, True), optimizer(full), full)
    assert result['passed']
    if full:
        assert result['new_state_ids'] == list(range(76))
        assert result['per_parameter_steps']['0'] == {'before': 0, 'after': 1, 'delta': 1}
        assert result['per_parameter_steps']['76']['before'] == 7070


@pytest.mark.parametrize('problem', ['reset', 'nonfinite', 'scope', 'lr', 'missing'])
def test_optimizer_corruption_rejected(problem):
    parent, final = optimizer(True, True), optimizer(True)
    if problem == 'reset':
        final['optimizer']['state'][76]['step'] = torch.tensor(1.)
    elif problem == 'nonfinite':
        final['optimizer']['state'][2]['exp_avg'][0] = float('nan')
    elif problem == 'scope':
        final['optimizer']['param_groups'][0]['params'].pop()
    elif problem == 'lr':
        final['optimizer']['param_groups'][0]['lr'] = .0003
    else:
        del final['optimizer']['state'][0]
    with pytest.raises(ValueError):
        run.optimizer_step_audit(parent, final, True)


def pool_fixture():
    pool = run.evidence.module_at('pool_fixture_loader', run.execution.POOL_HELPER)
    history, active, states = [], [], {}
    for key in range(9):
        iteration = 0 if key < 3 else 2 * (key - 2)
        loss = -1000. if key < 3 else -1000. - key
        row = {'id': key, 'hands': iteration * 10, 'iteration': iteration,
               'pool_strategy': 'loss-kbest', 'selection_loss': loss, 'selection_score': -loss,
               'score_components': {'policy_loss': loss, 'value_loss': 0, 'formula': 'fixture'}}
        active.append(pool.metadata(row))
        active.sort(key=lambda r: (r['selection_score'], r['hands'], r['id']), reverse=True)
        active = active[:5]
        row.update(selected=key in [r['id'] for r in active], active_ids_after=[r['id'] for r in active])
        history.append(row)
        states[iteration] = {'iteration': iteration, 'snapshot_every': 2, 'history_limit': 3,
                            'run_id': 'test', 'strategy': 'loss-kbest',
                            'history': copy.deepcopy(history[-3:]), 'active': copy.deepcopy(active)}
    metrics = [{'iteration': i, 'hands': 10 * i} for i in range(1, 13)]
    assignments = []
    for i in range(1, 13):
        state = states[max(k for k in states if k < i)]
        assignments.append({'applies_to_iteration': i, 'pool_snapshot_refs': [
            {'local_index': j, 'snapshot_hands': r['hands'], 'snapshot_id': r['id'],
             'snapshot_iteration': r['iteration']} for j, r in enumerate(state['active'])]})
    return [states[i] for i in (4, 8, 12)], metrics, assignments


def test_pool_legitimate_anchor_eviction_is_not_algorithm_failure():
    result = run.pool_audit(*pool_fixture())
    assert result['passed'] and result['anchor_retention_checks_missing'] > 0
    assert result['final_active_ids'] == [8, 7, 6, 5, 4]


@pytest.mark.parametrize('problem', ['score', 'assignment', 'archive'])
def test_pool_replay_still_rejects_corruption(problem):
    windows, metrics, assignments = pool_fixture()
    if problem == 'score':
        windows[-1]['history'][-1]['selection_loss'] += .1
    elif problem == 'assignment':
        assignments[-1]['pool_snapshot_refs'][0]['snapshot_id'] = 999
    else:
        windows[-1]['active'][-1]['hands'] += 1
    with pytest.raises(ValueError):
        run.pool_audit(windows, metrics, assignments)


def initial_parent():
    result = {key: {'fixture': 1} for key in run.INITIAL_KEYS}
    result.update(total_hands=100, iteration=10, ppo_replay_cumulative_rows=200,
                  main_process_rng_state={'torch_cuda': [torch.tensor([1])]},
                  all_policy_heads_only_training=False,
                  environment_hand_accounting={'completed_hands': 120},
                  moving_source_policy_reference=None,
                  config={'source_policy_reference_refresh_updates': 0,
                          'source_policy_reference_checkpoint': str(run.HELPER.STANDARD)})
    return result


def test_initial_exact_and_missing_state_fails():
    parent = initial_parent()
    run.initial_audit(parent, copy.deepcopy(parent), True)
    for key in ('optimizer', 'ppo_replay_rng_state', 'total_hands', 'main_process_rng_state'):
        bad = copy.deepcopy(parent)
        bad[key] = -1
        with pytest.raises((ValueError, AttributeError, TypeError)):
            run.initial_audit(parent, bad, True)


def test_fixed_cell_order_and_no_early_zero_score_promotion():
    assert run.ORDERS[1] == ((1, 'full'), (1, 'heads'), (3, 'heads'), (3, 'full'))
    summary = {'by_anchor': {a: {'ci95_high_bb100': 0} for a in run.execution.ANCHORS},
               'by_seat': {'0': {'ci95_high_bb100': 0}, '1': {'ci95_high_bb100': 0}}}
    assert not run.evidence.broad_collapse(summary)
