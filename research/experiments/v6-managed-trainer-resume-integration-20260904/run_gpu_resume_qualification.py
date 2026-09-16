"""Bounded production GPU resume qualification; never restart the 4M pipeline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
FOUR_M = ROOT / 'research/experiments/v6-static-current-kl-4m-scale-20260904'
PARENT = FOUR_M / 'seed1/latest.pt'
PARENT_SHA = '7ea4d74d0fcf881c75c4c99bdc0cbe84f82a55001ba277c01aafec6dc5a98f3f'
CANDIDATE_SHA = '1b4d23abfa3e0a9c675126fd7183d37b134a2a13253563e990e144cc01a90f8b'
STANDARD_SHA = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
PRODUCTION = ROOT / 'scripts/alpha_holdem/train_v5.py'
STANDARD = ROOT / 'models/baseline/standard10/latest.pt'
ORDER = (('single1', 1), ('multi8', 1), ('multi8', 2), ('single1', 2))
DELTA = 8192

spec = importlib.util.spec_from_file_location('gpu_resume_cpu_helpers', BASE / 'run_cpu_resume_probe.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
sha, equal, steps = helpers.sha, helpers.equal, helpers.steps


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def safe_output_name(value):
    if not value or Path(value).name != value or value in ('.', '..') or '/' in value or '\\' in value:
        raise ValueError('output name must be one new directory name')
    return value


def preflight():
    import psutil
    blocked = []
    guard = FOUR_M / 'guarded_followthrough_v1'
    ownership, state = read_json(guard / 'ownership.json'), read_json(guard / 'status.json')
    identities = list(ownership['waited_processes']) + [ownership]
    for row in identities:
        try:
            proc = psutil.Process(int(row['pid']))
            if abs(proc.create_time() - float(row['create_time'])) < .001 and proc.is_running():
                blocked.append(f'original guarded process still live: {proc.pid}')
        except psutil.NoSuchProcess:
            pass
    child_pid = state.get('active_child_pid')
    if child_pid and psutil.pid_exists(int(child_pid)):
        blocked.append(f'guarded active child PID still present: {child_pid}')
    if state.get('phase') not in ('EVIDENCE_READY_FOR_RESEARCH_ANALYSIS',
                                   'SAFE_BOUNDARY_NEEDS_MANAGED_TRAINING_CONTINUATION'):
        blocked.append(f'guarded phase not a qualified handoff: {state.get("phase")}')
    # Also fail closed for a surviving worker tree or another poker GPU owner.
    script_names = {'train_v5.py', 'train_v5_managed_candidate.py',
                    'v6_public_opponent_matched_eval.py', 'v6_legacy_bridge_drift_audit.py'}
    for proc in psutil.process_iter(['pid', 'cmdline']):
        argv = proc.info.get('cmdline') or []
        if any(Path(arg).name in script_names for arg in argv):
            blocked.append(f'other poker training/evaluation process: {proc.pid}')
    input_hashes = {}
    for path, expected in ((PARENT, PARENT_SHA), (PRODUCTION, CANDIDATE_SHA),
                           (BASE / 'staged_candidate.py', CANDIDATE_SHA), (STANDARD, STANDARD_SHA)):
        actual = sha(path)
        input_hashes[str(path)] = actual
        if actual != expected:
            blocked.append(f'input/source SHA mismatch or production not yet integrated: {path}')
    for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl', 'run_manifest.json'):
        path = PARENT.parent / name
        input_hashes[str(path)] = sha(path)
    for anchor in ('slumbot_free_anchor_position10m.pt', 'corrected_cfr96_anchor10.pt'):
        path = ROOT.parent / 'CardPilot_legacy_20260829/selected_assets/opponents' / anchor
        input_hashes[str(path)] = sha(path)
    for path, expected in ownership['frozen_sources'].items():
        if Path(path).resolve() == PRODUCTION.resolve():
            continue
        actual = sha(path)
        input_hashes[path] = actual
        if actual != expected:
            blocked.append(f'other original pipeline dependency changed: {path}')
    for path in (Path(__file__), BASE / 'run_cpu_resume_probe.py', BASE / 'gpu_qualification_protocol.md'):
        input_hashes[str(path)] = sha(path)
    return {'eligible': not blocked, 'blocked_by': blocked, 'input_hashes': input_hashes,
            'phase': state.get('phase'), 'new_hands': 0, 'workers_started': False}


def command(run, parent_path, parent_physical, mode, registry):
    if mode not in ('single1', 'multi8'):
        raise ValueError('only the two preregistered rollout arms are allowed')
    anchor = ROOT.parent / 'CardPilot_legacy_20260829/selected_assets/opponents'
    values = [
        '--device', 'cuda', '--workers', '12', '--hands-per-iter', '4096',
        '--total-hands', '99999999', '--total-environment-hands', str(parent_physical + DELTA),
        '--starting-stack', '200', '--env-version', 'v6legacyv4obs', '--norm-layer', 'gn',
        '--lr', '0.0003', '--ppo-epochs', '2', '--ppo-target-kl', '0.01',
        '--policy-advantage-clip', '3', '--source-policy-kl-coef', '1',
        '--source-policy-kl-direction', 'current_to_reference',
        '--source-policy-reference-checkpoint', str(STANDARD), '--separate-preflop-head',
        '--all-policy-heads-only-training', '--mini-batch-size', '16384',
        '--entropy-coef', '0.005', '--entropy-floor', '0.05',
        '--ppo-replay-buffer-iterations', '2', '--ppo-replay-ratio', '0.5',
        '--k-best', '5', '--pool-strategy', 'loss-kbest',
        '--initial-opponent-checkpoints', str(STANDARD),
        str(anchor / 'slumbot_free_anchor_position10m.pt'), str(anchor / 'corrected_cfr96_anchor10.pt'),
        '--hero-policy-mode', 'sample', '--self-play-fraction', '0.25',
        '--opponent-assignment', 'per-group', '--opponent-groups', '8',
        '--adaptive-opponent-league', '--adaptive-league-ema', '0.9',
        '--adaptive-league-temperature-bb', '2', '--adaptive-league-min-probability', '0.05',
        '--opponent-assignment-provenance-file', str(run / 'opponent_assignments.jsonl'),
        '--resume-assignment-state-from-provenance',
        '--rollout-mode', 'single' if mode == 'single1' else 'multi',
        '--rollout-envs-per-worker', '1' if mode == 'single1' else '8',
        '--inference-min-batch-slots', '0', '--inference-batch-deadline-us', '700',
        '--worker-seed-base', '2026300100', '--fixed-training-deal-stream',
        '--fixed-training-deal-start-index', '37300000', '--managed-deal-attempts',
        '--deal-attempt-registry', str(registry), '--critic-contract', 'critic_v2',
        '--h1-effective-stack-divisor', '200', '--h1-critic-init-seed', '2026071102',
        '--value-coef', '1', '--autonomous-critic-v2-continue',
        '--snapshot-every', '2', '--save-interval', '1', '--archive-checkpoint-every', '64',
        '--run-id', 'v6_nashpg_static_seed1_20260903', '--run-dir', str(run),
        '--out', str(run / 'latest.pt'), '--seed', '20263001', '--max-runtime-seconds', '600',
        '--resume', str(parent_path), '--allow-resume', '--no-reset-optimizer',
        '--preserve-resumed-optimizer-lr', '--validate-stream',
    ]
    return [sys.executable, '-u', str(PRODUCTION)] + values


def check_hashes(expected):
    for path, digest in expected.items():
        if sha(path) != digest:
            raise RuntimeError(f'frozen qualification input changed: {path}')


def finite_update_evidence(rows, text):
    core = ('entropy', 'approx_kl', 'reference_policy_kl')
    if not rows or not all(key in row and math.isfinite(float(row[key])) for row in rows for key in core):
        return False
    parsed = []
    for line in text.splitlines():
        match = re.match(r'\[\s*(\d+)\]', line)
        if match:
            fields = dict(re.findall(r'\b(ploss|vloss|vloss_bb2)=([^\s]+)', line))
            if set(fields) != {'ploss', 'vloss', 'vloss_bb2'}:
                return False
            try:
                if not all(math.isfinite(float(value)) for value in fields.values()):
                    return False
            except ValueError:
                return False
            parsed.append(int(match.group(1)))
    return parsed == [int(row['iteration']) for row in rows]


def live_known_children(identities):
    import psutil
    live = []
    for pid, created in identities.items():
        try:
            process = psutil.Process(pid)
            if abs(process.create_time() - created) < .001 and process.is_running():
                live.append(pid)
        except psutil.NoSuchProcess:
            pass
    return live


def inspect_attempt(run, parent, parent_path, expected_parent_sha, wall_seconds):
    import torch
    initial = torch.load(run / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
    final = torch.load(run / 'latest.pt', map_location='cpu', weights_only=False)
    manifest = read_json(run / 'run_manifest.json')
    old_physical = int(parent['environment_hand_accounting']['completed_hands'])
    new_physical = int(final['environment_hand_accounting']['completed_hands'])
    old_hands, new_hands = int(parent['total_hands']), int(final['total_hands'])
    attempt = final['fixed_deal_attempt']
    receipt = helpers.load_attempt(Path(attempt['path']), attempt['sha256'])
    gates = {'parent_unchanged': sha(parent_path) == expected_parent_sha,
             'terminal_manifest': manifest['status'] == 'finished',
             'target_reached': new_physical >= old_physical + DELTA,
             'manifest_counter_exact': manifest['environment_hand_accounting']['completed_hands'] == new_physical,
             'receipt_parent_exact': receipt['parent_checkpoint_sha256'] == expected_parent_sha,
             'receipt_embedded_exact': receipt == attempt['receipt'],
             'namespace_matches': receipt['namespace'] == final['config']['fixed_training_deal_namespace'],
             'initial_hand_counter_exact': initial['total_hands'] == old_hands,
             'initial_physical_counter_exact': initial['environment_hand_accounting']['completed_hands'] == old_physical,
             'initial_iteration_exact': initial['iteration'] == parent['iteration'],
             'optimizer_steps_advance': min(steps(final)) > max(steps(parent)),
             'replay_draws_advance': final['ppo_replay_cumulative_rows'] > parent['ppo_replay_cumulative_rows'],
             'weights_updated': not equal(final['model'], parent['model']),
             'replay_depth2': len(final['ppo_replay_entries']) == 2,
             'physical_covers_transition_hands': new_physical - old_physical >= new_hands - old_hands > 0}
    for key in ('model', 'optimizer', 'ppo_replay_entries', 'ppo_replay_rng_state',
                'ppo_replay_cumulative_rows', 'pool_snapshots', 'pool_strategy',
                'pool_active_metadata', 'pool_candidate_history'):
        gates[f'initial_{key}_exact'] = equal(initial[key], parent[key])
    if parent.get('main_process_rng_state') is not None:
        gates['main_rng_restored_exact'] = equal(initial['main_process_rng_state'], parent['main_process_rng_state'])
        gates['cuda_rng_present'] = bool(parent['main_process_rng_state'].get('torch_cuda'))
    else:
        gates['legacy_rng_bootstrap_declared'] = bool(initial['fixed_deal_attempt']['legacy_rng_bootstrap'])
    all_rows = [json.loads(line) for line in (run / 'h1_training_metrics.jsonl').read_text(encoding='utf-8').splitlines() if line]
    rows = [row for row in all_rows if int(row['iteration']) > int(parent['iteration'])]
    gates['contiguous_new_updates'] = ([row['iteration'] for row in rows]
                                      == list(range(int(parent['iteration']) + 1, int(final['iteration']) + 1)))
    gates['nonempty_updates'] = bool(rows)
    gates['finite_core_metrics_and_logged_losses'] = finite_update_evidence(
        rows, (run / 'latest_train.log').read_text(encoding='utf-8'))
    if not all(gates.values()):
        write_new(run / 'failed_verification.json', {'gates': gates})
        raise RuntimeError(f'GPU qualification gate failure: {[key for key, value in gates.items() if not value]}')
    metric_rate = None
    if len(rows) > 1:
        seconds = (datetime.fromisoformat(rows[-1]['recorded_at']) - datetime.fromisoformat(rows[0]['recorded_at'])).total_seconds()
        if seconds > 0:
            metric_rate = (rows[-1]['environment_hand_accounting']['completed_hands'] - rows[0]['environment_hand_accounting']['completed_hands']) / seconds
    result = {'passed': True, 'gates': gates, 'namespace': receipt['namespace'],
              'new_physical_hands': new_physical - old_physical, 'new_transition_hands': new_hands - old_hands,
              'new_iterations': int(final['iteration']) - int(parent['iteration']),
              'subprocess_wall_seconds': wall_seconds,
              'physical_hands_per_wall_second': (new_physical - old_physical) / wall_seconds,
              'transition_hands_per_wall_second': (new_hands - old_hands) / wall_seconds,
              'within_attempt_metric_physical_hands_per_second': metric_rate,
              'parent_checkpoint_sha256': expected_parent_sha,
              'checkpoint_sha256': sha(run / 'latest.pt'), 'initial_checkpoint_sha256': sha(run / 'initial_resumed_state.pt'),
              'receipt_sha256': attempt['sha256']}
    return result


def summarize(results, runner_wall_seconds):
    if [(row['arm'], row['attempt']) for row in results] != list(ORDER):
        raise ValueError('incomplete or reordered qualification evidence')
    if len({row['namespace'] for row in results}) != 4:
        raise ValueError('attempt namespace reused')
    if not all(row['passed'] for row in results):
        raise ValueError('failed mechanics cannot produce a throughput qualification')
    pooled = {}
    for arm in ('single1', 'multi8'):
        selected = [row for row in results if row['arm'] == arm]
        pooled[arm] = sum(row['new_physical_hands'] for row in selected) / sum(row['subprocess_wall_seconds'] for row in selected)
    ratios = {}
    for attempt in (1, 2):
        rates = {row['arm']: row['physical_hands_per_wall_second'] for row in results if row['attempt'] == attempt}
        ratios[str(attempt)] = rates['multi8'] / rates['single1']
    ratio = pooled['multi8'] / pooled['single1']
    selected = 'multi8' if ratio >= 1.25 and all(value > 1 for value in ratios.values()) else 'single1'
    return {'all_mechanics_passed': all(row['passed'] for row in results), 'cases': results,
            'pooled_physical_hands_per_wall_second': pooled, 'multi8_over_single1': ratio,
            'attempt_speed_ratios': ratios, 'provisional_throughput_choice': selected,
            'runner_wall_seconds': runner_wall_seconds,
            'diagnostic_environment_hands': sum(row['new_physical_hands'] for row in results),
            'diagnostic_transition_hands': sum(row['new_transition_hands'] for row in results),
            'evaluation_hands': 0, 'slumbot_hands': 0, 'research_lineage_hands': 0,
            'strength_claim': False, 'checkpoint_promotion_authorized': False,
            'statistical_not_bitwise_worker_continuation': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--output-name', default='gpu_current_recipe_v1')
    args = parser.parse_args()
    out = BASE / safe_output_name(args.output_name)
    before = preflight()
    if out.exists():
        before['blocked_by'].append(f'existing output must not be rerun: {out}')
        before['eligible'] = False
    if args.preflight_only:
        print(json.dumps(before, indent=2))
        return
    if not before['eligible']:
        raise RuntimeError(json.dumps(before['blocked_by']))
    import torch
    torch.set_num_threads(1)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA device unavailable; no CPU fallback for GPU qualification')
    # Controller loads and verifies on CPU; no concurrent controller CUDA model.
    out.mkdir()
    started = time.perf_counter()
    write_new(out / 'input_contract.json', before)
    results, parents = [], {'single1': PARENT, 'multi8': PARENT}
    for arm, number in ORDER:
        if not preflight()['eligible']:
            raise RuntimeError('safe handoff no longer valid before next diagnostic attempt')
        check_hashes(before['input_hashes'])
        parent_path = parents[arm]
        parent_sha = sha(parent_path)
        parent = torch.load(parent_path, map_location='cpu', weights_only=False)
        run = out / f'{arm}_attempt{number}'
        run.mkdir()
        prefixes = {}
        for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
            source = parent_path.parent / name
            prefixes[name] = {'path': str(source), 'sha256': sha(source), 'bytes': source.stat().st_size}
            shutil.copy2(source, run / name)
        argv = command(run, parent_path, int(parent['environment_hand_accounting']['completed_hands']), arm, out / 'attempt_registry')
        write_new(run / 'command.json', argv)
        write_new(run / 'prefixes.json', prefixes)
        shutil.copy2(PRODUCTION, run / 'trainer_source.py')
        start_utc = datetime.now(timezone.utc).isoformat()
        wall_start = time.perf_counter()
        env = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        child = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        import psutil
        child_identity = psutil.Process(child.pid)
        write_new(run / 'process.json', {'pid': child.pid, 'create_time': child_identity.create_time(), 'started_at': start_utc})
        observed_children = {}
        with (run / 'stdout.log').open('x', encoding='utf-8') as log:
            for line in child.stdout:
                log.write(line)
                log.flush()
                if '[Save] initial resume checkpoint' in line:
                    shutil.copy2(run / 'latest.pt', run / 'initial_resumed_state.pt')
                if 'envhands=' in line or 'Managed deal attempt:' in line:
                    print(f'{arm} attempt{number}: {line.strip()}', flush=True)
                if 'envhands=' in line:
                    try:
                        for descendant in child_identity.children(recursive=True):
                            observed_children[descendant.pid] = descendant.create_time()
                    except psutil.NoSuchProcess:
                        pass
        code = child.wait(timeout=10)
        wall_seconds = time.perf_counter() - wall_start
        cleanup_start = time.perf_counter()
        # Resource-tracker/worker exit can trail the parent by milliseconds.
        # Observe natural cleanup for at most five seconds; never kill or restart.
        while live_known_children(observed_children) and time.perf_counter() - cleanup_start < 5:
            time.sleep(.05)
        cleanup_seconds = time.perf_counter() - cleanup_start
        wall_seconds += cleanup_seconds
        write_new(run / 'termination.json', {'exit_code': code, 'wall_seconds': wall_seconds,
                  'started_at': start_utc, 'ended_at': datetime.now(timezone.utc).isoformat(),
                  'post_parent_cleanup_seconds': cleanup_seconds,
                  'observed_children': observed_children,
                  'remaining_observed_child_pids': live_known_children(observed_children)})
        if code != 0:
            raise RuntimeError(f'{run.name} exited {code}; preserve evidence, no automatic retry')
        if len(observed_children) < 12 or live_known_children(observed_children):
            raise RuntimeError('worker exit evidence missing or surviving child; do not launch next attempt')
        for name, prefix in prefixes.items():
            import hashlib
            with (run / name).open('rb') as handle:
                actual = hashlib.sha256(handle.read(prefix['bytes'])).hexdigest()
            if actual != prefix['sha256'] or sha(prefix['path']) != prefix['sha256']:
                raise RuntimeError(f'raw evidence prefix changed: {name}')
        result = inspect_attempt(run, parent, parent_path, parent_sha, wall_seconds)
        result.update(arm=arm, attempt=number, run_directory=str(run))
        write_new(run / 'verification.json', result)
        results.append(result)
        parents[arm] = run / 'latest.pt'
        del parent
    check_hashes(before['input_hashes'])
    report = summarize(results, time.perf_counter() - started)
    write_new(out / 'summary.json', report)
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
