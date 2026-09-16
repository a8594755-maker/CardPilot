"""Finish this exact experiment only after independent complete-pilot review."""
import json
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def main():
    record = json.loads((BASE/'experiment.json').read_text())
    if record['status'] != 'RUNNING':
        raise RuntimeError('Do not reopen or refinish terminal experiment')
    command = ['python', (BASE/'review_completed_pilot.py').relative_to(ROOT).as_posix()]
    subprocess.run([sys.executable, 'research/experiment_log.py', 'update', BASE.name,
        '--command', subprocess.list2cmdline(command), '--command',
        f'python {Path(__file__).relative_to(ROOT).as_posix()}'], cwd=ROOT, check=True)
    # Review itself rejects active writers, partial sessions or existing output.
    subprocess.run([sys.executable, *command[1:]], cwd=ROOT, check=True)
    result = json.loads((BASE/'completed_analysis.json').read_text())
    summary = result['raw']
    if result['status'] != 'PASS' or result['evaluation_hands'] != 20000:
        raise ValueError('Independent review did not pass')
    paths = [BASE/name for name in ['completed_analysis.json', 'result_summary.md',
        'review_completed_pilot.py', 'finish_completed_run.py']]
    subprocess.run([sys.executable, 'research/experiment_log.py', 'update', BASE.name,
        '--metric', 'independent_review_pass=1', '--metric', f'raw_bb100={summary["bb_per_100"]}',
        '--metric', f'raw_ci95_lower={summary["lower_bound_bb_per_100"]}',
        '--metric', f'raw_ci95_upper={summary["upper_bound_bb_per_100"]}',
        *[item for path in paths for item in ['--artifact', str(path)]]], cwd=ROOT, check=True)
    admitted = result['decision'] == 'ADMIT_SEPARATE_FRESH100K'
    subprocess.run([sys.executable, 'research/experiment_log.py', 'finish', BASE.name,
        '--status', 'COMPLETED', '--count', 'new_training_hands=0', '--count', 'evaluation_hands=20000', '--count', 'slumbot_hands=20000',
        '--summary', f'Exactly20000fresh strict native-sampled weak-KL hands: {summary["bb_per_100"]:+.4f}bb/100,95%CI[{summary["lower_bound_bb_per_100"]:+.4f},{summary["upper_bound_bb_per_100"]:+.4f}]. All8clients exited0; strict audit and independent chip-space review passed.',
        '--conclusion', 'Frozen source, raw identity/accounting, clean policy execution, observable session-independence and source hashes passed. Historical greedy and aborted parent hands excluded. This20kpilot does not meet the100kgoal.',
        '--decision', result['decision'], '--next-step',
        ('Preregister a separate fixed100000fresh-hand formal test of this exact frozen policy; exclude all pilot/historical hands.' if admitted else
         'Do not extend or reselect this pilot. Select the next general learned-weight experiment from the completed evidence.')], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
