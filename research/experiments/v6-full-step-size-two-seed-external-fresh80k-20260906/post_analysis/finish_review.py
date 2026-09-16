"""Finish only the same audited80k record after a hash-bound research decision."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_completed as review


def audit_command(logger, record, output):
    return logger + ['audit', '--since', record['created_at'], '--out-json', str(output), '--fail-on-warning']


def validate_decision(decision, report_sha, summary_sha):
    r = review.r
    r.protocol.require(decision.get('post_terminal_review_sha256') == report_sha and
                       decision.get('result_summary_sha256') == summary_sha,
                       'research decision is not bound to this reviewed evidence and summary')
    r.protocol.require(decision.get('goal_achieved') is False, 'development is not final qualification')
    for name in ('summary', 'conclusion', 'decision', 'next_step'):
        r.protocol.require(type(decision.get(name)) is str and len(decision[name].strip()) >= 20,
                           'missing substantive research decision: ' + name)


def finish():
    r, base, root = review.r, review.BASE, review.ROOT
    r.protocol.require(review.readiness()['ready'], 'owner/evidence not ready; no logger writes')
    record = r.read(base / 'experiment.json')
    r.protocol.require(record['status'] == 'RUNNING', 'finish only the same RUNNING experiment')
    path = base / 'post_terminal_review.json'
    report = r.read(path)
    r.protocol.require(report['schema'] == 'cardpilot.full_step_size.four_policy_post_terminal_review.v1' and
        report['passed'] is True and report['evaluation_hands'] == report['slumbot_hands'] == 80000 and
        report['new_training_hands'] == report['analysis_added_hands'] == report['final_qualification_hands'] == 0 and
        report['current_decision_replays'] > 0 and report['goal_achieved'] is False, 'review incomplete')
    r.check_hashes(report['input_sha256'])
    manifest = r.read(base / 'input_manifest.json')
    r.check_hashes(manifest['input_sha256'])
    qualification = r.read(HERE / 'qualification.json')
    r.protocol.require(qualification['passed'] and qualification['exit_code'] == 0, 'reviewer not qualified')
    r.check_hashes(qualification['source_sha256'])
    r.protocol.require(r.sha(HERE / 'tests.xml') == qualification['xml_sha256'], 'review test XML changed')
    finish_qualification = r.read(HERE / 'finish_qualification_v2.json')
    r.protocol.require(finish_qualification['passed'] and finish_qualification['exit_code'] == 0,
                       'finisher not qualified')
    r.check_hashes(finish_qualification['source_sha256'])
    r.protocol.require(r.sha(HERE / 'finish_tests_v2.xml') == finish_qualification['xml_sha256'],
                       'finish test XML changed')
    decision = r.read(HERE / 'research_decision.json')
    validate_decision(decision, r.sha(path), r.sha(base / 'result_summary.md'))
    stats = report['statistics']
    r.protocol.require(set(stats['arms']) == set(r.protocol.ARMS) and
        set(stats['half_minus_full_by_seed']) == {'1', '3'} and
        all(a['hands'] == 20000 and a['sessions'] == 8 for a in stats['arms'].values()),
        'four complete frozen policies and both contrasts required')

    logger = [sys.executable, str(root / 'research/experiment_log.py')]
    commands = [qualification['outer_argv'], qualification['pytest_argv'],
        finish_qualification['outer_argv'], finish_qualification['pytest_argv'],
        report['current_review_command'], [sys.executable, *sys.orig_argv[1:]]]
    existing = {row['command'] for row in record['commands']}
    argv = logger + ['update', base.name]
    for command in commands:
        exact = subprocess.list2cmdline(command)
        if exact not in existing:
            argv += ['--command', exact]
            existing.add(exact)
    subprocess.run(argv, cwd=root, check=True)
    artifacts = [path, base / 'result_summary.md', base / 'controller.stdout.log', base / 'controller.stderr.log']
    artifacts += [p for p in HERE.iterdir() if p.is_file()]
    batch, chars = [], 0
    for artifact in artifacts:
        if chars + len(str(artifact)) + 16 > 24000:
            subprocess.run(logger + ['update', base.name, *batch], cwd=root, check=True)
            batch, chars = [], 0
        batch += ['--artifact', str(artifact)]
        chars += len(str(artifact)) + 16
    if batch:
        subprocess.run(logger + ['update', base.name, *batch], cwd=root, check=True)
    metrics = {'independent_post_terminal_review_passed': True, 'goal_achieved': False,
        'execution_wall_seconds': report['execution_wall_seconds'],
        'decision_replays': report['current_decision_replays'],
        'frozen_input_hashes_rechecked': report['frozen_input_hashes_rechecked'],
        'automatic_scale_or_final_test': False, 'controller_phase': 'COMPLETED_REVIEWED'}
    for arm, values in stats['arms'].items():
        metrics[arm + '_bb100'] = values['bb_per_100']
        metrics[arm + '_raw_ci95'] = values['raw_hand_ci95']
        metrics[arm + '_session_t7'] = values['session_t7']
    for seed, values in stats['half_minus_full_by_seed'].items():
        metrics['seed' + seed + '_half_minus_full'] = values['independent_raw_hands']
    argv = logger + ['finish', base.name, '--status', 'COMPLETED',
        '--count', 'new_training_hands=0', '--count', 'evaluation_hands=80000',
        '--count', 'slumbot_hands=80000', '--count', 'final_qualification_hands=0']
    for key, value in metrics.items():
        argv += ['--metric', key + '=' + json.dumps(value, separators=(',', ':'))]
    for field, flag in [('summary', '--summary'), ('conclusion', '--conclusion'),
                        ('decision', '--decision'), ('next_step', '--next-step')]:
        argv += [flag, decision[field]]
    argv += ['--note', 'All41 jobs and exact OS identities terminal before independent raw review and sole-writer finish. Four distinct frozen policies at20000 hands each;80k is development only. Resume evidence and frozen training source retained. Source-bound offline qualification and exact observed analysis commands attached; no inference from zero warnings alone.']
    subprocess.run(argv, cwd=root, check=True)
    audit = base / 'post_finish_audit.json'
    subprocess.run(audit_command(logger, record, audit), cwd=root, check=True)
    subprocess.run(logger + ['update', base.name, '--artifact', str(audit)], cwd=root, check=True)
    print(json.dumps({'status': 'COMPLETED', 'audit_warning_count': r.read(audit)['warning_count'],
                      'goal_achieved': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-ready', action='store_true')
    args = parser.parse_args()
    if args.check_ready:
        print(json.dumps(review.readiness()))
    else:
        finish()
