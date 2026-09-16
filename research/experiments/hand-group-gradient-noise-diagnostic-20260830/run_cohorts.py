"""Bounded fresh source/mature cohorts with immutable code provenance and counts."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
ID = BASE.name
sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance

SOURCE = ROOT / 'models/baseline/standard10/latest.pt'
MATURE = ROOT / 'research/experiments/physical-budget-1m-learning-curve-20260830/frozen/final.pt'
ANCHORS = [SOURCE,
    Path('C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt'),
    Path('C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt')]
DIGESTS = ['91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428',
           '457d3babb82cb8014a2b7c378b2b5f916962565e63a44d192d5d7acd8393d6e7',
           '902a7049ca66c0552246d11fe482eed4df47ac5c675ddf051c34ed86dcf213a6']
MATURE_SHA = 'ddab8c71090a78346bbd9b2b425fd3676a2d6c1cd30e649fa95aab1ff06fa7a3'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def log(*args):
    subprocess.run([sys.executable, 'research/experiment_log.py', 'update', ID, *map(str, args)],
                   cwd=ROOT, check=True)


def command_record(command):
    log('--command', subprocess.list2cmdline(['python', *map(str, command)]))


def make_command(cohort, seed):
    run = BASE / cohort
    checkpoint = SOURCE if cohort == 'source' else MATURE
    return ['-u', 'scripts/alpha_holdem/train_v5.py', '--device', 'cuda', '--workers', '12',
        '--hands-per-iter', '4096', '--total-hands', '99999999', '--total-environment-hands', '16384',
        '--starting-stack', '200', '--env-version', 'v55preflopv2v4obs', '--norm-layer', 'gn',
        '--lr', '0.00003', '--ppo-epochs', '2', '--ppo-target-kl', '0.01', '--policy-advantage-clip', '3',
        '--source-policy-kl-coef', '1', '--source-policy-reference-checkpoint', str(SOURCE),
        '--gradient-noise-hand-groups', '16', '--separate-preflop-head', '--all-policy-heads-only-training',
        '--mini-batch-size', '1024', '--entropy-coef', '0.005', '--entropy-floor', '0.05',
        '--pool-strategy', 'latest', '--fixed-opponent-checkpoints', *map(str, ANCHORS),
        '--hero-policy-mode', 'sample', '--self-play-fraction', '0.25', '--opponent-assignment', 'per-group',
        '--opponent-groups', '8', '--adaptive-opponent-league', '--adaptive-league-ema', '0.9',
        '--adaptive-league-temperature-bb', '2', '--adaptive-league-min-probability', '0.05',
        '--opponent-assignment-provenance-file', str(run / 'opponent_assignments.jsonl'),
        '--rollout-mode', 'single', '--worker-seed-base', str(seed*100), '--fixed-training-deal-stream',
        '--critic-contract', 'critic_v2', '--h1-effective-stack-divisor', '200',
        '--h1-critic-init-seed', '2026071102', '--value-coef', '1', '--autonomous-critic-v2-continue',
        '--snapshot-every', '999999', '--save-interval', '1', '--archive-checkpoint-every', '1',
        '--run-id', f'hand_gradient_{cohort}_20260830', '--run-dir', str(run), '--out', str(run / 'latest.pt'),
        '--seed', str(seed), '--max-runtime-seconds', '1800', '--resume', str(checkpoint),
        '--allow-resume', '--reset-hand-counter',
        '--reset-optimizer' if cohort == 'source' else '--no-reset-optimizer']


def main():
    if sys.argv[1:]:
        raise ValueError('No implicit resume supported; inspect any terminal interruption before recovery')
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        if p.pid == psutil.Process().pid or not (p.info['name'] or '').lower().startswith('python'):
            continue
        if any(name in ' '.join(p.info['cmdline'] or []) for name in
               ['train_v5.py', 'v5_mirror_eval.py', 'play_slumbot.py']):
            raise RuntimeError('Existing training/evaluation process must finish first')
    for path, digest in [*zip(ANCHORS, DIGESTS), (MATURE, MATURE_SHA)]:
        if sha(path) != digest:
            raise ValueError('Frozen input checkpoint mismatch')
    for cohort in ['source', 'mature']:
        if (BASE / cohort).exists():
            raise RuntimeError('Refusing to repeat or overwrite an existing cohort')
    snapshot = BASE / 'execution_code'
    snapshot.mkdir(exist_ok=False)
    code = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'scripts/alpha_holdem').glob('*.py'))]
    code += [f'scripts/deep_cfr/{name}.py' for name in ['__init__', 'game_state', 'hand_eval']]
    code += ['research/experiment_log.py', Path(__file__).relative_to(ROOT).as_posix(),
             (BASE / 'analyze.py').relative_to(ROOT).as_posix()]
    capture_code_provenance(ROOT, snapshot, code)
    copied = []
    for relative in code:
        dst = snapshot / 'source_files' / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, dst)
        copied.append(dict(original=relative, copy=dst.relative_to(ROOT).as_posix(), sha256=sha(dst)))
    (snapshot / 'copy_manifest.json').write_text(json.dumps(copied, indent=2)+'\n')
    command_record([Path(__file__).relative_to(ROOT)])
    log(*[item for name in ['copy_manifest.json', 'source_manifest.json', 'code.patch']
          for item in ['--artifact', str(snapshot / name)]],
        '--note', 'Full Python source snapshot made before either cohort. Live source hashes checked before and after each cohort. Original model files and prior experiments remain immutable.')
    total = 0
    for cohort, seed in [('source', 20260895), ('mature', 20260896)]:
        for entry in copied:
            if sha(ROOT / entry['original']) != entry['sha256']:
                raise ValueError('Source changed after execution snapshot')
        run = BASE / cohort
        command = make_command(cohort, seed)
        command_record(command)
        stdout = BASE / f'{cohort}_process_stdout.log'
        with stdout.open('x', encoding='utf-8') as output:
            process = subprocess.Popen([sys.executable, *command], cwd=ROOT,
                stdout=output, stderr=subprocess.STDOUT)
            log('--metric', f'{cohort}_pid={process.pid}', '--artifact', str(stdout))
            seen = -1
            while process.poll() is None:
                path = run / 'run_manifest.json'
                if path.exists():
                    document = json.loads(path.read_text())
                    iteration = int(document.get('iteration', 0))
                    physical = document.get('environment_hand_accounting', {}).get('completed_hands', 0)
                    if iteration != seen and physical > 0:
                        log('--count', f'new_training_hands={total+physical}',
                            '--metric', f'{cohort}_latest_iteration={iteration}',
                            '--metric', f'{cohort}_physical_hands={physical}')
                        seen = iteration
                time.sleep(5)
            exit_code = process.wait()
        log('--metric', f'{cohort}_exit_code={exit_code}', '--artifact', str(stdout))
        if exit_code:
            raise RuntimeError('Cohort stopped; evidence preserved, no automatic restart')
        manifest = json.loads((run / 'run_manifest.json').read_text())
        accounting = manifest['environment_hand_accounting']
        if not accounting['prefix_complete'] or accounting['completed_hands'] < 16384:
            raise ValueError('Physical endpoint incomplete')
        total += accounting['completed_hands']
        audit_cmd = ['scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py', '--run-dir', str(run),
                     '--expected-target-hands', '99999999', '--expected-target-environment-hands', '16384',
                     '--expected-final-iteration', str(manifest['iteration']), '--expected-pool-size', '3',
                     '--expected-archive-every', '1', '--expected-normalization', 'global',
                     '--out', str(BASE / f'{cohort}_audit.json')]
        command_record(audit_cmd)
        subprocess.run([sys.executable, *audit_cmd], cwd=ROOT, check=True)
        for entry in copied:
            if sha(ROOT / entry['original']) != entry['sha256'] or sha(ROOT / entry['copy']) != entry['sha256']:
                raise ValueError('Source changed during cohort execution')
        for path, digest in [*zip(ANCHORS, DIGESTS), (MATURE, MATURE_SHA)]:
            if sha(path) != digest:
                raise ValueError('Frozen input changed')
        log('--count', f'new_training_hands={total}', '--metric', f'{cohort}_complete=1',
            '--metric', f'{cohort}_physical_hands={accounting["completed_hands"]}',
            '--artifact', str(BASE / f'{cohort}_audit.json'),
            *[item for name in ['latest.pt', 'run_manifest.json', 'h1_training_metrics.jsonl',
                               'opponent_assignments.jsonl', 'latest_train.log']
              for item in ['--artifact', str(run / name)]])
    analyze = [str(BASE / 'analyze.py')]
    command_record(analyze)
    subprocess.run([sys.executable, *analyze], cwd=ROOT, check=True)
    log('--artifact', str(BASE / 'gradient_noise_analysis.json'), '--artifact', str(BASE / 'result_summary.md'),
        '--metric', 'diagnostic_complete=1',
        '--note', 'Both physical-budget diagnostic cohorts and full session audits completed. Analyze mechanism evidence and finish same record before any batch-size training treatment. No strength evaluation performed.')


if __name__ == '__main__':
    main()
