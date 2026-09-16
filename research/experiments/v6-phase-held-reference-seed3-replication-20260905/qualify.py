"""Offline Seed3 parent/binding qualification; no environment or policy queries."""
from pathlib import Path
import json
import math
import subprocess
import sys

import run_control as c


def main():
    base, root = c.BASE, c.ROOT
    c.evidence.require(c.evidence.read_json(base / 'experiment.json')['status'] == 'RUNNING', 'register first')
    for name in ('seed3_parent_preflight.json', 'controller_tests.xml', 'qualification_result.json'):
        c.evidence.require(not (base / name).exists(), 'preserve existing qualification output: ' + name)
    import torch
    torch.set_num_threads(1)
    c.evidence.require(c.sha(c.PARENT) == c.PARENT_SHA, 'Seed3 parent SHA changed')
    parent = torch.load(c.PARENT, map_location='cpu', weights_only=False)
    manifest = c.evidence.read_json(c.PARENT.parent / 'run_manifest.json')
    proof_path = root / 'research/experiments/v6-static-current-kl-4m-scale-20260904/frozen_allseed_mechanics_inherited_bridge.json'
    proof = c.evidence.read_json(proof_path)
    seed_proof = next(row for row in proof['runs'] if row['name'] == 'seed3')
    c.evidence.require(seed_proof['posthoc_observed_mechanics_passed'] and all(seed_proof['stage_gates'].values()),
        'qualified Seed3 mechanics proof missing')
    c.evidence.require(seed_proof['freshness']['incident_unaffected'] and
        seed_proof['freshness']['known_repeated_deal_exposures_in_this_incident'] == 0 and
        seed_proof['freshness']['older_boundaries_not_certified_here'], 'freshness qualification lost')
    c.evidence.require(seed_proof['independently_verified_inherited_bridge']['passed'], 'bridge proof missing')
    inputs = {str(proof_path): c.sha(proof_path)}
    for key, name in {'checkpoint': 'latest.pt', 'assignments': 'opponent_assignments.jsonl',
            'metrics': 'h1_training_metrics.jsonl', 'manifest': 'run_manifest.json', 'log': 'latest_train.log'}.items():
        path = c.PARENT.parent / name
        digest = seed_proof['generic_audit']['hashes'][key]
        c.evidence.require(c.sha(path) == digest, 'historical parent evidence changed: ' + key)
        inputs[str(path)] = digest
    expected = {'seed': c.TRAINING_SEED, 'worker_seed_base': c.WORKER_SEED_BASE,
        'fixed_training_deal_start_index': c.FIXED_DEAL_START, 'run_id': c.LINEAGE_RUN_ID,
        'source_policy_reference_refresh_updates': 0, 'source_policy_kl_coef': 1.,
        'source_policy_kl_direction': 'current_to_reference', 'hero_policy_mode': 'sample',
        'self_play_fraction': .25, 'mini_batch_size': 16384, 'ppo_replay_buffer_iterations': 2,
        'ppo_replay_ratio': .5, 'all_policy_heads_only_training': True}
    c.evidence.require(all(parent['config'].get(k) == v for k, v in expected.items()), 'parent recipe or seed changed')
    c.evidence.require(parent['iteration'] == c.INITIAL_ITERATION == 880 and
        parent['total_hands'] == manifest['total_hands'] == 3624053 and
        parent['environment_hand_accounting']['completed_hands'] ==
        manifest['environment_hand_accounting']['completed_hands'] == c.INITIAL_PHYSICAL == 4194908,
        'parent counter mismatch')
    c.evidence.require(manifest['status'] == 'finished' and parent.get('moving_source_policy_reference') is None,
        'wrong parent completion/reference')
    c.evidence.require(parent.get('main_process_rng_state') is None, 'expected legacy bootstrap changed')
    c.evidence.require(len(parent['ppo_replay_entries']) == 2 and parent['ppo_replay_rng_state'] is not None
        and parent['ppo_replay_cumulative_rows'] == 6383843, 'replay evidence changed')
    c.evidence.require(parent['optimizer']['state'] and
        all(math.isclose(group['lr'], 1e-4, rel_tol=1e-12) for group in parent['optimizer']['param_groups']),
        'optimizer reset or effective LR changed')
    c.evidence.require(all(torch.isfinite(t).all().item() for t in parent['model'].values()), 'nonfinite parent weights')
    c.write_new(base / 'seed3_parent_preflight.json', {'passed': True, 'parent_sha256': c.PARENT_SHA,
        'iteration': 880, 'physical_hands': 4194908, 'transition_hands': 3624053,
        'config': expected, 'input_sha256': inputs, 'legacy_main_rng_bootstrap_required': True,
        'freshness_scope': seed_proof['freshness'], 'new_hands': 0, 'policy_queries': 0,
        'actual_saved_resume_state_will_be_verified_at_launch': True})
    command = [sys.executable, '-B', '-m', 'pytest', '-q', str(base / 'test_controller_evidence.py'),
        str(base / 'test_command_contract.py'), str(base / 'test_seed3_bindings.py'),
        f'--junitxml={base / "controller_tests.xml"}']
    subprocess.run([sys.executable, str(root / 'research/experiment_log.py'), 'update', base.name,
        '--command', subprocess.list2cmdline(command)], cwd=root, check=True)
    subprocess.run(command, cwd=root, check=True)
    result = c.preflight()
    c.evidence.require(result['training_authorized'], json.dumps(result))
    c.write_new(base / 'qualification_result.json', result)
    argv = [sys.executable, str(root / 'research/experiment_log.py'), 'update', base.name,
        '--metric', 'seed3_parent_and_controller_qualified=true', '--metric', 'qualification_new_hands=0']
    for name in ('seed3_parent_preflight.json', 'controller_tests.xml', 'qualification_result.json'):
        argv += ['--artifact', str(base / name)]
    subprocess.run(argv, cwd=root, check=True)
    print('Seed3 parent and controller qualification PASS; zero new hands.', flush=True)


if __name__ == '__main__':
    main()
