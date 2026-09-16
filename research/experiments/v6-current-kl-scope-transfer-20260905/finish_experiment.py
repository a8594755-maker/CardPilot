"""Close the qualified scope-transfer prerequisite through the experiment logger."""
from pathlib import Path
import json
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inspect_parents as p


def main():
    base, root = p.BASE, p.ROOT
    record = json.loads((base / 'experiment.json').read_text(encoding='utf-8'))
    p.require(record['status'] == 'RUNNING', 'not the same RUNNING record')
    path = base / 'real_parent_qualification.json'
    p.require(p.sha(path) == 'c35191054e22401c207f3384b851b7c9f5c790500cf8ebdaead12dd0dadebd92', 'qualification changed')
    report = json.loads(path.read_text(encoding='utf-8'))
    p.require(report['passed'] and report['new_training_hands'] == report['slumbot_hands'] == 0, 'not qualified')
    p.require(all(p.sha(Path(name)) == digest for name, digest in report['input_sha256'].items()), 'qualification input changed')
    for row in report['parents'].values():
        p.require(p.sha(Path(row['derived'])) == row['derived_sha256'], 'derived artifact changed')
    logger = [sys.executable, str(root / 'research/experiment_log.py')]
    argv = logger + ['finish', base.name, '--status', 'COMPLETED',
        '--command', f'python -B {base.relative_to(root).as_posix()}/finish_experiment.py',
        '--count', 'new_training_hands=0', '--count', 'evaluation_hands=0', '--count', 'slumbot_hands=0',
        '--count', 'offline_samples=0', '--metric', 'actual_parent_qualification_passed=true',
        '--metric', 'synthetic_paired_update_fixtures=2', '--metric', 'preserved_adam_states_per_parent=10',
        '--metric', 'new_representation_tensors_per_parent=76', '--metric', 'goal_achieved=false']
    for artifact in (path, Path(__file__), base / 'result_summary.md', base / 'scope_tests.xml',
        base / 'derived/seed1_full.pt', base / 'derived/seed3_full.pt'):
        argv += ['--artifact', str(artifact)]
    argv += ['--summary', 'Both static8M parents passed named Adam scope expansion:10 existing states retained,76 new representation tensors initialize only on first gradient,all138 other checkpoint fields unchanged.25 tests and two actual serialized-parent/supplied-gradient fixtures passed;zero poker hands.',
        '--conclusion', 'Existing head parameters and Adam updates are bitwise equal to heads-only controls for identical supplied gradients;derived weights remain identical to original parents. This qualifies scope-transfer mechanics only,not rollout continuation,CUDA equivalence or strength.',
        '--decision', 'ADMIT_PREREGISTERED_MATCHED_CURRENT_REGIMEN_REPRESENTATION_PILOT',
        '--next-step', 'Preregister a geometric two-seed full-representation versus heads-only continuation from both static8M parents. Bind current static Standard10 KL reference,unchanged poker contracts,effective LR and full initial state;use fresh managed namespaces and actual trainer initial-state audit before counting new hands. No automatic16M or Slumbot final test.',
        '--note', 'Original source/checkpoint hashes rechecked unchanged. Unstepped derived copies and exact commands are preserved;synthetic updated models were disposable and not saved. Existing experiment code/dirty patch and all later source/test artifact hashes remain available.']
    subprocess.run(argv, cwd=root, check=True)
    audit_path = base / 'post_finish_audit.json'
    p.require(not audit_path.exists(), 'preserve earlier audit')
    audit = logger + ['audit', '--since', record['created_at'], '--out-json', str(audit_path), '--fail-on-warning']
    subprocess.run(audit, cwd=root, check=True)
    subprocess.run(logger + ['update', base.name, '--artifact', str(audit_path), '--command', subprocess.list2cmdline(audit),
        '--note', 'Post-finish scoped logger audit completed with no warnings.'], cwd=root, check=True)


if __name__ == '__main__':
    main()
