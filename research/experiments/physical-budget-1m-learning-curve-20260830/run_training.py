"""One uninterrupted preregistered run, with live physical accounting.

Leaves the record RUNNING after training for frozen evaluation and analysis.
Existing output directories are never overwritten or silently resumed.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance

ID = 'physical-budget-1m-learning-curve-20260830'
BASE = Path('research/experiments') / ID
RUN = BASE / 'production'
SOURCE = 'models/baseline/standard10/latest.pt'
SOURCE_SHA = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'


def log(*args):
    subprocess.run([sys.executable, 'research/experiment_log.py', 'update', ID,
                    *map(str, args)], cwd=ROOT, check=True)


def main():
    if (ROOT / RUN).exists():
        raise RuntimeError('Refusing existing production directory; inspect before any resume')
    assert hashlib.sha256((ROOT / SOURCE).read_bytes()).hexdigest() == SOURCE_SHA
    snapshot = ROOT / BASE / 'execution_code'
    snapshot.mkdir(exist_ok=False)
    # Include all local Python modules so transitive environment/model imports
    # and untracked dependencies are recoverable, not merely the git patch.
    code_paths = [p.relative_to(ROOT).as_posix()
                  for p in sorted((ROOT / 'scripts/alpha_holdem').glob('*.py'))]
    code_paths += ['research/experiment_log.py', str(BASE / 'run_training.py')]
    _, artifacts = capture_code_provenance(ROOT, snapshot, code_paths)
    for relative in code_paths:
        src, dst = ROOT / relative, snapshot / 'source_files' / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        assert hashlib.sha256(src.read_bytes()).digest() == hashlib.sha256(dst.read_bytes()).digest()
    log(*[item for artifact in artifacts for item in ['--artifact', artifact]],
        '--artifact', str(BASE / 'execution_code/source_files'),
        '--note', 'Immutable pre-run snapshot contains all local alpha_holdem Python modules plus logger and launcher, including untracked files; full-byte copy hashes verified.')

    args = ['scripts/alpha_holdem/train_v5.py', '--device', 'cuda', '--workers', '12',
        '--hands-per-iter', '4096', '--total-hands', '99999999',
        '--total-environment-hands', '1048576', '--starting-stack', '200',
        '--env-version', 'v55preflopv2v4obs', '--norm-layer', 'gn', '--lr', '0.00003',
        '--ppo-epochs', '2', '--ppo-target-kl', '0.01', '--policy-advantage-clip', '3',
        '--source-policy-kl-coef', '1', '--separate-preflop-head',
        '--all-policy-heads-only-training', '--mini-batch-size', '1024',
        '--entropy-coef', '0.005', '--entropy-floor', '0.05', '--pool-strategy', 'latest',
        '--fixed-opponent-checkpoints', SOURCE,
        'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt',
        'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt',
        '--hero-policy-mode', 'sample', '--self-play-fraction', '0.25',
        '--opponent-assignment', 'per-group', '--opponent-groups', '8',
        '--adaptive-opponent-league', '--adaptive-league-ema', '0.9',
        '--adaptive-league-temperature-bb', '2', '--adaptive-league-min-probability', '0.05',
        '--opponent-assignment-provenance-file', str(RUN / 'opponent_assignments.jsonl'),
        '--rollout-mode', 'single', '--worker-seed-base', '2026089200',
        '--fixed-training-deal-stream', '--critic-contract', 'critic_v2',
        '--h1-effective-stack-divisor', '200', '--h1-critic-init-seed', '2026071102',
        '--value-coef', '1', '--autonomous-critic-v2-continue',
        '--snapshot-every', '999999', '--save-interval', '1', '--archive-checkpoint-every', '32',
        '--run-id', 'physical_budget_1m_20260830', '--run-dir', str(RUN),
        '--out', str(RUN / 'latest.pt'), '--seed', '20260892',
        '--max-runtime-seconds', '14400', '--resume', SOURCE, '--allow-resume',
        '--reset-optimizer', '--reset-hand-counter']
    log('--command', subprocess.list2cmdline(['python', '-u', *args]))
    stdout = ROOT / BASE / 'training_process_stdout.log'
    last_logged_iteration = -1
    with stdout.open('x', encoding='utf-8') as output:
        child = subprocess.Popen([sys.executable, '-u', *args], cwd=ROOT, stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        log('--metric', f'training_pid={child.pid}', '--metric', 'training_complete=0')
        while child.poll() is None:
            path = ROOT / RUN / 'run_manifest.json'
            if path.exists():
                try:
                    manifest = json.loads(path.read_text())
                    iteration = int(manifest.get('iteration', 0))
                    accounting = manifest.get('environment_hand_accounting') or {}
                    if iteration != last_logged_iteration and accounting.get('prefix_complete'):
                        log('--count', f"new_training_hands={accounting['completed_hands']}",
                            '--metric', f'latest_iteration={iteration}',
                            '--metric', f"legacy_marker_hands={manifest.get('total_hands', 0)}")
                        last_logged_iteration = iteration
                except (OSError, json.JSONDecodeError):
                    pass  # A concurrent atomic manifest replacement is transient.
            time.sleep(10)
    log('--metric', f'training_exit_code={child.returncode}', '--artifact', str(stdout.relative_to(ROOT)))
    if child.returncode:
        raise RuntimeError(f'Trainer exited {child.returncode}; retain evidence and inspect, never auto-restart')
    manifest = json.loads((ROOT / RUN / 'run_manifest.json').read_text())
    count = manifest['environment_hand_accounting']['completed_hands']
    log('--count', f'new_training_hands={count}', '--metric', f'latest_iteration={manifest["iteration"]}')
    if not manifest['environment_hand_accounting']['prefix_complete'] or count < 1048576:
        raise RuntimeError('Clean stop before budget: preserve session for explicit recovery assessment')
    audit = ['scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py', '--run-dir', str(RUN),
             '--expected-target-hands', '99999999', '--expected-target-environment-hands', '1048576',
             '--expected-final-iteration', str(manifest['iteration']), '--expected-pool-size', '3',
             '--expected-archive-every', '32', '--expected-normalization', 'global',
             '--out', str(BASE / 'production_audit.json')]
    log('--command', subprocess.list2cmdline(['python', *audit]))
    subprocess.run([sys.executable, *audit], cwd=ROOT, check=True)
    assert hashlib.sha256((ROOT / SOURCE).read_bytes()).hexdigest() == SOURCE_SHA
    artifacts = [str(RUN / name) for name in ['latest.pt', 'run_manifest.json',
                 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl', 'latest_train.log']]
    artifacts += [str(BASE / 'production_audit.json')]
    log('--metric', 'training_complete=1', '--metric', 'session_audit_pass=1',
        '--note', 'Training complete at measured physical endpoint. Record remains RUNNING pending preregistered frozen early/mid/final multi-anchor evaluation; do not infer strength from reward.',
        *[item for artifact in artifacts for item in ['--artifact', artifact]])


if __name__ == '__main__':
    main()
