"""Reuse19 qualified I/O tests; test extended grace and real unchanged-trainer CLI."""
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
ROOT = HERE.parents[3]
PREVIOUS = HERE.parent / 'recovery_20260905'


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    out, xml = HERE / 'io_grace_qualification.json', HERE / 'io_grace_tests.xml'
    if out.exists() or xml.exists():
        raise FileExistsError('Preserve previous qualification evidence')
    old_path = PREVIOUS / 'io_qualification_v2.json'
    old = json.loads(old_path.read_text(encoding='utf-8'))
    if not old['passed'] or old['reused_passed_io_tests'] != 19:
        raise ValueError('Original I/O qualification not passed')
    for raw, digest in old['input_sha256'].items():
        if sha(Path(raw)) != digest:
            raise ValueError(f'Previous qualified input changed: {raw}')
    sources = [HERE / n for n in ('train_with_checkpoint_io_45s.py', 'test_io_publication_grace.py', 'qualify_io_grace.py')]
    inputs = {**old['input_sha256'], str(old_path): sha(old_path), **{str(p): sha(p) for p in sources}}
    commands = [[sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                 str(HERE / 'test_io_publication_grace.py'), '--junitxml=' + str(xml)],
                [sys.executable, '-B', str(HERE / 'train_with_checkpoint_io_45s.py'), '--help']]
    results, started, begin = [], datetime.now(timezone.utc), time.perf_counter()
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
    passed = len(results) == 2 and all(r['exit_code'] == 0 for r in results) and tests == 3 and bad == 0
    passed = passed and '--managed-deal-attempts' in results[-1]['stdout']
    passed = passed and all(sha(Path(path)) == digest for path, digest in inputs.items())
    if xml.exists():
        inputs[str(xml)] = sha(xml)
    value = {'schema': 'cardpilot.seed3.io_45s_grace_qualification.v1', 'passed': passed,
             'started_at': started.isoformat(), 'ended_at': datetime.now(timezone.utc).isoformat(),
             'wall_seconds': time.perf_counter() - begin, 'command': [sys.executable, *sys.argv],
             'commands': results, 'new_tests': tests, 'failed_errors_skipped': bad, 'prior_passed_tests_reused': 19,
             'actual_windows_lock_over5s_test_required': True,
             'grace_policy': {'replace_timeout_seconds': 45.0, 'max_replace_attempts': 256},
             'input_sha256': inputs, 'original_failure_holder_not_established': True,
             'training_hands': 0, 'evaluation_hands': 0, 'training_started': False,
             'production_or_permissions_modified': False,
             'next_step': 'Qualify exact moving-reference/pending-candidate resume and continue the same experiment only.'}
    with out.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({k: v for k, v in value.items() if k != 'input_sha256'}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
