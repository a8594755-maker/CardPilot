import copy
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('pool_windows', Path(__file__).with_name('audit_pool_history_windows.py'))
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def fixture(limit=3):
    history, active, states = [], [], {}
    for key in range(9):
        iteration = 0 if key < 3 else 2 * (key - 2)
        loss = -1000.0 if key < 3 else 1 / (key + 1)
        row = {'id': key, 'hands': iteration * 10, 'iteration': iteration,
               'pool_strategy': 'loss-kbest', 'selection_loss': loss,
               'selection_score': -loss, 'score_components': {'policy_loss': loss,
                   'value_loss': 0, 'formula': 'policy_loss + 0.5*log1p(value_loss)'}}
        active.append(audit.metadata(row))
        active.sort(key=lambda item: (item['selection_score'], item['hands'], item['id']), reverse=True)
        active = active[:5]
        row.update(selected=key in [item['id'] for item in active],
                   active_ids_after=[item['id'] for item in active])
        history.append(row)
        states[iteration] = {'iteration': iteration, 'snapshot_every': 2,
            'history_limit': limit, 'run_id': 'test', 'strategy': 'loss-kbest',
            'history': copy.deepcopy(history[-limit:]), 'active': copy.deepcopy(active)}
    metrics = [{'iteration': i, 'hands': 10 * i} for i in range(1, 13)]
    assignments = []
    for i in range(1, 13):
        state = states[max(key for key in states if key < i)]
        refs = [{'local_index': index, 'snapshot_hands': row['hands'],
                 'snapshot_id': row['id'], 'snapshot_iteration': row['iteration']}
                for index, row in enumerate(state['active'])]
        assignments.append({'applies_to_iteration': i, 'pool_snapshot_refs': refs})
    return [states[i] for i in (4, 8, 12)], metrics, assignments


def test_capped_final_history_reconstructed_without_weakening_selection():
    result = audit.verify_windows(*fixture())
    assert result['passed']
    assert result['new_candidates_reconstructed'] == 4
    assert result['new_candidates_retained_in_final'] == 3
    assert result['new_candidates_evicted_from_final'] == 1
    assert result['verified_suffix_assignments'] == 8
    assert result['final_active_ids'] == [2, 1, 0, 8, 7]


def test_uncapped_history_also_supported():
    windows, metrics, assignments = fixture(limit=20)
    assert audit.verify_windows([windows[0], windows[-1]], metrics, assignments)['passed']


def test_missing_archive_does_not_invent_evicted_candidates():
    windows, metrics, assignments = fixture()
    with pytest.raises(ValueError, match='missing or extra'):
        audit.verify_windows([windows[0], windows[-1]], metrics, assignments)


@pytest.mark.parametrize('mutation', ['overlap', 'score', 'selected', 'active_ids',
                                    'assignment', 'checkpoint', 'cadence', 'metric', 'nonfinite'])
def test_rejects_corrupted_or_inconsistent_evidence(mutation):
    windows, metrics, assignments = fixture()
    if mutation == 'overlap':
        windows[1]['history'][0]['hands'] += 1
    elif mutation == 'score':
        windows[-1]['history'][-1]['selection_loss'] += .1
    elif mutation == 'selected':
        windows[-1]['history'][-1]['selected'] = False
    elif mutation == 'active_ids':
        windows[-1]['history'][-1]['active_ids_after'] = [0, 1, 2, 3, 4]
    elif mutation == 'assignment':
        assignments[5]['pool_snapshot_refs'][0]['snapshot_id'] = 999
    elif mutation == 'checkpoint':
        windows[-1]['active'][-1]['selection_score'] -= .1
    elif mutation == 'cadence':
        windows[-1]['snapshot_every'] = 4
    elif mutation == 'metric':
        metrics[5]['hands'] += 1
    else:
        windows[-1]['history'][-1]['score_components']['policy_loss'] = float('nan')
    with pytest.raises(ValueError):
        audit.verify_windows(windows, metrics, assignments)
