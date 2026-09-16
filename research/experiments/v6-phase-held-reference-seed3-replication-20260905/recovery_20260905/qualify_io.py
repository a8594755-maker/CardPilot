"""Record zero-hand I/O recovery qualification inside the existing Seed3 record."""
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


def main():
    out, xml = HERE / 'io_qualification.json', HERE / 'io_tests.xml'
    if out.exists() or xml.exists():
        raise FileExistsError('Preserve earlier qualification outputs')
    commands = [[sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                 str(HERE / 'test_checkpoint_io_recovery.py'),
                 str(ROOT / 'scripts/alpha_holdem/test_managed_checkpoint_io.py'), '--junitxml=' + str(xml)],
                [sys.executable, '-B', str(HERE / 'train_with_checkpoint_io.py'), '--help']]
    results, started = [], datetime.now(timezone.utc)
    begin = time.perf_counter()
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
                                timeout=45, env={**os.environ, 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'})
        results.append({'argv': command, 'exact_command': subprocess.list2cmdline(command),
                        'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            break
    suites = list(ET.parse(xml).getroot().iter('testsuite')) if xml.exists() else []
    tests = sum(int(s.get('tests', '0')) for s in suites)
    skipped = sum(int(s.get('skipped', '0')) for s in suites)
    passed = len(results) == 2 and all(r['exit_code'] == 0 for r in results) and tests == 19 and skipped == 0
    files = list(HERE.glob('*.py')) + [HERE / 'recovery_amendment.md',
             ROOT / 'scripts/alpha_holdem/train_v5.py', ROOT / 'scripts/alpha_holdem/managed_checkpoint_io.py']
    if xml.exists():
        files.append(xml)
    hashes = {}
    for path in files:
        with path.open('rb') as handle:
            hashes[str(path)] = hashlib.file_digest(handle, 'sha256').hexdigest()
    value = {'schema': 'cardpilot.seed3.io_recovery_qualification.v1', 'passed': passed,
             'started_at': started.isoformat(), 'ended_at': datetime.now(timezone.utc).isoformat(),
             'wall_seconds': time.perf_counter() - begin, 'command': [sys.executable, *sys.argv],
             'commands': results, 'tests': tests, 'skipped': skipped, 'artifact_sha256': hashes,
             'training_hands': 0, 'evaluation_hands': 0, 'production_source_modified': False,
             'actual_windows_sharing_lock_tests_required_and_executed': passed,
             'production_training_or_poker_inference_started': False,
             'next_step': 'Qualify interruption-aware remainder controller before any resumed hands' if passed else
                          'Preserve failed qualification, correct only evidenced issue, no training launch'}
    with out.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({k: v for k, v in value.items() if k not in ('commands', 'artifact_sha256')}, indent=2))
    for result in results:
        if result['exit_code']:
            print(result['stdout'], result['stderr'])
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
