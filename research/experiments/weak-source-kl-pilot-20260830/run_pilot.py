"""Matched physical-budget source-KL coefficients; fixed final sampled evaluation."""
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
ANCHORS = [SOURCE,
    Path('C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt'),
    Path('C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt')]
DIGESTS = ['91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428',
           '457d3babb82cb8014a2b7c378b2b5f916962565e63a44d192d5d7acd8393d6e7',
           '902a7049ca66c0552246d11fe482eed4df47ac5c675ddf051c34ed86dcf213a6']


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def log(*args):
    subprocess.run([sys.executable, 'research/experiment_log.py', 'update', ID, *map(str, args)],
                   cwd=ROOT, check=True)


def command_record(args):
    log('--command', subprocess.list2cmdline(['python', *map(str, args)]))


def make_command(arm):
    if arm not in ('control', 'weak'):
        raise ValueError('Unknown fixed arm')
    batch, lr = '1024', '0.00003'
    coefficient = '1' if arm == 'control' else '0.01'
    run = BASE / arm
    return ['-u', 'scripts/alpha_holdem/train_v5.py', '--device', 'cuda', '--workers', '12',
        '--hands-per-iter', '4096', '--total-hands', '99999999', '--total-environment-hands', '262144',
        '--starting-stack', '200', '--env-version', 'v55preflopv2v4obs', '--norm-layer', 'gn',
        '--lr', lr, '--ppo-epochs', '2', '--ppo-target-kl', '0.01', '--policy-advantage-clip', '3',
        '--source-policy-kl-coef', coefficient, '--source-policy-reference-checkpoint', str(SOURCE),
        '--separate-preflop-head', '--all-policy-heads-only-training', '--mini-batch-size', batch,
        '--entropy-coef', '0.005', '--entropy-floor', '0.05', '--pool-strategy', 'latest',
        '--fixed-opponent-checkpoints', *map(str, ANCHORS), '--hero-policy-mode', 'sample',
        '--self-play-fraction', '0.25', '--opponent-assignment', 'per-group', '--opponent-groups', '8',
        '--adaptive-opponent-league', '--adaptive-league-ema', '0.9', '--adaptive-league-temperature-bb', '2',
        '--adaptive-league-min-probability', '0.05', '--opponent-assignment-provenance-file',
        str(run / 'opponent_assignments.jsonl'), '--rollout-mode', 'single', '--worker-seed-base', '2026090700',
        '--fixed-training-deal-stream', '--critic-contract', 'critic_v2', '--h1-effective-stack-divisor', '200',
        '--h1-critic-init-seed', '2026071102', '--value-coef', '1', '--autonomous-critic-v2-continue',
        '--snapshot-every', '999999', '--save-interval', '1', '--archive-checkpoint-every', '4',
        '--run-id', f'weak_kl_{arm}_20260830', '--run-dir', str(run), '--out', str(run / 'latest.pt'),
        '--seed', '20260907', '--max-runtime-seconds', '7200', '--resume', str(SOURCE),
        '--allow-resume', '--reset-hand-counter', '--reset-optimizer']


def verify_sources(copied):
    for item in copied:
        if sha(ROOT / item['original']) != item['sha256'] or sha(ROOT / item['copy']) != item['sha256']:
            raise ValueError('Execution source changed; inspect rather than continue silently')
    for path, digest in zip(ANCHORS, DIGESTS):
        if sha(path) != digest:
            raise ValueError('Frozen anchor changed')


