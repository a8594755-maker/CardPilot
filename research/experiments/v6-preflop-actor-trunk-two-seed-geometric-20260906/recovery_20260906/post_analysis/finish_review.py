"""One-shot same-record research closure; no poker execution or source mutation."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import recovery_chain as chain

HERE = Path(__file__).resolve().parent
RECOVERY = HERE.parent
BASE = RECOVERY.parent
ROOT = BASE.parents[2]
ID = BASE.name
CHECK = HERE / 'finish_preflight.json'
AUDIT = RECOVERY / 'final_record_audit.json'
READ, SHA, REQUIRE = chain.read, chain.sha, chain.require
PYTHON = sys.executable
LOGGER = ROOT / 'research/experiment_log.py'

SUMMARY = ('Completed 4,203,389 retained new physical training hands across four '
           'two-seed actor-route branches and 262,144 internal executions. Final '
           'connected-minus-detached: Seed1 +9.0001, Seed3 +3.8766 bb/100; both '
           'nominal paired-deck 95% intervals cross zero. Recovery-aware review passed.')
CONCLUSION = ('Mechanically valid with an unconfirmed relative-benefit signal, not '
              'replicated general improvement: connected versus original parent is '
              '-12.8671 / +17.0123; connected 262k-to-1M parent-relative slopes are '
              '-6.6499 / +2.9484. No severe broad-collapse gate, no external strength '
              'or final-qualification claim. Unknown interrupted worker tail remains null.')
DECISION = ('Retain the connected family and detached control without promoting either '
            'or declaring long-run learning invalid. Calibrate all four final endpoints '
            'externally before allocating more training; do not cherry-pick Seed3.')
NEXT = ('Preregister a fixed four-policy external development calibration, 20,000 '
        'fresh Slumbot hands each, balanced cohorts and audited independent sessions. '
        'Freeze full execution contracts; no new algorithmic arm, labels, final100k '
        'or automatic paper-scale allocation. Use calibration, uncertainty and cost '
        'to choose the next geometric training allocation.')


def exact(argv):
    return subprocess.list2cmdline([str(x) for x in argv])


def closure_plan():
    REQUIRE(Path.cwd().resolve() == ROOT, 'run from recorded workspace cwd')
    chain.terminal_guard(BASE)
    record = READ(BASE / 'experiment.json')
    REQUIRE(record['status'] == 'RUNNING', 'preserve a terminal or unexpected record')
    REQUIRE(not AUDIT.exists(), 'preserve prior final audit before any logger writes')
    review_path = RECOVERY / 'post_terminal_review.json'
    curve_path = HERE / 'curve_comparison.json'
    report, curve = READ(review_path), READ(curve_path)
    REQUIRE(report['passed'] and curve['passed'], 'independent reviews incomplete')
    REQUIRE(report['all_recorded_processes_terminal'], 'jobs not terminal')
    REQUIRE(report['unknown_additional_worker_tail_hands'] is None, 'unknown tail erased')
    REQUIRE(report['unique_new_evaluation_decks'] == 32768, 'wrong evaluation coverage')
    REQUIRE(report['accounting']['new_training_hands'] == 4203389, 'unexpected retained dose')
    REQUIRE(report['accounting']['evaluation_hands'] == 262144, 'unexpected evaluation dose')
    hashes = chain.merge_hashes(report['input_sha256'], curve['input_sha256'])
    REQUIRE(all(SHA(p) == h for p, h in hashes.items()), 'review inputs changed')
    counts = {k: v for k, v in report['accounting'].items()
              if isinstance(v, int) and not isinstance(v, bool)}
    for key in ('new_training_hands', 'new_transition_hands', 'retained_training_hands',
                'retained_transition_hands', 'evaluation_hands', 'slumbot_hands',
                'final_qualification_hands'):
        REQUIRE(record['accounting'][key] == counts[key], 'controller accounting changed')

    metrics = {
        'terminal_review_passed': True, 'curve_review_passed': True,
        'unique_new_evaluation_decks': 32768,
        'prior_common_deck_rows_checked': report['prior_common_deck_rows_checked'],
        'observed_child_identities_checked': report['observed_child_identities_checked'],
        'unknown_additional_worker_tail_hands': None,
        'statistical_not_bitwise_worker_continuation': True,
        'no_external_strength_or_final_qualification_claim': True,
        'new_attempt_namespaces_count': len(report['new_attempt_namespaces']),
    }
    for key in ('completed_training_subprocess_wall_seconds', 'completed_all_job_wall_seconds',
                'interrupted_training_wall_seconds_bounds', 'training_subprocess_wall_seconds_bounds',
                'all_job_wall_seconds_bounds', 'retained_physical_hands_per_training_wall_second_bounds',
                'recovery_controller_wall_seconds'):
        metrics[key] = report[key]
    for seed in ('1', '3'):
        final = report['stages']['2'][seed]
        metrics[f'seed{seed}_final_connected_minus_detached'] = final['connected_minus_detached']['pooled']
        metrics[f'seed{seed}_final_endpoint_minus_parent'] = {
            a: v['pooled'] for a, v in final['endpoint_minus_parent'].items()}
        metrics[f'seed{seed}_connected_parent_relative_curve'] = curve['seeds'][seed][
            'endpoint_minus_original_parent_changes']['connected']['pooled']

    old_q = READ(BASE / 'post_analysis/qualification.json')
    new_q = READ(HERE / 'qualification.json')
    commands = [exact(old_q['command']), exact(new_q['command']), exact(new_q['tests_command']),
                exact(report['command']), exact(curve['command'])]
    commands += [exact(s['command']) for s in old_q['suites']]
    commands += [
        f'powershell -NoProfile -ExecutionPolicy Bypass -File research/experiments/{ID}/recovery_20260906/launch.ps1',
        f'python -B -m pytest -q -p no:cacheprovider research/experiments/{ID}/recovery_20260906/post_analysis/test_recovery_chain.py --junitxml=research/experiments/{ID}/recovery_20260906/post_analysis/recovery_chain_tests.xml',
    ]
    artifacts = {p.resolve() for folder in (HERE, BASE / 'post_analysis')
                 for p in folder.iterdir() if p.is_file()}
    artifacts.add(review_path)
    artifacts.add(RECOVERY / 'status.json')
    for folder in [*BASE.iterdir(), *RECOVERY.iterdir()]:
        if not folder.is_dir():
            continue
        for name in ('process.json', 'termination.json', 'parent_contract.json',
                     'prefixes.json', 'run_manifest.json'):
            p = folder / name
            if p.is_file():
                artifacts.add(p.resolve())
    REQUIRE(all(p.is_file() for p in artifacts), 'missing closure artifact')
    return {'counts': counts, 'metrics': metrics, 'commands': commands,
            'artifacts': sorted(str(p.relative_to(ROOT)).replace('\\', '/') for p in artifacts),
            'review_sha256': SHA(review_path), 'curve_sha256': SHA(curve_path),
            'analysis_sha256': SHA(HERE / 'research_conclusion.md'),
            'source_sha256': SHA(__file__), 'input_hashes_checked': len(hashes),
            'original_record_sha256': SHA(BASE / 'experiment.json')}


def run_logger(args):
    argv = [PYTHON, '-B', str(LOGGER), *args]
    REQUIRE(len(exact(argv)) < 30000, 'Windows command length exceeds safe bound')
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    REQUIRE(result.returncode == 0, result.stdout + result.stderr)
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    plan = closure_plan()
    if args.check:
        REQUIRE(not CHECK.exists(), 'preserve prior finish preflight')
        with CHECK.open('x', encoding='utf-8') as handle:
            json.dump({'passed': True, 'command': sys.orig_argv, 'plan': plan}, handle, indent=2)
        print(json.dumps({'passed': True, 'logger_writes': 0, 'new_poker_hands': 0,
                          'input_hashes_checked': plan['input_hashes_checked']}))
        return
    preview = READ(CHECK)
    REQUIRE(preview['passed'], 'missing preflight')
    for key in ('source_sha256', 'analysis_sha256', 'review_sha256', 'curve_sha256',
                'original_record_sha256'):
        REQUIRE(preview['plan'][key] == plan[key], f'preflight changed:{key}')
    record = READ(BASE / 'experiment.json')
    seen_commands = {x['command'] for x in record['commands']}
    commands = [*plan['commands'], exact(preview['command']), exact(sys.orig_argv)]
    new_commands = list(dict.fromkeys(c for c in commands if c not in seen_commands))
    existing = {Path(x).resolve() for x in record['artifacts']}
    artifacts = list(dict.fromkeys([*plan['artifacts'], str(CHECK.relative_to(ROOT)).replace('\\', '/')]))
    artifacts = [p for p in artifacts if (ROOT / p).resolve() not in existing]
    payload = []
    for flag, values in (('--count', plan['counts']), ('--metric', plan['metrics'])):
        for key, value in values.items():
            payload += [flag, key + '=' + json.dumps(value, separators=(',', ':'), allow_nan=False)]
    for command in new_commands:
        payload += ['--command', command]
    for artifact in artifacts:
        payload += ['--artifact', artifact]
    payload += ['--note', 'Terminal recovery-aware review and substantive analysis completed. '
                'Unknown interrupted worker tail remains null; counts are evidenced lower bounds. '
                'Original post_analysis reviewer and curve entry points were not executed. '
                'Deferred qualification commands/artifacts are now attached; nested original '
                'qualification test cwd values are recorded in post_analysis/qualification.json. '
                'No old tests, training or evaluation jobs were rerun for closure.']
    # Bound every OS command without dropping evidence from a long artifact list.
    while payload:
        chunk = []
        while payload and len(exact([PYTHON, '-B', LOGGER, 'update', ID, *chunk, *payload[:2]])) < 24000:
            chunk += payload[:2]
            del payload[:2]
        REQUIRE(chunk, 'unrepresentable logger argument')
        run_logger(['update', ID, *chunk])
    run_logger(['finish', ID, '--summary', SUMMARY, '--conclusion', CONCLUSION,
                '--decision', DECISION, '--next-step', NEXT])
    final = READ(BASE / 'experiment.json')
    REQUIRE(final['status'] == 'COMPLETED' and final['ended_at'], 'record not finished')
    REQUIRE(final['accounting']['wall_time_seconds'] is not None, 'missing logger wall time')
    REQUIRE(all(final['accounting'][k] == v for k, v in plan['counts'].items()), 'final count mismatch')
    audit = AUDIT
    REQUIRE(not audit.exists(), 'preserve prior final audit')
    audit_args = ['audit', '--since', final['created_at'], '--out-json', str(audit), '--fail-on-warning']
    audit_stdout = run_logger(audit_args)
    run_logger(['update', ID, '--artifact', str(audit.relative_to(ROOT)).replace('\\', '/'),
                '--command', exact([PYTHON, '-B', LOGGER, *audit_args])])
    # The attachment itself receives a fresh read-only audit; preserve its earlier report.
    final_audit_stdout = run_logger(['audit', '--since', final['created_at'], '--fail-on-warning'])
    print(json.dumps({'passed': True, 'status': READ(BASE / 'experiment.json')['status'],
                      'audit': audit_stdout, 'final_attachment_audit': final_audit_stdout,
                      'new_poker_hands': 0, 'next_experiment_started': False}))


if __name__ == '__main__':
    main()
