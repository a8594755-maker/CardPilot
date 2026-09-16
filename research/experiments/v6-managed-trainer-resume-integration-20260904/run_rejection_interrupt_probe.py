"""Bounded negative and partial-update tests from the completed diagnostic parent."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    import torch
    torch.set_num_threads(1)
    source = BASE / 'cpu_probe_r3/attempt3'
    parent_path = source / 'latest.pt'
    parent = torch.load(parent_path, map_location='cpu', weights_only=False)
    parent_sha = sha(parent_path)
    production_sha = sha(ROOT / 'scripts/alpha_holdem/train_v5.py')
    out = BASE / 'negative_probe'
    out.mkdir()
    reports = []
    for case in ('namespace_reuse', 'legacy_mode', 'optimizer_interrupt'):
        run = out / case
        run.mkdir()
        argv = json.loads((source / 'command.json').read_text())
        def replace(flag, value):
            argv[argv.index(flag) + 1] = str(value)
        replace('--resume', parent_path)
        replace('--run-dir', run)
        replace('--out', run / 'latest.pt')
        replace('--opponent-assignment-provenance-file', run / 'opponent_assignments.jsonl')
        replace('--total-environment-hands', parent['environment_hand_accounting']['completed_hands'] + 128)
        for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
            shutil.copy2(source / name, run / name)
        if case == 'namespace_reuse':
            argv += ['--deal-attempt-namespace', parent['fixed_deal_attempt']['receipt']['namespace']]
        elif case == 'legacy_mode':
            argv.remove('--managed-deal-attempts')
        else:
            argv[2] = str(BASE / 'inject_optimizer_interrupt.py')
        (run / 'command.json').write_text(json.dumps(argv, indent=2) + '\n')
        shutil.copy2(ROOT / 'scripts/alpha_holdem/train_v5_managed_candidate.py', run / 'trainer_source.py')
        initial_sha = None
        child = subprocess.Popen(argv, cwd=ROOT, env=dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        with (run / 'stdout.log').open('x', encoding='utf-8') as log:
            for line in child.stdout:
                log.write(line)
                log.flush()
                if '[Save] initial resume checkpoint' in line:
                    shutil.copy2(run / 'latest.pt', run / 'initial_resumed_state.pt')
                    initial_sha = sha(run / 'initial_resumed_state.pt')
                if 'DIAGNOSTIC:' in line or 'preserved the' in line:
                    print(line.strip(), flush=True)
        code = child.wait(timeout=10)
        stdout = (run / 'stdout.log').read_text()
        if case == 'optimizer_interrupt':
            assert code == 0 and 'DIAGNOSTIC: one actual optimizer step applied' in stdout
            manifest = json.loads((run / 'run_manifest.json').read_text())
            assert manifest['status'] == 'interrupted_during_ppo_update_checkpoint_preserved'
            assert initial_sha and sha(run / 'latest.pt') == initial_sha
            checkpoint = torch.load(run / 'latest.pt', map_location='cpu', weights_only=False)
            assert checkpoint['iteration'] == parent['iteration']
            assert checkpoint['total_hands'] == parent['total_hands']
            observed = manifest['environment_hand_accounting']['completed_hands']
            new_hands = observed - parent['environment_hand_accounting']['completed_hands']
            assert new_hands > 0
            reports.append({'case': case, 'passed': True, 'completed_checkpoint_unchanged': True,
                'actual_environment_hands': new_hands, 'retained_completed_updates': 0,
                'discarded_partial_optimizer_step': True, 'checkpoint_sha256': initial_sha})
        else:
            expected = 'FileExistsError' if case == 'namespace_reuse' else 'managed checkpoint cannot resume with legacy deal mode'
            assert code != 0 and expected in stdout and not (run / 'latest.pt').exists()
            reports.append({'case': case, 'passed': True, 'actual_environment_hands': 0})
        assert sha(parent_path) == parent_sha
        print(f'{case}: passed', flush=True)
    assert sha(ROOT / 'scripts/alpha_holdem/train_v5.py') == production_sha
    report = {'passed': True, 'cases': reports, 'production_unchanged': True,
              'candidate_sha256': sha(ROOT / 'scripts/alpha_holdem/train_v5_managed_candidate.py'),
              'diagnostic_actual_environment_hands': sum(row['actual_environment_hands'] for row in reports)}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
