"""Record bounded, zero-hand offline post-analysis qualification; no logger write."""
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
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    out, xml = HERE / 'qualification.json', HERE / 'tests.xml'
    if out.exists() or xml.exists():
        raise FileExistsError('Existing qualification artifacts must be preserved')
    sources = [*HERE.glob('*.py'), BASE / 'post_analysis/cross_seed_summary.py',
               BASE / 'post_analysis/summarize_geometric_control.py',
               BASE / 'control_evidence.py', BASE / 'run_control.py']
    before = {str(p): sha(p) for p in sources}
    started, begin = datetime.now(timezone.utc), time.perf_counter()
    commands = [[sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                 str(HERE / 'test_recovered_seed3.py'), '--junitxml=' + str(xml)],
                [sys.executable, '-B', str(HERE / 'analyze_recovered_seed3.py'), '--check-ready']]
    results = []
    env = {**os.environ, 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
                                timeout=45, env=env)
        results.append({'argv': command, 'exact_command': subprocess.list2cmdline(command),
                        'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            break
    suites = list(ET.parse(xml).getroot().iter('testsuite')) if xml.exists() else []
    tests = sum(int(s.get('tests', 0)) for s in suites)
    bad = sum(int(s.get(k, 0)) for s in suites for k in ('failures', 'errors', 'skipped'))
    unchanged = all(sha(Path(path)) == digest for path, digest in before.items())
    passed = len(results) == 2 and all(r['exit_code'] == 0 for r in results) and tests >= 25 and bad == 0 and unchanged
    hashes = dict(before)
    if xml.exists():
        hashes[str(xml)] = sha(xml)
    value = {'schema': 'cardpilot.seed3.recovered_post_analysis_qualification.v1', 'passed': passed,
             'started_at': started.isoformat(), 'ended_at': datetime.now(timezone.utc).isoformat(),
             'wall_seconds': time.perf_counter() - begin, 'command': [sys.executable, *sys.argv],
             'commands': results, 'tests': tests, 'failed_errors_skipped': bad,
             'sources_unchanged': unchanged, 'artifact_sha256': hashes,
             'training_hands': 0, 'evaluation_hands': 0, 'model_inference_calls': 0,
             'full_terminal_analysis_executed': False, 'logger_attachment_deferred_until_owner_terminal': True,
             'live_controller_and_training_sources_modified': False}
    with out.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({k: v for k, v in value.items() if k != 'artifact_sha256'}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