def main():
    if sys.argv[1:]:
        raise ValueError('No automatic restart/resume; inspect preserved state after terminal interruptions')
    profile = json.loads((ROOT / 'research/experiments/large-batch-optimizer-regimen-pilot-20260830/memory_profile.json').read_text())
    if profile['status'] != 'PASS' or profile['source_sha256'] != DIGESTS[0]:
        raise ValueError('Exact-source memory profile PASS is required')
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        if p.pid != psutil.Process().pid and (p.info['name'] or '').lower().startswith('python') and any(
            name in ' '.join(p.info['cmdline'] or []) for name in ['train_v5.py', 'v5_mirror_eval.py', 'play_slumbot.py']
        ):
            raise RuntimeError('Another training/evaluation process is live')
    if any((BASE / name).exists() for name in ['control', 'weak', 'frozen', 'execution_code']):
        raise RuntimeError('Refusing existing production or snapshot output')
    snapshot = BASE / 'execution_code'
    snapshot.mkdir()
    code = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'scripts/alpha_holdem').glob('*.py'))]
    code += [f'scripts/deep_cfr/{name}.py' for name in ['__init__', 'game_state', 'hand_eval']]
    code += ['research/experiment_log.py', Path(__file__).relative_to(ROOT).as_posix(),
             (BASE / 'evaluate.py').relative_to(ROOT).as_posix(), (BASE / 'test_pilot.py').relative_to(ROOT).as_posix()]
    capture_code_provenance(ROOT, snapshot, code)
    copied = []
    for relative in code:
        dst = snapshot / 'source_files' / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, dst)
        copied.append(dict(original=relative, copy=dst.relative_to(ROOT).as_posix(), sha256=sha(dst)))
    (snapshot / 'copy_manifest.json').write_text(json.dumps(copied, indent=2)+'\n')
    verify_sources(copied)
    command_record([Path(__file__).relative_to(ROOT)])
    log(*[item for name in ['copy_manifest.json', 'source_manifest.json', 'code.patch']
          for item in ['--artifact', str(snapshot / name)]],
        '--note', 'Full execution snapshot frozen before both arms. Same source/deal seeds/collection/physical budgets; only source-KL coefficient and output identity differ. No live source edits allowed during this wrapper.')
    total, selected = 0, {'source': dict(path=str(SOURCE), sha256=DIGESTS[0], physical_hands=0)}
    (BASE / 'frozen').mkdir()
    for arm in ['control', 'weak']:
        verify_sources(copied)
        run = BASE / arm
        command = make_command(arm)
        command_record(command)
        stdout = BASE / f'{arm}_process_stdout.log'
        with stdout.open('x', encoding='utf-8') as output:
            process = subprocess.Popen([sys.executable, *command], cwd=ROOT,
                                       stdout=output, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            log('--metric', f'{arm}_pid={process.pid}', '--artifact', str(stdout))
            seen = -1
            while process.poll() is None:
                path = run / 'run_manifest.json'
                if path.exists():
                    doc = json.loads(path.read_text())
                    iteration = int(doc.get('iteration', 0))
                    physical = doc.get('environment_hand_accounting', {}).get('completed_hands', 0)
                    if iteration != seen and physical > 0:
                        log('--count', f'new_training_hands={total+physical}',
                            '--metric', f'{arm}_latest_iteration={iteration}',
                            '--metric', f'{arm}_physical_hands={physical}')
                        seen = iteration
                time.sleep(5)
            code = process.wait()
        log('--metric', f'{arm}_exit_code={code}', '--artifact', str(stdout))
        if code:
            raise RuntimeError('Production stopped; preserve evidence and do not auto-restart')
        manifest = json.loads((run / 'run_manifest.json').read_text())
        count = manifest['environment_hand_accounting']['completed_hands']
        if count < 262144 or not manifest['environment_hand_accounting']['prefix_complete']:
            raise ValueError('Physical endpoint incomplete')
        total += count
        audit_path = BASE / f'{arm}_audit.json'
        audit = ['scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py', '--run-dir', str(run),
                 '--expected-target-hands', '99999999', '--expected-target-environment-hands', '262144',
                 '--expected-final-iteration', str(manifest['iteration']), '--expected-pool-size', '3',
                 '--expected-archive-every', '4', '--expected-normalization', 'global', '--out', str(audit_path)]
        command_record(audit)
        subprocess.run([sys.executable, *audit], cwd=ROOT, check=True)
        verify_sources(copied)
        frozen = BASE / 'frozen' / f'{arm}.pt'
        shutil.copy2(run / 'latest.pt', frozen)
        if sha(frozen) != sha(run / 'latest.pt'):
            raise ValueError('Final freeze copy mismatch')
        selected[arm] = dict(path=str(frozen), sha256=sha(frozen), physical_hands=count,
                             iteration=manifest['iteration'])
        log('--count', f'new_training_hands={total}', '--metric', f'{arm}_complete=1',
            '--metric', f'{arm}_physical_hands={count}', '--artifact', str(frozen), '--artifact', str(audit_path),
            *[item for name in ['latest.pt', 'run_manifest.json', 'h1_training_metrics.jsonl',
                               'opponent_assignments.jsonl', 'latest_train.log']
              for item in ['--artifact', str(run / name)]])
    selection = BASE / 'checkpoint_selection.json'
    selection.write_text(json.dumps(selected, indent=2)+'\n')
    log('--artifact', str(selection), '--metric', 'training_complete=1',
        '--note', 'Both preregistered final physical endpoints frozen by budget only; original source hash unchanged. Starting fixed independent sampled evaluation.')
    command = [str(BASE / 'evaluate.py')]
    command_record(command)
    subprocess.run([sys.executable, *command], cwd=ROOT, check=True)
    verify_sources(copied)


if __name__ == '__main__':
    main()
