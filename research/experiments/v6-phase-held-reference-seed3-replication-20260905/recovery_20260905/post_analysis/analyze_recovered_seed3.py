"""Post-terminal Seed3 accounting, raw evaluation and equal-seed synthesis."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
RECOVERY = HERE.parent
BASE = RECOVERY.parent
sys.path.insert(0, str(BASE / 'post_analysis'))
import cross_seed_summary as cross

ctl, ev, normal = cross.ctl, cross.ev, cross.report
ev.require(ctl.BASE == ev.BASE == BASE, 'wrong experiment binding')
OLD = BASE / 'static_stage1'
REMAINDER = RECOVERY / 'static_stage1_remainder'
FULL = 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS'
COLLAPSE = 'PREREGISTERED_BROAD_COLLAPSE_RESEARCH_REVIEW'


def readiness():
    for root in (BASE, RECOVERY):
        path = root / 'ownership.json'
        if not path.exists():
            return {'ready': False, 'reason': 'required owner receipt missing'}
        if ctl.owner_live(ev.read_json(path)):
            return {'ready': False, 'reason': 'exact controller still live; no outcome reaggregation'}
    # A dead controller alone does not establish that its trainers/workers exited.
    for root in (BASE, RECOVERY):
        for path in root.glob('*/process.json'):
            if ctl.owner_live(ev.read_json(path)):
                return {'ready': False, 'reason': 'tracked job still live; no outcome reaggregation'}
            terminal_path = path.parent / 'termination.json'
            if not terminal_path.exists():
                return {'ready': False, 'reason': 'tracked job termination evidence missing'}
            terminal = ev.read_json(terminal_path)
            if terminal['observer_errors'] or terminal['remaining_observed_child_pids']:
                return {'ready': False, 'reason': 'incomplete tracked termination evidence'}
            for pid, created in terminal['observed_children'].items():
                if ctl.owner_live({'pid': int(pid), 'create_time': created}):
                    return {'ready': False, 'reason': 'tracked descendant still live; no outcome reaggregation'}
    path = RECOVERY / 'pipeline_result.json'
    if not path.exists():
        return {'ready': False, 'reason': 'terminal recovery result absent; preserve/review interruption'}
    phase = ev.read_json(path)['phase']
    return {'ready': phase in (FULL, COLLAPSE), 'phase': phase,
            'reason': 'terminal result available' if phase in (FULL, COLLAPSE) else 'unexpected terminal phase'}


def retained_partial(audit):
    rows = ctl.complete_jsonl(OLD / 'h1_training_metrics.jsonl')
    ev.require([r['iteration'] for r in rows] == list(range(1, 1119)), 'original metric chain changed')
    before, after = rows[879], rows[1116]
    physical = after['environment_hand_accounting']['completed_hands'] - before['environment_hand_accounting']['completed_hands']
    transition = after['hands'] - before['hands']
    replay = after['ppo_replay_cumulative_rows'] - before['ppo_replay_cumulative_rows']
    no_decision = after['environment_hand_accounting']['no_trainable_decision_hands'] - before['environment_hand_accounting']['no_trainable_decision_hands']
    ev.require((physical, transition, replay) == (audit['new_retained_physical_hands'],
                audit['new_retained_transition_hands'], audit['new_retained_replay_rows']), 'partial retained accounting differs')
    return {'arm': 'static', 'stage': 1, 'namespace': audit['namespace'],
            'new_physical_hands': physical, 'new_transition_hands': transition, 'new_replay_rows': replay,
            'new_no_decision_hands': no_decision, 'residual_worker_tail_hands': physical - transition - no_decision,
            'unknown_additional_worker_tail_hands': None, 'original_exit_code': 1,
            'checkpoint_sha256': audit['checkpoint_sha256']}


def accounting(completed, partial, audit, failed_wall, stage_count):
    ev.require(stage_count in (1, 2), 'invalid stage count')
    expected = list(ctl.ORDER) if stage_count == 2 else list(ctl.ORDER[:2])
    ev.require([(r['arm'], r['stage']) for r in completed] == expected, 'wrong completed order or coverage')
    ev.require(partial['arm'] == 'static' and partial['stage'] == 1 and partial['original_exit_code'] == 1
               and partial['unknown_additional_worker_tail_hands'] is None, 'wrong interrupted prefix')
    ev.require(all(r['passed'] and r['unknown_crash_suffix_hands'] == 0 for r in completed), 'unqualified completed attempt')
    namespaces = [r['namespace'] for r in completed] + [partial['namespace']]
    ev.require(all(isinstance(n, str) and n for n in namespaces) and
               len(set(namespaces)) == len(namespaces), 'namespace missing or reused')
    keys = ('new_physical_hands', 'new_transition_hands', 'new_replay_rows',
            'new_no_decision_hands', 'residual_worker_tail_hands')
    for row in [*completed, partial]:
        ev.require(all(type(row[k]) is int and row[k] >= 0 for k in keys), 'invalid retained count')
        ev.require(row['new_physical_hands'] == row['new_transition_hands'] +
                   row['new_no_decision_hands'] + row['residual_worker_tail_hands'], 'unbalanced retained attempt')
    ev.require(all(math.isfinite(r['subprocess_wall_seconds']) and r['subprocess_wall_seconds'] > 0
                   for r in completed), 'invalid completed wall time')
    counts = {key: sum(r[key] for r in completed) + partial[key]
              for key in ('new_physical_hands', 'new_transition_hands', 'new_replay_rows',
                          'new_no_decision_hands', 'residual_worker_tail_hands')}
    ev.require(all(v >= 0 for v in counts.values()), 'negative retained count')
    ev.require(counts['new_physical_hands'] == counts['new_transition_hands'] +
               counts['new_no_decision_hands'] + counts['residual_worker_tail_hands'], 'unbalanced retained accounting')
    observed = audit['observed_completed_but_uncheckpointed_physical_hands']
    observed_transition = audit['observed_completed_but_uncheckpointed_transition_hands']
    ev.require(type(observed) is int and type(observed_transition) is int and
               0 <= observed_transition <= observed and math.isfinite(failed_wall) and failed_wall > 0,
               'invalid observed suffix or wall time')
    by_arm = {arm: ctl.INITIAL_PHYSICAL + sum(r['new_physical_hands'] for r in completed if r['arm'] == arm)
              + (partial['new_physical_hands'] if arm == 'static' else 0) for arm in ('static', 'moving256')}
    wall = failed_wall + sum(r['subprocess_wall_seconds'] for r in completed)
    return {'new_training_hands': counts['new_physical_hands'] + observed,
            'new_transition_hands': counts['new_transition_hands'] + observed_transition,
            'new_training_hands_semantics': 'observed physical executions, including known uncheckpointed update; excludes unknown extra worker tails',
            'retained_training_hands': counts['new_physical_hands'], 'retained_transition_hands': counts['new_transition_hands'],
            'new_replay_rows_not_new_hands': counts['new_replay_rows'], 'new_no_decision_hands': counts['new_no_decision_hands'],
            'retained_worker_tail_hands': counts['residual_worker_tail_hands'],
            'observed_uncheckpointed_training_hands': observed, 'observed_uncheckpointed_transition_hands': observed_transition,
            'unknown_additional_worker_tail_hands': None, 'actual_executed_hands_are_at_least_observed_count': True,
            'shared_parent_physical_hands': ctl.INITIAL_PHYSICAL,
            'known_retained_local_lineage_union_hands': ctl.INITIAL_PHYSICAL + counts['new_physical_hands'],
            'per_arm_cumulative_physical_hands': by_arm, 'largest_single_endpoint_local_lineage_hands': max(by_arm.values()),
            'training_seed_lineages': 1, 'unique_attempt_namespaces': namespaces,
            'pretrained_standard10_environment_hands_not_inferred': True,
            'statistical_not_bitwise_worker_continuation': True, 'original_failed_attempt_wall_seconds': failed_wall,
            'all_training_attempt_wall_seconds': wall,
            'retained_physical_hands_per_training_wall_second': counts['new_physical_hands'] / wall,
            'evaluation_hands': stage_count * 65536, 'offline_samples': stage_count * 40000, 'slumbot_hands': 0}


def verify_job(directory, *, original_failed=False):
    ev.require(not original_failed or directory == OLD, 'only original interrupted job may exit1')
    process = ev.read_json(directory / 'process.json')
    ev.require(not ctl.owner_live(process), 'tracked job still live')
    terminal = ev.read_json(directory / 'termination.json')
    expected = 1 if original_failed else 0
    ev.require(terminal['exit_code'] == expected and not terminal['observer_errors'] and
               not terminal['remaining_observed_child_pids'], 'wrong or incomplete termination receipt')
    for pid, created in terminal['observed_children'].items():
        ev.require(not ctl.owner_live({'pid': int(pid), 'create_time': created}), 'tracked descendant still live')
    return {str(directory / name): ev.sha(directory / name) for name in ('process.json', 'termination.json', 'command.json')}


def merge_hashes(*mappings):
    result = {}
    for mapping in mappings:
        for path, digest in mapping.items():
            ev.require(path not in result or result[path] == digest, f'conflicting frozen input: {path}')
            result[path] = digest
    return result


def build_report():
    ready = readiness()
    ev.require(ready['ready'], ready['reason'])
    stage_count = 2 if ready['phase'] == FULL else 1
    original = ev.read_json(BASE / 'input_contract.json')
    recovery = ev.read_json(RECOVERY / 'input_contract.json')
    pipeline = ev.read_json(RECOVERY / 'pipeline_result.json')
    audit = ev.read_json(RECOVERY / 'interruption_audit.json')
    ev.require(audit['passed'] and audit['original_exit_code'] == 1 and
               audit['unknown_additional_worker_tail_hands'] is None, 'unqualified interruption audit')
    ev.require(pipeline['original_pipeline_result_not_fabricated'] and
               pipeline['interrupted_retained_attempt_audit'] == str(RECOVERY / 'interruption_audit.json'), 'lost interruption provenance')
    inputs = merge_hashes(original['input_sha256'], recovery['input_sha256'],
                          audit['input_sha256'], audit['frozen_interrupted_inputs'])
    ctl.check_hashes(inputs)
    inputs.update(verify_job(OLD, original_failed=True))
    completed, expected_jobs, receipts = pipeline['completed_attempts'], {OLD}, []
    expected_order = list(ctl.ORDER) if stage_count == 2 else list(ctl.ORDER[:2])
    ev.require([(r['arm'], r['stage']) for r in completed] == expected_order, 'wrong pipeline run coverage')
    directories = {(arm, stage): REMAINDER if (arm, stage) == ('static', 1) else BASE / f'{arm}_stage{stage}'
                   for arm, stage in expected_order}
    expected_jobs.update(directories.values())
    expected_jobs.update(BASE / f'{prefix}_{arm}_stage{stage}' for stage in range(1, stage_count + 1)
                         for arm in ('static', 'moving256') for prefix in ('job_eval', 'drift'))
    actual_jobs = {p.parent for root in (BASE, RECOVERY) for p in root.glob('*/process.json')}
    ev.require(actual_jobs == expected_jobs, 'unexpected or missing job receipt')
    for directory in expected_jobs - {OLD}:
        inputs.update(verify_job(directory))
    import torch
    torch.set_num_threads(1)
    helper = ctl.qualified_command_helper()
    final_counts = {}
    for row in completed:
        directory = directories[row['arm'], row['stage']]
        expected_jobs.add(directory)
        inputs.update(verify_job(directory))
        ev.require(row == ev.read_json(directory / 'verification.json') and row['passed'], 'run verification differs')
        initial = ev.read_json(directory / 'initial_resume_gate.json')
        required_gates = {'model', 'optimizer', 'ppo_replay_entries', 'ppo_replay_rng_state',
                          'ppo_replay_cumulative_rows', 'pool_snapshots', 'pool_strategy',
                          'pool_active_metadata', 'pool_candidate_history', 'iteration',
                          'transition_counter', 'physical_counter', 'fresh_namespace'}
        required_gates.add('legacy_rng_bootstrap_declared' if (row['arm'], row['stage']) == ('moving256', 1)
                           else 'main_rng_restored_exact')
        ev.require(initial['passed'] and set(initial['gates']) == required_gates and
                   all(initial['gates'].values()), 'initial state restoration failed')
        ev.require(initial['initial_sha256'] == ev.sha(directory / 'initial_resumed_state.pt') and
                   initial['parent_sha256'] == row['parent_checkpoint_sha256'], 'initial gate state binding differs')
        ctl.check_hashes(row['checkpoint_windows_sha256'])
        ev.require(ev.sha(directory / 'latest.pt') == row['checkpoint_sha256'], 'endpoint changed')
        for name in ('verification.json', 'initial_resume_gate.json', 'initial_resumed_state.pt',
                     'latest.pt', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
            inputs[str(directory / name)] = ev.sha(directory / name)
        checkpoint = torch.load(directory / 'latest.pt', map_location='cpu', weights_only=False)
        final_counts[row['arm']] = checkpoint['environment_hand_accounting']['completed_hands']
        attempt = checkpoint['fixed_deal_attempt']
        receipt = helper.helpers.load_attempt(Path(attempt['path']), attempt['sha256'])
        ev.require(receipt == attempt['receipt'] and receipt['namespace'] == row['namespace'] and
                   receipt['parent_checkpoint_sha256'] == row['parent_checkpoint_sha256'], 'receipt/parent mismatch')
        inputs[attempt['path']] = attempt['sha256']
        receipts.append({'directory': str(directory), 'namespace': receipt['namespace'], 'sha256': attempt['sha256']})
    old_checkpoint = torch.load(OLD / 'latest.pt', map_location='cpu', weights_only=False)
    old_attempt = old_checkpoint['fixed_deal_attempt']
    old_receipt = helper.helpers.load_attempt(Path(old_attempt['path']), old_attempt['sha256'])
    ev.require(old_receipt == old_attempt['receipt'] and old_receipt['namespace'] == audit['namespace'], 'failed attempt receipt mismatch')
    inputs[old_attempt['path']] = old_attempt['sha256']
    corpus, stages = dict(original['prior_common_deck_corpus']), {}
    for stage in range(1, stage_count + 1):
        hashes = {arm: ev.sha(directories[arm, stage] / 'latest.pt') for arm in ('static', 'moving256')}
        stages[stage] = ev.aggregate_stage(stage, BASE, ctl.PARENT_SHA, hashes, original['anchors'], corpus)
        stage_path = BASE / f'stage{stage}_analysis.json'
        ev.require(stages[stage] == ev.read_json(stage_path), 'stage/raw result mismatch')
        inputs[str(stage_path)] = ev.sha(stage_path)
        inputs.update(stages[stage]['input_sha256'])
        for arm in ('static', 'moving256'):
            raw = BASE / f'eval_{arm}_stage{stage}/common_deck_pairs.jsonl.gz'
            corpus[str(raw)] = ev.sha(raw)
            for prefix in ('job_eval', 'drift'):
                job = BASE / f'{prefix}_{arm}_stage{stage}'
                expected_jobs.add(job)
                inputs.update(verify_job(job))
    ev.require(stages[1]['broad_collapse'] is (stage_count == 1), 'preregistered collapse gate not followed')
    counts = accounting(completed, retained_partial(audit), audit, ev.read_json(OLD / 'termination.json')['wall_seconds'], stage_count)
    ev.require(counts['per_arm_cumulative_physical_hands'] == final_counts and
               all(n >= ctl.TARGETS[stage_count] for n in final_counts.values()), 'retained endpoint dose mismatch')
    ev.require(ev.sha(cross.SEED1_REPORT) == cross.SEED1_SHA, 'completed Seed1 report changed')
    ev.require(ev.read_json(cross.SEED1_BASE / 'experiment.json')['status'] == 'COMPLETED', 'Seed1 not finished')
    one = ev.read_json(cross.SEED1_REPORT)
    s1, decks1 = cross.verify_raw_stages(one, 'seed1', inputs)
    s3, decks3 = cross.verify_raw_stages({'passed': True, 'stages': stages}, 'seed3', inputs)
    ev.require(decks1.isdisjoint(decks3), 'cross-seed decks overlap')
    inputs[str(cross.SEED1_REPORT)] = cross.SEED1_SHA
    for name in ('pipeline_result.json', 'interruption_audit.json', 'input_contract.json', 'ownership.json', 'recovery_preflight.json'):
        inputs[str(RECOVERY / name)] = ev.sha(RECOVERY / name)
    ctl.check_hashes(inputs)
    return {'schema': 'cardpilot.seed3.recovered_two_seed_report.v1', 'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'phase': ready['phase'], 'command': [sys.executable, *sys.argv],
        'accounting': counts, 'stages': stages, 'geometric_change': normal.geometric_report(stages) if stage_count == 2 else None,
        'equal_seed_synthesis': cross.combine({'seed1': s1, 'seed3': s3}), 'source_accounting_seed1': one['accounting'],
        'accounting_comparison_warning': 'Seed1 historical new_training_hands field counts retained hands; current Seed3 also reports observed unsaved hands separately. Do not blindly sum differently scoped fields.',
        'attempt_receipt_audits': receipts, 'cross_seed_deck_overlap': 0, 'input_sha256': inputs,
        'source_sha256': {str(p): ev.sha(p) for p in (Path(__file__).resolve(), Path(cross.__file__), Path(normal.__file__))},
        'provenance_limitations': 'Independent Seed3 continuation conditional on its qualified 4M parent; no blanket proof of all older boundaries. The moving-stage1 legacy parent uses declared main-RNG bootstrap. Resume is statistical, not bitwise worker continuation.',
        'scope_label_clarification': 'Frozen Seed3 raw-stage ci_scope label says Seed1 by copy; actual Seed3 identity is enforced by parent SHA and evaluation seeds. Original source/summary labels are preserved.',
        'analysis_added_training_hands': 0, 'analysis_added_evaluation_hands': 0,
        'goal_achieved': False, 'automatic_final_slumbot_test_authorized': False,
        'next_decision': 'RESEARCHER_REVIEW_OF_TWO_SEED_BREADTH_SLOPES_COST_AND_UNCONFIRMED_EXTERNAL_TRANSLATION'}


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
    ev.require(not args.out.exists(), 'preserve completed reports')
    value = build_report()
    ctl.write_new(args.out, value)
    print(json.dumps({'passed': True, 'accounting': value['accounting'], 'next_decision': value['next_decision']}, indent=2))


if __name__ == '__main__':
    main()
