"""Post-hoc endpoint evidence, explicitly not a reconstructed passing preflight."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts/alpha_holdem'))
from scripts.alpha_holdem.audit_v6_integrated_alphaholdem_geometric import audit_run, sha256_path
from scripts.alpha_holdem.audit_v6_static_current_kl_262k_training import load_jsonl, optimizer_steps, prefix_sha256


def load_verified(path, expected=None):
    import torch
    path = Path(path)
    before = sha256_path(path)
    if expected is not None and before != expected:
        raise RuntimeError(f'checkpoint SHA256 mismatch: {path}')
    checkpoint = torch.load(path, map_location='cpu', weights_only=False)
    if sha256_path(path) != before:
        raise RuntimeError(f'checkpoint changed while reading: {path}')
    return checkpoint, before


def verify_inherited_bridge(audit_path, checkpoint_sha, seen=None):
    """Resolve existing hash-bound audit links; do not mutate a failed audit."""
    seen = set() if seen is None else seen
    audit_path = Path(audit_path).resolve()
    key = (str(audit_path), checkpoint_sha)
    if key in seen:
        raise RuntimeError('inherited bridge audit cycle')
    seen.add(key)
    audit = json.loads(audit_path.read_text())
    matches = [row for row in audit['runs'] if row['hashes']['checkpoint'] == checkpoint_sha]
    if len(matches) != 1 or audit.get('passed') is not True:
        raise RuntimeError('inherited audit is not a unique passing checkpoint binding')
    row = matches[0]
    if not row.get('bridge_lineage') or row['bridge_lineage'][0]['sha256'] != checkpoint_sha:
        raise RuntimeError('inherited lineage does not begin at the requested checkpoint')
    actual_nodes = []
    for node in row['bridge_lineage']:
        checkpoint, digest = load_verified(node['path'], node['sha256'])
        expected_contract = 'hunl_v6_physical_legacy_v4_observation_bridge_v1'
        if checkpoint.get('observation_bridge_contract') != expected_contract or node['observation_bridge_contract'] != expected_contract:
            raise RuntimeError('actual inherited checkpoint bridge contract mismatch')
        rebound = bool(checkpoint.get('legacy_weights_rebound_to_new_contract'))
        if rebound != node['legacy_weights_rebound_to_new_contract']:
            raise RuntimeError('actual inherited rebinding event does not match prior audit')
        actual_nodes.append({'path': node['path'], 'sha256': digest, 'rebound': rebound})
    proof = {'audit_path': str(audit_path), 'audit_sha256': sha256_path(audit_path),
             'checkpoint_sha256': checkpoint_sha, 'actual_verified_nodes': actual_nodes}
    if any(node['rebound'] for node in actual_nodes):
        proof['passed'] = True
        return proof
    inherited = row.get('inherited_parent_lineage')
    if not inherited or sha256_path(Path(inherited['path'])) != inherited['sha256']:
        raise RuntimeError('no exact inherited bridge path to a rebinding root')
    parent = row['parent']
    load_verified(parent['path'], parent['sha256'])
    proof['parent_proof'] = verify_inherited_bridge(inherited['path'], parent['sha256'], seen)
    proof['passed'] = proof['parent_proof']['passed']
    return proof


def main():
    import torch
    torch.set_num_threads(1)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', type=int, nargs='+', choices=[1, 2, 3], required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--verify-inherited-bridge', action='store_true',
                        help='Add actual checkpoint/hash verification through existing inherited audit links')
    args = parser.parse_args()
    if len(set(args.seeds)) != len(args.seeds):
        parser.error('duplicate seed')
    stage_path = BASE / 'resume_stage_manifest.json'
    stage = json.loads(stage_path.read_text())
    staged = {row['name']: row for row in stage['staged']}
    base_path = ROOT / 'models/baseline/standard10/latest.pt'
    baseline, baseline_sha = load_verified(base_path, '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428')
    runs = []
    for seed in args.seeds:
        name = f'seed{seed}'
        run = BASE / name
        if json.loads((run / 'run_manifest.json').read_text())['status'] != 'finished':
            raise RuntimeError(f'{name} is not a finished endpoint; refusing live audit')
        row = staged[name]
        parent_path = Path(row['checkpoint']['path'])
        parent, parent_sha = load_verified(parent_path, row['checkpoint']['sha256'])
        endpoint, endpoint_sha = load_verified(run / 'latest.pt')
        generic = audit_run(name, run, baseline, min_environment_hands=4194304,
            expected_archive_iterations=[448, 512, 576, 640, 704, 768, 832],
            require_continuation=True, resume_preflight_path=None)
        metrics_path = run / 'h1_training_metrics.jsonl'
        assignments_path = run / 'opponent_assignments.jsonl'
        metrics = load_jsonl(metrics_path)
        by_iteration = {int(item['iteration']): item for item in metrics}
        sources = []
        if seed == 2:
            overlap_path = BASE / 'final_seed2_overlap.json'
            overlap = json.loads(overlap_path.read_text())
            for item in overlap['inputs']:
                checkpoint, digest = load_verified(item['path'], item['sha256'])
                sources.append((Path(item['path']), checkpoint, digest))
            if sources[-1][2] != endpoint_sha:
                raise RuntimeError('Seed2 live terminal endpoint differs from preserved frozen endpoint')
            freshness = {'known_repeated_deal_exposures': overlap['repeated_deal_exposures'],
                'unique_evidenced_stage_deals': overlap['unique_evidenced_deal_identities'],
                'incident_overlap_report_sha256': sha256_path(overlap_path),
                'clean_three_seed_scale_confirmation': False,
                'unknown_uncommitted_crash_suffix': True}
        else:
            sources = [(run / 'latest.pt', endpoint, endpoint_sha)]
            freshness = {'known_repeated_deal_exposures_in_this_incident': 0,
                'incident_unaffected': True, 'older_boundaries_not_certified_here': True}
        segments = []
        previous_path, previous, previous_sha = parent_path, parent, parent_sha
        for path, checkpoint, digest in sources:
            first, last = int(previous['iteration']), int(checkpoint['iteration'])
            suffix = [by_iteration[index] for index in range(first + 1, last + 1)]
            counter = checkpoint['environment_hand_accounting']
            prior_physical = int(previous['environment_hand_accounting']['completed_hands'])
            bases = {int(item['environment_hand_accounting']['completed_hands']) -
                     int(item['environment_hand_accounting']['session_completed_hands']) for item in suffix}
            previous_steps, next_steps = optimizer_steps(previous), optimizer_steps(checkpoint)
            checks = {
                'resume_path_names_actual_immutable_parent': Path(checkpoint['config']['resume']).resolve() == previous_path.resolve(),
                'same_run_id': checkpoint['config']['run_id'] == previous['config']['run_id'],
                'optimizer_no_reset_and_lr_preserved': checkpoint['config']['reset_optimizer'] is False and
                    checkpoint['optimizer']['param_groups'][0]['lr'] == previous['optimizer']['param_groups'][0]['lr'],
                'optimizer_steps_advanced': len(previous_steps) == len(next_steps) == 10 and
                    len(set(previous_steps)) == len(set(next_steps)) == 1 and next_steps[0] > previous_steps[0],
                'every_metric_has_expected_session_prefix': bases == {prior_physical},
                'physical_counter_reconciles': prior_physical + int(counter['session_completed_hands']) == int(counter['completed_hands']),
                'transition_counter_matches_metric': int(checkpoint['total_hands']) == int(by_iteration[last]['hands']) and
                    all(int(item['hands']) > int(by_iteration[int(item['iteration']) - 1]['hands']) for item in suffix),
                'replay_draw_counter_reconciles': int(previous['ppo_replay_cumulative_rows']) +
                    sum(int(item['ppo_replay_rows']) for item in suffix) == int(checkpoint['ppo_replay_cumulative_rows']),
                'replay_state_serialized': len(checkpoint['ppo_replay_entries']) == 2 and
                    checkpoint.get('ppo_replay_rng_state') is not None and not checkpoint['ppo_replay_recovery_boundaries'],
            }
            segments.append({'checkpoint_path': str(path), 'checkpoint_sha256': digest,
                'parent_sha256': previous_sha, 'first_iteration_exclusive': first, 'last_iteration': last,
                'physical_executions': int(counter['completed_hands']) - prior_physical,
                'optimizer_steps_before': previous_steps[0], 'optimizer_steps_after': next_steps[0],
                'gates': checks, 'passed': all(checks.values())})
            previous_path, previous, previous_sha = path, checkpoint, digest
        config = endpoint['config']
        stage_checks = {
            'staged_parent_hash_exact': parent_sha == row['checkpoint']['sha256'],
            'staged_metrics_prefix_exact': prefix_sha256(metrics_path, int(parent['iteration'])) == row['staged_metrics']['sha256'],
            'staged_assignments_prefix_exact': prefix_sha256(assignments_path, int(parent['iteration'])) == row['staged_assignments']['sha256'],
            'static_current_kl_unchanged': config['source_policy_kl_direction'] == 'current_to_reference' and
                config['source_policy_reference_refresh_updates'] == 0 and config['source_policy_kl_coef'] == 1 and
                Path(config['source_policy_reference_checkpoint']).resolve() == base_path.resolve() and
                endpoint.get('moving_source_policy_reference') is None,
            'frozen_hash_still_exact': sha256_path(run / 'latest.pt') == endpoint_sha,
        }
        bridge_proof = None
        generic_failures = {key for key, value in generic['gates'].items() if not value}
        if args.verify_inherited_bridge:
            bridge_proof = verify_inherited_bridge(parent_path.parent.parent / 'training_audit.json', parent_sha)
        resolved_generic_pass = generic['passed'] or (
            generic_failures == {'corrected_legacy_contract_bound'} and bridge_proof is not None and bridge_proof['passed'])
        passed = resolved_generic_pass and all(stage_checks.values()) and all(item['passed'] for item in segments)
        result = {'name': name, 'generic_audit': generic, 'segments': segments,
                  'stage_gates': stage_checks, 'posthoc_observed_mechanics_passed': passed,
                  'freshness': freshness, 'historical_preflights_reconstructed': False,
                  'bitwise_initial_resume_state_proven': False}
        if args.verify_inherited_bridge:
            result['independently_verified_inherited_bridge'] = bridge_proof
            result['generic_original_failure_preserved'] = not generic['passed']
        runs.append(result)
        print(json.dumps({'name': name, 'posthoc_observed_mechanics_passed': passed,
            'generic_failures': [key for key, value in generic['gates'].items() if not value],
            'segment_failures': [[key for key, value in item['gates'].items() if not value] for item in segments],
            'stage_failures': [key for key, value in stage_checks.items() if not value]}), flush=True)
    report = {'schema': 'cardpilot.static4m.frozen_endpoint_posthoc_mechanics.v1',
        'stage_sha256': sha256_path(stage_path), 'baseline_sha256': baseline_sha, 'runs': runs,
        'posthoc_observed_mechanics_passed': all(item['posthoc_observed_mechanics_passed'] for item in runs),
        'not_a_passing_historical_preflight': True, 'not_a_clean_three_seed_training_freshness_certificate': True,
        'new_training_or_evaluation_hands': 0}
    if args.out.exists():
        if json.loads(args.out.read_text()) != report:
            raise RuntimeError('immutable audit differs on replay')
        print('Immutable post-hoc report replay: PASS')
    else:
        with args.out.open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write('\n')
    if not report['posthoc_observed_mechanics_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
