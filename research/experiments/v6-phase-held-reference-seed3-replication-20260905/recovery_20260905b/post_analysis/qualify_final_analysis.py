"""Offline qualification only; defer same-record attachment until controller exits."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
ROOT = BASE.parents[2]


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    out, xml = HERE / 'qualification.json', HERE / 'tests.xml'
    if out.exists() or xml.exists():
        raise FileExistsError('Do not overwrite prior qualification')
    old_path = BASE / 'recovery_20260905/post_analysis/qualification.json'
    old = json.loads(old_path.read_text(encoding='utf-8'))
    if not old['passed'] or old['tests'] != 32:
        raise ValueError('Previous accounting/guard qualification not passed')
    for path, digest in old['artifact_sha256'].items():
        if sha(path) != digest:
            raise ValueError(f'Prior qualification changed: {path}')
    inputs = {str(old_path): sha(old_path), **old['artifact_sha256'], **{str(p): sha(p) for p in HERE.glob('*.py')}}
    commands = [[sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                 str(HERE / 'test_twice_recovered.py'), '--junitxml=' + str(xml)],
                [sys.executable, '-B', str(HERE / 'analyze_twice_recovered.py'), '--check-ready']]
    started, begin, results = datetime.now(timezone.utc), time.perf_counter(), []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=45,
                                env={**os.environ, 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
        results.append({'argv': command, 'exact_command': subprocess.list2cmdline(command),
                        'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            break
    suites = list(ET.parse(xml).getroot().iter('testsuite')) if xml.exists() else []
    tests = sum(int(s.get('tests', 0)) for s in suites)
    bad = sum(int(s.get(k, 0)) for s in suites for k in ('failures', 'errors', 'skipped'))
    passed = len(results) == 2 and all(r['exit_code'] == 0 for r in results) and tests >= 25 and bad == 0
    passed = passed and all(sha(path) == digest for path, digest in inputs.items())
    if xml.exists():
        inputs[str(xml)] = sha(xml)
    value = {'schema': 'cardpilot.seed3.twice_recovered_post_analysis_qualification.v1', 'passed': passed,
        'started_at': started.isoformat(), 'ended_at': datetime.now(timezone.utc).isoformat(),
        'wall_seconds': time.perf_counter() - begin, 'command': [sys.executable, *sys.orig_argv[1:]],
        'commands': results, 'tests': tests, 'failed_errors_skipped': bad, 'prior_passed_tests_reused': 32,
        'input_sha256': inputs, 'training_hands': 0, 'evaluation_hands': 0, 'model_inference_calls': 0,
        'full_terminal_analysis_executed': False, 'logger_attachment_deferred_until_owner_terminal': True,
        'live_controller_or_training_source_modified': False}
    with out.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({k: v for k, v in value.items() if k != 'input_sha256'}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
