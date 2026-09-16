"""Actual isolated trainer cycles; never modify or restart the active research run."""
from __future__ import annotations

import hashlib
import argparse
import math
import struct
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
from scripts.alpha_holdem.fixed_deal_attempt import load_attempt


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def equal(left, right):
    import numpy as np
    import torch
    if isinstance(left, torch.Tensor):
        return torch.equal(left.cpu(), right.cpu())
    if isinstance(left, np.ndarray):
        return left.dtype == right.dtype and left.shape == right.shape and left.tobytes() == right.tobytes()
    if isinstance(left, float) and math.isnan(left):
        return isinstance(right, float) and struct.pack('d', left) == struct.pack('d', right)
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equal(left[k], right[k]) for k in left)
    if isinstance(left, (tuple, list)):
        return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right))
    return left == right


def steps(checkpoint):
    return sorted({int(state['step']) for state in checkpoint['optimizer']['state'].values()})


def main():
    import torch
    torch.set_num_threads(1)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-name', default='cpu_probe')
    parser.add_argument('--continue-existing', action='store_true',
                        help='Verify completed diagnostic attempts without training them again')
    parser.add_argument('--retry-attempt2-directory', default='',
                        help='Preserve failed attempt2 and use a new explicit directory/namespace')
    parser.add_argument('--verify-only', action='store_true', help='Never start workers or rewrite completed evidence')
    options = parser.parse_args()
    if options.verify_only and not options.continue_existing:
        parser.error('--verify-only requires --continue-existing')
    if Path(options.output_name).name != options.output_name:
        parser.error('--output-name must be a single directory name')
    out = BASE / options.output_name
    out.mkdir(exist_ok=options.continue_existing)
    production = ROOT / 'scripts/alpha_holdem/train_v5.py'
    production_sha = sha(production)
    candidate = ROOT / 'scripts/alpha_holdem/train_v5_managed_candidate.py'
    environment = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    results, commands = [], []
    saved_commands = json.loads((out / 'commands.json').read_text()) if (out / 'commands.json').exists() else []
    # Start from an already-terminal critic-v2 checkpoint, preserving optimizer,
    # replay and counters even for this diagnostic; do not reset the research run.
    parent_path = ROOT / 'research/experiments/v6-static-current-kl-4m-scale-20260904/seed1/latest.pt'
    parent = torch.load(parent_path, map_location='cpu', weights_only=False)
    for number, mode, slots in ((1, 'single', 1), (2, 'single', 1), (3, 'multi', 2)):
        name = options.retry_attempt2_directory if number == 2 and options.retry_attempt2_directory else f'attempt{number}'
        if Path(name).name != name:
            parser.error('attempt directory must be a single directory name')
        run = out / name
        run.mkdir(exist_ok=options.continue_existing)
        target = 128 + (int(parent['environment_hand_accounting']['completed_hands']) if parent else 0)
        metrics = run / 'h1_training_metrics.jsonl'
        assignments = run / 'opponent_assignments.jsonl'
        if number > 1 and not metrics.exists():
            shutil.copy2(parent_path.parent / metrics.name, metrics)
            shutil.copy2(parent_path.parent / assignments.name, assignments)
        argv = [sys.executable, '-u', str(candidate), '--device', 'cpu', '--torch-threads', '1',
                '--workers', '1', '--hands-per-iter', '64', '--total-environment-hands', str(target),
                '--starting-stack', '200', '--env-version', 'v6legacyv4obs', '--norm-layer', 'gn',
                '--lr', '0.0001', '--ppo-epochs', '2', '--mini-batch-size', '512',
                '--separate-preflop-head', '--all-policy-heads-only-training',
                '--critic-contract', 'critic_v2', '--h1-effective-stack-divisor', '200',
                '--value-coef', '1',
                '--autonomous-critic-v2-continue', '--ppo-replay-buffer-iterations', '2',
                '--ppo-replay-ratio', '0.5', '--k-best', '2', '--pool-strategy', 'loss-kbest',
                '--initial-opponent-checkpoints', str(ROOT / 'models/baseline/standard10/latest.pt'),
                '--self-play-fraction', '1', '--opponent-assignment', 'per-group', '--opponent-groups', '1',
                '--adaptive-opponent-league', '--opponent-assignment-provenance-file', str(assignments),
                '--hero-policy-mode', 'sample', '--rollout-mode', mode, '--rollout-envs-per-worker', str(slots),
                '--worker-seed-base', '2026090400', '--fixed-training-deal-stream',
                '--fixed-training-deal-start-index', '0', '--managed-deal-attempts',
                '--deal-attempt-registry', str(out / 'attempt_registry'),
                '--snapshot-every', '1', '--save-interval', '1', '--archive-checkpoint-every', '1',
                '--run-id', 'v6_managed_resume_diagnostic_20260904', '--run-dir', str(run),
                '--out', str(run / 'latest.pt'), '--seed', '20260904',
                '--max-runtime-seconds', '120', '--validate-stream']
        if parent:
            argv += ['--resume', str(parent_path), '--allow-resume', '--no-reset-optimizer',
                     '--preserve-resumed-optimizer-lr']
            if number > 1:
                argv += ['--resume-assignment-state-from-provenance']
                if parent.get('assignment_replay_origin') is None:
                    argv += ['--assignment-replay-origin-checkpoint', str(parent_path.parent / 'initial_resumed_state.pt')]
        commands.append(argv)
        before_parent_sha = sha(parent_path) if parent else None
        initial = None
        if (run / 'stdout.log').exists():
            manifest_path = run / 'run_manifest.json'
            if not options.continue_existing or not manifest_path.exists() or json.loads(manifest_path.read_text())['status'] != 'finished':
                raise RuntimeError('existing attempt is not proven finished; refusing automatic replay')
            recorded_argv = (json.loads((run / 'command.json').read_text())
                             if (run / 'command.json').exists()
                             else saved_commands[number - 1] if number <= len(saved_commands) else None)
            if recorded_argv != argv:
                raise RuntimeError('existing attempt command differs from requested diagnostic')
            initial = torch.load(run / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
            print(f'attempt{number}: verifying existing completed work; zero repeated training', flush=True)
        else:
            if options.verify_only:
                raise RuntimeError('verify-only cannot launch a missing attempt')
            (run / 'command.json').write_text(json.dumps(argv, indent=2) + '\n')
            # Original commands.json is immutable once written. Preserve each
            # later actual invocation separately, including failed attempts.
            if not (out / 'commands.json').exists():
                (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
            shutil.copy2(candidate, run / 'trainer_source.py')
            child = subprocess.Popen(argv, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
            with (run / 'stdout.log').open('x', encoding='utf-8') as log:
                for line in child.stdout:
                    log.write(line)
                    log.flush()
                    if '[Save] initial resume checkpoint' in line:
                        initial_path = run / 'initial_resumed_state.pt'
                        shutil.copy2(run / 'latest.pt', initial_path)
                        initial = torch.load(initial_path, map_location='cpu', weights_only=False)
                    if ('[' in line and 'envhands=' in line) or 'Managed deal attempt:' in line:
                        print(f'attempt{number}: {line.strip()}', flush=True)
            code = child.wait(timeout=10)
            if code != 0:
                raise RuntimeError(f'attempt{number} failed: exit{code}; see {run / "stdout.log"}')
        checkpoint_path = run / 'latest.pt'
        checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
        physical = int(checkpoint['environment_hand_accounting']['completed_hands'])
        assert physical >= target, 'runtime guard reached before diagnostic target'
        attempt = checkpoint['fixed_deal_attempt']
        receipt = load_attempt(Path(attempt['path']), attempt['sha256'])
        namespace = receipt['namespace']
        assert namespace == checkpoint['config']['fixed_training_deal_namespace']
        assert namespace not in [row['namespace'] for row in results]
        assert receipt['parent_checkpoint_sha256'] == before_parent_sha
        assert len(checkpoint['ppo_replay_entries']) == 2
        gates = {'unique_namespace': True, 'target_reached': True, 'replay2_serialized': True}
        if parent:
            assert initial is not None, 'initial resume snapshot not captured'
            assert sha(parent_path) == before_parent_sha
            gates.update({
                'initial_model_exact': equal(initial['model'], parent['model']),
                'initial_optimizer_exact': equal(initial['optimizer'], parent['optimizer']),
                'initial_replay_exact': equal(initial['ppo_replay_entries'], parent['ppo_replay_entries']),
                'initial_replay_rng_exact': equal(initial['ppo_replay_rng_state'], parent['ppo_replay_rng_state']),
                'initial_main_rng_exact_or_declared_legacy_bootstrap': (
                    equal(initial['main_process_rng_state'], parent['main_process_rng_state'])
                    if parent.get('main_process_rng_state') is not None
                    else initial['fixed_deal_attempt']['legacy_rng_bootstrap']),
                'initial_hand_counter_exact': initial['total_hands'] == parent['total_hands'],
                'initial_physical_counter_exact': initial['environment_hand_accounting']['completed_hands'] == parent['environment_hand_accounting']['completed_hands'],
                'initial_iteration_exact': initial['iteration'] == parent['iteration'],
                'optimizer_step_advanced': min(steps(checkpoint)) > max(steps(parent)),
                'replay_draws_advanced': checkpoint['ppo_replay_cumulative_rows'] > parent['ppo_replay_cumulative_rows'],
            })
        assert all(gates.values()), gates
        row = {'attempt': number, 'namespace': namespace, 'mode': mode, 'slots': slots,
               'physical_hands': physical, 'new_physical_hands': physical - (int(parent['environment_hand_accounting']['completed_hands']) if parent else 0),
               'iteration': int(checkpoint['iteration']), 'optimizer_steps': steps(checkpoint),
               'checkpoint_sha256': sha(checkpoint_path), 'gates': gates, 'passed': True}
        row['run_directory'] = str(run)
        results.append(row)
        if not options.verify_only:
            (out / 'progress.json').write_text(json.dumps(results, indent=2) + '\n')
        parent, parent_path = checkpoint, checkpoint_path
    assert sha(production) == production_sha
    report = {'passed': True, 'cases': results, 'production_source_unchanged': True,
              'production_sha256': production_sha, 'candidate_sha256': sha(candidate),
              'environment_training_hands': sum(r['new_physical_hands'] for r in results),
              'diagnostic_only_no_strength_claim': True}
    if options.verify_only:
        saved_report = json.loads((out / 'summary.json').read_text())
        for actual, saved in zip(results, saved_report['cases'], strict=True):
            for key in ('checkpoint_sha256', 'namespace', 'physical_hands', 'new_physical_hands', 'gates'):
                assert actual[key] == saved[key], (actual['attempt'], key)
        report['verification_only_no_new_hands_no_evidence_rewrite'] = True
    else:
        (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
