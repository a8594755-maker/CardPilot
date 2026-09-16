"""Qualify the second remainder and derive a byte-identical, separately named parent."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import resume_control_second as r
ctl, ev, HERE = r.ctl, r.ev, r.HERE


def main():
    r.require_dead()
    out = HERE / 'recovery_preflight.json'
    ev.require(not out.exists() and not r.VIEW.exists() and not r.RUN.exists(), 'preserve previous preparation')
    started = time.perf_counter()
    audit = ev.read_json(HERE / 'pending_checkpoint_audit.json')
    io = ev.read_json(HERE / 'io_grace_qualification.json')
    ev.require(audit['passed'] and io['passed'] and audit['candidate_sha256'] == r.CANDIDATE_SHA, 'unqualified candidate/I/O')
    ctl.check_hashes(audit['input_sha256'])
    ctl.check_hashes(io['input_sha256'])
    for arm in ('static', 'moving256'):
        for stage in (1, 2):
            for prefix in ('eval', 'job_eval', 'drift'):
                ev.require(not (r.BASE / f'{prefix}_{arm}_stage{stage}').exists(), 'evaluation already exists; do not redo')
    xml = HERE / 'second_recovery_tests.xml'
    ev.require(not xml.exists(), 'preserve prior test evidence')
    command = [sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
               str(HERE / 'test_second_recovery.py'), '--junitxml=' + str(xml)]
    tests = subprocess.run(command, cwd=ctl.ROOT, capture_output=True, text=True, encoding='utf-8', timeout=45)
    if tests.returncode:
        ctl.write_new(HERE / 'failed_second_recovery_tests.json', {'command': command, 'stdout': tests.stdout, 'stderr': tests.stderr})
        raise ValueError(tests.stdout + tests.stderr)
    suites = list(ET.parse(xml).getroot().iter('testsuite'))
    count = sum(int(s.get('tests', 0)) for s in suites)
    ev.require(count >= 10 and all(int(s.get(k, 0)) == 0 for s in suites for k in ('failures', 'errors', 'skipped')), 'missing tests')
    r.VIEW.mkdir()
    source = Path(audit['candidate_path'])
    shutil.copy2(source, r.VIEW / 'latest.pt')
    for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
        shutil.copy2(source.parent / name, r.VIEW / name)
    ev.require(ev.sha(r.VIEW / 'latest.pt') == r.CANDIDATE_SHA, 'derived candidate differs')
    derivation = {'source_path': str(source), 'source_sha256': r.CANDIDATE_SHA,
        'derived_checkpoint_sha256': r.CANDIDATE_SHA, 'candidate_iteration': 1215,
        'candidate_physical_hands': 5776996, 'full_raw_metrics_and_assignments_copied': True,
        'trimmed_or_discarded_rows': 0, 'original_published_and_pending_files_unchanged': True,
        'unpublished_update_hands_preserved_without_reexecution': 5256,
        'moving_reference_completed_updates': 335, 'moving_reference_round': 1,
        'unknown_additional_worker_tail_hands': None}
    ctl.write_new(r.VIEW / 'derivation.json', derivation)
    inputs = {**audit['input_sha256'], **io['input_sha256']}
    for path in [*HERE.glob('*.py'), *r.VIEW.iterdir(), HERE / 'recovery_amendment.md',
                 HERE / 'pending_checkpoint_audit.json', HERE / 'current_file_users.json',
                 HERE / 'io_grace_qualification.json', xml, HERE / 'launch.ps1']:
        inputs[str(path)] = ev.sha(path)
    ctl.check_hashes(inputs)
    result = {'schema': 'cardpilot.seed3.second_recovery_preflight.v1', 'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'command': [sys.executable, *sys.argv],
        'wall_seconds': time.perf_counter() - started, 'tests_command': command,
        'tests_exact_command': subprocess.list2cmdline(command), 'tests_stdout': tests.stdout,
        'tests_stderr': tests.stderr, 'tests': count, 'derivation': derivation,
        'remaining_stage1_hands': 515064, 'completed_static_stage1_reused': True,
        'algorithm_seeds_targets_and_eval_unchanged': True, 'input_sha256': inputs,
        'training_hands_added': 0, 'evaluation_hands_added': 0, 'training_started': False,
        'next_step': 'One hidden same-record second recovery launch with actual initial-state gate; no retries or completed work reruns.'}
    ctl.write_new(out, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'input_sha256'}, indent=2))


if __name__ == '__main__':
    main()
