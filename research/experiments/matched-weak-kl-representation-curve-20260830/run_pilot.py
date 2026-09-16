"""Matched representation scope; fixed physical-budget curve and sampled evaluation."""
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
    Path('C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt'),
    ROOT / 'research/experiments/weak-source-kl-pilot-20260830/frozen/weak.pt']
DIGESTS = ['91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428',
           '457d3babb82cb8014a2b7c378b2b5f916962565e63a44d192d5d7acd8393d6e7',
           '902a7049ca66c0552246d11fe482eed4df47ac5c675ddf051c34ed86dcf213a6',
           'a68ac47aad7fa943f0e784e1c14be3d742fac7390a2cd853ba6cb971b429019b']


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
    if arm not in ('heads', 'full'):
        raise ValueError('Unknown fixed arm')
    batch, lr = '1024', '0.00003'
    coefficient = '0.01'
    run = BASE / arm
    command = ['-u', 'scripts/alpha_holdem/train_v5.py', '--device', 'cuda', '--workers', '12',
        '--hands-per-iter', '4096', '--total-hands', '99999999', '--total-environment-hands', '524288',
        '--starting-stack', '200', '--env-version', 'v55preflopv2v4obs', '--norm-layer', 'gn',
        '--lr', lr, '--ppo-epochs', '2', '--ppo-target-kl', '0.01', '--policy-advantage-clip', '3',
        '--source-policy-kl-coef', coefficient, '--source-policy-reference-checkpoint', str(SOURCE),
        '--separate-preflop-head', '--mini-batch-size', batch,
        '--entropy-coef', '0.005', '--entropy-floor', '0.05', '--pool-strategy', 'latest',
        '--fixed-opponent-checkpoints', *map(str, ANCHORS[:3]), '--hero-policy-mode', 'sample',
        '--self-play-fraction', '0.25', '--opponent-assignment', 'per-group', '--opponent-groups', '8',
        '--adaptive-opponent-league', '--adaptive-league-ema', '0.9', '--adaptive-league-temperature-bb', '2',
        '--adaptive-league-min-probability', '0.05', '--opponent-assignment-provenance-file',
        str(run / 'opponent_assignments.jsonl'), '--rollout-mode', 'single', '--worker-seed-base', '2026091100',
        '--fixed-training-deal-stream', '--critic-contract', 'critic_v2', '--h1-effective-stack-divisor', '200',
        '--h1-critic-init-seed', '2026071102', '--value-coef', '1', '--autonomous-critic-v2-continue',
        '--snapshot-every', '999999', '--save-interval', '1', '--archive-checkpoint-every', '4',
        '--run-id', f'representation_{arm}_20260830', '--run-dir', str(run), '--out', str(run / 'latest.pt'),
        '--seed', '20260911', '--max-runtime-seconds', '10800', '--resume', str(SOURCE),
        '--allow-resume', '--reset-hand-counter', '--reset-optimizer']
    if arm == 'heads':
        command.append('--all-policy-heads-only-training')
    return command


def verify_sources(copied):
    for item in copied:
        if sha(ROOT / item['original']) != item['sha256'] or sha(ROOT / item['copy']) != item['sha256']:
            raise ValueError('Execution source changed; inspect rather than continue silently')
    for path, digest in zip(ANCHORS, DIGESTS):
        if sha(path) != digest:
            raise ValueError('Frozen anchor changed')


def make_audit_command(run, manifest, output):
    return ['scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py', '--run-dir', str(run),
            '--expected-target-hands', '99999999', '--expected-target-environment-hands', '524288',
            '--expected-final-iteration', str(manifest['iteration']), '--expected-pool-size', '3',
            '--expected-archive-every', '4', '--expected-normalization', 'global', '--out', str(output)]


def choose_midpoint_row(rows, archive_iterations, threshold=262144):
    if [r['iteration'] for r in rows] != list(range(1, len(rows)+1)):
        raise ValueError('Incomplete or nonmonotonic update evidence')
    counts = [r['environment_hand_accounting']['completed_hands'] for r in rows]
    if any(b <= a for a, b in zip(counts, counts[1:])):
        raise ValueError('Nonmonotonic physical evidence')
    scheduled = [r for r in rows if r['iteration'] % 4 == 0]
    if {r['iteration'] for r in scheduled} != set(archive_iterations):
        raise ValueError('Missing or unexpected scheduled archives')
    eligible = [r for r in scheduled if r['environment_hand_accounting']['completed_hands'] >= threshold]
    if not eligible:
        raise ValueError('No scheduled archive crosses the registered midpoint')
    return eligible[0]


