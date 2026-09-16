"""Close this same fixed-dose study after terminal evidence and research review.

Outside live frozen dependencies. --check-ready is read-only. The normal command
must wait for owner exit and a written decision bound to both reviewed stages.
"""
import argparse
import json
import subprocess
import sys

from review import BASE, ROOT, live, read, require, sha


def validate_decision(decision, report_sha, curve_sha):
    require(decision.get('post_terminal_review_sha256') == report_sha,
            'decision is not bound to this terminal review')
    require(decision.get('curve_comparison_sha256') == curve_sha,
            'decision is not bound to this complete learning curve')
    for key in ('summary', 'conclusion', 'decision', 'next_step'):
        require(isinstance(decision.get(key), str) and decision[key].strip(), f'missing research {key}')
    require(decision.get('goal_achieved') is False, 'this internal study cannot qualify the external goal')


def mutation_batches(prefix, entries, max_chars=24000):
    """Reduce repeated artifact rehashing without exceeding Windows argv limits."""
    batch = list(prefix)
    for flag, value in entries:
        addition = [flag, str(value)]
        require(len(subprocess.list2cmdline(prefix + addition)) < max_chars,
                'single mutation exceeds command-line limit')
        if len(subprocess.list2cmdline(batch + addition)) >= max_chars:
            yield batch
            batch = list(prefix)
        batch.extend(addition)
    if len(batch) > len(prefix):
        yield batch


