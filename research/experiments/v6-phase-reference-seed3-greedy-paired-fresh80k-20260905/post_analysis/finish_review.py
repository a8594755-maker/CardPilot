"""Finish the same Seed3 fixed80k record after qualified independent review."""
from pathlib import Path
import json
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_completed as review

REPORT_SHA = '9493ac2ec242d6e619e846f9a70851861552d2a5347f5dc16cc73f06e6738036'


def main():
    r, base, root = review.r, review.BASE, review.ROOT
    r.protocol.require(review.readiness()['ready'], 'owner or evidence not ready')
    record = r.read(base / 'experiment.json')
    r.protocol.require(record['status'] == 'RUNNING', 'not the same RUNNING experiment')
    path = base / 'post_terminal_review.json'
    r.protocol.require(r.sha(path) == REPORT_SHA, 'review report changed')
    report = r.read(path)
    r.protocol.require(report['passed'] and report['evaluation_hands'] == 80000 and
        report['current_decision_replays'] == 246789 and report['final_qualification_hands'] == 0,
        'review incomplete')
    r.check_hashes(report['input_sha256'])
    qualification = r.read(base / 'post_analysis/qualification.json')
    r.protocol.require(qualification['passed'] and qualification['exit_code'] == 0,
        'reviewer not qualified')
    r.check_hashes(qualification['source_sha256'])
    r.protocol.require(r.sha(base / 'post_analysis/tests.xml') == qualification['xml_sha256'],
        'qualification XML changed')
    logger = [sys.executable, str(root / 'research/experiment_log.py')]
    relative = base.relative_to(root).as_posix()
    commands = [
        f'python -B {relative}/post_analysis/qualify_review.py',
        subprocess.list2cmdline(qualification['pytest_argv']),
        f'python -B {relative}/post_analysis/review_completed.py --check-ready',
        f'python -B {relative}/post_analysis/review_completed.py --out {relative}/post_terminal_review.json',
        f'python -B {relative}/post_analysis/finish_review.py',
    ]
    existing = {row['command'] for row in record['commands']}
    argv = logger + ['update', base.name]
    for command in commands:
        if command not in existing:
            argv += ['--command', command]
    artifacts = [path, base / 'result_summary.md', *sorted((base / 'post_analysis').glob('*.py')),
        base / 'post_analysis/qualification.json', base / 'post_analysis/tests.xml', base / 'post_analysis/README.md']
    for artifact in artifacts:
        argv += ['--artifact', str(artifact)]
    subprocess.run(argv, cwd=root, check=True)
    stats = report['statistics']
    combined = report['exploratory_two_seed_synthesis']['conditional_equal_seed_sampling_intervals']['raw_hands']
    metrics = {'independent_post_terminal_review_passed': True,
        'execution_wall_seconds': report['execution_wall_seconds'], 'goal_achieved': False,
        'static_bb100': stats['arms']['static']['bb_per_100'],
        'moving_bb100': stats['arms']['moving256']['bb_per_100'],
        'moving_minus_static_bb100': stats['moving_minus_static']['independent_raw_hands']['ordinary']['bb_per_100'],
        'moving_minus_static_ci95': stats['moving_minus_static']['independent_raw_hands']['ordinary']['ci'],
        'exploratory_equal_seed_external_contrast': combined['moving_minus_static']['nominal'],
        'decision_replays': report['current_decision_replays'],
        'frozen_input_hashes_rechecked': report['frozen_input_hashes_rechecked'],
        'automatic_16m_or_final_test': False, 'controller_phase': 'COMPLETED_REVIEWED'}
    argv = logger + ['finish', base.name, '--status', 'COMPLETED',
        '--count', 'new_training_hands=0', '--count', 'evaluation_hands=80000',
        '--count', 'slumbot_hands=80000', '--count', 'final_qualification_hands=0']
    for key, value in metrics.items():
        argv += ['--metric', key + '=' + json.dumps(value, separators=(',', ':'))]
    argv += ['--summary', 'Both Seed3 fixed40k policies completed:static -25.68955bb/100 CI[-40.38771,-10.99139];moving -40.73755 CI[-57.75896,-23.71614]. Independent246789-decision evidence review passed;no qualification.',
        '--conclusion', 'Two-seed external moving-minus-static point is-12.32515 CI[-28.29702,3.64672],exploratory and unresolved. Both seeds have negative external method points despite positive internal points. No profitable policy or support for automatic16M;not a rejection of long-run learning for insufficient scale.',
        '--decision', 'PREREGISTER_CURRENT_REGIMEN_REPRESENTATION_SCOPE_CONTROL_NO_AUTOMATIC_16M',
        '--next-step', 'Qualify named-state scope expansion from both static8M parents,preserving existing Adam,replay,counters and RNG with fresh attempt identities. Then run a preregistered geometric matched representation-learning versus heads-only control under the current corrected bridge/current-KL regimen;retain older full-network and temperature negatives and use broad multi-seed evidence for scaling.',
        '--note', 'All37 jobs exited0 and exact OS identities were terminal before independent review and sole-writer finish.26 offline review tests passed without current outcome access;deferred exact commands and source hashes attached.5298.625s is execution wall,not full experiment lifetime;post-terminal elapsed time is not credited as training or poker execution. All four policies across Seed1/Seed3 remain distinct;combined160k is development analysis only.']
    subprocess.run(argv, cwd=root, check=True)


if __name__ == '__main__':
    main()
