"""Exclusive offline Seed3 endpoint/session qualification; no network or model calls."""
from datetime import datetime, timezone
from importlib import metadata
import ast
import difflib
from pathlib import Path
import platform
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(BASE))
import run_pair as runner

OLD = ROOT / 'research/experiments/v6-phase-reference-greedy-paired-fresh80k-20260905'
OLD_PREP = ROOT / 'research/experiments/v6-phase-held-reference-control-20260904/recovery_20260905/external_preparation'
OLD_SPEC_SHA = '5a12f172c99330491e02fefdbd43adaba913667114b685cf4c4ab6fbf79be8ed'
OLD_REPORT_SHA = '0ca3eff30cd967690d6099f2e7a36e4095a822953b6a1236c32800c53dd54d05'


def structural_items(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    return {node.name: ast.dump(node, include_attributes=False)
            for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}


def main():
    started = time.monotonic()
    runner.protocol.require(runner.read(BASE / 'experiment.json')['status'] == 'RUNNING', 'register first')
    for name in ('launch_spec.json', 'environment.json', 'preparation_report.json', 'execution.json',
                 'source_derivation.json', 'binding_qualification.json', 'preparation_tests.xml'):
        runner.protocol.require(not (BASE / name).exists(), 'preparation already attempted; preserve: ' + name)
    runner.training_ready()
    runner.protocol.require(runner.read(OLD / 'experiment.json')['status'] == 'COMPLETED', 'Seed1 comparison incomplete')
    runner.protocol.require(runner.sha(OLD / 'launch_spec.json') == OLD_SPEC_SHA and
                            runner.sha(OLD / 'post_terminal_review.json') == OLD_REPORT_SHA,
                            'preserved Seed1 external provenance changed')
    old_spec = runner.read(OLD / 'launch_spec.json')
    runner.check_hashes(old_spec['code_sha256'])
    runner.protocol.require(runner.sha(runner.RUNTIME_SOURCE / 'alpha_holdem/play_slumbot_v6_journaled.py') ==
        'cea29a9217784b27168665dc01c981433832bb0d7352aefdfe7041f7c896429d', 'client changed')
    prior, unreadable = runner.prior_initial_sessions(ROOT / 'research/experiments', BASE)
    runner.check_unused_session_identifiers(prior)
    runner.check_prior_prefixes(prior)

    templates = {name: OLD_PREP / name for name in
                 ('run_pair.py', 'pair_protocol.py', 'test_run_pair.py', 'test_pair_protocol.py')}
    templates.update({name: OLD / name for name in ('prepare_launch.py', 'launch.ps1')})
    derivation, unchanged = {}, {}
    for name, old_path in templates.items():
        runner.protocol.require(old_spec['code_sha256'].get(str(old_path)) == runner.sha(old_path), 'template not qualified')
        path = BASE / name
        derivation[name] = {'template_path': str(old_path), 'template_sha256': runner.sha(old_path),
            'derived_path': str(path), 'derived_sha256': runner.sha(path),
            'unified_diff': list(difflib.unified_diff(old_path.read_text(encoding='utf-8').splitlines(),
                path.read_text(encoding='utf-8').splitlines(), fromfile=str(old_path), tofile=str(path), lineterm=''))}
    for name, allowed in (('run_pair.py', {'training_ready', 'preflight'}), ('pair_protocol.py', {'schedule'})):
        old_items, new_items = structural_items(templates[name]), structural_items(BASE / name)
        names = sorted(set(old_items) - allowed)
        runner.protocol.require(all(old_items[key] == new_items.get(key) for key in names),
                                'execution/evidence/statistical logic changed beyond declared admission and identifiers')
        unchanged[name] = names
    runner.write_new(BASE / 'source_derivation.json', {'passed': True, 'templates': derivation,
        'ast_identical_execution_evidence_statistical_items': unchanged,
        'scope': 'AST equality for unchanged core functions/classes, not a proof of all new admission behavior',
        'old_launch_spec_sha256': OLD_SPEC_SHA, 'old_external_report_sha256': OLD_REPORT_SHA})

    sources = [BASE / name for name in ('run_pair.py', 'pair_protocol.py', 'test_run_pair.py',
                                      'test_pair_protocol.py', 'prepare_launch.py', 'launch.ps1')]
    sources += [ROOT / 'research/experiment_log.py']
    source_hashes = {str(path): runner.sha(path) for path in sources}
    argv = [sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
            str(BASE / 'test_run_pair.py'), str(BASE / 'test_pair_protocol.py'),
            f'--junitxml={BASE / "preparation_tests.xml"}']
    test_start = time.monotonic()
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    runner.write_new(BASE / 'binding_qualification.json', {'passed': result.returncode == 0,
        'created_at': datetime.now(timezone.utc).isoformat(), 'outer_argv': [sys.executable, *sys.orig_argv[1:]],
        'argv': argv, 'exact_command': subprocess.list2cmdline(argv), 'exit_code': result.returncode,
        'stdout': result.stdout, 'stderr': result.stderr, 'wall_seconds': time.monotonic() - test_start,
        'source_sha256': source_hashes, 'new_training_hands': 0, 'evaluation_hands': 0,
        'network_requests': 0, 'model_inference_calls': 0})
    runner.check_hashes(source_hashes)
    runner.protocol.require(result.returncode == 0, 'offline binding tests failed; preserve this preparation')
    versions = {name: metadata.version(name) for name in ('torch', 'numpy', 'scipy', 'requests', 'psutil', 'pytest')}
    runner.write_new(BASE / 'environment.json', {'recorded_at': datetime.now(timezone.utc).isoformat(),
        'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(), 'packages': versions,
        'purpose': 'CPU frozen-policy external development; no training or network in preparation'})
    bound_extra = [BASE / name for name in ('environment.json', 'source_derivation.json',
                                           'binding_qualification.json', 'preparation_tests.xml')]
    bound_extra += list(templates.values()) + [OLD / 'launch_spec.json', OLD / 'post_terminal_review.json']
    spec = {'schema': 'cardpilot.phase_reference.external_pair.v1', 'development_only': True,
        'schedule': runner.protocol.schedule(),
        'models': {arm: {'path': str(path), 'sha256': digest} for arm, (path, digest) in runner.EXPECTED_MODELS.items()},
        'runtime_source': str(runner.RUNTIME_SOURCE),
        'runtime_sha256': {str(path): runner.sha(path) for path in runner.RUNTIME_SOURCE.rglob('*.py') if '__pycache__' not in path.parts},
        'training_report_sha256': runner.sha(runner.REPORT),
        'preregistration_sha256': runner.sha(BASE / 'preregistration.md'),
        'code_sha256': source_hashes | {str(path): runner.sha(path) for path in bound_extra}}
    runner.write_new(BASE / 'launch_spec.json', spec)
    runner.preflight(BASE)
    runner.write_new(BASE / 'preparation_report.json', {'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'wall_seconds': time.monotonic() - started,
        'outer_argv': [sys.executable, *sys.orig_argv[1:]], 'network_requests': 0, 'new_hands': 0,
        'runtime_python_files': len(spec['runtime_sha256']), 'planned_sessions': len(spec['schedule']),
        'planned_hands': sum(row['hands'] for row in spec['schedule']),
        'prior_initial_sessions_checked': len(prior), 'unreadable_prior_initial_records': unreadable,
        'planned_session_ids_and_seeds_unused': True, 'launch_spec_sha256': runner.sha(BASE / 'launch_spec.json'),
        'frozen_runtime_tests_will_rerun_before_first_request': True})
    log = [sys.executable, str(ROOT / 'research/experiment_log.py'), 'update', BASE.name,
        '--metric', 'offline_preflight_passed=true', '--metric', 'preparation_added_hands=0',
        '--command', subprocess.list2cmdline(argv)]
    for name in ('environment.json', 'launch_spec.json', 'preparation_report.json', 'source_derivation.json',
                 'binding_qualification.json', 'preparation_tests.xml'):
        log += ['--artifact', str(BASE / name)]
    subprocess.run(log, cwd=ROOT, check=True)
    print('Offline Seed3 preparation PASS; 32 registered sessions, 80000 planned hands, zero network requests.', flush=True)


if __name__ == '__main__':
    main()