def commands_from_evidence(base):
    commands = {subprocess.list2cmdline(read(path)) for path in base.glob('*/command.json')}
    # Actual sys.orig_argv saved by completed analyses; do not guess invocations.
    outputs = [base / 'post_terminal_review.json', base / 'post_analysis/curve_comparison.json',
               base / 'post_analysis/stage1_independent_review.json',
               base / 'post_analysis/gradient_route_observation.json',
               *sorted((base / 'post_analysis').glob('seed*_realized_dose.json'))]
    for path in outputs:
        argv = read(path).get('command')
        require(isinstance(argv, list) and argv and all(isinstance(x, str) for x in argv),
                f'missing actual command:{path}')
        commands.add(subprocess.list2cmdline(argv))
    relative = base.relative_to(ROOT).as_posix()
    suites = {
        'review_tests.xml': ['test_review.py'],
        'curve_tests.xml': ['test_review.py', 'test_curve_comparison.py'],
        'finish_preparation_tests.xml': ['test_review.py', 'test_curve_comparison.py', 'test_finish_record.py'],
    }
    for output, tests in suites.items():
        require((base / 'post_analysis' / output).is_file(), f'missing executed tests:{output}')
        commands.add('python -B -m pytest -q -p no:cacheprovider '
            + ' '.join(f'{relative}/post_analysis/{name}' for name in tests)
            + f' --junitxml={relative}/post_analysis/{output}')
    commands.add(subprocess.list2cmdline(sys.orig_argv))
    return commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-ready', action='store_true')
    args = parser.parse_args()
    owner = read(BASE / 'ownership.json')
    owner_live = live(owner['pid'], owner['create_time'])
    report_path = BASE / 'post_terminal_review.json'
    curve_path = BASE / 'post_analysis/curve_comparison.json'
    decision_path = BASE / 'post_analysis/research_decision.json'
    summary_path = BASE / 'result_summary.md'
    required = (report_path, curve_path, decision_path, summary_path)
    if args.check_ready:
        print(json.dumps({'owner_live': owner_live,
            'missing_inputs': [str(p) for p in required if not p.is_file()],
            'ready_for_validation': not owner_live and all(p.is_file() for p in required),
            'writes_performed': False}))
        return
    require(not owner_live, 'original controller still owns the logger')
    require(not (BASE / 'controller_error.json').exists(), 'failure needs its own evidence review')
    record, report, curve, decision = [read(p) for p in
        (BASE / 'experiment.json', report_path, curve_path, decision_path)]
    require(record['status'] == 'RUNNING', 'not the same RUNNING record')
    require(report['passed'] and report['all_recorded_processes_terminal'], 'terminal review failed')
    require(set(report['stages']) == {'1', '2'} and report['accounting']['evaluation_hands'] == 262144
            and report['unique_new_evaluation_decks'] == 32768, 'fixed-dose evaluation incomplete')
    require(report['accounting']['slumbot_hands'] == report['accounting']['final_qualification_hands'] == 0,
            'unexpected external hand credit')
    require(curve['passed'] and set(curve['seeds']) == {'1', '3'}
            and curve['automatic_promotion_or_qualification'] is False, 'curve review incomplete')
    require(curve['input_sha256'][str(report_path)] == sha(report_path), 'curve used another review')
    validate_decision(decision, sha(report_path), sha(curve_path))
    require(summary_path.is_file(), 'missing written result summary')
    audit_path = BASE / 'post_finish_audit.json'
    require(not audit_path.exists(), 'preserve prior final audit')
    for evidence in (report, curve):
        require(all(sha(path) == digest for path, digest in evidence['input_sha256'].items()), 'review evidence changed')
    for path in BASE.glob('*/process.json'):
        process, terminal = read(path), read(path.with_name('termination.json'))
        require(not live(process['pid'], process['create_time']), 'recorded job identity live')
        require(terminal['exit_code'] == 0 and not terminal['observer_errors']
                and not terminal['remaining_observed_child_pids'], 'job not cleanly terminal')
        require(all(not live(pid, created) for pid, created in terminal['observed_children'].items()),
                'recorded descendant identity live')
    logger = [sys.executable, str(ROOT / 'research/experiment_log.py')]
    commands = commands_from_evidence(BASE) - {row['command'] for row in record['commands']}
    artifacts = [report_path, summary_path, *sorted((BASE / 'post_analysis').glob('*'))]
    entries = [('--command', command) for command in sorted(commands)]
    entries += [('--artifact', str(path)) for path in artifacts if path.is_file()]
    # The first logger mutation is possible only after all validations above.
    require(not live(owner['pid'], owner['create_time']), 'owner became live before mutation')
    for argv in mutation_batches(logger + ['update', BASE.name], entries):
        subprocess.run(argv, cwd=ROOT, check=True, capture_output=True)
    argv = logger + ['finish', BASE.name, '--status', 'COMPLETED']
    for key, value in report['accounting'].items():
        argv += ['--count', f'{key}={value}']
    metrics = {key: report[key] for key in ('training_subprocess_wall_seconds', 'all_job_wall_seconds',
        'actual_new_physical_hands_per_training_wall_second', 'controller_wall_seconds')}
    metrics.update(independent_terminal_review_passed=True, goal_achieved=False,
                   controller_phase=report['phase'], automatic_next_scale=False)
    for key, value in metrics.items():
        argv += ['--metric', key + '=' + json.dumps(value)]
    for key in ('summary', 'conclusion', 'decision', 'next_step'):
        argv += ['--' + key.replace('_', '-'), decision[key]]
    argv += ['--note', 'Closed after exact owner/children terminal, complete raw paired evaluation, '
        'initial optimizer/replay state, counters, source and weight hashes were independently reviewed. '
        'Deferred post-analysis commands are recovered from actual invocation evidence. '
        'Earlier heads-only hands are not full-representation training; trainable scope is not proof '
        'that preflop or critic objectives update the shared body. Managed worker restarts are '
        'statistical continuation, not bitwise rollout RNG replay. No external qualification claim.']
    subprocess.run(argv, cwd=ROOT, check=True)
    audit = logger + ['audit', '--since', record['created_at'], '--out-json', str(audit_path), '--fail-on-warning']
    subprocess.run(audit, cwd=ROOT, check=True)
    subprocess.run(logger + ['update', BASE.name, '--artifact', str(audit_path),
        '--command', subprocess.list2cmdline(audit), '--note', 'Post-finish scoped logger audit passed without warnings.'],
        cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
