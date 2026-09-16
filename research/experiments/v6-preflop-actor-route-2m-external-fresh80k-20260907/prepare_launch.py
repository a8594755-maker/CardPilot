"""Exclusive offline four-policy qualification plus endpoint inference parity; no requests."""
from datetime import datetime, timezone
from importlib import metadata
import ast
import difflib
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(BASE))
import run_pair as runner

OLD = ROOT / 'research/experiments/v6-preflop-actor-route-two-seed-external-fresh80k-20260906'


def structural_items(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    result = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            result[node.name] = ast.dump(node, include_attributes=False)
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, ast.FunctionDef):
                    result[node.name + '.' + child.name] = ast.dump(child, include_attributes=False)
    return result


def main():
    started = time.monotonic()
    runner.protocol.require(runner.read(BASE / 'experiment.json')['status'] == 'RUNNING', 'register first')
    for name in ('launch_spec.json', 'environment.json', 'preparation_report.json', 'execution.json',
                 'source_derivation.json', 'binding_qualification.json', 'preparation_tests.xml', 'endpoint_parity.json'):
        runner.protocol.require(not (BASE / name).exists(), 'preparation already attempted; preserve: ' + name)
    runner.training_ready()
    runner.protocol.require(runner.read(OLD / 'experiment.json')['status'] == 'COMPLETED', 'qualified external template incomplete')
    old_spec = runner.read(OLD / 'launch_spec.json')
    runner.protocol.require(runner.sha(OLD / 'launch_spec.json') ==
        '43d667dd1cf048a46b4f07d8a658cca3848337fad4a4dba126a3a7cb28e4cb10', 'template launch binding changed')
    runner.protocol.require(runner.sha(runner.RUNTIME_SOURCE / 'alpha_holdem/play_slumbot_v6_journaled.py') ==
        'cea29a9217784b27168665dc01c981433832bb0d7352aefdfe7041f7c896429d', 'qualified client changed')
    network_sha = '95fe31834a3c55bb0ad7a13da7188d74bfb9513da9c10396acad94a7c563b406'
    runner.protocol.require(runner.sha(runner.RUNTIME_SOURCE / 'alpha_holdem/network_hybrid_h1.py') ==
                            runner.sha(ROOT / 'scripts/alpha_holdem/network_hybrid_h1.py') == network_sha,
                            'frozen/current model architecture changed')
    prior, unreadable = runner.prior_initial_sessions(ROOT / 'research/experiments', BASE)
    runner.check_unused_session_identifiers(prior)
    runner.check_prior_prefixes(prior)
    templates = {name: OLD / name for name in ('run_pair.py', 'pair_protocol.py',
                 'test_run_pair.py', 'test_pair_protocol.py', 'prepare_launch.py', 'launch.ps1')}
    derivation = {}
    for name, old_path in templates.items():
        runner.protocol.require(old_spec['code_sha256'].get(str(old_path)) == runner.sha(old_path), 'template source no longer qualified')
        path = BASE / name
        derivation[name] = {'template_path': str(old_path), 'template_sha256': runner.sha(old_path),
            'derived_path': str(path), 'derived_sha256': runner.sha(path),
            'unified_diff': list(difflib.unified_diff(old_path.read_text(encoding='utf-8').splitlines(),
                path.read_text(encoding='utf-8').splitlines(), fromfile=str(old_path), tofile=str(path), lineterm=''))}
    unchanged = {
        'run_pair.py': ['read', 'sha', 'write_new', 'check_hashes', 'prior_initial_sessions',
            'check_prior_prefixes', 'check_unused_session_identifiers', 'live_identity',
            'RawCounter', 'parse_raw', 'Runner.__init__', 'Runner.verify_inputs', 'Runner.log',
            'Runner.record', 'Runner.launch', 'Runner.wait_jobs', 'Runner.audit_job', 'Runner.run', 'Runner.prepare', 'Runner.tick', 'verify_audits', 'seat_report'],
        'pair_protocol.py': ['require', 'session_command', 'values_ok', 'mean_t', 'welch', 'arm_summary', 'summarize_four'],
    }
    for name, names in unchanged.items():
        old_items, new_items = structural_items(templates[name]), structural_items(BASE / name)
        runner.protocol.require(all(old_items[key] == new_items.get(key) for key in names),
                                'claimed unchanged qualified core actually changed')
    runner.write_new(BASE / 'source_derivation.json', {'passed': True, 'templates': derivation,
        'ast_identical_items': unchanged,
        'material_changes': ['four fixed2M actor-route endpoints from completed terminal report',
            'detached/control and connected/treatment labels; fresh IDs/seeds; identical allocation/statistic math',
            'eight clean current jobs and56 descendants; inherited unknown tail remains explicit',
            'actual final-weight training-network versus frozen inference-network forward parity',
            'no optimizer updates, new training or new evaluation hands during preparation'],
        'scope': 'AST equality for declared unchanged helpers only; changed admission/coverage/statistics require new tests',
        'old_launch_spec_sha256': runner.sha(OLD / 'launch_spec.json')})
    names = ('run_pair.py', 'pair_protocol.py', 'test_run_pair.py', 'test_pair_protocol.py', 'prepare_launch.py', 'launch.ps1')
    sources = [BASE / name for name in names] + [BASE / 'endpoint_parity.py', ROOT / 'research/experiment_log.py']
    hashes = {str(path): runner.sha(path) for path in sources}
    argv = [sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
            str(BASE / 'test_run_pair.py'), str(BASE / 'test_pair_protocol.py'),
            f'--junitxml={BASE / "preparation_tests.xml"}']
    test_start = time.monotonic()
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    runner.write_new(BASE / 'binding_qualification.json', {'passed': result.returncode == 0,
        'created_at': datetime.now(timezone.utc).isoformat(), 'outer_argv': [sys.executable, *sys.orig_argv[1:]],
        'argv': argv, 'exact_command': subprocess.list2cmdline(argv), 'exit_code': result.returncode,
        'stdout': result.stdout, 'stderr': result.stderr, 'wall_seconds': time.monotonic() - test_start,
        'source_sha256': hashes, 'new_training_hands': 0, 'evaluation_hands': 0,
        'network_requests': 0, 'model_inference_calls': 0})
    runner.check_hashes(hashes)
    runner.protocol.require(result.returncode == 0, 'offline binding tests failed; preserve preparation')
    parity_argv = [sys.executable, '-B', str(BASE / 'endpoint_parity.py')]
    parity_run = subprocess.run(parity_argv, cwd=ROOT, capture_output=True, text=True)
    runner.protocol.require(parity_run.returncode == 0, parity_run.stdout + parity_run.stderr)
    runner.protocol.require(runner.read(BASE / 'endpoint_parity.json')['passed'], 'endpoint parity failed')
    versions = {name: metadata.version(name) for name in ('torch', 'numpy', 'scipy', 'requests', 'psutil', 'pytest')}
    runner.write_new(BASE / 'environment.json', {'recorded_at': datetime.now(timezone.utc).isoformat(),
        'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(), 'packages': versions,
        'launch_environment': {'PYTHONDONTWRITEBYTECODE': '1', 'OMP_NUM_THREADS': '1',
                               'MKL_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'},
        'purpose': 'CPU frozen-policy external development; retained-state forward parity only; no training or requests in preparation'})
    bound = [BASE / name for name in ('environment.json', 'source_derivation.json',
                                      'binding_qualification.json', 'preparation_tests.xml', 'endpoint_parity.json')]
    bound += list(templates.values()) + [OLD / 'launch_spec.json']
    spec = {'schema': 'cardpilot.actor_route.four_policy_external.v1', 'development_only': True,
        'schedule': runner.protocol.schedule(),
        'models': {arm: {'path': str(path), 'sha256': digest} for arm, (path, digest) in runner.EXPECTED_MODELS.items()},
        'runtime_source': str(runner.RUNTIME_SOURCE),
        'runtime_sha256': {str(path): runner.sha(path) for path in runner.RUNTIME_SOURCE.rglob('*.py') if '__pycache__' not in path.parts},
        'training_report_sha256': runner.sha(runner.REPORT),
        'preregistration_sha256': runner.sha(BASE / 'preregistration.md'),
        'code_sha256': hashes | {str(path): runner.sha(path) for path in bound}}
    runner.write_new(BASE / 'launch_spec.json', spec)
    runner.preflight(BASE)
    runner.write_new(BASE / 'preparation_report.json', {'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'wall_seconds': time.monotonic() - started,
        'outer_argv': [sys.executable, *sys.orig_argv[1:]], 'network_requests': 0, 'new_hands': 0,
        'runtime_python_files': len(spec['runtime_sha256']), 'planned_sessions': len(spec['schedule']),
        'planned_hands': sum(row['hands'] for row in spec['schedule']),
        'prior_initial_sessions_checked': len(prior), 'unreadable_prior_initial_records': unreadable,
        'planned_session_ids_and_seeds_unused': True, 'launch_spec_sha256': runner.sha(BASE / 'launch_spec.json'),
        'frozen_offline_tests_will_rerun_before_first_request': True})
    log = [sys.executable, str(ROOT / 'research/experiment_log.py'), 'update', BASE.name,
        '--metric', 'offline_preflight_passed=true', '--metric', 'preparation_added_hands=0',
        '--command', subprocess.list2cmdline(argv), '--command', subprocess.list2cmdline(parity_argv)]
    for name in ('environment.json', 'launch_spec.json', 'preparation_report.json', 'source_derivation.json',
                 'binding_qualification.json', 'preparation_tests.xml', 'endpoint_parity.json'):
        log += ['--artifact', str(BASE / name)]
    subprocess.run(log, cwd=ROOT, check=True)
    print('Offline four-policy preparation PASS: 32 sessions, 80000 planned hands, zero requests.', flush=True)


if __name__ == '__main__':
    main()
