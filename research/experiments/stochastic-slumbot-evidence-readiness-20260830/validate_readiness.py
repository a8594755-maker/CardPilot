"""Freeze readiness code, run offline contracts, and close a zero-game experiment."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import psutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance
from scripts.alpha_holdem.audit_slumbot_hand_evidence import sha


def log(*args):
    subprocess.run([sys.executable, 'research/experiment_log.py', 'update', BASE.name, *map(str, args)],
                   cwd=ROOT, check=True)


def command(args):
    log('--command', subprocess.list2cmdline(['python', *map(str, args)]))
    return [sys.executable, *map(str, args)]


def main():
    for process in psutil.process_iter(['pid', 'name', 'cmdline']):
        if (process.info['name'] or '').lower().startswith('python') and any(
                Path(arg).name in ['play_slumbot.py', 'train_v5.py', 'v5_mirror_eval.py']
                for arg in process.info['cmdline'] or []):
            raise RuntimeError('Validation must not overlap live poker work')
    snapshot = BASE / 'final_code'
    if snapshot.exists() or (BASE / 'synthetic').exists() or (BASE / 'readiness_analysis.json').exists():
        raise RuntimeError('Do not overwrite existing validation evidence')
    snapshot.mkdir()
    paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += [f'scripts/deep_cfr/{name}.py' for name in ['__init__', 'game_state', 'hand_eval']]
    paths += ['research/experiment_log.py', Path(__file__).relative_to(ROOT).as_posix()]
    _, artifacts = capture_code_provenance(ROOT, snapshot, paths)
    copies = []
    for relative in paths:
        target = snapshot / 'source_files' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
        copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha(target)))
    (snapshot/'copy_manifest.json').write_text(json.dumps(copies, indent=2)+'\n')
    log('--command', f'python {Path(__file__).relative_to(ROOT).as_posix()}',
        '--note', 'Final implementation source/patch snapshot is final_code; start-state provenance remains untouched. Validation below is synthetic/offline only,not Slumbot evidence.',
        *[item for path in [*artifacts, snapshot/'copy_manifest.json', __file__] for item in ['--artifact', str(path)]])
    tests = ['-m', 'pytest', 'scripts/alpha_holdem/test_stochastic_slumbot_evidence.py',
        'scripts/alpha_holdem/test_slumbot_ci_from_hands.py', 'scripts/alpha_holdem/test_slumbot_execution_telemetry.py',
        'scripts/alpha_holdem/test_sampled_mirror_eval.py', 'research/test_experiment_log.py', '-q',
        f'--junitxml={BASE / "test_results.xml"}']
    completed = subprocess.run(command(tests), cwd=ROOT, capture_output=True, text=True)
    (BASE/'validation_stdout.log').write_text(completed.stdout+'\n'+completed.stderr)
    if completed.returncode:
        raise RuntimeError('Validation tests failed; preserve snapshot and inspect')
    passed = int(re.search(r'(\d+) passed', completed.stdout).group(1))
    from scripts.alpha_holdem.test_stochastic_slumbot_evidence import fixture
    synthetic = BASE/'synthetic'
    synthetic.mkdir()
    manifest, _ = fixture(synthetic)
    synthetic_audit = synthetic/'SYNTHETIC_ONLY_audit.json'
    args = ['scripts/alpha_holdem/audit_slumbot_hand_evidence.py', '--manifest', manifest, '--out-json', synthetic_audit]
    subprocess.run(command(args), cwd=ROOT, check=True)
    evidence = json.loads(synthetic_audit.read_text())
    if evidence['status'] != 'PASS' or evidence['summary']['hands'] != 200:
        raise ValueError('Synthetic end-to-end contract failed')
    dry = json.loads((BASE/'seeded_deployment_dry_run.json').read_text())
    source = ROOT/'models/baseline/standard10/latest.pt'
    digest = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
    if (sha(source) != digest or dry['model_sha256'] != digest or dry['successful_hands'] != 0
            or dry['requested_hands'] != 0 or not dry['dry_run'] or dry['policy_seed'] != 2026090400
            or dry['policy_mode_raw'] != 'sample' or dry['temperature'] != 1):
        raise ValueError('Frozen source or zero-game seeded deployment check failed')
    for row in copies:
        if sha(ROOT/row['original']) != row['sha256'] or sha(ROOT/row['copy']) != row['sha256']:
            raise ValueError('Source changed during readiness validation')
    result = dict(status='PASS', tests_passed=passed, synthetic_independence_test_records=100000,
        synthetic_end_to_end_records=200, actual_slumbot_hands=0, actual_training_hands=0,
        source_sha256=digest, live_network_games_run=False,
        limitations=['Observable replay diagnostics cannot prove hidden-deck statistical independence.',
            'Normal raw-hand CI assumes sufficiently independent hand outcomes; no strength claim arises from fixtures.',
            'The strict new-run contract rejects old files missing execution metadata without retroactively relabeling old experiments.',
            'Native-policy behavior/observation strength is not established by evidence-format tests or a zero-hand loader.'])
    (BASE/'readiness_analysis.json').write_text(json.dumps(result, indent=2)+'\n')
    report = ['# Stochastic Slumbot evidence readiness', '', f'Validation: PASS; {passed} tests passed.', '',
        'Added action-independent aligned/shifted deal replay checks, duplicate-input rejection, strict raw/session/model/seed/reward/CI reconciliation, and client fallback telemetry. '
        'An optional explicit post-load RNG seed and per-row policy identity preserve reproducibility without changing native action probabilities.', '',
        'Tests include100000 synthetic independent initial deals and deliberately duplicated streams with different sampled actions/winnings. '
        'The saved end-to-end fixture contains200 SYNTHETIC records and a dummy fixture checkpoint; none are actual poker evaluation hands. '
        'The real unchanged Standard10 sample/temp1 seed2026090400 zero-hand loader passed.', '',
        '**Actual new training/evaluation/Slumbot hands:0.** All final source hashes matched the frozen final_code snapshot.', '',
        'Limitations:', '', *['- '+text for text in result['limitations']], '',
        'Next: separately preregister a fixed20000 fresh native-sampled Standard10 external baseline with immutable output directories, '
        'distinct explicit session seeds, staggered first-hand readiness, exact counters and strict terminal evidence audit. '
        'A later qualifying100k remains independent and is not satisfied by this readiness work.']
    (BASE/'result_summary.md').write_text('\n'.join(report)+'\n')
    log('--metric', f'tests_passed={passed}', '--metric', 'synthetic_independence_records=100000',
        '--metric', 'actual_slumbot_hands=0', '--metric', 'final_source_hash_checks_pass=1',
        '--command', 'python scripts/alpha_holdem/play_slumbot.py --hands 0 --strategy model --model models/baseline/standard10/latest.pt --device cpu --policy-mode sample --temperature 1 --policy-seed 2026090400 --result-json research/experiments/stochastic-slumbot-evidence-readiness-20260830/seeded_deployment_dry_run.json',
        *[item for path in [BASE/name for name in ['test_results.xml', 'validation_stdout.log',
            'seeded_deployment_dry_run.json', 'readiness_analysis.json', 'result_summary.md']]+list(synthetic.iterdir())
          for item in ['--artifact', str(path)]])
    subprocess.run([sys.executable, 'research/experiment_log.py', 'finish', BASE.name,
        '--status', 'COMPLETED', '--count', 'new_training_hands=0', '--count', 'evaluation_hands=0',
        '--summary', f'Stochastic evidence-readiness validation passed{passed} tests,100k-sized synthetic independent streams and a200-record synthetic end-to-end manifest. Real seeded Standard10 loader passed atzero hands; no external games.',
        '--conclusion', 'Repeated deals with different actions and shifted repeats are rejected. Strict accounting rejects duplicate/missing/corrupt/reward-inconsistent/fallback/wrong-policy evidence. Final source/patch snapshot and unchanged source hash verified. These checks establish evidence readiness,not poker strength or full statistical independence.',
        '--decision', 'READY_FOR_SEPARATELY_PREREGISTERED_NATIVE_SAMPLED_BASELINE',
        '--next-step', 'Preregister fixed20k fresh Slumbot hands for unchanged Standard10 sample/temp1,with immutable evidence and explicit session seeds. Finish/assess all evidence before any subsequent independent100k formal test or learned-weight direction.'], cwd=ROOT, check=True)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
