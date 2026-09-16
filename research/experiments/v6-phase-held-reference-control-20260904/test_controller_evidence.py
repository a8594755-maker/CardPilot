import copy
import gzip
import json
import os
from pathlib import Path

import psutil
import pytest

import control_evidence as ev
import run_control as run


def checkpoint(iteration, reference_value=1, model_value=1):
    count = iteration - 882
    return {'iteration': iteration, 'model': {'w': model_value},
            'config': {'source_policy_reference_refresh_updates': 256},
            'environment_hand_accounting': {'completed_hands': iteration * 100},
            'moving_source_policy_reference': {
                'schema_version': 'alpha_holdem.moving_source_policy_reference.v1',
                'direction': 'current_to_reference', 'refresh_interval_updates': 256,
                'completed_updates': count, 'last_refresh_update': count // 256 * 256,
                'reference_round': count // 256, 'activation_iteration': 882,
                'trainer_iteration': iteration, 'reference_model': {'w': reference_value}, 'rng_state': {}}}


def metric(iteration):
    count = iteration - 882
    return {'iteration': iteration, 'moving_reference_refresh_updates': 256,
            'moving_reference_completed_updates': count,
            'moving_reference_last_refresh_update': count // 256 * 256,
            'moving_reference_round': count // 256, 'moving_reference_refreshed': count % 256 == 0}


@pytest.mark.parametrize('field,value', [('activation_iteration', 883), ('completed_updates', 257),
                                       ('refresh_interval_updates', 1), ('direction', 'reference_to_current'),
                                       ('reference_round', 2), ('last_refresh_update', 0)])
def test_reference_bad_counters_rejected(field, value):
    c = checkpoint(1138)
    c['moving_source_policy_reference'][field] = value
    with pytest.raises(ValueError):
        ev.reference_state(c)


def test_initial_reference_is_actual_parent_and_resume_does_not_rebase():
    original = checkpoint(882)
    del original['moving_source_policy_reference']
    ev.initial_reference('moving256', original, checkpoint(882), lambda a, b: a == b)
    with pytest.raises(ValueError, match='initial reference'):
        ev.initial_reference('moving256', original, checkpoint(882, reference_value=8), lambda a, b: a == b)
    parent = checkpoint(1300, reference_value=2, model_value=3)
    ev.initial_reference('moving256', parent, copy.deepcopy(parent), lambda a, b: a == b)
    with pytest.raises(ValueError, match='moving resume'):
        ev.initial_reference('moving256', parent, checkpoint(1300, reference_value=3), lambda a, b: a == b)


def test_phase_boundary_and_constant_reference_verified():
    initial = checkpoint(882)
    parent = copy.deepcopy(initial)
    del parent['moving_source_policy_reference']
    windows = [checkpoint(896), checkpoint(1138, 2, 2), checkpoint(1140, 2, 3)]
    rows = [metric(i) for i in range(883, 1141)]
    result = ev.verify_reference_windows('moving256', parent, initial, windows, rows, lambda a, b: a == b)
    assert result['last_reference_round'] == 1
    assert result['phase_boundaries'][0]['iteration'] == 1138
    with pytest.raises(ValueError, match='phase-boundary'):
        ev.verify_reference_windows('moving256', parent, initial, windows[::2], rows, lambda a, b: a == b)
    windows[-1]['moving_source_policy_reference']['reference_model']['w'] = 8
    with pytest.raises(ValueError, match='inside phase'):
        ev.verify_reference_windows('moving256', parent, initial, windows, rows, lambda a, b: a == b)


def row(index=0, control=None, treatment=None):
    deck = list(range(52))
    deck[0], deck[index] = deck[index], deck[0]
    return ev.derived_row({'anchor': 'standard10', 'anchor_seed': 9, 'pair_index': index, 'deck': deck},
                          control or [1., -1.], treatment or [2., 3.])


def test_shared_parent_cancels_not_counted_twice():
    a, b = row(treatment=[2, 3]), row(treatment=[5, 1])
    result = ev.join_arms([a], [b])
    assert len(result) == 1
    assert result[0]['treatment_minus_control_rewards_bb'] == [3, -2]
    assert result[0]['treatment_minus_control_pair_mean_bb'] == .5


@pytest.mark.parametrize('problem', ['parent', 'deck', 'identity', 'arithmetic', 'nonfinite', 'duplicate'])
def test_pair_join_refuses_invalid_evidence(problem):
    a, b = row(), row()
    if problem == 'parent':
        b = row(control=[3, 1])
    elif problem == 'deck':
        b['deck'][0], b['deck'][1] = b['deck'][1], b['deck'][0]
    elif problem == 'identity':
        b['pair_index'] = 9
    elif problem == 'arithmetic':
        b['treatment_minus_control_pair_mean_bb'] += 3
    elif problem == 'nonfinite':
        b['treatment_rewards_bb'][0] = float('nan')
    with pytest.raises(ValueError):
        ev.join_arms([a, a] if problem == 'duplicate' else [a], [b])


def test_prior_cohort_overlap_and_hash_fail_closed(tmp_path):
    path = tmp_path / 'old.jsonl.gz'
    with gzip.open(path, 'wt') as handle:
        handle.write(json.dumps(row()) + '\n')
    corpus = {str(path): ev.sha(path)}
    assert ev.check_prior_decks([row(1)], corpus)['overlap'] == 0
    with pytest.raises(ValueError, match='overlaps'):
        ev.check_prior_decks([row()], corpus)
    corpus[str(path)] = 'wrong'
    with pytest.raises(ValueError, match='changed'):
        ev.check_prior_decks([row(1)], corpus)


def test_collapse_is_three_anchors_AND_both_seats_strict_bounds():
    summary = {'by_anchor': {a: {'ci95_high_bb100': -26} for a in ev.ANCHORS},
               'by_seat': {str(s): {'ci95_high_bb100': -1} for s in (0, 1)}}
    assert ev.broad_collapse(summary)
    summary['by_seat']['1']['ci95_high_bb100'] = 0
    assert not ev.broad_collapse(summary)
    summary['by_seat']['1']['ci95_high_bb100'] = -1
    for a in ev.ANCHORS[:2]:
        summary['by_anchor'][a]['ci95_high_bb100'] = -25
    assert not ev.broad_collapse(summary)


def test_runtime_boundary_is_not_algorithm_failure_or_retry():
    run.target_or_safe_boundary(run.TARGETS[1] + 5, run.TARGETS[1])
    with pytest.raises(run.SafeBoundary, match='no automatic restart'):
        run.target_or_safe_boundary(run.TARGETS[1] - 1, run.TARGETS[1])


def test_source_hash_guard_and_exclusive_evidence(tmp_path):
    path = tmp_path / 'evidence.json'
    run.write_new(path, {'value': 1})
    run.check_hashes({str(path): run.sha(path)})
    with pytest.raises(ValueError, match='changed'):
        run.check_hashes({str(path): 'wrong'})
    with pytest.raises(FileExistsError):
        run.write_new(path, {'value': 2})


def test_owner_pid_creation_time_both_required():
    proc = psutil.Process(os.getpid())
    assert run.owner_live({'pid': proc.pid, 'create_time': proc.create_time()})
    assert not run.owner_live({'pid': proc.pid, 'create_time': proc.create_time() - 1})


def test_live_accounting_preserves_prefix_and_uses_terminal_tails(tmp_path, monkeypatch):
    monkeypatch.setattr(run, 'BASE', tmp_path)
    stage = run.stage_directory('static', 1)
    stage.mkdir()
    run.write_new(stage / 'parent_contract.json', {'physical_hands': 100, 'transition_hands': 90})
    with (stage / 'h1_training_metrics.jsonl').open('w') as handle:
        handle.write(json.dumps({'iteration': 2, 'hands': 180,
                                 'environment_hand_accounting': {'completed_hands': 200}}) + '\n')
        handle.write('{"incomplete":')
    assert run.live_accounting()[0]['new_training_hands'] == 100
    run.write_new(stage / 'run_manifest.json', {'status': 'finished', 'total_hands': 180,
                                              'environment_hand_accounting': {'completed_hands': 207}})
    totals, _ = run.live_accounting()
    assert totals['new_training_hands'] == 107
    assert totals['new_transition_hands'] == 90


def test_live_gzip_rows_are_lower_bound_before_footer(tmp_path):
    path = tmp_path / 'live.gz'
    with gzip.open(path, 'wt') as handle:
        handle.write(json.dumps({'x': 1}) + '\n')
        handle.flush()
        assert run.gzip_count(path) == 1
    assert run.gzip_count(path) == 1


def test_complete_stage_aggregate_contract(tmp_path):
    """Synthetic fixtures only: exercise the full real-output schema before workers."""
    import numpy as np
    rng = np.random.default_rng(741)
    rows = []
    for anchor_index, anchor in enumerate(ev.ANCHORS):
        for index in range(2048):
            rows.append(ev.derived_row({'anchor': anchor, 'anchor_seed': 20263411 + 1000003 * anchor_index,
                        'pair_index': index, 'deck': rng.permutation(52).tolist()}, [1., -1.], [2., 3.]))
    anchors = {a: {'sha256': a} for a in ev.ANCHORS}
    hashes = {'static': 'static_hash', 'moving256': 'moving_hash'}
    for arm in ('static', 'moving256'):
        directory = tmp_path / f'eval_{arm}_stage1'
        directory.mkdir()
        raw = directory / 'common_deck_pairs.jsonl.gz'
        actual = rows if arm == 'static' else [ev.derived_row(r, [1., -1.], [4., 5.]) for r in rows]
        with gzip.open(raw, 'wt') as handle:
            for r in actual:
                handle.write(json.dumps(r) + '\n')
        run.write_new(directory / 'summary.json', {'status': 'COMPLETED', 'evaluation_hands': 32768,
            'raw_pairs_sha256': ev.sha(raw), 'policy_mode': 'greedy', 'starting_stack_bb': 200,
            'command': ['python', 'eval.py', '--seed', '20263411'],
            'input_sha256': {'control': 'parent', 'treatment': hashes[arm], **{f'anchor:{a}': a for a in ev.ANCHORS}}})
        directory = tmp_path / f'drift_{arm}_stage1'
        directory.mkdir()
        raw = directory / 'drift_raw.jsonl.gz'
        with gzip.open(raw, 'wt') as handle:
            for index in range(20000):
                handle.write(json.dumps({'row': index}) + '\n')
        run.write_new(directory / 'drift_analysis.json', {'status': 'PASS', 'design': {'states': 20000, 'seed': 20263421},
            'overall': {'states': 20000}, 'raw_sha256': ev.sha(raw), 'parent': {'sha256': 'standard10'},
            'treatment': {'sha256': hashes[arm]}, 'tensor_scope': {'status': 'PASS'},
            'checkpoint_metadata_mismatches': [], 'by_street': {}})
    result = ev.aggregate_stage(1, tmp_path, 'parent', hashes, anchors, {})
    assert result['passed'] and not result['broad_collapse']
    assert result['moving_minus_static']['pooled']['samples'] == 8192
    assert result['moving_minus_static']['pooled']['bb100'] == 200
    assert result['evaluation_hands'] == 65536
    assert result['offline_states'] == 40000
