"""Post-terminal raw synthesis including both preserved checkpoint interruptions."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SECOND = HERE.parent
BASE = SECOND.parent
FIRST = BASE / 'recovery_20260905'
sys.path.insert(0, str(FIRST / 'post_analysis'))
import analyze_recovered_seed3 as previous

ctl, ev, cross, normal = previous.ctl, previous.ev, previous.cross, previous.normal
ev.require(ctl.BASE == ev.BASE == BASE, 'wrong Seed3 module binding')
ROOTS = (BASE, FIRST, SECOND)
FAILED = {BASE / 'static_stage1', BASE / 'moving256_stage1'}
FULL, COLLAPSE = previous.FULL, previous.COLLAPSE
COUNT_KEYS = ('new_physical_hands', 'new_transition_hands', 'new_replay_rows',
              'new_no_decision_hands', 'residual_worker_tail_hands')


def readiness():
    for root in ROOTS:
        path = root / 'ownership.json'
        if not path.exists():
            return {'ready': False, 'reason': 'required controller receipt missing'}
        if ctl.owner_live(ev.read_json(path)):
            return {'ready': False, 'reason': 'exact controller still live; do not read outcomes'}
    for root in ROOTS:
        for path in root.glob('*/process.json'):
            if ctl.owner_live(ev.read_json(path)):
                return {'ready': False, 'reason': 'tracked job still live'}
            terminal_path = path.parent / 'termination.json'
            if not terminal_path.exists():
                return {'ready': False, 'reason': 'tracked termination receipt missing'}
            receipt = ev.read_json(terminal_path)
            if receipt['observer_errors'] or receipt['remaining_observed_child_pids']:
                return {'ready': False, 'reason': 'tracked termination evidence incomplete'}
            if any(ctl.owner_live({'pid': int(pid), 'create_time': created})
                   for pid, created in receipt['observed_children'].items()):
                return {'ready': False, 'reason': 'tracked descendant still live'}
    path = SECOND / 'pipeline_result.json'
    if not path.exists():
        return {'ready': False, 'reason': 'terminal second recovery result absent; scoped review required'}
    phase = ev.read_json(path)['phase']
    return {'ready': phase in (FULL, COLLAPSE), 'phase': phase,
            'reason': 'terminal evidence available' if phase in (FULL, COLLAPSE) else 'unexpected terminal phase'}


def verify_job(directory):
    ev.require(not ctl.owner_live(ev.read_json(directory / 'process.json')), 'tracked job still live')
    receipt = ev.read_json(directory / 'termination.json')
    ev.require(receipt['exit_code'] == (1 if directory in FAILED else 0) and
               not receipt['observer_errors'] and not receipt['remaining_observed_child_pids'], 'unqualified termination receipt')
    ev.require(not any(ctl.owner_live({'pid': int(pid), 'create_time': created})
                      for pid, created in receipt['observed_children'].items()), 'tracked descendant still live')
    return {str(directory / n): ev.sha(directory / n) for n in ('process.json', 'termination.json', 'command.json')}


def partial_attempts(static_audit, moving_audit):
    static = previous.retained_partial(static_audit)
    static.update(subprocess_wall_seconds=ev.read_json(BASE / 'static_stage1/termination.json')['wall_seconds'],
                  known_unretained_physical_hands=static_audit['observed_completed_but_uncheckpointed_physical_hands'],
                  known_unretained_transition_hands=static_audit['observed_completed_but_uncheckpointed_transition_hands'],
                  recovered_unpublished_hands_already_in_retained=0)
    rows = ctl.complete_jsonl(BASE / 'moving256_stage1/h1_training_metrics.jsonl')
    ev.require([r['iteration'] for r in rows] == list(range(1, 1216)), 'moving interrupted metric chain changed')
    start, end = rows[879], rows[-1]
    actual = {'new_physical_hands': end['environment_hand_accounting']['completed_hands'] - start['environment_hand_accounting']['completed_hands'],
              'new_transition_hands': end['hands'] - start['hands'],
              'new_replay_rows': end['ppo_replay_cumulative_rows'] - start['ppo_replay_cumulative_rows'],
              'new_no_decision_hands': end['environment_hand_accounting']['no_trainable_decision_hands'] - start['environment_hand_accounting']['no_trainable_decision_hands']}
    actual['residual_worker_tail_hands'] = actual['new_physical_hands'] - actual['new_transition_hands'] - actual['new_no_decision_hands']
    expected = {k: moving_audit[a] for k, a in zip(COUNT_KEYS, ('recoverable_new_physical_hands',
        'recoverable_new_transition_hands', 'recoverable_new_replay_rows', 'recoverable_new_no_decision_hands', 'recoverable_worker_tail_hands'))}
    ev.require(actual == expected and moving_audit['known_completed_but_not_serialized_hands_in_this_attempt'] == 0,
               'candidate/retained metric accounting mismatch')
    moving = {**actual, 'arm': 'moving256', 'stage': 1, 'namespace': moving_audit['namespace'],
        'checkpoint_sha256': moving_audit['candidate_sha256'], 'original_exit_code': 1,
        'unknown_additional_worker_tail_hands': None, 'known_unretained_physical_hands': 0,
        'known_unretained_transition_hands': 0,
        'recovered_unpublished_hands_already_in_retained': moving_audit['unpublished_completed_update_physical_hands'],
        'subprocess_wall_seconds': ev.read_json(BASE / 'moving256_stage1/termination.json')['wall_seconds']}
    return [static, moving]


def accounting(completed, partials, stage_count):
    ev.require(stage_count in (1, 2), 'invalid stage count')
    expected = list(ctl.ORDER) if stage_count == 2 else list(ctl.ORDER[:2])
    ev.require([(r['arm'], r['stage']) for r in completed] == expected, 'completed order/coverage mismatch')
    ev.require([(r['arm'], r['stage']) for r in partials] == [('static', 1), ('moving256', 1)], 'interruption order/coverage mismatch')
    ev.require(all(r['passed'] and r['unknown_crash_suffix_hands'] == 0 for r in completed), 'unqualified completed attempt')
    ev.require(all(r['original_exit_code'] == 1 and r['unknown_additional_worker_tail_hands'] is None
                   for r in partials), 'interruption tail must remain unknown')
    # Actual chronological attempt order, not a fabricated composite run/namespace.
    attempts = [partials[0], completed[0], partials[1], *completed[1:]]
    namespaces = [r['namespace'] for r in attempts]
    ev.require(all(isinstance(n, str) and n for n in namespaces) and len(set(namespaces)) == len(namespaces), 'namespace reused/missing')
    for row in attempts:
        ev.require(all(type(row[k]) is int and row[k] >= 0 for k in COUNT_KEYS), 'invalid retained count')
        ev.require(row['new_physical_hands'] == row['new_transition_hands'] + row['new_no_decision_hands'] +
                   row['residual_worker_tail_hands'], 'unbalanced per-attempt count')
        ev.require(math.isfinite(row['subprocess_wall_seconds']) and row['subprocess_wall_seconds'] > 0, 'invalid wall time')
    for row in partials:
        keys = ('known_unretained_physical_hands', 'known_unretained_transition_hands', 'recovered_unpublished_hands_already_in_retained')
        ev.require(all(type(row[k]) is int and row[k] >= 0 for k in keys) and
                   row[keys[1]] <= row[keys[0]] and row[keys[2]] <= row['new_physical_hands'], 'invalid interruption accounting')
    sums = {k: sum(r[k] for r in attempts) for k in COUNT_KEYS}
    lost = sum(r['known_unretained_physical_hands'] for r in partials)
    lost_transition = sum(r['known_unretained_transition_hands'] for r in partials)
    by_arm = {arm: ctl.INITIAL_PHYSICAL + sum(r['new_physical_hands'] for r in attempts if r['arm'] == arm)
              for arm in ('static', 'moving256')}
    wall = sum(r['subprocess_wall_seconds'] for r in attempts)
    return {'new_training_hands': sums['new_physical_hands'] + lost,
        'new_transition_hands': sums['new_transition_hands'] + lost_transition,
        'new_training_hands_semantics': 'observed executions including known unretained first update; unknown extra worker tails excluded',
        'retained_training_hands': sums['new_physical_hands'], 'retained_transition_hands': sums['new_transition_hands'],
        'retained_no_decision_hands': sums['new_no_decision_hands'], 'retained_worker_tail_hands': sums['residual_worker_tail_hands'],
        'new_replay_rows_not_new_hands': sums['new_replay_rows'], 'observed_uncheckpointed_training_hands': lost,
        'observed_uncheckpointed_transition_hands': lost_transition,
        'recovered_unpublished_hands_already_in_retained': sum(r['recovered_unpublished_hands_already_in_retained'] for r in partials),
        'unknown_additional_worker_tail_hands': None, 'actual_executions_are_at_least_observed_count': True,
        'shared_parent_physical_hands': ctl.INITIAL_PHYSICAL,
        'known_retained_local_lineage_union_hands': ctl.INITIAL_PHYSICAL + sums['new_physical_hands'],
        'per_arm_cumulative_physical_hands': by_arm, 'largest_single_endpoint_local_lineage_hands': max(by_arm.values()),
        'unique_attempt_namespaces': namespaces, 'interrupted_attempts': partials, 'training_seed_lineages': 1,
        'pretrained_standard10_environment_hands_not_inferred': True, 'statistical_not_bitwise_worker_continuation': True,
        'all_training_attempt_wall_seconds': wall, 'retained_physical_hands_per_training_wall_second': sums['new_physical_hands'] / wall,
        'evaluation_hands': stage_count * 65536, 'offline_samples': stage_count * 40000, 'slumbot_hands': 0}


def verify_completed_run(row, directory, helper, inputs):
    import torch
    ev.require(row == ev.read_json(directory / 'verification.json') and row['passed'], 'verification/pipeline mismatch')
    ctl.check_hashes(row['checkpoint_windows_sha256'])
    ev.require(ev.sha(directory / 'latest.pt') == row['checkpoint_sha256'], 'endpoint changed')
    parent_contract = ev.read_json(directory / 'parent_contract.json')
    parent_path = Path(parent_contract['path'])
    ev.require(ev.sha(parent_path) == parent_contract['sha256'] == row['parent_checkpoint_sha256'], 'parent binding changed')
    parent = torch.load(parent_path, map_location='cpu', weights_only=False)
    initial = torch.load(directory / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
    final = torch.load(directory / 'latest.pt', map_location='cpu', weights_only=False)
    keys = ('model', 'optimizer', 'ppo_replay_entries', 'ppo_replay_rng_state', 'ppo_replay_cumulative_rows',
            'pool_snapshots', 'pool_strategy', 'pool_active_metadata', 'pool_candidate_history',
            'iteration', 'total_hands', 'main_process_rng_state')
    ev.require(parent['main_process_rng_state'] is not None and all(helper.equal(parent[k], initial[k]) for k in keys),
               'actual initial state differs from retained parent')
    ev.require(all(parent['environment_hand_accounting'][k] == initial['environment_hand_accounting'][k]
                   for k in ('completed_hands', 'no_trainable_decision_hands')), 'initial physical counters changed')
    ev.initial_reference(row['arm'], parent, initial, helper.equal)
    gate = ev.read_json(directory / 'initial_resume_gate.json')
    ev.require(gate['passed'] and len(gate['gates']) == 14 and all(gate['gates'].values()) and
               gate['gates'].get('main_rng_restored_exact') is True and gate['parent_sha256'] == parent_contract['sha256'] and
               gate['initial_sha256'] == ev.sha(directory / 'initial_resumed_state.pt'), 'initial gate mismatch')
    names = ['verification.json', 'initial_resume_gate.json', 'parent_contract.json', 'prefixes.json',
             'initial_resumed_state.pt', 'latest.pt', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl', 'run_manifest.json']
    if directory != FIRST / 'static_stage1_remainder':
        extra = ev.read_json(directory / 'second_resume_gate.json')
        ev.require(extra['passed'] and len(extra['gates']) == 2 and all(extra['gates'].values()) and
                   extra['parent_sha256'] == gate['parent_sha256'] and extra['initial_sha256'] == gate['initial_sha256'] and
                   helper.equal(parent.get('moving_source_policy_reference'), initial.get('moving_source_policy_reference')),
                   'second recovery reference/namespace gate mismatch')
        names.append('second_resume_gate.json')
    metrics = ctl.complete_jsonl(directory / 'h1_training_metrics.jsonl')
    ev.require([r['iteration'] for r in metrics] == list(range(1, final['iteration'] + 1)) and
               metrics[-1]['hands'] == final['total_hands'] and
               metrics[-1]['environment_hand_accounting'] == final['environment_hand_accounting'], 'terminal metrics mismatch')
    ev.require(final['environment_hand_accounting']['completed_hands'] - parent['environment_hand_accounting']['completed_hands'] == row['new_physical_hands'] and
               final['total_hands'] - parent['total_hands'] == row['new_transition_hands'] and
               final['ppo_replay_cumulative_rows'] - parent['ppo_replay_cumulative_rows'] == row['new_replay_rows'] and
               final['environment_hand_accounting']['no_trainable_decision_hands'] -
               parent['environment_hand_accounting']['no_trainable_decision_hands'] == row['new_no_decision_hands'] and
               ev.read_json(directory / 'termination.json')['wall_seconds'] == row['subprocess_wall_seconds'], 'actual dose/wall differs')
    for name, info in ev.read_json(directory / 'prefixes.json').items():
        import hashlib
        with (directory / name).open('rb') as handle:
            digest = hashlib.sha256(handle.read(info['bytes'])).hexdigest()
        ev.require(digest == info['sha256'] == ev.sha(info['path']), 'inherited raw prefix changed')
    attempt = final['fixed_deal_attempt']
    receipt = helper.helpers.load_attempt(Path(attempt['path']), attempt['sha256'])
    ev.require(receipt == attempt['receipt'] and receipt['namespace'] == row['namespace'] and
               receipt['parent_checkpoint_sha256'] == row['parent_checkpoint_sha256'], 'attempt receipt mismatch')
    inputs.update({str(directory / n): ev.sha(directory / n) for n in names})
    inputs[attempt['path']] = attempt['sha256']
    inputs.update(row['checkpoint_windows_sha256'])
    return final['environment_hand_accounting']['completed_hands']


def build_report():
    ready = readiness()
    ev.require(ready['ready'], ready['reason'])
    stage_count = 2 if ready['phase'] == FULL else 1
    contracts = [ev.read_json(root / 'input_contract.json') for root in ROOTS]
    old = ev.read_json(FIRST / 'interruption_audit.json')
    pending = ev.read_json(SECOND / 'pending_checkpoint_audit.json')
    ev.require(old['passed'] and pending['passed'] and old['unknown_additional_worker_tail_hands'] is None and
               pending['unknown_additional_worker_tail_hands'] is None, 'interruption audit unqualified')
    pipeline = ev.read_json(SECOND / 'pipeline_result.json')
    ev.require(pipeline['earlier_failed_pipeline_results_not_fabricated'] and pipeline['preserved_interruption_audits'] ==
               [str(FIRST / 'interruption_audit.json'), str(SECOND / 'pending_checkpoint_audit.json')], 'interruption provenance lost')
    completed = pipeline['completed_attempts']
    expected = list(ctl.ORDER) if stage_count == 2 else list(ctl.ORDER[:2])
    ev.require([(r['arm'], r['stage']) for r in completed] == expected and
               pipeline['new_attempts_in_second_recovery'] == completed[1:], 'completed attempt coverage changed')
    inputs = previous.merge_hashes(*(c['input_sha256'] for c in contracts), old['input_sha256'], pending['input_sha256'])
    ctl.check_hashes(inputs)
    directories = {(arm, stage): (FIRST / 'static_stage1_remainder' if (arm, stage) == ('static', 1) else
                   SECOND / 'moving256_stage1_remainder' if (arm, stage) == ('moving256', 1) else BASE / f'{arm}_stage{stage}')
                   for arm, stage in expected}
    jobs = FAILED | set(directories.values()) | {BASE / f'{prefix}_{arm}_stage{stage}' for stage in range(1, stage_count + 1)
            for arm in ('static', 'moving256') for prefix in ('job_eval', 'drift')}
    ev.require({p.parent for root in ROOTS for p in root.glob('*/process.json')} == jobs, 'unexpected/missing tracked jobs')
    for directory in jobs:
        inputs.update(verify_job(directory))
    import torch
    torch.set_num_threads(1)
    helper, final_counts = ctl.qualified_command_helper(), {}
    for row in completed:
        final_counts[row['arm']] = verify_completed_run(row, directories[row['arm'], row['stage']], helper, inputs)
    counts = accounting(completed, partial_attempts(old, pending), stage_count)
    ev.require(counts['per_arm_cumulative_physical_hands'] == final_counts and
               all(n >= ctl.TARGETS[stage_count] for n in final_counts.values()), 'final retained lineage dose differs')
    stages, corpus = {}, dict(contracts[0]['prior_common_deck_corpus'])
    for stage in range(1, stage_count + 1):
        hashes = {arm: ev.sha(directories[arm, stage] / 'latest.pt') for arm in ('static', 'moving256')}
        value = ev.aggregate_stage(stage, BASE, ctl.PARENT_SHA, hashes, contracts[0]['anchors'], corpus)
        path = BASE / f'stage{stage}_analysis.json'
        ev.require(value == ev.read_json(path), 'stage result/raw reaggregation differs')
        stages[stage] = value
        inputs[str(path)] = ev.sha(path)
        inputs.update(value['input_sha256'])
        for arm in ('static', 'moving256'):
            raw = BASE / f'eval_{arm}_stage{stage}/common_deck_pairs.jsonl.gz'
            corpus[str(raw)] = ev.sha(raw)
    ev.require(stages[1]['broad_collapse'] is (stage_count == 1), 'preregistered continuation gate changed')
    ev.require(ev.sha(cross.SEED1_REPORT) == cross.SEED1_SHA and
               ev.read_json(cross.SEED1_BASE / 'experiment.json')['status'] == 'COMPLETED', 'Seed1 source changed/incomplete')
    one = ev.read_json(cross.SEED1_REPORT)
    s1, decks1 = cross.verify_raw_stages(one, 'seed1', inputs)
    s3, decks3 = cross.verify_raw_stages({'passed': True, 'stages': stages}, 'seed3', inputs)
    ev.require(decks1.isdisjoint(decks3), 'cross-seed evaluation decks overlap')
    inputs[str(cross.SEED1_REPORT)] = cross.SEED1_SHA
    for root in ROOTS:
        for name in ('input_contract.json', 'ownership.json'):
            inputs[str(root / name)] = ev.sha(root / name)
    for name in ('pipeline_result.json', 'pending_checkpoint_audit.json', 'recovery_preflight.json'):
        inputs[str(SECOND / name)] = ev.sha(SECOND / name)
    ctl.check_hashes(inputs)
    return {'schema': 'cardpilot.seed3.twice_recovered_two_seed_report.v1', 'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'phase': ready['phase'],
        'command': [sys.executable, *sys.orig_argv[1:]], 'accounting': counts, 'stages': stages,
        'geometric_change': normal.geometric_report(stages) if stage_count == 2 else None,
        'equal_seed_synthesis': cross.combine({'seed1': s1, 'seed3': s3}), 'source_accounting_seed1': one['accounting'],
        'accounting_comparison_warning': 'Seed1 historical new_training_hands means retained; current Seed3 reports observed executions including4292 known unretained. Recovered5256 are already retained. Never sum fields of different scopes.',
        'input_sha256': inputs, 'source_sha256': {str(p): ev.sha(p) for p in
             (Path(__file__).resolve(), Path(previous.__file__), Path(cross.__file__), Path(normal.__file__))},
        'cross_seed_deck_overlap': 0, 'analysis_added_training_hands': 0, 'analysis_added_evaluation_hands': 0,
        'scope_label_clarification': 'Frozen Seed3 raw-stage ci_scope text says Seed1 by copy; actual Seed3 parent SHA and evaluation seeds are verified. No old source/summary was rewritten.',
        'provenance_limitations': 'Conditional on the qualified Seed3 4M parent, not a blanket certificate of all older boundaries. Original moving activation used declared legacy main-RNG bootstrap. Both new remainder resumes are main-state-exact but statistical, not bitwise worker continuation.',
        'goal_achieved': False, 'automatic_final_slumbot_test_authorized': False,
        'next_decision': 'REVIEW_TWO_SEED_BREADTH_GEOMETRIC_SLOPES_COST_AND_UNCONFIRMED_EXTERNAL_TRANSLATION'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-ready', action='store_true')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.check_ready:
        print(json.dumps(readiness(), indent=2))
        return
    if args.out is None:
        parser.error('--out required')
    ev.require(not args.out.exists(), 'preserve previous report')
    result = build_report()
    ctl.write_new(args.out, result)
    print(json.dumps({'passed': True, 'accounting': result['accounting'], 'next_decision': result['next_decision']}, indent=2))


if __name__ == '__main__':
    main()
