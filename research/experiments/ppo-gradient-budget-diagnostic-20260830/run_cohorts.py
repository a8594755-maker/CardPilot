"""Execute preregistered physical-budget gradient cohorts; never reuse outputs."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance

ID = 'ppo-gradient-budget-diagnostic-20260830'
BASE = Path('research/experiments') / ID
SOURCE = 'models/baseline/standard10/latest.pt'
MATURE = ('research/experiments/adaptive-league-all-heads-pilot-20260830/'
          'production/checkpoints/checkpoint_iter000064_hands000000263602.pt')
ANCHORS = [SOURCE,
    'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt',
    'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt']


def execute(args):
    command = subprocess.list2cmdline(['python', *map(str, args)])
    subprocess.run([sys.executable, 'research/experiment_log.py', 'update', ID,
                    '--command', command], cwd=ROOT, check=True)
    return subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, check=True)


def main():
    mature_only = sys.argv[1:] == ['--mature-only']
    if sys.argv[1:] and not mature_only:
        raise ValueError('Only optional --mature-only is supported')
    if mature_only:
        source_audit = json.loads((ROOT / BASE / 'source_audit.json').read_text())
        assert source_audit['status'] == 'PASS'
    # All source bytes are copied, including untracked modules absent from git diff.
    import shutil
    code_paths = ['scripts/alpha_holdem/train_v5.py',
                  'scripts/alpha_holdem/train_mp3_hybrid_h1.py',
                  'scripts/alpha_holdem/test_ppo_gradient_diagnostics.py',
                  'scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py',
                  str(BASE / 'run_cohorts.py')]
    snapshot = ROOT / BASE / ('mature_execution_code' if mature_only else 'execution_code')
    snapshot.mkdir(exist_ok=False)
    _, artifacts = capture_code_provenance(ROOT, snapshot, code_paths)
    for relative in code_paths:
        source = ROOT / relative
        dest = snapshot / 'source_files' / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        assert hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(dest.read_bytes()).digest()
        artifacts.append(dest.relative_to(ROOT).as_posix())
    args = [sys.executable, 'research/experiment_log.py', 'update', ID]
    for artifact in artifacts:
        args += ['--artifact', artifact]
    args += ['--note', 'Pre-execution source snapshot includes full bytes of tracked and untracked code. No run will overwrite an existing cohort directory.']
    subprocess.run(args, cwd=ROOT, check=True)

    total = source_audit['actual_environment_hands'] if mature_only else 0
    cohorts = [('mature', MATURE)] if mature_only else [('source', SOURCE), ('mature', MATURE)]
    for cohort, checkpoint in cohorts:
        run = BASE / cohort
        if (ROOT / run).exists():
            raise RuntimeError(f'Refusing existing cohort output: {run}')
        command = ['scripts/alpha_holdem/train_v5.py',
            '--device', 'cuda', '--workers', '12', '--hands-per-iter', '4096',
            '--total-hands', '999999', '--total-environment-hands', '16384',
            '--starting-stack', '200', '--env-version', 'v55preflopv2v4obs',
            '--norm-layer', 'gn', '--lr', '0.00003', '--ppo-epochs', '2',
            '--ppo-target-kl', '0.01', '--policy-advantage-clip', '3',
            '--source-policy-kl-coef', '1', '--source-policy-reference-checkpoint', SOURCE,
            '--gradient-diagnostic-minibatches', '4', '--separate-preflop-head',
            '--all-policy-heads-only-training', '--mini-batch-size', '1024',
            '--entropy-coef', '0.005', '--entropy-floor', '0.05',
            '--pool-strategy', 'latest', '--fixed-opponent-checkpoints', *ANCHORS,
            '--hero-policy-mode', 'sample', '--self-play-fraction', '0.25',
            '--opponent-assignment', 'per-group', '--opponent-groups', '8',
            '--adaptive-opponent-league', '--adaptive-league-ema', '0.9',
            '--adaptive-league-temperature-bb', '2', '--adaptive-league-min-probability', '0.05',
            '--opponent-assignment-provenance-file', str(run / 'opponent_assignments.jsonl'),
            '--rollout-mode', 'single', '--worker-seed-base', '2026089000',
            '--fixed-training-deal-stream', '--critic-contract', 'critic_v2',
            '--h1-effective-stack-divisor', '200', '--h1-critic-init-seed', '2026071102',
            '--value-coef', '1', '--autonomous-critic-v2-continue',
            '--snapshot-every', '999999', '--save-interval', '1', '--archive-checkpoint-every', '1',
            '--run-id', f'ppo_gradient_{cohort}_20260830', '--run-dir', str(run),
            '--out', str(run / 'latest.pt'), '--seed', '20260890', '--max-runtime-seconds', '1200',
            '--resume', checkpoint, '--allow-resume', '--reset-hand-counter',
            '--reset-optimizer' if cohort == 'source' else '--no-reset-optimizer']
        execute(command)
        manifest = json.loads((ROOT / run / 'run_manifest.json').read_text())
        count = manifest['environment_hand_accounting']['completed_hands']
        assert manifest['environment_hand_accounting']['prefix_complete'] and count >= 16384
        total += count
        execute(['scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py',
                 '--run-dir', str(run), '--expected-target-hands', '999999',
                 '--expected-target-environment-hands', '16384',
                 '--expected-final-iteration', str(manifest['iteration']),
                 '--expected-pool-size', '3', '--expected-archive-every', '1',
                 '--expected-normalization', 'global', '--out', str(BASE / f'{cohort}_audit.json')])
        update = [sys.executable, 'research/experiment_log.py', 'update', ID,
                  '--count', f'new_training_hands={total}', '--metric', f'{cohort}_physical_hands={count}']
        for path in ['latest.pt', 'run_manifest.json', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl', 'latest_train.log']:
            update += ['--artifact', str(run / path)]
        update += ['--artifact', str(BASE / f'{cohort}_audit.json')]
        subprocess.run(update, cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
