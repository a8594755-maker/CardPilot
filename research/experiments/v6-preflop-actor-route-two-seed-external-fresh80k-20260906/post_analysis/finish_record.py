"""Close the completed fixed80k record once; never rerun poker or prior reviews."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import compare_parent_transfer as comparison

r = comparison.r
BASE, ROOT, HERE = comparison.BASE, comparison.ROOT, comparison.HERE
ID = BASE.name
CHECK = HERE / 'closure_preflight.json'
AUDIT = BASE / 'post_finish_audit.json'
DECISION = json.loads("{\"summary\":\"Fixed four-policy fresh80k completed: Seed1 detached -34.0751, connected -13.6833; Seed3 detached -18.3084, connected -33.2342 bb/100. All41 jobs exit0; 248457 decision replays and independent evidence review passed.\",\"conclusion\":\"Connected-minus-detached +20.3918 / -14.9258 across seeds, both ordinary/family-adjusted contrast intervals include0. No replicated benefit or winning endpoint; Seed3 connected lost in all8 sessions. Historical-parent comparisons are exploratory. Preserve offline native-loader failure and prose/executable session-prefix deviation.\",\"decision\":\"No policy promotion or final qualification. Treat transfer gain as unconfirmed, not long-run mechanism disproof. Keep both seeds and connected family with detached control for one bounded unchanged-regimen1M-to2M scale-uncertainty experiment; no automatic larger allocation.\",\"next_step\":\"Preregister exact-state continuation of all four current final endpoints to2097152 post-split physical hands per branch, with new managed namespaces and unchanged optimizer/replay/configuration. One512-pairs-per-anchor four-anchor both-seat terminal check, then separate fixed external calibration of all four2M endpoints before any additional scale; no cherry-picking.\"}")


def exact(argv):
    return subprocess.list2cmdline([str(x) for x in argv])


def require(value, message):
    r.protocol.require(value, message)


def plan():
    require(Path.cwd().resolve() == ROOT, 'wrong workspace')
    comparison.terminal_guard()
    record = r.read(BASE / 'experiment.json')
    require(record['status'] == 'RUNNING' and not AUDIT.exists(), 'preserve terminal record/audit')
    review = r.read(BASE / 'post_terminal_review.json')
    parents = r.read(HERE / 'parent_transfer_comparison.json')
    require(review['passed'] and parents['passed'], 'reviews incomplete')
    require(review['evaluation_hands'] == review['slumbot_hands'] == 80000, 'wrong fixed dose')
    require(review['new_training_hands'] == review['final_qualification_hands'] == 0, 'wrong scope')
    require(review['current_decision_replays'] == 248457, 'replay coverage changed')
    hashes = dict(review['input_sha256'])
    for path, digest in parents['input_sha256'].items():
        require(path not in hashes or hashes[path] == digest, 'conflicting frozen hashes')
        hashes[path] = digest
    r.check_hashes(hashes)
    fq = r.read(HERE / 'followthrough_qualification.json')
    pq = r.read(HERE / 'parent_transfer_qualification.json')
    follow = r.read(HERE / 'followthrough_execution.json')
    require(fq['passed'] and pq['passed'], 'deferred qualification incomplete')
    commands = [exact(fq['outer_argv']), exact(fq['pytest_argv']),
                exact(pq['command']), exact(pq['pytest_argv']),
                exact(follow['command']), exact(follow['review_child']['command']),
                exact(review['current_review_command']), exact(parents['command']),
                f'powershell -NoProfile -ExecutionPolicy Bypass -File research/experiments/{ID}/post_analysis/launch_followthrough.ps1']
    artifacts = {p.resolve() for p in HERE.iterdir() if p.is_file()}
    for name in ('post_terminal_review.json', 'result_summary.md', 'controller.stdout.log',
                 'controller.stderr.log'):
        path = BASE / name
        if path.exists():
            artifacts.add(path.resolve())
    # Actual launcher log spellings are bound rather than guessed.
    artifacts.update(p.resolve() for p in BASE.glob('controller*') if p.is_file())
    counts = {'new_training_hands': 0, 'evaluation_hands': 80000, 'slumbot_hands': 80000,
              'final_qualification_hands': 0, 'lineage_training_hands': 11551174}
    metrics = {'terminal_review_passed': True, 'current_decision_replays': 248457,
               'frozen_input_hashes_rechecked': review['frozen_input_hashes_rechecked'],
               'controller_execution_wall_seconds': review['execution_wall_seconds'],
               'external_statistics': review['statistics'],
               'prose_executable_session_prefix_deviation': True,
               'offline_native_loader_failure_preserved': True,
               'historical_parent_comparison_exploratory': True,
               'goal_achieved': False}
    bindings = {str(p): r.sha(p) for p in (Path(__file__), BASE/'result_summary.md',
                BASE/'post_terminal_review.json', HERE/'parent_transfer_comparison.json',
                BASE/'experiment.json')}
    return {'counts': counts, 'metrics': metrics, 'commands': commands,
            'artifacts': sorted(str(p.relative_to(ROOT)).replace('\\', '/') for p in artifacts),
            'bindings': bindings, 'input_hashes_checked': len(hashes)}


def logger(args):
    argv = [sys.executable, '-B', str(ROOT/'research/experiment_log.py'), *args]
    require(len(exact(argv)) < 30000, 'Windows argv bound')
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    require(result.returncode == 0, result.stdout + result.stderr)
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    current = plan()
    if args.check:
        r.write_new(CHECK, {'passed': True, 'command': sys.orig_argv, 'plan': current})
        print(json.dumps({'passed': True, 'input_hashes_checked': current['input_hashes_checked'],
                          'logger_writes': 0, 'new_hands': 0}))
        return
    preview = r.read(CHECK)
    require(preview['passed'] and preview['plan']['bindings'] == current['bindings'],
            'closure bindings changed after preflight')
    record = r.read(BASE/'experiment.json')
    seen = {x['command'] for x in record['commands']}
    commands = list(dict.fromkeys([*current['commands'], exact(preview['command']), exact(sys.orig_argv)]))
    old_artifacts = {Path(p).resolve() for p in record['artifacts']}
    artifacts = [*current['artifacts'], str(CHECK.relative_to(ROOT)).replace('\\', '/')]
    payload = []
    for flag, values in (('--count', current['counts']), ('--metric', current['metrics'])):
        for key, value in values.items():
            payload += [flag, key + '=' + json.dumps(value, separators=(',', ':'), allow_nan=False)]
    for command in commands:
        if command not in seen:
            payload += ['--command', command]
    for artifact in dict.fromkeys(artifacts):
        if (ROOT/artifact).resolve() not in old_artifacts:
            payload += ['--artifact', artifact]
    payload += ['--note', 'Terminal fixed80k and independent review completed. Deferred actual commands and terminal logs attached. Native-loader preflight failure remains preserved; corrected actual bridge parity passed without poker. Human session-prefix prose differs from the executable schedule fixed before requests; all32 actual IDs/seeds and evidence are unchanged, as disclosed outcome-blind. Parent fixture tests retain one SciPy constant-data warning. lineage_training_hands is maximum inherited single lineage, not new training or a branch sum. No completed test, review, training or evaluation rerun for closure. Logger wall includes analysis, status discussion and waiting; controller wall is narrower.']
    while payload:
        chunk = []
        while payload and len(exact([sys.executable, ROOT/'research/experiment_log.py',
                                     'update', ID, *chunk, *payload[:2]])) < 24000:
            chunk += payload[:2]
            del payload[:2]
        require(chunk, 'single logger item exceeds bound')
        logger(['update', ID, *chunk])
    logger(['finish', ID, '--summary', DECISION['summary'], '--conclusion', DECISION['conclusion'],
            '--decision', DECISION['decision'], '--next-step', DECISION['next_step']])
    final = r.read(BASE/'experiment.json')
    require(final['status'] == 'COMPLETED' and final['ended_at'], 'finish failed')
    require(all(final['accounting'][k] == v for k,v in current['counts'].items()), 'count mismatch')
    audit_args = ['audit', '--since', final['created_at'], '--out-json', str(AUDIT), '--fail-on-warning']
    first = logger(audit_args)
    logger(['update', ID, '--artifact', str(AUDIT.relative_to(ROOT)).replace('\\', '/'),
            '--command', exact([sys.executable, '-B', ROOT/'research/experiment_log.py', *audit_args])])
    last = logger(['audit', '--since', final['created_at'], '--fail-on-warning'])
    print(json.dumps({'passed': True, 'status': 'COMPLETED', 'audit': first,
                      'attachment_audit': last, 'new_hands': 0}))


if __name__ == '__main__':
    main()

