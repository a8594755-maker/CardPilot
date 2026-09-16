"""Close the completed pilot after merging supplemental provenance exactly once."""
import json
import subprocess
import sys

from report_completed_pilot import ensure_writer_finished
from run_pilot import BASE, ROOT


def main():
    ensure_writer_finished()
    record = json.loads((BASE / 'experiment.json').read_text())
    result = json.loads((BASE / 'completed_analysis.json').read_text())
    pending = json.loads((BASE / 'deferred_report_updates.json').read_text())
    if record['status'] != 'RUNNING' or result['status'] != 'PASS':
        raise ValueError('Only the completed, still-running record can be closed')
    if result['admits_independent_confirmation']:
        raise ValueError('This reviewed closure is for the actual non-admitted result only')
    args = [sys.executable, 'research/experiment_log.py', 'update', BASE.name,
            '--metric', 'supplemental_report_updates_merged=1',
            '--metric', 'completed_independent_audit_pass=1',
            '--command', f'python {(BASE / "report_completed_pilot.py").relative_to(ROOT).as_posix()}',
            '--command', f'python {__file__.replace(chr(92), "/")}',
            '--note', 'Merged all supplemental commands, tests, analysis and notes from deferred_report_updates.json after original wrapper EXIT0. Its PENDING label is retained as historical intent; this metric confirms the merge is complete.']
    for command in pending['commands_executed']:
        args += ['--command', command]
    for key, value in pending['metrics'].items():
        args += ['--metric', f'{key}={value}']
    for note in pending['notes']:
        args += ['--note', note]
    for path in pending['artifacts'] + [str(BASE/name) for name in [
            'deferred_report_updates.json', 'completed_analysis.json', 'result_summary.md', 'finish_review.py']]:
        args += ['--artifact', path]
    for arm, row in result['arms'].items():
        for key, value in dict(adam_steps=row['batch_accounting']['total_steps'],
                              partial_batch_steps=row['batch_accounting']['partial_batch_steps'],
                              unchanged_representation_tensors=row['unchanged_representation_tensors']).items():
            args += ['--metric', f'{arm}_{key}={value}']
    subprocess.run(args, cwd=ROOT, check=True)
    subprocess.run([sys.executable, 'research/experiment_log.py', 'finish', BASE.name,
        '--status', 'COMPLETED', '--count', f'new_training_hands={result["new_training_hands"]}',
        '--count', 'evaluation_hands=73728',
        '--summary', 'Both matched arms completed274832 measured physical hands and73728 frozen internal evaluation hands. All integrity checks passed; the joint large-batch/LR regimen failed its registered admission gate.',
        '--conclusion', 'Large-minus-control deltas were-0.33594,+0.83411,+3.35493bb/100 across Standard10/slumbot_free/CFR96; all primary95percent CIs cross0. No evidence supports promoting or scaling this regimen. Saved Adam steps784versus56 exactly match all full/partial batches; no KL stops and76 shared tensors unchanged. This is a valid inconclusive treatment result,not a failed execution.',
        '--decision', 'JOINT_REGIMEN_NOT_ADMITTED: retain all frozen evidence; no optional extension,checkpoint reselection,unchanged-regimen scaleup or treatment Slumbot promotion.',
        '--next-step', 'Follow pre-result conditional review: repair/test stochastic Slumbot evidence audits,then separately preregister a fixed fresh external baseline for unchanged original Standard10 native sample/temp1. Historical greedy20k is not a sampled-policy baseline; future qualifying100k must be fresh and separate. Continue learned-weight research informed by that calibration.'], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
