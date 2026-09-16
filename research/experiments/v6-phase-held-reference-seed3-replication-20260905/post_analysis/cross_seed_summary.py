"""Post-terminal, equal-seed descriptive synthesis; no model calls or selection."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import math
from pathlib import Path
import sys

import summarize_geometric_control as report

ev, ctl, BASE, ROOT = report.ev, report.ctl, report.BASE, report.ROOT
SEED1_BASE = ROOT / 'research/experiments/v6-phase-held-reference-control-20260904'
SEED1_REPORT = SEED1_BASE / 'recovery_20260905/post_terminal_report.json'
SEED1_SHA = '461a74b29504eb70d7156f61f2f3b693d4c6a6cb609ccc213a3bd28ade0a65c9'
SEEDS = {'seed1', 'seed3'}


def equal_seed_stat(values):
    ev.require(set(values) == SEEDS, 'exactly the two prespecified training seeds required')
    for value in values.values():
        ev.require(all(math.isfinite(float(value[k])) for k in ('bb100', 'ci95_halfwidth_bb100')),
                   'nonfinite seed statistic')
        ev.require(value['ci95_halfwidth_bb100'] >= 0, 'negative seed interval width')
    means = [float(v['bb100']) for v in values.values()]
    mean = sum(means) / 2
    half = math.hypot(*(float(v['ci95_halfwidth_bb100']) for v in values.values())) / 2
    return {'bb100': mean, 'conditional_ci95_low_bb100': mean - half,
            'conditional_ci95_high_bb100': mean + half, 'conditional_ci95_halfwidth_bb100': half,
            'by_seed': values, 'seed_weights': {'seed1': .5, 'seed3': .5},
            'training_seed_count': 2, 'both_seed_point_estimates_positive': all(x > 0 for x in means),
            'both_seed_point_estimates_negative': all(x < 0 for x in means),
            'observed_seed_range_bb100': [min(means), max(means)],
            'training_seed_population_ci95': None,
            'ci_scope': 'Normal sampling interval for the equal mean of these two fixed lineages on disjoint evaluation cohorts; not training-seed population uncertainty. Shared pretrained initialization and only two seeds preclude a reliable general stability claim.'}


def equal_seed_breadth(values):
    ev.require(set(values) == SEEDS, 'missing training seed')
    output = {'pooled': equal_seed_stat({s: v['pooled'] for s, v in values.items()})}
    for group, expected in (('by_anchor', set(ev.ANCHORS)), ('by_seat', {'0', '1'})):
        ev.require(all(set(v[group]) == expected for v in values.values()), 'incomplete breadth')
        output[group] = {key: equal_seed_stat({s: v[group][key] for s, v in values.items()})
                         for key in sorted(expected)}
    return output


def combine(stages):
    ev.require(set(stages) == SEEDS and set(stages['seed1']) == {1, 2}
               and set(stages['seed3']) in ({1}, {1, 2}), 'invalid completed stage coverage')
    common = sorted(set(stages['seed1']) & set(stages['seed3']))
    pooled = {}
    for stage in common:
        pooled[stage] = {'endpoint_minus_original4M': {
            arm: equal_seed_breadth({s: stages[s][stage]['endpoint_minus_original4M'][arm] for s in SEEDS})
            for arm in ('static', 'moving256')},
            'moving_minus_static': equal_seed_breadth({s: stages[s][stage]['moving_minus_static'] for s in SEEDS})}
    geometry = {s: report.geometric_report(v) for s, v in stages.items() if set(v) == {1, 2}}
    slopes = None
    if set(geometry) == SEEDS:
        slopes = {'endpoint_minus_original4M_slope_change': {
            arm: equal_seed_breadth({s: geometry[s]['endpoint_minus_original4M_slope_change'][arm] for s in SEEDS})
            for arm in ('static', 'moving256')},
            'moving_minus_static_contrast_change': equal_seed_breadth({
                s: geometry[s]['moving_minus_static_contrast_change'] for s in SEEDS})}
    return {'by_stage': pooled, 'per_seed_geometric_change': geometry, 'equal_seed_geometric_change': slopes,
            'missing_stage2_reason': None if slopes is not None else
                'Seed3 stopped at its preregistered stage1 collapse gate; no imputed stage2 endpoint or two-seed later slope.',
            'method_superiority_established': False, 'automatic_promotion': False,
            'scope': 'Internal fixed-anchor development evidence only. Initial reference rebasing plus cadence is one package. Seed1 external translation remains unconfirmed; no fresh Slumbot evidence is added here.'}


def verify_raw_stages(value, label, inputs):
    stages = {int(k): v for k, v in value['stages'].items()}
    ev.require(value['passed'] and set(stages) in ({1}, {1, 2}), 'incomplete source report')
    seen_decks = set()
    for stage, data in stages.items():
        arm_rows = {}
        for arm in ('static', 'moving256'):
            candidates = [Path(p) for p in data['input_sha256'] if
                          Path(p).name == 'common_deck_pairs.jsonl.gz'
                          and Path(p).parent.name == f'eval_{arm}_stage{stage}']
            ev.require(len(candidates) == 1, 'ambiguous raw evidence path')
            path = candidates[0]
            digest = data['input_sha256'][str(path)]
            ev.require(ev.sha(path) == digest, 'raw evidence changed')
            rows = ev.read_rows(path)
            ev.require(len(rows) == len(ev.validated_map(rows)) == 8192, 'wrong raw pair count')
            ev.require(ev.summarize_rows(rows) == data['endpoint_minus_original4M'][arm],
                       'endpoint summary does not match raw evidence')
            ev.require(ev.sha(path) == digest, 'raw changed during read')
            arm_rows[arm] = rows
            inputs[str(path)] = digest
        joined = ev.join_arms(arm_rows['static'], arm_rows['moving256'])
        ev.require(ev.summarize_rows(joined) == data['moving_minus_static'], 'contrast raw mismatch')
        decks = {tuple(r['deck']) for r in arm_rows['static']}
        ev.require(seen_decks.isdisjoint(decks), f'{label} stage cohorts overlap')
        seen_decks.update(decks)
    return stages, seen_decks


def build_report(seed3_path):
    ready = report.readiness(BASE)
    ev.require(ready['ready'], ready['reason'])
    ev.require(ev.sha(SEED1_REPORT) == SEED1_SHA, 'completed Seed1 report changed')
    one, three = ev.read_json(SEED1_REPORT), ev.read_json(seed3_path)
    ev.require(ev.read_json(SEED1_BASE / 'experiment.json')['status'] == 'COMPLETED', 'Seed1 not finished')
    ev.require(three['phase'] == ready['phase'], 'Seed3 report/terminal phase mismatch')
    expected_stages = {1, 2} if ready['phase'] == 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS' else {1}
    ev.require({int(k) for k in three['stages']} == expected_stages, 'Seed3 report stage coverage')
    inputs = {str(SEED1_REPORT): SEED1_SHA, str(seed3_path): ev.sha(seed3_path)}
    inputs.update(report.verify_all_jobs(BASE, len(expected_stages)))
    for value in (one, three):
        ctl.check_hashes(value['input_sha256'])
        inputs.update(value['input_sha256'])
    stages1, decks1 = verify_raw_stages(one, 'seed1', inputs)
    stages3, decks3 = verify_raw_stages(three, 'seed3', inputs)
    ev.require(decks1.isdisjoint(decks3), 'cross-seed evaluation deck overlap')
    result = combine({'seed1': stages1, 'seed3': stages3})
    ctl.check_hashes(inputs)
    return {'schema': 'cardpilot.phase_reference.two_seed_synthesis.v1', 'passed': True,
            'created_at': datetime.now(timezone.utc).isoformat(), 'command': [sys.executable, *sys.argv],
            'summary': result, 'source_accounting_by_seed': {'seed1': one['accounting'], 'seed3': three['accounting']},
            'cross_seed_deck_overlap': 0, 'input_sha256': inputs,
            'source_sha256': {str(p): ev.sha(p) for p in (Path(__file__).resolve(), Path(report.__file__).resolve())},
            'analysis_added_training_hands': 0, 'analysis_added_evaluation_hands': 0,
            'goal_achieved': False, 'next_decision': 'RESEARCHER_REVIEW_OF_BREADTH_SLOPES_COST_AND_EXTERNAL_TRANSLATION'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed3-report', type=Path, default=BASE / 'post_terminal_report.json')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    ev.require(not args.out.exists(), 'refusing to overwrite report')
    value = build_report(args.seed3_report)
    ctl.write_new(args.out, value)
    print('PASS: two-seed conditional synthesis; no automatic promotion or final benchmark claim')


if __name__ == '__main__':
    main()
