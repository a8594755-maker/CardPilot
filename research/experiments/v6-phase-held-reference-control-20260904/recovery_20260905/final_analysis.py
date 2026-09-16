"""Read-only terminal reaggregation with interrupted-prefix accounting explicit."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(BASE))
import run_control as ctl
import control_evidence as ev

GEOMETRIC = BASE / 'post_analysis/summarize_geometric_control.py'
REMAINDER = HERE / 'static_stage2_remainder'


def readiness():
    for root in (BASE, HERE):
        path = root / 'ownership.json'
        if path.exists() and ctl.owner_live(ev.read_json(path)):
            return {'ready': False, 'reason': 'exact controller owner still live'}
    path = HERE / 'pipeline_result.json'
    if not path.exists():
        return {'ready': False, 'reason': 'recovery terminal result absent'}
    result = ev.read_json(path)
    return {'ready': result['phase'] == 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS', 'phase': result['phase']}


def accounting(completed, partial, interruption, process):
    ev.require([(row['arm'], row['stage']) for row in completed] == list(ctl.ORDER), 'completed attempt order changed')
    ev.require(partial['arm'] == 'static' and partial['stage'] == 2 and partial['retained_boundary_verified'], 'wrong interrupted prefix')
    ev.require(not partial['terminal_attempt'] and partial['unknown_crash_suffix_hands'] is None, 'unknown crash suffix mislabeled')
    namespaces = [row['namespace'] for row in completed] + [partial['namespace']]
    ev.require(len(set(namespaces)) == 5, 'attempt namespace reused')
    ev.require(all(row['unknown_crash_suffix_hands'] == 0 and row['passed'] for row in completed), 'unverified completed attempt')
    counts = {key: sum(row[key] for row in completed) + partial[key]
              for key in ('new_physical_hands', 'new_transition_hands', 'new_replay_rows', 'new_no_decision_hands')}
    by_arm = {arm: ctl.INITIAL_PHYSICAL + sum(row['new_physical_hands'] for row in completed if row['arm'] == arm)
              + (partial['new_physical_hands'] if arm == 'static' else 0) for arm in ('static', 'moving256')}
    tails = sum(row['residual_worker_tail_hands'] for row in completed) + partial['retained_worker_tail_hands']
    ev.require(counts['new_physical_hands'] == counts['new_transition_hands'] + counts['new_no_decision_hands'] + tails,
               'physical/transition/no-decision/tail accounting fails')
    start = datetime.fromisoformat(process['started_at'])
    checkpoint = datetime.fromisoformat(partial['last_checkpoint_utc'])
    absent = datetime.fromisoformat(interruption['audited_at'])
    lower, upper = (checkpoint - start).total_seconds(), (absent - start).total_seconds()
    ev.require(0 < lower <= upper, 'invalid interrupted wall bounds')
    known_wall = sum(row['subprocess_wall_seconds'] for row in completed)
    return {
        'new_training_hands': counts['new_physical_hands'], 'new_transition_hands': counts['new_transition_hands'],
        'new_replay_rows_not_new_hands': counts['new_replay_rows'], 'new_no_decision_hands': counts['new_no_decision_hands'],
        'retained_worker_tail_hands': tails, 'unknown_crash_suffix_hands': None,
        'actual_executed_training_hands_are_at_least_retained_count': True,
        'shared_parent_physical_hands': ctl.INITIAL_PHYSICAL,
        'known_local_lineage_union_physical_hands': ctl.INITIAL_PHYSICAL + counts['new_physical_hands'],
        'per_arm_cumulative_physical_hands': by_arm, 'largest_single_endpoint_local_lineage_hands': max(by_arm.values()),
        'training_seed_lineages': 1, 'statistically_matched_initialization_not_independent_seeds': True,
        'statistical_not_bitwise_worker_continuation': True, 'unique_attempt_namespaces': namespaces,
        'pretrained_standard10_environment_hands_not_inferred': True,
        'completed_attempt_wall_seconds': known_wall,
        'interrupted_attempt_wall_seconds': None,
        'interrupted_attempt_wall_bounds_seconds': [lower, upper],
        'all_training_attempt_wall_bounds_seconds': [known_wall + lower, known_wall + upper],
        'retained_physical_hands_per_training_wall_second_bounds': [
            counts['new_physical_hands'] / (known_wall + upper), counts['new_physical_hands'] / (known_wall + lower)],
        'wall_bounds_method': 'Last saved checkpoint timestamp to first absence in preserved audit; conservative upper bound includes possible post-exit idle time. Unknown crash work not credited.',
        'evaluation_hands': 131072, 'offline_samples': 80000, 'slumbot_hands': 0}


def build_report():
    ready = readiness()
    ev.require(ready['ready'], str(ready))
    original = ev.read_json(BASE / 'input_contract.json')
    recovery = ev.read_json(HERE / 'input_contract.json')
    interruption = ev.read_json(HERE / 'interruption_audit.json')
    pipeline = ev.read_json(HERE / 'pipeline_result.json')
    ctl.check_hashes(original['input_sha256'])
    ctl.check_hashes(recovery['input_sha256'])
    ev.require(pipeline['interrupted_retained_attempt'] == interruption['partial_attempt'], 'interruption evidence changed')
    ev.require(pipeline['unknown_crash_suffix_hands'] is None and pipeline['original_pipeline_result_not_fabricated'], 'lost interruption qualification')
    completed = pipeline['completed_attempts']
    directories = [BASE / name for name in ('static_stage1', 'moving256_stage1', 'moving256_stage2')] + [REMAINDER]
    helper = ctl.qualified_command_helper()
    inputs, receipt_audits = {}, []
    import torch
    torch.set_num_threads(1)
    for directory, row in zip(directories, completed):
        ev.require(row == ev.read_json(directory / 'verification.json') and row['passed'], 'verification differs from pipeline')
        ev.require(not ctl.owner_live(ev.read_json(directory / 'process.json')), 'trainer still live')
        termination = ev.read_json(directory / 'termination.json')
        ev.require(termination['exit_code'] == 0 and not termination['observer_errors'] and
                   not termination['remaining_observed_child_pids'], 'termination not clean')
        ev.require(not helper.live_known_children({int(k): v for k, v in termination['observed_children'].items()}), 'worker identity remains live')
        ctl.check_hashes(row['checkpoint_windows_sha256'])
        ev.require(ctl.sha(directory / 'latest.pt') == row['checkpoint_sha256'], 'endpoint SHA changed')
        for name in ('verification.json', 'termination.json', 'latest.pt', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
            inputs[str(directory / name)] = ctl.sha(directory / name)
    for directory in directories + [BASE / 'static_stage2']:
        checkpoint = torch.load(directory / 'latest.pt', map_location='cpu', weights_only=False)
        attempt = checkpoint['fixed_deal_attempt']
        receipt = helper.helpers.load_attempt(Path(attempt['path']), attempt['sha256'])
        parent = ev.read_json(directory / 'parent_contract.json')
        ev.require(receipt == attempt['receipt'] and receipt['namespace'] == checkpoint['config']['fixed_training_deal_namespace'] and
                   receipt['parent_checkpoint_sha256'] == parent['sha256'], 'attempt receipt/parent identity mismatch')
        inputs[attempt['path']] = attempt['sha256']
        receipt_audits.append({'directory': str(directory), 'namespace': receipt['namespace'], 'receipt_sha256': attempt['sha256']})
    ev.require(len({row['namespace'] for row in receipt_audits}) == 5, 'namespace reused across interrupted and completed attempts')
    corpus, stages = dict(original['prior_common_deck_corpus']), {}
    for stage in (1, 2):
        endpoint = {arm: (REMAINDER / 'latest.pt' if (arm, stage) == ('static', 2)
                         else BASE / f'{arm}_stage{stage}/latest.pt') for arm in ('static', 'moving256')}
        stage_result = ev.aggregate_stage(stage, BASE, ctl.PARENT_SHA,
            {arm: ctl.sha(path) for arm, path in endpoint.items()}, original['anchors'], corpus)
        ev.require(stage_result == ev.read_json(BASE / f'stage{stage}_analysis.json'), 'raw stage reaggregation differs')
        stages[stage] = stage_result
        inputs.update(stage_result['input_sha256'])
        for arm in ('static', 'moving256'):
            path = BASE / f'eval_{arm}_stage{stage}/common_deck_pairs.jsonl.gz'
            corpus[str(path)] = ctl.sha(path)
        for arm in ('static', 'moving256'):
            for directory in (BASE / f'job_eval_{arm}_stage{stage}', BASE / f'drift_{arm}_stage{stage}'):
                ev.require(not ctl.owner_live(ev.read_json(directory / 'process.json')), 'evaluation still live')
                terminated = ev.read_json(directory / 'termination.json')
                ev.require(terminated['exit_code'] == 0 and not terminated['observer_errors'], 'evaluation termination invalid')
                inputs[str(directory / 'termination.json')] = ctl.sha(directory / 'termination.json')
    ev.require(stages[1]['broad_collapse'] is False, 'stage2 was not eligible')
    counts = accounting(completed, pipeline['interrupted_retained_attempt'], interruption,
                        ev.read_json(BASE / 'static_stage2/process.json'))
    final = torch.load(REMAINDER / 'latest.pt', map_location='cpu', weights_only=False)
    ev.require(counts['per_arm_cumulative_physical_hands']['static'] == final['environment_hand_accounting']['completed_hands'], 'recovered lineage counted twice or reset')
    ev.require(all(value >= ctl.TARGETS[2] for value in counts['per_arm_cumulative_physical_hands'].values()), 'target incomplete')
    geometric = ev.module_at('recovered_geometric_summary', GEOMETRIC)
    for directory, names in ((HERE, ('pipeline_result.json', 'interruption_audit.json', 'ownership.json', 'input_contract.json')),
                             (BASE, ('stage1_analysis.json', 'stage2_analysis.json'))):
        for name in names:
            inputs[str(directory / name)] = ctl.sha(directory / name)
    ctl.check_hashes(inputs)
    return {'schema': 'cardpilot.phase_reference.recovered_post_terminal_report.v1', 'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'accounting': counts, 'stages': stages,
        'geometric_change': geometric.geometric_report(stages), 'attempt_receipt_audits': receipt_audits,
        'source_sha256': {str(Path(__file__)): ctl.sha(__file__), str(GEOMETRIC): ctl.sha(GEOMETRIC)},
        'input_sha256': inputs, 'goal_achieved': False, 'analysis_added_training_hands': 0,
        'analysis_added_evaluation_hands': 0, 'unknown_interrupted_suffix_not_recovered_or_counted': True,
        'next_decision': 'PREREGISTER_BOTH_ENDPOINT_EXTERNAL_DEVELOPMENT_COMPARISON',
        'automatic_final_slumbot_test_authorized': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-ready', action='store_true')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.check_ready:
        print(json.dumps(readiness(), indent=2))
    else:
        if args.out is None:
            parser.error('--out required')
        ev.require(not args.out.exists(), 'refusing to overwrite report')
        result = build_report()
        ctl.write_new(args.out, result)
        print(json.dumps({'passed': result['passed'], 'accounting': result['accounting'], 'next_decision': result['next_decision']}, indent=2))
