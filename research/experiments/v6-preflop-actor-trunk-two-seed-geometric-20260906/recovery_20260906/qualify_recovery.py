"""Qualify scheduling/accounting for the retained checkpoint; adds no poker hands."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import resume_actor as r


def main():
    r.audit.require_dead()
    out = r.HERE / 'recovery_preflight.json'
    xml = r.HERE / 'recovery_tests.xml'
    r.require(not out.exists() and not xml.exists() and not r.RUN.exists(), 'preserve prior qualification')
    audit = r.read(r.HERE / 'interruption_audit.json')
    r.require(audit['passed'] and audit['checkpoint_sha256'] == r.SAVED_SHA, 'wrong retained checkpoint')
    r.require(audit['metric_rows'] == 2217 and audit['assignment_rows'] == 2218 and
              audit['assignment_replay']['pending_assignments'] is not None, 'pending evidence changed')
    r.require(audit['observed_completed_but_uncheckpointed_physical_hands'] == 0 and
              audit['observed_completed_but_uncheckpointed_transition_hands'] == 0, 'unexpected unsaved suffix')
    r.ctl.execution.check_hashes(audit['input_sha256'])
    command = [sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
               str(r.HERE / 'test_resume_actor.py'), '--junitxml=' + str(xml)]
    result = subprocess.run(command, cwd=r.ROOT, capture_output=True, text=True, encoding='utf-8', timeout=60)
    if result.returncode:
        r.ctl.write_new(r.HERE / 'failed_recovery_tests.json', {'command': command, 'stdout': result.stdout, 'stderr': result.stderr})
        raise ValueError(result.stdout + result.stderr)
    suites = list(ET.parse(xml).getroot().iter('testsuite'))
    count = sum(int(s.get('tests', '0')) for s in suites)
    r.require(count >= 18 and all(all(int(s.get(k, '0')) == 0 for k in ('failures', 'errors', 'skipped')) for s in suites),
              'missing recovery coverage')
    completed = r.read(r.BASE / 'seed1_detached_stage1/verification.json')
    r.ctl.execution.check_hashes(completed['checkpoint_windows_sha256'])
    files = [*r.HERE.glob('*.py'), r.HERE / 'interruption_audit.json', r.HERE / 'recovery_plan.md', r.HERE / 'launch.ps1', xml]
    files += [p for p in (r.BASE / 'seed1_detached_stage1').rglob('*')
              if p.is_file() and '__pycache__' not in p.parts]
    inputs = {**audit['input_sha256'], **{str(p): r.sha(p) for p in files}}
    r.ctl.execution.check_hashes(inputs)
    r.audit.require_dead()
    report = {'schema': 'cardpilot.actor_route.recovery_preflight.v1', 'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'command': [sys.executable, *sys.orig_argv[1:]],
        'tests_command': command, 'tests_cwd': str(r.ROOT), 'tests_stdout': result.stdout, 'tests_stderr': result.stderr,
        'test_count': count, 'checkpoint_sha256': r.SAVED_SHA, 'remaining_stage1_retained_hands': 253157,
        'input_sha256': inputs, 'unknown_additional_worker_tail_hands': None,
        'algorithm_seed_target_evaluation_unchanged': True, 'training_started': False,
        'training_hands_added': 0, 'evaluation_hands_added': 0,
        'next_step': 'One reviewed hidden launch of remaining fixed plan; no automatic retries.'}
    r.ctl.write_new(out, report)
    print(json.dumps({k: v for k, v in report.items() if k != 'input_sha256'}, indent=2))


if __name__ == '__main__':
    main()
