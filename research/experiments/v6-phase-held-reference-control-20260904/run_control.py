"""Single-owner preregistered phase-control; no retries, resets or old-run writes."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

import psutil
import control_evidence as evidence

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT = ROOT / 'research/experiments/v6-static-current-kl-4m-scale-20260904/seed1/latest.pt'
PARENT_SHA = '7ea4d74d0fcf881c75c4c99bdc0cbe84f82a55001ba277c01aafec6dc5a98f3f'
PRODUCTION = ROOT / 'scripts/alpha_holdem/train_v5.py'
PRODUCTION_SHA = '1b4d23abfa3e0a9c675126fd7183d37b134a2a13253563e990e144cc01a90f8b'
INITIAL_PHYSICAL = 4197976
TARGETS = {1: INITIAL_PHYSICAL + 2097152, 2: INITIAL_PHYSICAL + 4194304}
ORDER = (('static', 1), ('moving256', 1), ('moving256', 2), ('static', 2))
GPU_HELPER = ROOT / 'research/experiments/v6-managed-trainer-resume-integration-20260904/run_gpu_resume_qualification.py'
GPU_HELPER_SHA = 'c9430179f702d3871c4297ad837decf9d1b4327fc12cf537a8ec4ad9ff2a262a'
ANCHORS = {
    'standard10': ROOT / 'models/baseline/standard10/latest.pt',
    'cfr4': ROOT / 'research/experiments/v6-cfr4-full-e2-greedy-fresh20k-confirmation-20260901/frozen/final.pt',
    'legacy_iter16': ROOT / 'research/experiments/v6-legacy-iter16-greedy-fresh20k-20260901/frozen/final.pt',
    'legacy_mixed65k': ROOT / 'research/experiments/v6-legacy-contract-mixed-league-65k-pilot-20260901/training/latest.pt',
}
ANCHOR_SHA256 = {
    'standard10': '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428',
    'cfr4': '571a9c413834247c80b63a797548689ea745878c060f265876d00bddcc3ff2db',
    'legacy_iter16': '0b1b58a87637f620ae580754bc940ec7aca246d94762d77717c9b578aac9f290',
    'legacy_mixed65k': 'defe2b5904386ffb97c737d36ffe29e2ba013f92584515dacfb53c9f54eb11bb',
}
POOL_HELPER = ROOT / 'research/experiments/v6-static-current-kl-4m-scale-20260904/audit_pool_history_windows.py'


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def write_status(value):
    pending = BASE / 'status.pending.json'
    with pending.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(pending, BASE / 'status.json')


def check_hashes(expected):
    for path, digest in expected.items():
        evidence.require(sha(path) == digest, f'frozen input changed: {path}')


def owner_live(owner):
    try:
        process = psutil.Process(int(owner['pid']))
        return abs(process.create_time() - owner['create_time']) < .001 and process.is_running()
    except psutil.NoSuchProcess:
        return False


def logger_update(*args):
    result = subprocess.run([sys.executable, str(ROOT / 'research/experiment_log.py'),
                             'update', BASE.name, *args], cwd=ROOT, capture_output=True, text=True,
                            encoding='utf-8', timeout=45)
    evidence.require(result.returncode == 0, f'experiment logger failed: {result.stderr}')


def complete_jsonl(path):
    if not path.exists():
        return []
    rows = []
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            if not line.endswith('\n'):
                break
            if line.strip():
                rows.append(json.loads(line))
    return rows


def gzip_count(path):
    import gzip
    if not path.exists():
        return 0
    count = 0
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            for line in handle:
                if line.endswith('\n') and line.strip():
                    json.loads(line)
                    count += 1
    except EOFError:
        pass  # live gzip footer not yet written; only complete rows counted
    return count


def live_accounting():
    totals = {'new_training_hands': 0, 'new_transition_hands': 0, 'evaluation_hands': 0,
              'offline_samples': 0, 'slumbot_hands': 0}
    runs = {}
    for arm, stage in ORDER:
        run = stage_directory(arm, stage)
        contract = run / 'parent_contract.json'
        if not contract.exists():
            continue
        old = evidence.read_json(contract)
        rows = complete_jsonl(run / 'h1_training_metrics.jsonl')
        if not rows:
            continue
        row = rows[-1]
        physical, transition = row['environment_hand_accounting']['completed_hands'], row['hands']
        manifest_path = run / 'run_manifest.json'
        if manifest_path.exists():
            try:
                manifest = evidence.read_json(manifest_path)
                if manifest.get('status') == 'finished':
                    physical = manifest['environment_hand_accounting']['completed_hands']
                    transition = manifest['total_hands']
            except json.JSONDecodeError:
                pass  # do not substitute partial manifest; complete metric is a lower bound
        new = physical - old['physical_hands']
        new_trans = transition - old['transition_hands']
        evidence.require(new >= 0 and new_trans >= 0, 'live counter reset')
        totals['new_training_hands'] += new
        totals['new_transition_hands'] += new_trans
        runs[run.name] = {'iteration': row['iteration'], 'physical_hands': physical,
                          'new_physical_hands': new, 'new_transition_hands': new_trans,
                          'target': TARGETS[stage], 'raw_counter_is_lower_bound_while_live': True}
    for stage in (1, 2):
        for arm in ('static', 'moving256'):
            totals['evaluation_hands'] += 4 * gzip_count(BASE / f'eval_{arm}_stage{stage}/common_deck_pairs.jsonl.gz')
            totals['offline_samples'] += gzip_count(BASE / f'drift_{arm}_stage{stage}/drift_raw.jsonl.gz')
    return totals, runs


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def qualified_command_helper():
    if sha(GPU_HELPER) != GPU_HELPER_SHA:
        raise ValueError('Qualified command helper changed')
    spec = importlib.util.spec_from_file_location('phase_control_qualified_gpu_commands', GPU_HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def set_option(argv, option, value):
    if argv.count(option) != 1:
        raise ValueError(f'Expected one option: {option}')
    argv[argv.index(option) + 1] = str(value)


def stage_directory(arm, stage):
    if arm not in ('static', 'moving256') or stage not in TARGETS:
        raise ValueError('Unknown preregistered arm/stage')
    return BASE / f'{arm}_stage{stage}'


def training_command(arm, stage, parent_path, parent_physical):
    run = stage_directory(arm, stage)
    argv = qualified_command_helper().command(run, Path(parent_path), int(parent_physical),
                                               'multi8', BASE / 'attempt_registry')
    set_option(argv, '--total-environment-hands', TARGETS[stage])
    set_option(argv, '--max-runtime-seconds', 7200)
    if arm == 'moving256':
        index = argv.index('--source-policy-reference-checkpoint')
        del argv[index:index + 2]
        argv += ['--source-policy-reference-refresh-updates', '256']
    else:
        argv += ['--source-policy-reference-refresh-updates', '0']
    return argv


def preflight():
    expected = {str(PARENT): PARENT_SHA, str(PRODUCTION): PRODUCTION_SHA,
                str(GPU_HELPER): GPU_HELPER_SHA}
    checks = {f'sha:{path}': sha(path) == digest for path, digest in expected.items()}
    for experiment in ('v6-static-current-kl-4m-scale-20260904',
                       'v6-managed-trainer-resume-integration-20260904',
                       'v6-static-seed1-4m-greedy-fresh20k-slumbot-20260904'):
        record = json.loads((ROOT / 'research/experiments' / experiment / 'experiment.json').read_text(encoding='utf-8'))
        checks[f'completed:{experiment}'] = record['status'] == 'COMPLETED'
    conflicts = []
    names = {'train_v5.py', 'train_v5_managed_candidate.py', 'play_slumbot_v6_journaled.py',
             'audit_bridge_cli.py', 'gpu_qualification_v2_handoff.py', 'v6_public_opponent_matched_eval.py'}
    for proc in psutil.process_iter(['pid', 'cmdline']):
        if any(Path(arg).name in names for arg in proc.info['cmdline'] or []):
            conflicts.append(proc.pid)
    checks['no_active_training_or_evaluation'] = not conflicts
    checks['stage_outputs_unused'] = not any(stage_directory(*item).exists() for item in ORDER)
    checks['owner_not_previously_reserved'] = not (BASE / 'ownership.json').exists()
    checks['anchors_match_frozen_preregistered_weights'] = all(
        path.is_file() and sha(path) == ANCHOR_SHA256[name] for name, path in ANCHORS.items())
    checks['space_at_least_12GB'] = shutil.disk_usage(BASE).free > 12 * 1024**3
    qualification = BASE / 'controller_tests.xml'
    checks['controller_tests_passed'] = False
    if qualification.is_file():
        import xml.etree.ElementTree as ET
        root = ET.parse(qualification).getroot()
        suites = list(root.iter('testsuite'))
        checks['controller_tests_passed'] = bool(suites) and all(
            int(s.get('tests', '0')) >= 15 and int(s.get('failures', '0')) == 0 and
            int(s.get('errors', '0')) == 0 for s in suites)
    return {'schema': 'cardpilot.phase_control.command_preflight.v1',
            'mechanical_preconditions_passed': all(checks.values()), 'checks': checks,
            'conflicting_pids': conflicts, 'source_sha256': expected,
            'stage_targets': TARGETS, 'order': ORDER, 'new_hands': 0,
            'training_started': False, 'training_authorized': all(checks.values()),
            'implementation_stage': 'QUALIFIED_CONTROLLER' if all(checks.values()) else 'PREFLIGHT_BLOCKED'}


class SafeBoundary(Exception):
    pass


def target_or_safe_boundary(final_physical, target):
    if int(final_physical) < int(target):
        raise SafeBoundary('Natural completed-update runtime boundary below target; no automatic restart')


class Controller:
    def __init__(self):
        before = preflight()
        evidence.require(before['training_authorized'], json.dumps(before))
        self.started = time.perf_counter()
        self.owner = {'pid': os.getpid(), 'create_time': psutil.Process().create_time(),
                      'started_at': datetime.now(timezone.utc).isoformat(),
                      'command': [sys.executable, *sys.argv]}
        # Exclusive persistent receipt: even a dead previous owner needs researcher review.
        write_new(BASE / 'ownership.json', self.owner)
        self.phase = 'FREEZING_INPUTS'
        self.child = None
        self.results = []
        sources = list((ROOT / 'scripts/alpha_holdem').rglob('*.py'))
        sources += list(BASE.glob('*.py')) + [GPU_HELPER, GPU_HELPER.parent / 'run_cpu_resume_probe.py',
                                             POOL_HELPER, ROOT / 'research/experiment_log.py']
        self.sources = {str(p): sha(p) for p in sources}
        self.inputs = {**self.sources, str(PARENT): PARENT_SHA, str(BASE / 'protocol.md'): sha(BASE / 'protocol.md')}
        self.inputs.update({str(p): sha(p) for p in ANCHORS.values()})
        for p in (ROOT.parent / 'CardPilot_legacy_20260829/selected_assets/opponents').glob('*.pt'):
            if p.name in ('slumbot_free_anchor_position10m.pt', 'corrected_cfr96_anchor10.pt'):
                self.inputs[str(p)] = sha(p)
        for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl', 'run_manifest.json'):
            path = PARENT.parent / name
            self.inputs[str(path)] = sha(path)
        self.anchors = {key: {'path': str(path), 'sha256': sha(path)} for key, path in ANCHORS.items()}
        evidence.require(self.anchors['standard10']['sha256'] == qualified_command_helper().STANDARD_SHA, 'reference changed')
        self.corpus = {str(p): sha(p) for p in (ROOT / 'research/experiments').rglob('common_deck_pairs.jsonl.gz')
                       if not p.is_relative_to(BASE)}
        write_new(BASE / 'input_contract.json', {'preflight': before, 'input_sha256': self.inputs,
                  'anchors': self.anchors, 'prior_common_deck_corpus': self.corpus,
                  'statistical_not_bitwise_worker_continuation': True})
        self.last_tick = 0
        logger_update('--status', 'RUNNING', '--metric', 'controller_implemented=true',
                      '--metric', 'training_started=false', '--command', subprocess.list2cmdline(self.owner['command']),
                      '--artifact', str(BASE / 'input_contract.json'), '--artifact', str(BASE / 'ownership.json'),
                      '--artifact', str(BASE / 'run_control.py'), '--artifact', str(BASE / 'control_evidence.py'),
                      '--artifact', str(BASE / 'controller_tests.xml'),
                      '--note', 'One owner now owns this record and frozen sources. No retries or overwrites; statistical managed continuation, not bitwise worker replay. Initial rebasing is part of treatment.')

    def tick(self, force=False):
        if not force and time.perf_counter() - self.last_tick < 60:
            return
        evidence.require(owner_live(self.owner), 'controller ownership lost')
        check_hashes(self.sources)
        totals, runs = live_accounting()
        status = {**self.owner, 'phase': self.phase, 'updated_at': datetime.now(timezone.utc).isoformat(),
                  'active_child_pid': self.child.pid if self.child and self.child.poll() is None else None,
                  'accounting': totals, 'runs': runs, 'controller_wall_seconds': time.perf_counter() - self.started}
        write_status(status)
        args = [item for key, value in totals.items() for item in ('--count', f'{key}={value}')]
        logger_update(*args, '--metric', f'controller_phase={self.phase}')
        print(json.dumps({'phase': self.phase, 'accounting': totals, 'runs': runs}), flush=True)
        self.last_tick = time.perf_counter()

    def execute(self, argv, run, observer=None, training=False):
        check_hashes(self.inputs)
        write_new(run / 'command.json', argv)
        logger_update('--command', subprocess.list2cmdline(argv), '--artifact', str(run / 'command.json'))
        begun = time.perf_counter()
        self.child = subprocess.Popen(argv, cwd=ROOT, env=dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        identity = psutil.Process(self.child.pid)
        write_new(run / 'process.json', {'pid': self.child.pid, 'create_time': identity.create_time(),
                  'started_at': datetime.now(timezone.utc).isoformat()})
        lines, observed, errors = queue.Queue(), {}, []

        def reader():
            try:
                for line in self.child.stdout:
                    lines.put(line)
            finally:
                lines.put(None)

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        with (run / 'stdout.log').open('x', encoding='utf-8') as log:
            while True:
                try:
                    line = lines.get(timeout=2)
                    if line is None:
                        break
                    log.write(line)
                    log.flush()
                    if observer and not errors:
                        observer(line)
                except queue.Empty:
                    pass
                except Exception as exc:
                    errors.append(repr(exc))
                    self.phase = 'OBSERVER_ERROR_PRESERVING_CURRENT_ATTEMPT'
                    write_new(run / 'observer_error.json', {'error': repr(exc), 'no_next_job': True})
                try:
                    for desc in identity.children(recursive=True):
                        observed[desc.pid] = desc.create_time()
                except psutil.NoSuchProcess:
                    pass
                try:
                    self.tick()
                except Exception as exc:
                    if repr(exc) not in errors:
                        errors.append(repr(exc))
                        print(f'Controller evidence error; draining existing attempt, no next job: {exc}', flush=True)
        code = self.child.wait(timeout=10)
        helper = qualified_command_helper()
        deadline = time.perf_counter() + 5
        while helper.live_known_children(observed) and time.perf_counter() < deadline:
            time.sleep(.05)
        wall = time.perf_counter() - begun
        live = helper.live_known_children(observed)
        write_new(run / 'termination.json', {'exit_code': code, 'wall_seconds': wall,
                  'ended_at': datetime.now(timezone.utc).isoformat(), 'observed_children': observed,
                  'remaining_observed_child_pids': live, 'observer_errors': errors})
        self.child = None
        evidence.require(code == 0 and not errors and not live, f'Job failed, preserved without retry: {run.name}, {code}, {errors}, {live}')
        evidence.require(not training or len(observed) >= 12, 'missing worker exit evidence')
        check_hashes(self.inputs)
        self.tick(force=True)
        return wall

    def train(self, arm, stage):
        import torch
        torch.set_num_threads(1)
        parent_path = PARENT if stage == 1 else stage_directory(arm, 1) / 'latest.pt'
        parent_sha = sha(parent_path)
        if stage == 2:
            evidence.require(parent_sha == evidence.read_json(parent_path.parent / 'verification.json')['checkpoint_sha256'], 'stage1 changed')
        parent = torch.load(parent_path, map_location='cpu', weights_only=False)
        old = int(parent['environment_hand_accounting']['completed_hands'])
        evidence.require(old < TARGETS[stage], 'target already satisfied; never redo')
        run = stage_directory(arm, stage)
        run.mkdir()
        write_new(run / 'parent_contract.json', {'path': str(parent_path), 'sha256': parent_sha,
                  'physical_hands': old, 'transition_hands': int(parent['total_hands']), 'iteration': parent['iteration']})
        prefixes = {}
        for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
            source = parent_path.parent / name
            prefixes[name] = {'path': str(source), 'sha256': sha(source), 'bytes': source.stat().st_size}
            shutil.copy2(source, run / name)
        write_new(run / 'prefixes.json', prefixes)
        shutil.copy2(PRODUCTION, run / 'trainer_source.py')
        helper = qualified_command_helper()
        last_iteration = int(parent['iteration'])

        def capture(line):
            nonlocal last_iteration
            match = re.match(r'\[\s*(\d+)\]', line)
            if match:
                last_iteration = int(match.group(1))
            initial = '[Save] initial resume checkpoint' in line
            boundary = arm == 'moving256' and '[Save]' in line and not initial and (last_iteration - 882) % 256 == 0
            if initial or boundary:
                path = run / ('initial_resumed_state.pt' if initial else f'phase_iter{last_iteration:06d}.pt')
                evidence.require(not path.exists(), 'checkpoint evidence would be overwritten')
                shutil.copy2(run / 'latest.pt', path)
                checkpoint = torch.load(path, map_location='cpu', weights_only=False)
                evidence.require(checkpoint['iteration'] == last_iteration, 'capture raced checkpoint save')
                if initial:
                    evidence.initial_reference(arm, parent, checkpoint, helper.equal)
                    for key in ('model', 'optimizer', 'ppo_replay_entries', 'ppo_replay_rng_state',
                                'ppo_replay_cumulative_rows', 'pool_snapshots', 'pool_candidate_history'):
                        evidence.require(helper.equal(parent[key], checkpoint[key]), f'initial state changed: {key}')
                    logger_update('--metric', 'training_started=true', '--artifact', str(path),
                                  '--note', f'{run.name}: actual initial completed checkpoint captured and checked; no counter/optimizer/replay reset.')
                else:
                    state = evidence.reference_state(checkpoint)
                    evidence.require(helper.equal(state['reference_model'], checkpoint['model']), 'phase refresh not exact actor')

        self.phase = f'TRAINING_{run.name}'
        wall = self.execute(training_command(arm, stage, parent_path, old), run, capture, training=True)
        final = torch.load(run / 'latest.pt', map_location='cpu', weights_only=False)
        for name, info in prefixes.items():
            with (run / name).open('rb') as handle:
                prefix_hash = hashlib.sha256(handle.read(info['bytes'])).hexdigest()
            evidence.require(prefix_hash == info['sha256'] == sha(info['path']), 'raw prefix changed')
        # Below-target terminal evidence remains intact and receives accounting, not an algorithm failure.
        target_or_safe_boundary(final['environment_hand_accounting']['completed_hands'], TARGETS[stage])
        helper.DELTA = TARGETS[stage] - old
        result = helper.inspect_attempt(run, parent, parent_path, parent_sha, wall)
        initial = torch.load(run / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
        paths = list((run / 'checkpoints').glob('*.pt')) + list(run.glob('phase_iter*.pt')) + [run / 'latest.pt']
        pool = evidence.module_at('phase_pool_windows', POOL_HELPER)
        pool_windows = [pool.load_window(parent_path, parent_sha)]
        reference_windows, checkpoint_hashes = [], {}
        for path in paths:
            digest = sha(path)
            ckpt = torch.load(path, map_location='cpu', weights_only=False)
            if ckpt['iteration'] <= parent['iteration']:
                continue
            checkpoint_hashes[str(path)] = digest
            pool_windows.append(pool.load_window(path, digest))
            reference_windows.append({key: ckpt[key] for key in ('iteration', 'model', 'environment_hand_accounting')}
                                     | {'moving_source_policy_reference': ckpt.get('moving_source_policy_reference')})
        pool_windows.sort(key=lambda w: w['iteration'])
        reference_windows.sort(key=lambda c: c['iteration'])
        metrics = complete_jsonl(run / 'h1_training_metrics.jsonl')
        assignments = complete_jsonl(run / 'opponent_assignments.jsonl')
        result['pool_window_audit'] = pool.verify_windows(pool_windows, metrics, assignments)
        result['moving_reference_audit'] = evidence.verify_reference_windows(arm, parent, initial, reference_windows, metrics, helper.equal)
        result.update(arm=arm, stage=stage, checkpoint_windows_sha256=checkpoint_hashes,
                      overshoot_hands=int(final['environment_hand_accounting']['completed_hands']) - TARGETS[stage],
                      new_replay_rows=final['ppo_replay_cumulative_rows'] - parent['ppo_replay_cumulative_rows'],
                      new_no_decision_hands=final['environment_hand_accounting']['no_trainable_decision_hands'] -
                          parent['environment_hand_accounting']['no_trainable_decision_hands'],
                      statistical_not_bitwise_worker_continuation=True, unknown_crash_suffix_hands=0)
        result['residual_worker_tail_hands'] = result['new_physical_hands'] - result['new_transition_hands'] - result['new_no_decision_hands']
        evidence.require(result['namespace'] not in [r['namespace'] for r in self.results], 'duplicate managed namespace')
        write_new(run / 'verification.json', result)
        self.results.append(result)
        self.inputs[str(run / 'latest.pt')] = result['checkpoint_sha256']
        logger_update('--artifact', str(run / 'verification.json'), '--artifact', str(run / 'termination.json'),
                      '--artifact', str(run / 'latest.pt'), '--artifact', str(run / 'h1_training_metrics.jsonl'),
                      '--artifact', str(run / 'opponent_assignments.jsonl'),
                      '--note', f'{run.name} completed target with preserved optimizer/replay and audited reference/pool history.')
        self.tick(force=True)

    def evaluate(self, stage):
        hashes = {}
        for arm in ('static', 'moving256'):
            checkpoint = stage_directory(arm, stage) / 'latest.pt'
            hashes[arm] = sha(checkpoint)
            run = BASE / f'eval_{arm}_stage{stage}'
            evidence.require(not run.exists(), 'evaluation output already exists')
            job = BASE / f'job_eval_{arm}_stage{stage}'
            job.mkdir()
            command = [sys.executable, '-u', str(ROOT / 'scripts/alpha_holdem/v6_public_opponent_matched_eval.py'),
                       '--control', str(PARENT), '--treatment', str(checkpoint)]
            for name, path in ANCHORS.items():
                command += ['--anchor', f'{name}={path}']
            command += ['--pairs-per-anchor', '2048', '--seed', str(20263410 + stage), '--device', 'cuda', '--out-dir', str(run)]
            self.phase = f'EVALUATING_{arm}_stage{stage}'
            self.execute(command, job)
            drift = BASE / f'drift_{arm}_stage{stage}'
            drift.mkdir()
            command = [sys.executable, '-u', str(ROOT / 'scripts/alpha_holdem/v6_legacy_bridge_drift_audit.py'),
                       '--parent', str(ANCHORS['standard10']), '--parent-sha256', self.anchors['standard10']['sha256'],
                       '--treatment', str(checkpoint), '--out-dir', str(drift), '--states', '20000',
                       '--seed', str(20263420 + stage), '--device', 'cuda', '--batch-size', '1024',
                       '--source-tv-max', '1', '--greedy-disagreement-max', '1']
            self.phase = f'DRIFT_{arm}_stage{stage}'
            self.execute(command, drift)
        self.phase = f'AGGREGATING_stage{stage}'
        result = evidence.aggregate_stage(stage, BASE, PARENT_SHA, hashes, self.anchors, self.corpus)
        write_new(BASE / f'stage{stage}_analysis.json', result)
        for arm in ('static', 'moving256'):
            path = BASE / f'eval_{arm}_stage{stage}/common_deck_pairs.jsonl.gz'
            self.corpus[str(path)] = sha(path)
        logger_update('--artifact', str(BASE / f'stage{stage}_analysis.json'),
                      '--note', f'Stage{stage} completed fixed common-deck comparisons, repeated-parent join and prior-corpus check. Broad-collapse gate={result["broad_collapse"]}; no final-benchmark claim.')
        self.tick(force=True)
        return result

    def run(self):
        try:
            self.train('static', 1)
            self.train('moving256', 1)
            stage1 = self.evaluate(1)
            if stage1['broad_collapse']:
                self.phase = 'PREREGISTERED_BROAD_COLLAPSE_RESEARCH_REVIEW'
            else:
                self.train('moving256', 2)
                self.train('static', 2)
                self.evaluate(2)
                self.phase = 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS'
            write_new(BASE / 'pipeline_result.json', {'phase': self.phase, 'runs': self.results,
                      'wall_seconds': time.perf_counter() - self.started, 'final_goal_qualified': False})
        except SafeBoundary as exc:
            self.phase = 'SAFE_BOUNDARY_REQUIRES_RESEARCHER_RESUME_REVIEW'
            write_new(BASE / 'safe_boundary.json', {'reason': str(exc), 'preserved': True, 'automatic_retry': False})
            logger_update('--note', str(exc), '--artifact', str(BASE / 'safe_boundary.json'))
        except BaseException as exc:
            self.phase = 'ERROR_PRESERVED_RESEARCH_REVIEW'
            write_new(BASE / 'controller_error.json', {'error': repr(exc), 'automatic_retry': False})
            raise
        finally:
            self.tick(force=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    if args.preflight_only:
        print(json.dumps(preflight(), indent=2))
    else:
        Controller().run()


if __name__ == '__main__':
    main()
