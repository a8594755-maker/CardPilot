"""Record completed supplemental work after the sole evaluation writer exits.

The queued commands are evidence of past executions, not jobs to execute again.
This updates the same record and never starts training/evaluation or finishes it.
"""
import json
from pathlib import Path
import subprocess
import sys

import psutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def main():
    for process in psutil.process_iter(['pid', 'cmdline']):
        command = ' '.join(process.info['cmdline'] or [])
        if process.pid != psutil.Process().pid and BASE.name in command and any(
            script in command for script in ['run_training.py', 'run_evaluation.py', 'v5_mirror_eval.py']
        ):
            raise RuntimeError('Wait for original writers; do not race their accounting')
    record = json.loads((BASE / 'experiment.json').read_text())
    analysis = json.loads((BASE / 'completed_analysis.json').read_text())
    if record['status'] != 'RUNNING' or analysis['status'] != 'PASS':
        raise RuntimeError('Requires the same RUNNING record and completed independent analysis')
    if analysis['evaluation_hands'] != 147456 or record['metrics'].get('discovery_matrix_complete') != 1:
        raise RuntimeError('The preregistered matrix is incomplete')
    queued = json.loads((BASE / 'deferred_record_updates.json').read_text())
    cmd = [sys.executable, 'research/experiment_log.py', 'update', BASE.name]
    for command in queued['commands']:
        cmd += ['--command', command]
    for artifact in queued['artifacts']:
        if not (ROOT / artifact).exists():
            raise FileNotFoundError(artifact)
        cmd += ['--artifact', artifact]
    for key, value in queued['metrics'].items():
        cmd += ['--metric', f'{key}={value}']
    for note in queued['notes']:
        cmd += ['--note', note]
    for filename in ['deferred_record_updates.json', 'merge_deferred_record_updates.py',
                     'completed_analysis.json', 'result_summary.md']:
        cmd += ['--artifact', (BASE / filename).relative_to(ROOT).as_posix()]
    for path in sorted((BASE / 'frozen').glob('*.pt')):
        cmd += ['--artifact', path.relative_to(ROOT).as_posix()]
    for filename in ['analyze_completed_run.py', 'merge_deferred_record_updates.py']:
        cmd += ['--command', 'python ' + (BASE / filename).relative_to(ROOT).as_posix()]
    cmd += ['--count', f"new_training_hands={analysis['physical_training_hands']}",
            '--count', 'evaluation_hands=147456',
            '--metric', f"legacy_marker_hands={analysis['legacy_marker_hands']}",
            '--metric', 'independent_analysis_pass=1', '--metric', 'deferred_updates_applied=1',
            '--note', 'Merged deferred test/provenance/prefix-audit evidence after original writers exited. Queued commands were only recorded, not rerun. Final legacy marker metric synchronized to immutable final checkpoint868858; actual physical accounting1049891 remains unchanged.']
    if len(subprocess.list2cmdline(cmd)) > 30000:
        raise RuntimeError('Logger command exceeds conservative Windows argument budget')
    subprocess.run(cmd, cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
