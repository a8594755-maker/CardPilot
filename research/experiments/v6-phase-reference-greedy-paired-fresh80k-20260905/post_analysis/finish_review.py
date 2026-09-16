"""Finish the completed fixed80k record via its logger after sole-owner exit."""
from pathlib import Path
import json
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_completed as review


def main():
    r, base, root = review.r, review.BASE, review.ROOT
    r.protocol.require(review.readiness()['ready'], 'owner or evidence not ready')
    record = r.read(base / 'experiment.json')
    r.protocol.require(record['status'] == 'RUNNING', 'not the same RUNNING experiment')
    path = base / 'post_terminal_review.json'
    r.protocol.require(r.sha(path) == '0ca3eff30cd967690d6099f2e7a36e4095a822953b6a1236c32800c53dd54d05',
        'review report changed')
    report = r.read(path)
    r.protocol.require(report['passed'] and report['evaluation_hands'] == 80000, 'review incomplete')
    r.check_hashes(report['input_sha256'])
    logger = [sys.executable, str(root / 'research/experiment_log.py')]
    rel = base.relative_to(root).as_posix()
    commands = [
        f'python -B -m pytest -q {rel}/post_analysis/test_review_completed.py --junitxml={rel}/post_analysis/tests.xml',
        f'python -B {rel}/post_analysis/review_completed.py --check-ready',
        f'python -B {rel}/post_analysis/review_completed.py --out {rel}/post_terminal_review.json',
        f'python -B {rel}/post_analysis/finish_review.py',
    ]
    existing = {row['command'] for row in record['commands']}
    argv = logger + ['update', base.name]
    for command in commands:
        if command not in existing:
            argv += ['--command', command]
    for artifact in (path, Path(__file__), base / 'result_summary.md',
        base / 'post_analysis/review_completed.py', base / 'post_analysis/test_review_completed.py',
        base / 'post_analysis/tests.xml', base / 'post_analysis/README.md'):
        argv += ['--artifact', str(artifact)]
    subprocess.run(argv, cwd=root, check=True)
    stats = report['statistics']
    metrics = {'independent_post_terminal_review_passed': True,
        'execution_wall_seconds': report['execution_wall_seconds'], 'goal_achieved': False,
        'static_bb100': stats['arms']['static']['bb_per_100'],
        'moving_bb100': stats['arms']['moving256']['bb_per_100'],
        'moving_minus_static_bb100': stats['moving_minus_static']['independent_raw_hands']['ordinary']['bb_per_100'],
        'moving_minus_static_ci95': stats['moving_minus_static']['independent_raw_hands']['ordinary']['ci'],
        'decision_replays': 247474, 'independent_training_seed_replication': False}
    argv = logger + ['finish', base.name, '--status', 'COMPLETED',
        '--count', 'new_training_hands=0', '--count', 'evaluation_hands=80000',
        '--count', 'slumbot_hands=80000', '--count', 'final_qualification_hands=0']
    for key, value in metrics.items():
        argv += ['--metric', key + '=' + json.dumps(value, separators=(',', ':'))]
    argv += ['--summary', 'Both fixed40k endpoints completed with full evidence:static -19.8721bb/100 CI[-34.8451,-4.8991];moving -29.4744 CI[-46.5176,-12.4312]. Moving-minus-static -9.6023 CI[-32.2884,13.0838],unresolved;no qualification.',
        '--conclusion', 'All32 sessions,247474 decision replays,per-arm independence,cross-arm/prior tokens and independent raw reaggregation passed. No confirmed stronger or profitable policy;internal/external point signs differ without a resolved method reversal. Retain all four waves and historical uncertainty.',
        '--decision', 'PREREGISTER_UNAFFECTED_SEED3_SAME_DOSE_REFERENCE_REPLICATION',
        '--next-step', 'Verify unaffected original Seed3 4M parent and qualify a matched static-versus-phase-held two-stage continuation at the same approximately8M endpoint dose. No automatic16M or final100k;do not extend this completed external cohort.',
        '--note', 'All controller/child identities terminal before sole-writer finish. Deferred review source/tests and actual commands attached;6 preparation tests passed and final independent report passed with zero added hands. Execution wall3004.625s excludes subsequent final artifact-index writes;logger wall includes full record lifetime. The prepared finish source is not a new research experiment.']
    subprocess.run(argv, cwd=root, check=True)


if __name__ == '__main__':
    main()
