"""One-shot continuation of this experiment only; never starts more training.

While this process is live it owns this experiment's logger updates. Do not edit
its frozen source dependencies or run a competing evaluation/record writer.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
EXPERIMENT = BASE.name
REL = BASE.relative_to(ROOT).as_posix()
PARENT = 'research/experiments/v6-static-current-kl-2m-scale-20260904'
TARGET = 4194304
PRODUCTION_SHA = '594f1de70f9a6abdf8076fe129a18056b5a3bd84087ad4f6cc2f1498850a6956'
ANCHORS = (
    'standard10=models/baseline/standard10/latest.pt',
    'cfr4=research/experiments/v6-cfr4-full-e2-greedy-fresh20k-confirmation-20260901/frozen/final.pt',
    'legacy_iter16=research/experiments/v6-legacy-iter16-greedy-fresh20k-20260901/frozen/final.pt',
    'legacy_mixed65k=research/experiments/v6-legacy-contract-mixed-league-65k-pilot-20260901/training/latest.pt',
)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def last_metric(path):
    with Path(path).open('rb') as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - 262144))
        lines = handle.read().splitlines()
    for line in reversed(lines):
        try:
            return json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    raise RuntimeError('no complete raw metric in tail')


def evidenced_evaluation_hands():
    rows = 0
    for seed in (1, 2, 3):
        path = BASE / f'eval_seed{seed}/common_deck_pairs.jsonl.gz'
        if not path.exists():
            continue
        # During a cohort the gzip footer may not yet exist. Only complete,
        # parseable pair rows count; unrecorded in-flight work remains unknown.
        try:
            with gzip.open(path, 'rt', encoding='utf-8') as handle:
                for line in handle:
                    if line.endswith('\n'):
                        json.loads(line)
                        rows += 1
        except (EOFError, OSError, json.JSONDecodeError):
            pass
    return rows * 4


def validate_original_audit(audit):
    if [row['name'] for row in audit['runs']] != ['seed1', 'seed2', 'seed3']:
        raise RuntimeError('original audit must include exactly all three seeds')
    if not all(audit['session_independence'].values()):
        raise RuntimeError('new session independence failure')
    for row in audit['runs']:
        allowed = {'corrected_legacy_contract_bound'}
        if row['name'] == 'seed2':
            allowed |= {'resume_controls_exact', 'physical_accounting_exact'}
        failed = {key for key, passed in row['gates'].items() if not passed}
        if failed - allowed:
            raise RuntimeError(f"unrelated original audit failure: {row['name']} {sorted(failed-allowed)}")
        if row['physical_environment_hands'] < TARGET:
            raise RuntimeError('original audit endpoint below target')
    # This whitelist only permits proceeding to the independent post-hoc
    # verifier. It does not make this historical audit pass or start evaluation.


def eval_argv(seed):
    argv = [sys.executable, 'scripts/alpha_holdem/v6_public_opponent_matched_eval.py',
            '--control', f'{PARENT}/seed{seed}/latest.pt',
            '--treatment', f'{REL}/seed{seed}/latest.pt']
    for anchor in ANCHORS:
        argv += ['--anchor', anchor]
    return argv + ['--pairs-per-anchor', '2048', '--seed', str(20263280+seed),
                   '--device', 'cuda', '--out-dir', f'{REL}/eval_seed{seed}']


def capture_process(pid, required_text):
    process = psutil.Process(pid)
    command = process.cmdline()
    if required_text not in ' '.join(command):
        raise RuntimeError(f'PID{pid} is not the expected process')
    return {'pid': pid, 'create_time': process.create_time(), 'command': command}


def same_process_live(identity):
    try:
        process = psutil.Process(identity['pid'])
        return process.is_running() and process.create_time() == identity['create_time']
    except psutil.NoSuchProcess:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trainer-pid', type=int, required=True)
    parser.add_argument('--launcher-pid', type=int, required=True)
    parser.add_argument('--directory', default='guarded_followthrough_v1')
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    if Path(args.directory).name != args.directory:
        parser.error('directory must be a single path component')
    identities = [capture_process(args.trainer_pid, 'scripts/alpha_holdem/train_v5.py'),
                  capture_process(args.launcher_pid, 'run_training_recovery2.ps1')]
    if sha(ROOT / 'scripts/alpha_holdem/train_v5.py') != PRODUCTION_SHA:
        raise RuntimeError('production source changed before pipeline ownership')
    for seed in (1, 2, 3):
        for prefix in ('eval', 'drift'):
            if (BASE / f'{prefix}_seed{seed}').exists():
                raise RuntimeError('evaluation evidence already exists; do not automatically redo it')
    watched = [ROOT / path for path in (
        'scripts/alpha_holdem/train_v5.py',
        'scripts/alpha_holdem/audit_v6_static_current_kl_1m_training.py',
        'scripts/alpha_holdem/v6_public_opponent_matched_eval.py',
        'scripts/alpha_holdem/v6_legacy_bridge_drift_audit.py',
        'scripts/alpha_holdem/aggregate_v6_static_current_kl_1m.py',
        'scripts/alpha_holdem/aggregate_v6_static_current_kl_262k.py',
    )] + [BASE / name for name in ('audit_frozen_endpoints.py', 'report_4m_deviation.py',
                                 'resume_deviation_amendment.md', 'run_guarded_followthrough.py')]
    watched.extend(sorted((ROOT / 'scripts/alpha_holdem').rglob('*.py')))
    source_hashes = {str(path): sha(path) for path in watched}
    if args.preflight_only:
        print(json.dumps({'passed': True, 'live_process_ids': [row['pid'] for row in identities],
            'unchanged_production': True, 'frozen_source_files': len(source_hashes),
            'evaluation_seeds': [20263281,20263282,20263283],
            'new_hands': 0, 'pipeline_started': False}))
        return
    directory = BASE / args.directory
    directory.mkdir()
    (directory / 'ownership.json').write_text(json.dumps({'pid': os.getpid(),
        'create_time': psutil.Process().create_time(), 'waited_processes': identities,
        'frozen_sources': source_hashes, 'scope': 'same experiment evaluation only; no new training'}, indent=2)+'\n')
    phase = 'WAITING_FOR_NATURAL_TRAINING_BOUNDARY'
    frozen_inputs = {}
    active_child = None

    def status(**extra):
        record = {'phase': phase, 'pid': os.getpid(), 'at': datetime.now(timezone.utc).isoformat(),
                  'active_child_pid': active_child.pid if active_child is not None and active_child.poll() is None else None, **extra}
        pending = directory / 'status.pending.json'
        pending.write_text(json.dumps(record, indent=2)+'\n')
        os.replace(pending, directory / 'status.json')
        print(json.dumps(record), flush=True)

    def update(note='', artifact=None, command=None):
        physical = []
        for seed in (1,2,3):
            run = BASE / f'seed{seed}'
            count = last_metric(run/'h1_training_metrics.jsonl')['environment_hand_accounting']['completed_hands']
            try:
                manifest = json.loads((run/'run_manifest.json').read_text())
                if manifest['status'] == 'finished':
                    count = manifest['environment_hand_accounting']['completed_hands']
            except json.JSONDecodeError:
                pass  # Concurrent legacy manifest write; last complete raw metric is authoritative.
            physical.append(count)
        total = sum(physical)
        argv = [sys.executable, 'research/experiment_log.py', 'update', EXPERIMENT,
                '--count', f'new_training_hands={total-6296802}',
                '--count', f'environment_training_hands={total-6296802}',
                '--count', f'lineage_training_hands={total}',
                '--count', f'evaluation_hands={evidenced_evaluation_hands()}',
                '--metric', f'guarded_pipeline_phase={json.dumps(phase)}']
        if note:
            argv += ['--note', note]
        if artifact:
            argv += ['--artifact', str(artifact)]
        if command:
            argv += ['--command', subprocess.list2cmdline(command)]
        subprocess.run(argv, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)

    def check_sources():
        for path, expected in {**source_hashes, **frozen_inputs}.items():
            if sha(path) != expected:
                raise RuntimeError(f'frozen pipeline dependency changed: {path}')

    def run_once(name, argv, artifact, allowed_codes=(0,)):
        nonlocal active_child
        check_sources()
        if artifact.exists():
            raise RuntimeError(f'refusing to redo or overwrite existing output: {artifact}')
        command_path = directory / f'{name}.command.json'
        command_path.write_text(json.dumps(argv, indent=2)+'\n')
        update(command=argv, artifact=command_path)
        status(active_command=name)
        with (directory / f'{name}.stdout.log').open('x', encoding='utf-8') as log:
            child = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                env=dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'))
            active_child = child
            status(active_command=name, child_pid=child.pid)
            last_update = time.monotonic()
            while child.poll() is None:
                time.sleep(5)
                if time.monotonic() - last_update >= 60:
                    update()
                    last_update = time.monotonic()
            if child.returncode not in allowed_codes:
                raise RuntimeError(f'{name} exited{child.returncode}; preserve its raw evidence')
            active_child = None
        if not artifact.exists():
            raise RuntimeError(f'{name} did not produce its required artifact')
        update(artifact=artifact)

    try:
        status()
        update(note='One-shot guarded followthrough owns this experiment logger until terminal. It waits for the exact live trainer and launcher identities, never restarts training, requires actual4M endpoints and independent mechanical qualification, preserves original audit failures, and runs only the existing preregistered evaluation. No production source edits or competing record writer while owner is live.', artifact=directory/'ownership.json')
        last_update = time.monotonic()
        while any(same_process_live(identity) for identity in identities):
            time.sleep(5)
            if time.monotonic() - last_update >= 300:
                update()
                last_update = time.monotonic()
        check_sources()
        import torch
        torch.set_num_threads(1)
        for seed in (1,2,3):
            path = BASE / f'seed{seed}/latest.pt'
            before = sha(path)
            checkpoint = torch.load(path, map_location='cpu', weights_only=False)
            manifest = json.loads((path.parent/'run_manifest.json').read_text())
            if before != sha(path) or manifest['status'] != 'finished':
                raise RuntimeError('terminal process did not leave a stable finished checkpoint')
            if checkpoint['environment_hand_accounting']['completed_hands'] < TARGET:
                phase = 'SAFE_BOUNDARY_NEEDS_MANAGED_TRAINING_CONTINUATION'
                status(seed=seed, physical_hands=checkpoint['environment_hand_accounting']['completed_hands'])
                update(note='Natural process boundary below target: no evaluation started and no work replayed. Main researcher must preserve checkpoint, integrate/qualify managed resume, and continue only remaining hands.')
                return
            if manifest['iteration'] != checkpoint['iteration']:
                raise RuntimeError('terminal manifest/checkpoint iteration mismatch')
            frozen_inputs[str(path)] = before
            parent_path = ROOT / PARENT / f'seed{seed}/latest.pt'
            frozen_inputs[str(parent_path)] = sha(parent_path)
        for value in ANCHORS:
            path = ROOT / value.split('=',1)[1]
            frozen_inputs[str(path)] = sha(path)
        (directory/'frozen_evaluation_inputs.json').write_text(json.dumps(frozen_inputs,indent=2)+'\n')
        phase = 'ORIGINAL_AND_INDEPENDENT_MECHANICS'
        audit_path = BASE / 'training_audit.json'
        argv = [sys.executable, 'scripts/alpha_holdem/audit_v6_static_current_kl_1m_training.py',
                '--experiment-dir', REL, '--base', 'models/baseline/standard10/latest.pt',
                '--min-environment-hands', str(TARGET)]
        for iteration in (448,512,576,640,704,768,832):
            argv += ['--expected-archive-iteration', str(iteration)]
        argv += ['--schema', 'cardpilot.static_current_kl_4m_training_audit.v1', '--out', str(audit_path)]
        run_once('original_audit', argv, audit_path, (0,1))
        validate_original_audit(json.loads(audit_path.read_text()))
        posthoc = BASE / 'frozen_allseed_mechanics_inherited_bridge.json'
        run_once('posthoc_mechanics', [sys.executable, str(BASE/'audit_frozen_endpoints.py'),
            '--seeds', '1','2','3','--verify-inherited-bridge','--out',str(posthoc)], posthoc)
        if not json.loads(posthoc.read_text())['posthoc_observed_mechanics_passed']:
            raise RuntimeError('post-hoc qualification did not pass')
        phase = 'PREREGISTERED_FROZEN_EVALUATION'
        for seed in (1,2,3):
            run_once(f'eval_seed{seed}', eval_argv(seed), BASE/f'eval_seed{seed}/summary.json')
        phase = 'PREREGISTERED_OFFLINE_DRIFT'
        for seed in (1,2,3):
            out = BASE / f'drift_seed{seed}'
            argv = [sys.executable, 'scripts/alpha_holdem/v6_legacy_bridge_drift_audit.py',
                '--parent','models/baseline/standard10/latest.pt','--parent-sha256',
                '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428',
                '--treatment',f'{REL}/seed{seed}/latest.pt','--out-dir',str(out),
                '--states','20000','--seed',str(20263290+seed),'--device','cuda',
                '--batch-size','1024','--source-tv-max','1','--greedy-disagreement-max','1']
            run_once(f'drift_seed{seed}',argv,out/'drift_analysis.json')
        phase = 'DESCRIPTIVE_AGGREGATION_NO_AUTO_SCALE'
        aggregate = BASE / 'aggregate.json'
        argv = [sys.executable, 'scripts/alpha_holdem/aggregate_v6_static_current_kl_1m.py', '--experiment-dir', REL]
        for prior in ('v6-static-current-kl-262k-scale-20260903','v6-static-current-kl-262k-fresh-confirmation-20260903',
                      'v6-static-current-kl-1m-scale-20260903','v6-static-current-kl-2m-scale-20260904'):
            argv += ['--prior-dir',f'research/experiments/{prior}']
        argv += ['--expected-prior-raw-rows','122880','--eval-seed-base','20263280','--drift-seed-base','20263290',
                 '--scale-label','4M','--schema','cardpilot.static_current_kl_4m_aggregate.v1',
                 '--breadth-informational-only','--require-positive-combined','--require-improved-breadth','--out',str(aggregate)]
        run_once('original_aggregate',argv,aggregate,(0,1))
        report = BASE / 'deviation_aware_report.json'
        run_once('deviation_report',[sys.executable,str(BASE/'report_4m_deviation.py'),
            '--legacy-aggregate',str(aggregate),'--posthoc-mechanics',str(posthoc),'--out',str(report)],report)
        phase = 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS'
        status(report=str(report))
        update(note='All original evaluation and drift budgets completed. Original failed gates/labels remain preserved; scoped report uses preregisteredOR and fixed1/3 subset. No automatic promotion or next training. Main researcher must analyze results, finish this record, then choose compute allocation.',artifact=report)
    except BaseException as error:
        phase = 'STOPPED_FOR_RESEARCHER_ATTENTION'
        status(error=f'{type(error).__name__}: {error}')
        update(note=f'Guarded followthrough stopped without restarting/overwriting evidence: {type(error).__name__}: {error}', artifact=directory/'status.json')
        raise


if __name__ == '__main__':
    main()