def select_midpoint(run):
    import re
    import torch
    rows = [json.loads(line) for line in (run/'h1_training_metrics.jsonl').read_text().splitlines() if line.strip()]
    archives = {}
    for path in (run/'checkpoints').glob('checkpoint_iter*_hands*.pt'):
        match = re.fullmatch(r'checkpoint_iter(\d+)_hands(\d+)\.pt', path.name)
        if not match or int(match[1]) in archives:
            raise ValueError('Ambiguous archival evidence')
        archives[int(match[1])] = path
    row = choose_midpoint_row(rows, archives)
    path = archives[row['iteration']]
    payload = torch.load(path, map_location='cpu', weights_only=False)
    if (payload['iteration'] != row['iteration']
            or payload['environment_hand_accounting']['completed_hands'] != row['environment_hand_accounting']['completed_hands']
            or not payload['environment_hand_accounting']['prefix_complete']):
        raise ValueError('Archive physical counters differ from metrics')
    return path


def main():
    if sys.argv[1:]:
        raise ValueError('No automatic restart/resume; inspect preserved state after terminal interruptions')
    profile = json.loads((BASE / 'memory_profile.json').read_text())
    if profile['status'] != 'PASS' or profile['source_sha256'] != DIGESTS[0]:
        raise ValueError('Exact-source memory profile PASS is required')
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        if p.pid != psutil.Process().pid and (p.info['name'] or '').lower().startswith('python') and any(
            name in ' '.join(p.info['cmdline'] or []) for name in ['train_v5.py', 'v5_mirror_eval.py', 'play_slumbot.py']
        ):
            raise RuntimeError('Another training/evaluation process is live')
    if any((BASE / name).exists() for name in ['heads', 'full', 'frozen', 'execution_code']):
        raise RuntimeError('Refusing existing production or snapshot output')
    snapshot = BASE / 'execution_code'
    snapshot.mkdir()
    code = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'scripts/alpha_holdem').glob('*.py'))]
    code += [f'scripts/deep_cfr/{name}.py' for name in ['__init__', 'game_state', 'hand_eval']]
    code += ['research/experiment_log.py']
    code += [p.relative_to(ROOT).as_posix() for p in sorted(BASE.glob('*.py'))]
    code.append((BASE / 'preregistration.md').relative_to(ROOT).as_posix())
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
        '--note', 'Full execution snapshot frozen before both arms. Same source/deal seeds/collection/physical budgets; only parameter scope and output identity differ. No live source edits allowed during this wrapper.')
    total, selected = 0, {'source': dict(path=str(SOURCE), sha256=DIGESTS[0], physical_hands=0)}
    (BASE / 'frozen').mkdir()
    for arm in ['heads', 'full']:
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
        if count < 524288 or not manifest['environment_hand_accounting']['prefix_complete']:
            raise ValueError('Physical endpoint incomplete')
        total += count
        audit_path = BASE / f'{arm}_audit.json'
        audit = make_audit_command(run, manifest, audit_path)
        command_record(audit)
        subprocess.run([sys.executable, *audit], cwd=ROOT, check=True)
        verify_sources(copied)
        frozen = BASE / 'frozen' / f'{arm}.pt'
        shutil.copy2(run / 'latest.pt', frozen)
        if sha(frozen) != sha(run / 'latest.pt'):
            raise ValueError('Final freeze copy mismatch')
        selected[f'{arm}_final'] = dict(path=str(frozen), sha256=sha(frozen), physical_hands=count,
                             iteration=manifest['iteration'])
        mid = select_midpoint(run)
        import torch
        mid_payload = torch.load(mid, map_location='cpu', weights_only=False)
        mid_frozen = BASE / 'frozen' / f'{arm}_mid.pt'
        shutil.copy2(mid, mid_frozen)
        if sha(mid_frozen) != sha(mid):
            raise ValueError('Midpoint frozen copy mismatch')
        selected[f'{arm}_mid'] = dict(path=str(mid_frozen), sha256=sha(mid_frozen),
            physical_hands=mid_payload['environment_hand_accounting']['completed_hands'],
            iteration=mid_payload['iteration'], original_archive=str(mid))
        del mid_payload
        log('--artifact', str(mid_frozen))
        log('--count', f'new_training_hands={total}', '--metric', f'{arm}_complete=1',
            '--metric', f'{arm}_physical_hands={count}', '--artifact', str(frozen), '--artifact', str(audit_path),
            *[item for name in ['latest.pt', 'run_manifest.json', 'h1_training_metrics.jsonl',
                               'opponent_assignments.jsonl', 'latest_train.log']
              for item in ['--artifact', str(run / name)]])
    selection = BASE / 'checkpoint_selection.json'
    selection.write_text(json.dumps(selected, indent=2)+'\n')
    log('--artifact', str(selection), '--metric', 'training_complete=1',
        '--note', 'Both preregistered final and first262144-crossing archive endpoints frozen by counters only; original source hash unchanged. Starting fixed independent sampled evaluation.')
    command = [str(BASE / 'evaluate.py')]
    command_record(command)
    subprocess.run([sys.executable, *command], cwd=ROOT, check=True)
    verify_sources(copied)


if __name__ == '__main__':
    main()
