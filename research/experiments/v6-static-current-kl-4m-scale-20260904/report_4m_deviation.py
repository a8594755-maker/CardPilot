"""Scoped outcome-blind 4M interpretation; never rewrite a historical report."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT / 'scripts/alpha_holdem'))
from aggregate_v6_static_current_kl_262k import ANCHORS, read_rows, sha256_path, summarize_rows


def broad_reversal(summary):
    """The actual 4M preregistration says OR, unlike the old shared helper."""
    return summary['both_seats_negative'] or sum(
        row['bb100'] < 0 for row in summary['by_anchor'].values()) >= 3


def verify_raw_arithmetic(rows):
    for row in rows:
        if sorted(row['deck']) != list(range(52)):
            raise ValueError('invalid physical deck')
        control, treatment = row['control_rewards_bb'], row['treatment_rewards_bb']
        if len(control) != 2 or len(treatment) != 2:
            raise ValueError('both seats required')
        if not all(math.isfinite(value) for value in control + treatment):
            raise ValueError('nonfinite terminal reward')
        difference = [treatment[seat] - control[seat] for seat in (0, 1)]
        expected = {
            'control_pair_mean_bb': sum(control) / 2,
            'treatment_pair_mean_bb': sum(treatment) / 2,
            'treatment_minus_control_pair_mean_bb': sum(difference) / 2,
        }
        recorded_difference = row['treatment_minus_control_rewards_bb']
        if len(recorded_difference) != 2 or any(not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)
            for a, b in zip(recorded_difference, difference)) or any(
            not math.isclose(row[key], value, rel_tol=1e-12, abs_tol=1e-9) for key, value in expected.items()
        ):
            raise ValueError('stored paired outcome differs from raw terminal rewards')


def descriptive_report(rows_by_seed, drift):
    if set(rows_by_seed) != {1, 2, 3} or set(drift) != {'1', '2', '3'}:
        raise ValueError('all three preregistered seeds are mandatory')
    for rows in rows_by_seed.values():
        verify_raw_arithmetic(rows)
    by_seed = {str(seed): summarize_rows(rows_by_seed[seed]) for seed in (1, 2, 3)}
    combined = summarize_rows([row for seed in (1, 2, 3) for row in rows_by_seed[seed]])
    unaffected = summarize_rows([row for seed in (1, 3) for row in rows_by_seed[seed]])
    slopes = [by_seed[str(seed)]['pooled']['bb100'] for seed in (1, 2, 3)]
    reversal_seeds = [seed for seed in (1, 2, 3) if broad_reversal(by_seed[str(seed)])]
    breadth_seeds = [seed for seed in (1, 2, 3) if by_seed[str(seed)]['both_seats_nonnegative'] and
                     by_seed[str(seed)]['positive_anchor_count'] >= 3]
    no_negative_seat = all(row['ci95_high_bb100'] >= 0 for row in combined['by_seat'].values())
    gates = {
        'positive_slope_at_least_two_seeds': sum(slope > 0 for slope in slopes) >= 2,
        'median_slope_positive': statistics.median(slopes) > 0,
        'combined_slope_positive': combined['pooled']['bb100'] > 0,
        'improved_breadth': bool(breadth_seeds) or no_negative_seat,
        'no_replicated_broad_proxy_reversal_OR': len(reversal_seeds) < 2,
        'all_final_source_drift_below_limits': all(row['mean_tv'] < .08 and
            row['greedy_disagreement_rate'] < .12 for row in drift.values()),
    }
    return {
        'aggregate': {'combined_all_three': combined, 'by_seed': by_seed,
                      'incident_unaffected_seed1_seed3': unaffected},
        'incident_unaffected_seed_ids': [1, 3],
        'incident_unaffected_is_not_a_three_seed_replacement': True,
        'paired_ci_interpretation': 'conditional on these frozen policies and selected anchors; not a training-population CI',
        'preregistered_broad_reversal': 'both_seats_negative OR at_least_three_negative_anchors',
        'broad_reversal_seed_ids': reversal_seeds, 'breadth_seed_ids': breadth_seeds,
        'directional_gates_descriptive_only': gates,
        'all_directional_gates_descriptively_pass': all(gates.values()),
        'promote': False, 'automatic_scaling_authorized': False,
        'decision': 'RESEARCH_REVIEW_REQUIRED_4M_TRAINING_DEVIATION',
        'strength_or_final_slumbot_success_claimed': False,
    }


def validate_nontraining_integrity(integrity):
    if 'training_audit_passed' not in integrity:
        raise ValueError('original training audit status missing')
    failures = [key for key, value in integrity.items() if key != 'training_audit_passed' and value is not True]
    if failures:
        raise ValueError(f'unrelated evaluation/drift integrity failure: {failures}')


def verify_hash_map(mapping):
    for path, expected in mapping.items():
        if sha256_path(Path(path)) != expected:
            raise ValueError(f'input changed since source audit: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-aggregate', type=Path, required=True)
    parser.add_argument('--posthoc-mechanics', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.legacy_aggregate.resolve().parent != BASE or args.posthoc_mechanics.resolve().parent != BASE:
        parser.error('this report is scoped to the preregistered 4M experiment')
    original = json.loads(args.legacy_aggregate.read_text())
    mechanics = json.loads(args.posthoc_mechanics.read_text())
    if original['schema'] != 'cardpilot.static_current_kl_4m_aggregate.v1' or original['status'] != 'COMPLETED':
        raise ValueError('expected complete original 4M aggregate')
    if original['evaluation_hands'] != 98304 or original['offline_drift_states'] != 60000:
        raise ValueError('original full evaluation budget not completed')
    validate_nontraining_integrity(original['integrity'])
    verify_hash_map(original['input_sha256'])
    if mechanics['posthoc_observed_mechanics_passed'] is not True or [row['name'] for row in mechanics['runs']] != ['seed1', 'seed2', 'seed3']:
        raise ValueError('all three frozen endpoints require observed mechanical qualification')
    source_hashes = {str(args.legacy_aggregate.resolve()): sha256_path(args.legacy_aggregate),
                     str(args.posthoc_mechanics.resolve()): sha256_path(args.posthoc_mechanics)}
    rows_by_seed = {}
    for seed, mechanical_run in zip((1, 2, 3), mechanics['runs'], strict=True):
        if not mechanical_run['posthoc_observed_mechanics_passed']:
            raise ValueError('unqualified endpoint')
        generic = mechanical_run['generic_audit']
        run = BASE / f'seed{seed}'
        source_paths = {'checkpoint': run / 'latest.pt', 'manifest': run / 'run_manifest.json',
                        'metrics': run / 'h1_training_metrics.jsonl', 'assignments': run / 'opponent_assignments.jsonl',
                        'log': run / 'latest_train.log'}
        verify_hash_map({str(path): generic['hashes'][key] for key, path in source_paths.items()})
        for segment in mechanical_run['segments']:
            verify_hash_map({segment['checkpoint_path']: segment['checkpoint_sha256']})
            if not segment['passed'] or not all(segment['gates'].values()):
                raise ValueError('unqualified recovery segment')
        summary_path = BASE / f'eval_seed{seed}' / 'summary.json'
        summary = json.loads(summary_path.read_text())
        if summary['input_sha256']['treatment'] != generic['hashes']['checkpoint']:
            raise ValueError('evaluated treatment differs from mechanically audited endpoint')
        raw_path = summary_path.parent / 'common_deck_pairs.jsonl.gz'
        rows = read_rows(raw_path)
        if len(rows) != 8192 or len({(row['anchor'], row['pair_index']) for row in rows}) != 8192:
            raise ValueError('wrong or repeated pair count')
        rows_by_seed[seed] = rows
    result = descriptive_report(rows_by_seed, original['drift'])
    all_decks = [tuple(row['deck']) for seed in (1, 2, 3) for row in rows_by_seed[seed]]
    if len(all_decks) != len(set(all_decks)):
        raise ValueError('shared decks across anchors/seeds require explicit clustered inference')
    for seed in (1, 2, 3):
        if result['aggregate']['by_seed'][str(seed)] != original['aggregate']['by_seed'][str(seed)]:
            raise ValueError('raw reconstruction disagrees with original summary')
    if result['aggregate']['combined_all_three'] != original['aggregate']['combined']:
        raise ValueError('raw reconstruction disagrees with original pooled summary')
    overlap_path = BASE / 'final_seed2_overlap.json'
    overlap = json.loads(overlap_path.read_text())
    if overlap['inputs'][-1]['sha256'] != mechanics['runs'][1]['generic_audit']['hashes']['checkpoint']:
        raise ValueError('known training deviation belongs to another checkpoint')
    amendment = BASE / 'resume_deviation_amendment.md'
    source_hashes.update({str(overlap_path): sha256_path(overlap_path), str(amendment): sha256_path(amendment)})
    result.update({
        'schema': 'cardpilot.static4m.deviation_aware_descriptive_report.v1',
        'status': 'COMPLETED', 'evaluation_hands': 98304, 'new_hands_used_by_report': 0,
        'original_training_audit_passed': original['integrity']['training_audit_passed'],
        'independent_observed_mechanics_passed': True,
        'original_integrity_gates_preserved': original['integrity'],
        'original_decision_preserved_not_authoritative_for_promotion': original['decision'],
        'known_training_repeated_deal_exposures': overlap['repeated_deal_exposures'],
        'input_sha256': source_hashes,
    })
    if args.out.exists():
        if json.loads(args.out.read_text()) != result:
            raise RuntimeError('existing immutable report differs on replay')
    else:
        with args.out.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write('\n')
    print(json.dumps({'decision': result['decision'], 'promote': False,
                      'descriptive_gates': result['directional_gates_descriptive_only']}))


if __name__ == '__main__':
    main()
