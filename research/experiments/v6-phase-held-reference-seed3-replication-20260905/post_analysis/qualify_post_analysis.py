"""Record bounded offline qualification without touching the live experiment logger."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def main():
    out, xml = HERE / 'qualification.json', HERE / 'tests.xml'
    if out.exists() or xml.exists():
        raise FileExistsError('Existing qualification evidence is never overwritten')
    started = datetime.now(timezone.utc)
    commands = [[sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                 str(HERE / 'test_geometric_summary.py'), str(HERE / 'test_cross_seed_summary.py'),
                 '--junitxml=' + str(xml)],
                [sys.executable, '-B', str(HERE / 'summarize_geometric_control.py'), '--check-ready']]
    results = []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
                                timeout=45, env={**os.environ, 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'})
        results.append({'argv': command, 'exact_command': subprocess.list2cmdline(command),
                        'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            break
    files = list(HERE.glob('*.py')) + [HERE.parent / 'run_control.py', HERE.parent / 'control_evidence.py']
    if xml.exists():
        files.append(xml)
    hashes = {}
    for path in files:
        with path.open('rb') as handle:
            hashes[str(path)] = hashlib.file_digest(handle, 'sha256').hexdigest()
    value = {'schema': 'cardpilot.seed3.post_analysis_qualification.v1',
             'passed': len(results) == 2 and all(r['exit_code'] == 0 for r in results),
             'started_at': started.isoformat(), 'ended_at': datetime.now(timezone.utc).isoformat(),
             'command': [sys.executable, *sys.argv], 'commands': results, 'artifact_sha256': hashes,
             'training_hands': 0, 'evaluation_hands': 0, 'logger_attachment_deferred_until_owner_terminal': True,
             'live_controller_and_training_sources_modified': False}
    with out.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps(value, indent=2))
    return 0 if value['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
