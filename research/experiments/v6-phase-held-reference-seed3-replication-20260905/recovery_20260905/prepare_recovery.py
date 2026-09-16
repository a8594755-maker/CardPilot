"""Validate retained learning and derive a separate, byte-exact consumed metric view."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import resume_control as recovery

ctl, ev, HERE, BASE = recovery.ctl, recovery.ev, recovery.HERE, recovery.BASE


def consumed_metric_prefix(data, iteration):
    ev.require(data.endswith(b'\n'), 'incomplete metric file')
    lines = data.splitlines(keepends=True)
    rows = [json.loads(line) for line in lines]
    ev.require([r['iteration'] for r in rows] == list(range(1, len(rows) + 1)), 'metric gap or duplicate')
    ev.require(0 < iteration < len(rows), 'expected explicit uncheckpointed suffix')
    return b''.join(lines[:iteration]), rows[iteration:]


def main():
    import torch
    torch.set_num_threads(1)
    recovery.require_dead()
    out = HERE / 'recovery_preflight.json'
    ev.require(not out.exists() and not recovery.VIEW.exists() and not recovery.RUN.exists(), 'preserve previous preparation')
    io = ev.read_json(HERE / 'io_qualification_v2.json')
    ev.require(io['passed'], 'I/O qualification not passed')
    ctl.check_hashes(io['input_sha256'])
    audit = ev.read_json(HERE / 'interruption_audit.json')
    ev.require(audit['passed'] and audit['checkpoint_sha256'] == recovery.SAVED_SHA, 'wrong retained boundary')
    ctl.check_hashes(audit['input_sha256'])
    xml = HERE / 'recovery_tests.xml'
    ev.require(not xml.exists(), 'preserve prior tests')
    command = [sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
               str(HERE / 'test_recovery_control.py'), '--junitxml=' + str(xml)]
    tests = subprocess.run(command, cwd=ctl.ROOT, capture_output=True, text=True, encoding='utf-8', timeout=45)
    if tests.returncode:
        ctl.write_new(HERE / 'failed_recovery_tests.json', {'command': command, 'stdout': tests.stdout, 'stderr': tests.stderr})
        raise ValueError(tests.stdout + tests.stderr)
    suites = list(ET.parse(xml).getroot().iter('testsuite'))
    ev.require(sum(int(s.get('tests', '0')) for s in suites) >= 10 and
               all(int(s.get('failures', '0')) == int(s.get('errors', '0')) == int(s.get('skipped', '0')) == 0 for s in suites), 'missing recovery coverage')
    saved = torch.load(recovery.OLD / 'latest.pt', map_location='cpu', weights_only=False)
    parent = torch.load(recovery.ORIGINAL_PARENT, map_location='cpu', weights_only=False)
    initial = torch.load(recovery.OLD / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
    original_metrics = (recovery.OLD / 'h1_training_metrics.jsonl').read_bytes()
    prefix, excluded = consumed_metric_prefix(original_metrics, saved['iteration'])
    ev.require([r['iteration'] for r in excluded] == [1118], 'unexpected unsaved suffix')
    metrics = [json.loads(line) for line in prefix.splitlines()]
    assignments = ctl.complete_jsonl(recovery.OLD / 'opponent_assignments.jsonl')
    pool = ev.module_at('seed3_retained_pool_windows', ctl.POOL_HELPER)
    windows = [pool.load_window(recovery.ORIGINAL_PARENT, ctl.PARENT_SHA)]
    refs, archive_hashes = [], {}
    for path in [*sorted((recovery.OLD / 'checkpoints').glob('*.pt')), recovery.OLD / 'latest.pt']:
        digest = ev.sha(path)
        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        ev.require(parent['iteration'] < checkpoint['iteration'] <= saved['iteration'], 'unexpected archived boundary')
        archive_hashes[str(path)] = digest
        windows.append(pool.load_window(path, digest))
        refs.append({key: checkpoint[key] for key in ('iteration', 'model', 'environment_hand_accounting')}
                    | {'moving_source_policy_reference': checkpoint.get('moving_source_policy_reference')})
    windows.sort(key=lambda r: r['iteration'])
    refs.sort(key=lambda r: r['iteration'])
    pool_audit = pool.verify_windows(windows, metrics, [r for r in assignments if r['applies_to_iteration'] <= saved['iteration']])
    helper = ctl.qualified_command_helper()
    reference_audit = ev.verify_reference_windows('static', parent, initial, refs, metrics, helper.equal)
    log = (recovery.OLD / 'latest_train.log').read_text(encoding='utf-8')
    consumed_log = '\n'.join(line for line in log.splitlines() if not (match := re.match(r'\[\s*(\d+)\]', line))
                             or int(match.group(1)) <= saved['iteration'])
    ev.require(helper.finite_update_evidence([r for r in metrics if r['iteration'] > parent['iteration']], consumed_log), 'invalid retained updates')
    recovery.VIEW.mkdir()
    shutil.copy2(recovery.OLD / 'latest.pt', recovery.VIEW / 'latest.pt')
    shutil.copy2(recovery.OLD / 'opponent_assignments.jsonl', recovery.VIEW / 'opponent_assignments.jsonl')
    with (recovery.VIEW / 'h1_training_metrics.jsonl').open('xb') as handle:
        handle.write(prefix)
    derivation = {'source_path': str(recovery.OLD / 'h1_training_metrics.jsonl'),
        'source_sha256': hashlib.sha256(original_metrics).hexdigest(), 'derived_sha256': hashlib.sha256(prefix).hexdigest(),
        'byte_exact_prefix_length': len(prefix), 'retained_iterations': [1, 1117],
        'excluded_from_active_resume_view_only': [1118], 'original_unsaved_metric_preserved': True,
        'assignment_rows_copied_without_trimming': 1118, 'checkpoint_bytes_unchanged': True,
        'original_manifest1118_is_not_checkpoint1117_state': True}
    ctl.write_new(recovery.VIEW / 'derivation.json', derivation)
    inputs = {**audit['input_sha256'], **io['input_sha256'], **archive_hashes}
    for path in [*HERE.glob('*.py'), *recovery.VIEW.iterdir(), HERE / 'recovery_amendment.md',
                 HERE / 'interruption_audit.json', HERE / 'io_qualification_v2.json', xml, HERE / 'launch.ps1']:
        inputs[str(path)] = ev.sha(path)
    ctl.check_hashes(inputs)
    result = {'schema': 'cardpilot.seed3.recovery_preflight.v1', 'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'command': [sys.executable, *sys.argv],
        'tests_command': command, 'tests_stdout': tests.stdout, 'tests_stderr': tests.stderr,
        'test_count': sum(int(s.get('tests', '0')) for s in suites),
        'retained_optimizer_updates': saved['iteration'] - parent['iteration'],
        'pool_window_audit': pool_audit, 'reference_audit': reference_audit, 'derivation': derivation,
        'input_sha256': inputs, 'remaining_stage1_retained_hands': ctl.TARGETS[1] - audit['retained_physical_hands'],
        'unknown_additional_worker_tail_hands': None, 'training_hands_added': 0, 'evaluation_hands_added': 0,
        'training_started': False, 'next_step': 'One hidden recovery launch, no automatic retries'}
    ctl.write_new(out, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'input_sha256'}, indent=2))


if __name__ == '__main__':
    main()
