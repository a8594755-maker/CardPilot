"""Finish only the fixed successful mechanical qualification via logger."""
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qualify as q


def main():
    base, root = q.BASE, q.ROOT
    record = q.json.loads((base / 'experiment.json').read_text(encoding='utf-8'))
    q.require(record['status'] == 'RUNNING', 'not same running record')
    report_path = base / 'qualification.json'
    q.require(q.sha(report_path) == 'afe2955b7a5fd1d257cf0dbd66a86d703f9023315034855e7449515f33fa028b', 'report changed')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    q.require(report['passed'] and report['new_training_hands'] == 0, 'qualification failed')
    q.require(all(q.sha(Path(path)) == digest for path, digest in report['input_sha256'].items()), 'input changed')
    for row in report['parents'].values():
        q.require(q.sha(Path(row['derived'])) == row['derived_sha256'], 'derived changed')
    logger = [sys.executable, str(root / 'research/experiment_log.py')]
    argv = logger + ['finish', base.name, '--status', 'COMPLETED', '--command',
        f'python -B {base.relative_to(root).as_posix()}/finish_record.py',
        '--count', 'new_training_hands=0', '--count', 'evaluation_hands=0', '--count', 'slumbot_hands=0',
        '--count', 'final_qualification_hands=0', '--metric', 'actual_parent_qualification_passed=true',
        '--metric', 'synthetic_update_fixtures=2', '--metric', 'goal_achieved=false',
        '--summary', 'Both current full endpoints passed24 tests and two actual serialized-model same-gradient fixtures: all86 Adam states retained,only actual LR halved,zero poker hands.',
        '--conclusion', 'The half-rate transformation preserves all non-LR checkpoint state; fixture Adam moments are bitwise identical and displacement ratio is0.5000002. This proves transfer mechanics,not PPO dose,worker replay or strength.',
        '--decision', 'ADMIT_SEPARATE_TWO_SEED_FULL_RATE_VERSUS_HALF_RATE_CONTINUATION',
        '--next-step', 'Preregister matched262k-to1M additional physical hands per arm/seed from both current full endpoints. Preserve all optimizer/replay/counters and use exact initial-state audits,fresh managed attempts,unchanged four-anchor/both-seat evaluations. No automatic larger scale or final Slumbot test.']
    for path in (report_path, Path(__file__), base / 'result_summary.md', base / 'derived/seed1_half.pt', base / 'derived/seed3_half.pt'):
        argv += ['--artifact', str(path)]
    subprocess.run(argv, cwd=root, check=True)
    audit_path = base / 'post_finish_audit.json'
    q.require(not audit_path.exists(), 'preserve audit')
    audit = logger + ['audit', '--since', record['created_at'], '--out-json', str(audit_path), '--fail-on-warning']
    subprocess.run(audit, cwd=root, check=True)
    subprocess.run(logger + ['update', base.name, '--artifact', str(audit_path), '--command', subprocess.list2cmdline(audit),
                            '--note', 'Scoped post-finish audit passed with zero warnings.'], cwd=root, check=True)


if __name__ == '__main__':
    main()
