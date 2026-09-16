"""Merge deferred provenance and close only the reviewed complete matched pilot."""
import json
from pathlib import Path
import subprocess
import sys

from report_completed_pilot import ensure_writer_finished
from run_pilot import BASE, ROOT, sha


def main():
    ensure_writer_finished()
    record = json.loads((BASE/'experiment.json').read_text())
    if record['status'] != 'RUNNING':
        raise RuntimeError('Do not reopen/refinish a terminal record')
    pending = json.loads((BASE/'deferred_review_updates.json').read_text())
    command = ['python', (BASE/'report_completed_pilot.py').relative_to(ROOT).as_posix()]
    if (BASE/'completed_analysis.json').exists():
        raise RuntimeError('Existing completed review requires explicit inspection before closure')
    subprocess.run([sys.executable, *command[1:]], cwd=ROOT, check=True)
    result = json.loads((BASE/'completed_analysis.json').read_text())
    if result['status'] != 'PASS' or result['evaluation_hands'] != 73728 or result['slumbot_hands'] != 0:
        raise ValueError('Incomplete independent review')
    if sha(BASE/'report_completed_pilot.py') != result['review_script_sha256']:
        raise ValueError('Review source changed')
    args = [sys.executable, 'research/experiment_log.py', 'update', BASE.name,
        '--metric', 'supplemental_review_updates_merged=1', '--metric', 'independent_review_pass=1',
        '--command', subprocess.list2cmdline(command),
        '--command', f'python {Path(__file__).relative_to(ROOT).as_posix()}',
        '--note', 'Original wrapper is terminal before merging supplemental review provenance. Deferred PENDING label is retained as original intent; merged metric establishes completion. No training or evaluation hands were added by offline tests/review.']
    for item in pending['commands_executed']:
        args += ['--command', item]
    for key, value in pending['metrics'].items():
        args += ['--metric', f'{key}={value}']
    for note in pending['notes']:
        args += ['--note', note]
    for path in pending['artifacts']+[str(BASE/name) for name in [
        'deferred_review_updates.json', 'completed_analysis.json', 'result_summary.md', 'finish_review.py']]:
        args += ['--artifact', path]
    for arm, row in result['arms'].items():
        for key, value in dict(adam_steps=row['batch_accounting']['total_steps'],
                unchanged_trunk_tensors=row['unchanged_representation_tensors'],
                max_reference_kl=row['max_reference_kl'], max_clip_fraction=row['max_clip_fraction']).items():
            args += ['--metric', f'{arm}_{key}={value}']
    subprocess.run(args, cwd=ROOT, check=True)
    primary = result['comparisons']['weak_vs_control']
    contrasts = '; '.join(f'{r["anchor"]}:{r["delta_bb100"]:+.5f}bb/100'
        f' adjustedCI[{r["bonferroni_lower"]:+.5f},{r["bonferroni_upper"]:+.5f}]' for r in primary)
    admitted = result['admits_independent_confirmation']
    subprocess.run([sys.executable, 'research/experiment_log.py', 'finish', BASE.name,
        '--status', 'COMPLETED', '--count', f'new_training_hands={result["new_training_hands"]}',
        '--count', 'evaluation_hands=73728',
        '--summary', f'Matched source-KL1versus0.01 completed{result["new_training_hands"]}physical training hands and73728internal sampled hands. Independent raw,source,session,model and Adam reviews passed; {result["decision"]}.',
        '--conclusion', contrasts+'. Frozen trunk76tensors unchanged in both arms; exact Adam steps reconstructed from full/partial minibatches. These are internal pilot results,not Slumbot strength or Nash convergence.',
        '--decision', result['decision'], '--next-step',
        ('Separately preregister independent sampled multi-anchor confirmation of exactly these frozen endpoints before any promotion; no discovery pooling.' if admitted else
         'Do not extend or promote this non-admitted pilot. Choose the next general learned-weight mechanism using completed contrasts and training health; preserve all endpoints and raw evidence.')], cwd=ROOT, check=True)
    print(json.dumps(dict(decision=result['decision'], new_training_hands=result['new_training_hands'], evaluation_hands=73728)))


if __name__ == '__main__':
    main()
