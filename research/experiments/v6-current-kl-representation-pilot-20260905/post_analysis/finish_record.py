"""Finish this same record only after terminal review and a written research decision."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from review import BASE, live, read, require, sha

ROOT = BASE.parents[2]


def validate_decision(decision, report_sha):
    require(decision.get('post_terminal_review_sha256') == report_sha, 'decision is not bound to this review')
    for key in ('summary', 'conclusion', 'decision', 'next_step'):
        require(isinstance(decision.get(key), str) and decision[key].strip(), f'missing research {key}')
    require(decision.get('goal_achieved') is False, 'this internal pilot cannot qualify the external goal')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-ready', action='store_true')
    args = parser.parse_args()
    owner = read(BASE / 'ownership.json')
    owner_live = live(owner['pid'], owner['create_time'])
    report_path, decision_path = BASE / 'post_terminal_review.json', BASE / 'post_analysis/research_decision.json'
    if args.check_ready:
        print(json.dumps({'owner_live': owner_live, 'terminal_review_exists': report_path.exists(),
                          'written_research_decision_exists': decision_path.exists(),
                          'ready_for_validation': not owner_live and report_path.exists() and decision_path.exists(),
                          'writes_performed': False}))
        return
    require(not owner_live, 'original controller still owns the logger')
    record, report, decision = read(BASE / 'experiment.json'), read(report_path), read(decision_path)
    require(record['status'] == 'RUNNING', 'not the same RUNNING record')
    require(report['passed'] and report['all_recorded_processes_terminal'], 'terminal review failed')
    require(report['accounting']['slumbot_hands'] == report['accounting']['final_qualification_hands'] == 0,
            'unexpected external evidence in internal pilot')
    validate_decision(decision, sha(report_path))
    require((BASE / 'result_summary.md').is_file(), 'missing written result summary')
    audit_path = BASE / 'post_finish_audit.json'
    require(not audit_path.exists(), 'preserve prior final audit')
    require(all(sha(path) == digest for path, digest in report['input_sha256'].items()), 'review evidence changed')
    for path in BASE.glob('*/process.json'):
        process = read(path)
        require(not live(process['pid'], process['create_time']), 'recorded job identity live')
        terminal = read(path.with_name('termination.json'))
        require(all(not live(pid, created) for pid, created in terminal['observed_children'].items()),
                'recorded descendant identity live')
    logger = [sys.executable, str(ROOT / 'research/experiment_log.py')]
    relative = BASE.relative_to(ROOT).as_posix()
    commands = {subprocess.list2cmdline(read(path)) for path in BASE.glob('*/command.json')}
    commands.update(f'python -B {relative}/post_analysis/{name}.py' for name in ('stage1_milestone', 'review', 'finish_record'))
    commands.add(f'python -B {relative}/post_analysis/finish_record.py --check-ready')
    if (BASE / 'post_analysis/curve_comparison.json').exists():
        commands.add(f'python -B {relative}/post_analysis/curve_comparison.py')
    if (BASE / 'post_analysis/curve_preparation_tests.xml').exists():
        commands.add(f'python -B -m pytest -q -p no:cacheprovider {relative}/post_analysis/test_review.py {relative}/post_analysis/test_finish_record.py {relative}/post_analysis/test_curve_comparison.py --junitxml={relative}/post_analysis/curve_preparation_tests.xml')
    for name in ('review_tests.xml', 'review_tests_v2.xml', 'review_tests_v3.xml', 'review_tests_stage1_milestone.xml'):
        if (BASE / 'post_analysis' / name).exists():
            commands.add(f'python -B -m pytest -q -p no:cacheprovider {relative}/post_analysis/test_review.py --junitxml={relative}/post_analysis/{name}')
    for name in ('finish_preparation_tests.xml', 'finish_preparation_tests_v2.xml'):
        if (BASE / 'post_analysis' / name).exists():
            commands.add(f'python -B -m pytest -q -p no:cacheprovider {relative}/post_analysis/test_review.py {relative}/post_analysis/test_finish_record.py --junitxml={relative}/post_analysis/{name}')
    existing = {row['command'] for row in record['commands']}
    # Separate argv per addition avoids the Windows command-line size limit.
    for command in sorted(commands - existing):
        subprocess.run(logger + ['update', BASE.name, '--command', command], cwd=ROOT, check=True, capture_output=True)
    artifacts = [report_path, BASE / 'result_summary.md', *sorted((BASE / 'post_analysis').glob('*'))]
    for artifact in artifacts:
        if artifact.is_file():
            subprocess.run(logger + ['update', BASE.name, '--artifact', str(artifact)], cwd=ROOT, check=True, capture_output=True)
    argv = logger + ['finish', BASE.name, '--status', 'COMPLETED']
    for key, value in report['accounting'].items():
        argv += ['--count', f'{key}={value}']
    metrics = {'independent_terminal_review_passed': True, 'goal_achieved': False,
               'training_subprocess_wall_seconds': report['training_subprocess_wall_seconds'],
               'all_job_wall_seconds': report['all_job_wall_seconds'],
               'actual_new_physical_hands_per_training_wall_second': report['actual_new_physical_hands_per_training_wall_second'],
               'controller_wall_seconds': report['controller_wall_seconds'],
               'controller_phase': report['phase'], 'automatic_next_scale': False}
    for key, value in metrics.items():
        argv += ['--metric', key + '=' + json.dumps(value)]
    for key in ('summary', 'conclusion', 'decision', 'next_step'):
        argv += ['--' + key.replace('_', '-'), decision[key]]
    argv += ['--note', 'Closed only after exact owner/children were terminal and raw paired evidence and source/weight hashes were independently checked. Stage1 milestone and deferred post-analysis commands/artifacts attached after sole-writer ownership ended. Inherited unknown interruption tails remain unknown; new managed attempts are statistical worker continuation, not bitwise worker RNG replay. Internal hands are not Slumbot qualification.']
    subprocess.run(argv, cwd=ROOT, check=True)
    audit = logger + ['audit', '--since', record['created_at'], '--out-json', str(audit_path), '--fail-on-warning']
    subprocess.run(audit, cwd=ROOT, check=True)
    subprocess.run(logger + ['update', BASE.name, '--artifact', str(audit_path), '--command', subprocess.list2cmdline(audit),
                            '--note', 'Post-finish scoped logger audit passed without warnings.'], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
