"""Post-terminal raw reaggregation; never launches a model or edits the live record."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(BASE))
import control_evidence as ev
import run_control as ctl


def readiness(base):
    owner = ev.read_json(base / 'ownership.json')
    if ctl.owner_live(owner):
        return {'ready': False, 'reason': 'controller is live; no concurrent post-analysis or logger mutation'}
    result_path = base / 'pipeline_result.json'
    if not result_path.exists():
        return {'ready': False, 'reason': 'terminal pipeline result absent; interruption/error needs scoped review'}
    result = ev.read_json(result_path)
    phase = result['phase']
    valid = phase in ('EVIDENCE_READY_FOR_RESEARCH_ANALYSIS', 'PREREGISTERED_BROAD_COLLAPSE_RESEARCH_REVIEW')
    return {'ready': valid, 'phase': phase, 'reason': 'terminal evidence available' if valid else 'unexpected terminal phase'}


def independent_stage_difference(earlier, later):
    """Difference of independent cohort means, not a new paired match sample."""
    for value in (earlier, later):
        ev.require(int(value['samples']) > 1, 'insufficient cohort observations')
        ev.require(all(math.isfinite(float(value[k])) for k in ('bb100', 'ci95_halfwidth_bb100')),
                   'nonfinite mean/interval')
        ev.require(value['ci95_halfwidth_bb100'] >= 0, 'negative interval width')
    mean = later['bb100'] - earlier['bb100']
    half = math.hypot(earlier['ci95_halfwidth_bb100'], later['ci95_halfwidth_bb100'])
    return {'bb100': mean, 'descriptive_ci95_low_bb100': mean - half,
            'descriptive_ci95_high_bb100': mean + half, 'ci95_halfwidth_bb100': half,
            'earlier_cohort_samples': earlier['samples'], 'later_cohort_samples': later['samples'],
            'direct_paired_stage1_vs_stage2_hands': 0,
            'method': 'difference of cohort means; sum of independent estimated variances'}


def difference_summary(earlier, later):
    result = {'pooled': independent_stage_difference(earlier['pooled'], later['pooled'])}
    for group, expected in (('by_anchor', set(ev.ANCHORS)), ('by_seat', {'0', '1'})):
        ev.require(set(earlier[group]) == set(later[group]) == expected, 'missing or mismatched breadth group')
        result[group] = {key: independent_stage_difference(earlier[group][key], later[group][key])
                         for key in earlier[group]}
    return result


def geometric_report(stages):
    ev.require(set(stages) == {1, 2}, 'both completed geometric stages required')
    return {
        'endpoint_minus_original4M_slope_change': {
            arm: difference_summary(stages[1]['endpoint_minus_original4M'][arm],
                                    stages[2]['endpoint_minus_original4M'][arm])
            for arm in ('static', 'moving256')},
        'moving_minus_static_contrast_change': difference_summary(stages[1]['moving_minus_static'],
                                                                  stages[2]['moving_minus_static']),
        'interpretation': 'Stage2 minus stage1, each estimated on its own fresh deck cohort. Original4M cancels in expectation, not via matched raw outcomes across stages.',
        'interval_limitations': 'Descriptive normal intervals conditional on fixed endpoints/anchors and independent cohort sampling; no multiplicity or continuation-selection adjustment and no training-seed population claim.',
        'initial_reference_rebasing_is_part_of_treatment': True,
        'automatic_promotion': False,
    }


def accounting_from_runs(runs):
    ev.require(bool(runs), 'no completed runs')
    namespaces = [r['namespace'] for r in runs]
    ev.require(len(namespaces) == len(set(namespaces)), 'attempt namespace reused')
    total_physical = sum(r['new_physical_hands'] for r in runs)
    total_transition = sum(r['new_transition_hands'] for r in runs)
    by_arm = {}
    for arm in ('static', 'moving256'):
        selected = [r for r in runs if r['arm'] == arm]
        ev.require(bool(selected) and [r['stage'] for r in selected] == list(range(1, len(selected) + 1)),
                   'arm stage gap/reordering')
        by_arm[arm] = ctl.INITIAL_PHYSICAL + sum(r['new_physical_hands'] for r in selected)
    return {'new_training_hands': total_physical, 'new_transition_hands': total_transition,
            'new_replay_rows_not_new_hands': sum(r['new_replay_rows'] for r in runs),
            'new_no_decision_hands': sum(r['new_no_decision_hands'] for r in runs),
            'residual_worker_tail_hands': sum(r['residual_worker_tail_hands'] for r in runs),
            'unknown_crash_suffix_hands': sum(r['unknown_crash_suffix_hands'] for r in runs),
            'shared_parent_physical_hands': ctl.INITIAL_PHYSICAL,
            'known_local_lineage_union_physical_hands': ctl.INITIAL_PHYSICAL + total_physical,
            'per_arm_cumulative_physical_hands': by_arm,
            'largest_single_endpoint_local_lineage_hands': max(by_arm.values()),
            'training_seed_lineages': 1, 'statistically_matched_initialization_not_independent_seeds': True,
            'sum_arm_cumulative_counts_double_counts_shared_parent': True,
            'pretrained_standard10_environment_hands_not_inferred': True,
            'training_subprocess_wall_seconds': sum(r['subprocess_wall_seconds'] for r in runs),
            'training_physical_hands_per_wall_second': total_physical / sum(r['subprocess_wall_seconds'] for r in runs)}


def build_report(base):
    ready = readiness(base)
    ev.require(ready['ready'], ready['reason'])
    contract = ev.read_json(base / 'input_contract.json')
    ctl.check_hashes(contract['input_sha256'])
    pipeline = ev.read_json(base / 'pipeline_result.json')
    stage_count = 2 if pipeline['phase'] == 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS' else 1
    expected_order = list(ctl.ORDER) if stage_count == 2 else list(ctl.ORDER[:2])
    ev.require([(r['arm'], r['stage']) for r in pipeline['runs']] == expected_order, 'unexpected run order/count')
    inputs = {str(base / name): ev.sha(base / name) for name in ('pipeline_result.json', 'input_contract.json', 'ownership.json')}
    for run in pipeline['runs']:
        directory = base / f'{run["arm"]}_stage{run["stage"]}'
        verification = ev.read_json(directory / 'verification.json')
        ev.require(verification == run and run['passed'], 'verification/pipeline mismatch')
        process = ev.read_json(directory / 'process.json')
        ev.require(not ctl.owner_live(process), 'trainer still live')
        termination = ev.read_json(directory / 'termination.json')
        ev.require(termination['exit_code'] == 0 and not termination['observer_errors'] and
                   not termination['remaining_observed_child_pids'], 'incomplete termination evidence')
        helper = ctl.qualified_command_helper()
        children = {int(pid): created for pid, created in termination['observed_children'].items()}
        ev.require(not helper.live_known_children(children), 'surviving original child identity')
        ev.require(ev.sha(directory / 'latest.pt') == run['checkpoint_sha256'], 'endpoint changed')
        ctl.check_hashes(run['checkpoint_windows_sha256'])
        for name in ('verification.json', 'termination.json', 'latest.pt', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
            path = directory / name
            inputs[str(path)] = ev.sha(path)
    record = ev.read_json(base / 'experiment.json')
    for raw_path, description in record['artifact_integrity'].items():
        path = ROOT / raw_path
        if description.get('type') == 'file':
            ev.require(ev.sha(path) == description['sha256'], f'logged artifact changed: {path}')
    corpus, stages = dict(contract['prior_common_deck_corpus']), {}
    for stage in range(1, stage_count + 1):
        hashes = {arm: ev.sha(base / f'{arm}_stage{stage}/latest.pt') for arm in ('static', 'moving256')}
        recomputed = ev.aggregate_stage(stage, base, ctl.PARENT_SHA, hashes, contract['anchors'], corpus)
        path = base / f'stage{stage}_analysis.json'
        ev.require(recomputed == ev.read_json(path), 'stage summary differs from original raw reaggregation')
        stages[stage] = recomputed
        inputs[str(path)] = ev.sha(path)
        inputs.update(recomputed['input_sha256'])
        for arm in ('static', 'moving256'):
            raw = base / f'eval_{arm}_stage{stage}/common_deck_pairs.jsonl.gz'
            corpus[str(raw)] = ev.sha(raw)
    ev.require(stages[1]['broad_collapse'] is (stage_count == 1), 'continuation differs from preregistered gate')
    counts = accounting_from_runs(pipeline['runs'])
    counts.update(evaluation_hands=stage_count * 65536, offline_samples=stage_count * 40000, slumbot_hands=0)
    ctl.check_hashes(inputs)
    return {'schema': 'cardpilot.phase_reference.post_terminal_report.v1', 'passed': True,
            'created_at': datetime.now(timezone.utc).isoformat(), 'phase': pipeline['phase'],
            'command': [sys.executable, *sys.argv], 'accounting': counts, 'stages': stages,
            'geometric_change': geometric_report(stages) if stage_count == 2 else None,
            'source_sha256': {str(Path(__file__).resolve()): ev.sha(__file__)}, 'input_sha256': inputs,
            'analysis_added_training_hands': 0, 'analysis_added_evaluation_hands': 0,
            'goal_achieved': False, 'automatic_final_slumbot_test_authorized': False,
            'next_decision': 'PREREGISTER_BOTH_ENDPOINT_EXTERNAL_DEVELOPMENT_COMPARISON' if stage_count == 2 else
                             'REVIEW_PREREGISTERED_BROAD_COLLAPSE_WITHOUT_WHOLE_FAMILY_IMPOSSIBILITY_CLAIM'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-ready', action='store_true')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.check_ready:
        print(json.dumps(readiness(BASE), indent=2))
        return
    if args.out is None:
        parser.error('--out is required for post-terminal reaggregation')
    ev.require(not args.out.exists(), 'refusing to overwrite a completed report')
    report = build_report(BASE)
    ctl.write_new(args.out, report)
    print(json.dumps({'passed': True, 'accounting': report['accounting'], 'next_decision': report['next_decision']}, indent=2))


if __name__ == '__main__':
    main()
