"""Reuse passed I/O tests; qualify only the corrected trainer import-path wrapper."""
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


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    out = HERE / 'io_qualification_v2.json'
    if out.exists():
        raise FileExistsError(out)
    previous_path = HERE / 'io_qualification.json'
    previous = json.loads(previous_path.read_text(encoding='utf-8'))
    if previous['tests'] != 19 or previous['skipped'] != 0 or previous['commands'][0]['exit_code'] != 0:
        raise ValueError('Original19 I/O tests did not pass')
    for raw, expected in previous['artifact_sha256'].items():
        if sha(Path(raw)) != expected:
            raise ValueError(f'Prior qualification source/evidence changed: {raw}')
    tests = ET.parse(HERE / 'io_tests.xml').getroot()
    for name in ('test_actual_windows_sharing_conflict_recovers', 'test_actual_persistent_lock_keeps_recoverable_candidate'):
        matches = [case for case in tests.iter('testcase') if case.get('name') == name]
        if len(matches) != 1 or list(matches[0]):
            raise ValueError('Required actual Windows case did not pass')
    command = [sys.executable, '-B', str(HERE / 'train_with_checkpoint_io_v2.py'), '--help']
    started, begin = datetime.now(timezone.utc), time.perf_counter()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=45,
                            env={**os.environ, 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'})
    passed = result.returncode == 0 and '--managed-deal-attempts' in result.stdout
    inputs = {str(previous_path): sha(previous_path), **previous['artifact_sha256']}
    sources = [Path(__file__).resolve(), HERE / 'train_with_checkpoint_io_v2.py']
    inputs.update({str(p): sha(p) for p in sources})
    value = {'schema': 'cardpilot.seed3.io_recovery_qualification.v2', 'passed': passed,
             'started_at': started.isoformat(), 'ended_at': datetime.now(timezone.utc).isoformat(),
             'wall_seconds': time.perf_counter() - begin, 'command': [sys.executable, *sys.argv],
             'qualification_command': command, 'exact_command': subprocess.list2cmdline(command),
             'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
             'input_sha256': inputs, 'reused_passed_io_tests': 19, 'new_io_tests': 0,
             'actual_windows_transient_and_persistent_lock_tests_passed': True,
             'v1_failure_preserved': True, 'v1_failure_component': 'wrapper module search path; not I/O unit tests',
             'v1_actual_windows_tests_flag_was_conflated_with_whole_qualification': True,
             'training_hands': 0, 'evaluation_hands': 0, 'production_source_modified': False,
             'training_started': False, 'next_step': 'Qualify interruption-aware remainder controller'}
    with out.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({k: v for k, v in value.items() if k not in ('input_sha256', 'stdout')}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
