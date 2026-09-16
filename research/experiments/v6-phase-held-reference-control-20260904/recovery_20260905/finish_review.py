"""Close this completed experiment through its logger, without executing poker."""
from pathlib import Path
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(HERE))
import final_analysis as analysis


def main():
    report_path = HERE / 'post_terminal_report.json'
    record = analysis.ev.read_json(BASE / 'experiment.json')
    analysis.ev.require(record['status'] == 'RUNNING', 'not the same RUNNING record')
    analysis.ev.require(analysis.readiness()['ready'], 'controller still owns record')
    analysis.ev.require(analysis.ctl.sha(report_path) ==
        '461a74b29504eb70d7156f61f2f3b693d4c6a6cb609ccc213a3bd28ade0a65c9', 'report changed')
    report = analysis.ev.read_json(report_path)
    analysis.ev.require(report['passed'] and not report['goal_achieved'], 'wrong report')
    analysis.ctl.check_hashes(report['input_sha256'])
    analysis.ctl.check_hashes(report['source_sha256'])

    # Only immutable completed outputs/preparation sources, never experiment.json.
    artifacts = {report_path, BASE / 'result_summary.md', Path(__file__),
        ROOT / 'research/decision_notes/phase-held-external-readiness-20260905.md'}
    artifacts.update(Path(path) for path in report['input_sha256'])
    for folder in (BASE / 'post_analysis', HERE, HERE / 'external_preparation'):
        for pattern in ('*.py', '*.md', '*.xml'):
            artifacts.update(folder.glob(pattern))
    existing = {(ROOT / path).resolve() for path in record['artifacts']}
    additions = sorted(str(path.resolve()) for path in artifacts if path.resolve() not in existing)
    analysis.ev.require(all(Path(path).is_file() for path in additions), 'artifact missing')
    logger = [sys.executable, str(ROOT / 'research/experiment_log.py')]
    for offset in range(0, len(additions), 12):
        argv = logger + ['update', BASE.name]
        for path in additions[offset:offset + 12]:
            argv += ['--artifact', path]
        subprocess.run(argv, cwd=ROOT, check=True)

    relative = BASE.relative_to(ROOT).as_posix()
    post = relative + '/post_analysis'
    recovery = relative + '/recovery_20260905'
    prep = recovery + '/external_preparation'
    commands = [
        f'python -m pytest -q {post}/test_geometric_summary.py --junitxml={post}/tests.xml',
        f'python -m py_compile {post}/summarize_geometric_control.py',
        f'python {post}/summarize_geometric_control.py --check-ready',
        f'python {post}/review_stage1_resume.py --out {post}/stage1_resume_review.json',
        f'python -B -m pytest -q {recovery}/test_final_analysis.py --junitxml={recovery}/final_analysis_tests.xml',
        f'python -B {recovery}/final_analysis.py --check-ready',
        f'python -B {recovery}/final_analysis.py --out {recovery}/post_terminal_report.json',
        f'python -B -m pytest -q {prep}/test_pair_protocol.py --junitxml={prep}/tests.xml',
        f'python -B {recovery}/finish_review.py',
    ]
    for output in ('runner_tests.xml', 'runner_tests_v2.xml', 'runner_tests_v3.xml', 'runner_tests_final.xml'):
        commands.append(f'python -B -m pytest -q {prep}/test_run_pair.py {prep}/test_pair_protocol.py --junitxml={prep}/{output}')
    existing_commands = {item['command'] for item in record['commands']}
    for command in commands:
        if command not in existing_commands:
            subprocess.run(logger + ['update', BASE.name, '--command', command], cwd=ROOT, check=True)

    counts = report['accounting']
    counts['lineage_training_hands'] = counts['largest_single_endpoint_local_lineage_hands']
    argv = logger + ['finish', BASE.name, '--status', 'COMPLETED']
    for key, value in counts.items():
        argv += ['--count', key + '=' + json.dumps(value, separators=(',', ':'))]
    for key, value in {'independent_final_report_passed': True, 'goal_achieved': False,
            'external_preparation_tests_passed': 45, 'external_preparation_added_hands': 0,
            'final_static_delta_bb100': -7.440185546875,
            'final_moving_delta_bb100': 7.5068359375,
            'final_moving_minus_static_bb100': 14.947021484375,
            'final_moving_minus_static_ci95_low': -5.294534019798189,
            'final_moving_minus_static_ci95_high': 35.188576988548185}.items():
        argv += ['--metric', key + '=' + json.dumps(value)]
    argv += ['--summary', 'Both frozen approximately8.395M endpoints completed;8394971 new retained training hands,131072 internal hands,80000 drift states,0 Slumbot. Static-minus4M -7.44;phase-held +7.51;paired difference +14.95 CI[-5.29,35.19],unresolved.',
        '--conclusion', 'Valid single-seed matched-initialization control with statistical resume and unknown interrupted suffix preserved. No demonstrated stable winning policy or continued positive moving-reference slope. Intervals are nominal conditional internal diagnostics.',
        '--decision', 'PREREGISTER_BOTH_ENDPOINT_EXTERNAL_DEVELOPMENT_COMPARISON',
        '--next-step', 'Separately preregister and qualify fixed40k fresh Slumbot hands per final endpoint;no internal-rank selection,no automatic16M or final100k. Use external alignment and uncertainty to decide independent Seed3 replication.',
        '--note', 'Final review occurs after both controller owners exited. Deferred post-analysis and external-preparation sources/tests/actual commands are now attached. External preparation used synthetic fixtures, zero poker hands;no external record or launch yet. Original interrupted static_stage2 outputs remain unchanged; unknown crash suffix is null. lineage_training_hands denotes the largest single endpoint local lineage, not the two-arm union or unknown pretraining exposure. Historical command recording is provenance, not permission to rerun overwrite-protected completed outputs.']
    subprocess.run(argv, cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
