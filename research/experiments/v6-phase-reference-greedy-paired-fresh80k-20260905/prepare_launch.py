"""Exclusive offline preparation for the preregistered fixed80k comparison."""
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
import platform
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PREP = ROOT / 'research/experiments/v6-phase-held-reference-control-20260904/recovery_20260905/external_preparation'
sys.path.insert(0, str(PREP))
import run_pair as runner


def main():
    runner.protocol.require(runner.read(BASE / 'experiment.json')['status'] == 'RUNNING', 'register first')
    runner.training_ready()
    for name in ('launch_spec.json', 'environment.json', 'preparation_report.json', 'execution.json'):
        runner.protocol.require(not (BASE / name).exists(), 'preparation already attempted; preserve: ' + name)
    for path, digest in runner.EXPECTED_MODELS.values():
        runner.protocol.require(runner.sha(path) == digest, 'endpoint changed')
    runner.protocol.require(runner.sha(runner.REPORT) ==
        '461a74b29504eb70d7156f61f2f3b693d4c6a6cb609ccc213a3bd28ade0a65c9', 'training report changed')
    runner.protocol.require(runner.sha(runner.RUNTIME_SOURCE / 'alpha_holdem/play_slumbot_v6_journaled.py') ==
        'cea29a9217784b27168665dc01c981433832bb0d7352aefdfe7041f7c896429d', 'client changed')
    prior, unreadable = runner.prior_initial_sessions(ROOT / 'research/experiments', BASE)
    runner.check_unused_session_identifiers(prior)
    runner.check_prior_prefixes(prior)
    sources = [PREP / name for name in ('run_pair.py', 'pair_protocol.py', 'test_run_pair.py', 'test_pair_protocol.py')]
    sources += [Path(__file__), BASE / 'launch.ps1', ROOT / 'research/experiment_log.py']
    spec = {'schema': 'cardpilot.phase_reference.external_pair.v1', 'development_only': True,
        'schedule': runner.protocol.schedule(),
        'models': {arm: {'path': str(path), 'sha256': digest} for arm, (path, digest) in runner.EXPECTED_MODELS.items()},
        'runtime_source': str(runner.RUNTIME_SOURCE),
        'runtime_sha256': {str(path): runner.sha(path) for path in runner.RUNTIME_SOURCE.rglob('*.py') if '__pycache__' not in path.parts},
        'training_report_sha256': runner.sha(runner.REPORT),
        'preregistration_sha256': runner.sha(BASE / 'preregistration.md'),
        'code_sha256': {str(path): runner.sha(path) for path in sources}}
    versions = {name: metadata.version(name) for name in ('torch', 'numpy', 'scipy', 'requests', 'psutil', 'pytest')}
    runner.write_new(BASE / 'environment.json', {'recorded_at': datetime.now(timezone.utc).isoformat(),
        'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(), 'packages': versions,
        'purpose': 'CPU frozen-policy external development; no training or network in this preparation'})
    # Include environment metadata in continuously checked input bindings.
    spec['code_sha256'][str(BASE / 'environment.json')] = runner.sha(BASE / 'environment.json')
    runner.write_new(BASE / 'launch_spec.json', spec)
    runner.preflight(BASE)
    runner.write_new(BASE / 'preparation_report.json', {'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'network_requests': 0, 'new_hands': 0,
        'runtime_python_files': len(spec['runtime_sha256']), 'planned_sessions': len(spec['schedule']),
        'planned_hands': sum(row['hands'] for row in spec['schedule']),
        'prior_initial_sessions_checked': len(prior), 'unreadable_prior_initial_records': unreadable,
        'planned_session_ids_and_seeds_unused': True, 'launch_spec_sha256': runner.sha(BASE / 'launch_spec.json'),
        'frozen_runtime_tests_will_rerun_before_first_request': True})
    argv = [sys.executable, str(ROOT / 'research/experiment_log.py'), 'update', BASE.name,
        '--metric', 'offline_preflight_passed=true', '--metric', 'preparation_added_hands=0']
    for name in ('environment.json', 'launch_spec.json', 'preparation_report.json'):
        argv += ['--artifact', str(BASE / name)]
    subprocess.run(argv, cwd=ROOT, check=True)
    print('Offline preparation PASS; 32 registered sessions, 80000 planned hands, zero network requests.', flush=True)


if __name__ == '__main__':
    main()
