"""Preservation-first remainder and frozen evaluations for one interrupted stage."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(BASE))
import run_control as ctl
import control_evidence as ev

OLD = BASE / 'static_stage2'
PARENT = OLD / 'latest.pt'
PARENT_SHA = 'c44a52bcbcc30e88c8e6a96a0d6d6c0eb1a869d5041585129e942d3a8a587974'
RUN = HERE / 'static_stage2_remainder'
ORIGINAL_STAGE_DIRECTORY = ctl.stage_directory
ORIGINAL_ACCOUNTING = ctl.live_accounting
RETAIN_KEYS = ('model', 'optimizer', 'ppo_replay_entries', 'ppo_replay_rng_state',
               'ppo_replay_cumulative_rows', 'pool_snapshots', 'pool_strategy',
               'pool_active_metadata', 'pool_candidate_history', 'main_process_rng_state')


def require_dead():
    for path in (BASE / 'ownership.json', OLD / 'process.json'):
        ev.require(not ctl.owner_live(ev.read_json(path)), f'original owner still live: {path}')
    names = {'train_v5.py', 'v6_public_opponent_matched_eval.py', 'v6_legacy_bridge_drift_audit.py', 'run_control.py'}
    for proc in ctl.psutil.process_iter(['pid', 'cmdline']):
        argv = proc.info.get('cmdline') or []
        ev.require(not any(Path(arg).name in names for arg in argv), f'other poker job live: {proc.pid}')


def exact_rows(path):
    rows = ctl.complete_jsonl(path)
    data = path.read_bytes()
    ev.require(not data or data.endswith(b'\n'), f'incomplete JSONL tail: {path}')
    ev.require(len(rows) == sum(bool(line.strip()) for line in data.splitlines()), f'unparsed evidence: {path}')
    return rows


def validate_boundary(parent, manifest, metrics, assignments):
    iteration = int(parent['iteration'])
    physical = int(parent['environment_hand_accounting']['completed_hands'])
    ev.require(iteration == 1525 and physical == 7237515 and parent['total_hands'] == 6284575,
               'unexpected retained checkpoint')
    ev.require(manifest['iteration'] == iteration and manifest['total_hands'] == parent['total_hands'], 'manifest boundary mismatch')
    ev.require(manifest['environment_hand_accounting'] == parent['environment_hand_accounting'], 'manifest physical accounting differs')
    ev.require([r['iteration'] for r in metrics] == list(range(1, iteration + 1)), 'metric update gap or unsaved suffix')
    ev.require(metrics[-1]['hands'] == parent['total_hands'] and
               metrics[-1]['environment_hand_accounting'] == parent['environment_hand_accounting'], 'last metric differs from checkpoint')
    ev.require([r['applies_to_iteration'] for r in assignments] == list(range(1, iteration + 2)), 'pending assignment chain differs')
    ev.require(assignments[-1]['total_hands_before_iteration'] == parent['total_hands'], 'pending assignment counter mismatch')
    ev.require(physical < ctl.TARGETS[2], 'target already reached; no restart')


def audit_windows(run, parent_path, parent, final, metrics, assignments):
    """Pending assignment is separately replayed; pool audit uses consumed rows."""
    import torch
    helper = ctl.qualified_command_helper()
    pool = ev.module_at('recovery_pool_windows', ctl.POOL_HELPER)
    windows = [pool.load_window(parent_path, ctl.sha(parent_path))]
    ref_windows, hashes = [], {}
    for path in list((run / 'checkpoints').glob('*.pt')) + [run / 'latest.pt']:
        digest = ctl.sha(path)
        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        if not parent['iteration'] < checkpoint['iteration'] <= final['iteration']:
            continue
        hashes[str(path)] = digest
        windows.append(pool.load_window(path, digest))
        ref_windows.append({key: checkpoint[key] for key in ('iteration', 'model', 'environment_hand_accounting')}
                           | {'moving_source_policy_reference': checkpoint.get('moving_source_policy_reference')})
    windows.sort(key=lambda row: row['iteration'])
    ref_windows.sort(key=lambda row: row['iteration'])
    initial = torch.load(run / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
    return {'pool_window_audit': pool.verify_windows(windows, metrics,
                [r for r in assignments if r['applies_to_iteration'] <= final['iteration']]),
            'moving_reference_audit': ev.verify_reference_windows('static', parent, initial, ref_windows, metrics, helper.equal),
            'checkpoint_windows_sha256': hashes}


def audit():
    import torch
    torch.set_num_threads(1)
    require_dead()
    ev.require(not (HERE / 'interruption_audit.json').exists(), 'audit exists; preserve it, never overwrite')
    ev.require(not RUN.exists() and not (HERE / 'ownership.json').exists(), 'recovery already started')
    original = ev.read_json(BASE / 'input_contract.json')
    ctl.check_hashes(original['input_sha256'])
    ev.require(ctl.sha(PARENT) == PARENT_SHA, 'retained checkpoint SHA mismatch')
    parent = torch.load(PARENT, map_location='cpu', weights_only=False)
    initial = torch.load(OLD / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
    prior_path = BASE / 'static_stage1/latest.pt'
    prior = torch.load(prior_path, map_location='cpu', weights_only=False)
    helper = ctl.qualified_command_helper()
    metrics, assignments = (exact_rows(OLD / name) for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'))
    validate_boundary(parent, ev.read_json(OLD / 'run_manifest.json'), metrics, assignments)
    ev.require(all(helper.equal(initial[k], prior[k]) for k in RETAIN_KEYS), 'interrupted attempt initial state differs')
    ev.require(min(helper.steps(parent)) > max(helper.steps(prior)), 'optimizer did not advance')
    ev.require(len(parent['ppo_replay_entries']) == 2 and parent['ppo_replay_cumulative_rows'] > prior['ppo_replay_cumulative_rows'], 'replay did not advance')
    ev.require(all(torch.isfinite(tensor).all().item() for tensor in parent['model'].values()), 'nonfinite model')
    ev.require(helper.finite_update_evidence([r for r in metrics if r['iteration'] > prior['iteration']],
                                            (OLD / 'latest_train.log').read_text(encoding='utf-8')), 'nonfinite/missing update evidence')
    trainer = ev.module_at('interruption_assignment_replay', ctl.PRODUCTION)
    replayed = trainer.restore_group_assignment_rng_from_evidence(assignments, metrics, rng=random.Random(0),
        seed=20263001, worker_count=12, pool_size=len(parent['pool_snapshots']), group_count=8,
        self_play_fraction=.25, checkpoint_iteration=parent['iteration'], checkpoint_total_hands=parent['total_hands'],
        pool_snapshot_ids=[r['id'] for r in parent['pool_active_metadata']],
        replay_origin=parent.get('assignment_replay_origin'))
    ev.require(replayed['pending_assignments'] is not None, 'pending assignment was lost')
    windows = audit_windows(OLD, prior_path, prior, parent, metrics, assignments)
    frozen = {str(path): ctl.sha(path) for path in OLD.rglob('*') if path.is_file() and '__pycache__' not in path.parts}
    for name in ('status.json', 'ownership.json', 'input_contract.json'):
        frozen[str(BASE / name)] = ctl.sha(BASE / name)
    for run_name in ('static_stage1', 'moving256_stage1', 'moving256_stage2'):
        completed = ev.read_json(BASE / run_name / 'verification.json')
        path = BASE / run_name / 'latest.pt'
        ev.require(completed['passed'] and ctl.sha(path) == completed['checkpoint_sha256'], f'completed run changed: {run_name}')
        frozen[str(path)] = ctl.sha(path)
        for name in ('verification.json', 'termination.json'):
            frozen[str(BASE / run_name / name)] = ctl.sha(BASE / run_name / name)
    session = parent['environment_hand_accounting']
    partial = {'arm': 'static', 'stage': 2, 'attempt': 'interrupted_original', 'retained_boundary_verified': True,
        'terminal_attempt': False, 'iteration': parent['iteration'], 'namespace': parent['fixed_deal_attempt']['receipt']['namespace'],
        'checkpoint_sha256': PARENT_SHA, 'new_physical_hands': session['completed_hands'] - prior['environment_hand_accounting']['completed_hands'],
        'new_transition_hands': parent['total_hands'] - prior['total_hands'],
        'new_replay_rows': parent['ppo_replay_cumulative_rows'] - prior['ppo_replay_cumulative_rows'],
        'new_no_decision_hands': session['no_trainable_decision_hands'] - prior['environment_hand_accounting']['no_trainable_decision_hands'],
        'unknown_crash_suffix_hands': None, 'subprocess_wall_seconds': None,
        'last_checkpoint_utc': datetime.fromtimestamp(PARENT.stat().st_mtime, timezone.utc).isoformat()}
    partial['retained_worker_tail_hands'] = partial['new_physical_hands'] - partial['new_transition_hands'] - partial['new_no_decision_hands']
    result = {'schema': 'cardpilot.phase_control.interruption.v1', 'passed': True,
        'audited_at': datetime.now(timezone.utc).isoformat(), 'cause': None, 'original_exit_code': None,
        'original_processes_absent': True, 'original_handles_missing_previously_observed': True,
        'physical_hands': session['completed_hands'], 'transition_hands': parent['total_hands'],
        'remaining_physical_hands': ctl.TARGETS[2] - session['completed_hands'], 'partial_attempt': partial,
        'assignment_replay': replayed, 'raw_prefixes_copied_without_trimming': True,
        'state_retained': list(RETAIN_KEYS), 'frozen_interrupted_inputs': frozen, **windows,
        'statistical_not_bitwise_worker_continuation': True, 'new_training_hands': 0, 'new_evaluation_hands': 0}
    ctl.write_new(HERE / 'interruption_audit.json', result)
    ctl.logger_update('--artifact', str(HERE / 'interruption_audit.json'), '--artifact', str(Path(__file__)),
        '--artifact', str(HERE / 'README.md'), '--command', subprocess.list2cmdline([sys.executable, '-B', str(Path(__file__)), '--audit-only']),
        '--note', 'Interrupted static stage2 retained197 updates pass model/optimizer/replay, pool windows, metric counters and full1526-row assignment replay. Pending1526 is preserved, not trimmed. Unknown crash suffix remains unknown; no model/hands rerun by audit.')
    print(json.dumps({k: result[k] for k in ('passed', 'remaining_physical_hands', 'assignment_replay', 'partial_attempt')}, indent=2))


def recovered_stage_directory(arm, stage):
    return RUN if (arm, stage) == ('static', 2) else ORIGINAL_STAGE_DIRECTORY(arm, stage)


def recovery_accounting():
    totals, runs = ORIGINAL_ACCOUNTING()
    partial = ev.read_json(HERE / 'interruption_audit.json')['partial_attempt']
    totals['new_training_hands'] += partial['new_physical_hands']
    totals['new_transition_hands'] += partial['new_transition_hands']
    runs['static_stage2_interrupted_retained'] = partial
    return totals, runs


def write_recovery_status(value):
    value['unknown_prior_crash_suffix_hands'] = None
    value['original_status_preserved_at'] = str(BASE / 'status.json')
    pending = HERE / 'status.pending.json'
    with pending.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(pending, HERE / 'status.json')


def drain_current(controller):
    """After an unexpected observer exception, no subsequent job is authorized."""
    child = controller.child
    if child is None or child.poll() is not None:
        return
    controller.phase = 'ERROR_DRAINING_EXISTING_BOUNDED_JOB_NO_NEXT_JOB'
    while child.poll() is None:
        time.sleep(2)
    controller.child = None


class Recovery(ctl.Controller):
    def __init__(self):
        require_dead()
        audit = ev.read_json(HERE / 'interruption_audit.json')
        ev.require(audit['passed'] and audit['remaining_physical_hands'] == 1154765, 'recovery audit not qualified')
        ev.require(not RUN.exists() and not (HERE / 'ownership.json').exists(), 'recovery already attempted; no automatic retry')
        ev.require(not (BASE / 'pipeline_result.json').exists(), 'original pipeline already terminal')
        tests = ET.parse(HERE / 'tests.xml').getroot()
        suites = [tests] if tests.tag == 'testsuite' else list(tests.iter('testsuite'))
        ev.require(sum(int(s.attrib.get('tests', 0)) for s in suites) >= 8 and
                   all(int(s.attrib.get('failures', 0)) == int(s.attrib.get('errors', 0)) == 0 for s in suites), 'recovery tests not passed')
        original = ev.read_json(BASE / 'input_contract.json')
        self.inputs = dict(original['input_sha256']) | audit['frozen_interrupted_inputs']
        for path in (HERE / 'README.md', HERE / 'interruption_audit.json', HERE / 'tests.xml', Path(__file__), HERE / 'test_resume_control.py', HERE / 'launch.ps1'):
            self.inputs[str(path)] = ctl.sha(path)
        ctl.check_hashes(self.inputs)
        ev.require(shutil.disk_usage(BASE).free >= 8 * 1024**3, 'insufficient checkpoint/evaluation disk space')
        self.sources = {p: digest for p, digest in self.inputs.items() if p.endswith('.py')}
        self.anchors = original['anchors']
        self.corpus = dict(original['prior_common_deck_corpus'])
        for arm in ('static', 'moving256'):
            path = BASE / f'eval_{arm}_stage1/common_deck_pairs.jsonl.gz'
            self.corpus[str(path)] = ctl.sha(path)
        self.results = [ev.read_json(BASE / name / 'verification.json') for name in ('static_stage1', 'moving256_stage1', 'moving256_stage2')]
        self.partial = audit['partial_attempt']
        self.started, self.last_tick, self.child = time.perf_counter(), 0, None
        self.phase = 'QUALIFIED_REMAINDER_READY'
        self.owner = {'pid': os.getpid(), 'create_time': ctl.psutil.Process().create_time(),
            'started_at': datetime.now(timezone.utc).isoformat(), 'command': [sys.executable, '-u', str(Path(__file__)), '--run']}
        ctl.write_new(HERE / 'ownership.json', self.owner)
        ctl.write_new(HERE / 'input_contract.json', {'input_sha256': self.inputs, 'prior_common_deck_corpus': self.corpus,
                      'original_protocol_unchanged': True, 'recovery_endpoint': str(RUN / 'latest.pt')})
        ctl.stage_directory, ctl.live_accounting, ctl.write_status = recovered_stage_directory, recovery_accounting, write_recovery_status
        ctl.logger_update('--command', subprocess.list2cmdline(self.owner['command']), '--artifact', str(HERE / 'ownership.json'),
            '--artifact', str(HERE / 'input_contract.json'), '--metric', 'unknown_crash_suffix_hands=null',
            '--note', 'Qualified remainder controller owns same experiment. File-backed hidden launch, original attempt immutable. Resume7237515 to original8392280 target; no reset, fresh managed namespace, exact pending assignment reuse; then both original stage2 evaluations.')

    def train_remainder(self):
        import torch
        torch.set_num_threads(1)
        parent = torch.load(PARENT, map_location='cpu', weights_only=False)
        old = int(parent['environment_hand_accounting']['completed_hands'])
        RUN.mkdir()
        ctl.write_new(RUN / 'parent_contract.json', {'path': str(PARENT), 'sha256': PARENT_SHA,
            'physical_hands': old, 'transition_hands': parent['total_hands'], 'iteration': parent['iteration']})
        prefixes = {}
        for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
            path = OLD / name
            prefixes[name] = {'path': str(path), 'sha256': ctl.sha(path), 'bytes': path.stat().st_size}
            shutil.copy2(path, RUN / name)
        ctl.write_new(RUN / 'prefixes.json', prefixes)
        shutil.copy2(ctl.PRODUCTION, RUN / 'trainer_source.py')
        helper = ctl.qualified_command_helper()

        def capture(line):
            if '[Save] initial resume checkpoint' not in line:
                return
            path = RUN / 'initial_resumed_state.pt'
            ev.require(not path.exists(), 'initial checkpoint already captured')
            shutil.copy2(RUN / 'latest.pt', path)
            initial = torch.load(path, map_location='cpu', weights_only=False)
            ev.require(initial['iteration'] == parent['iteration'] and initial['total_hands'] == parent['total_hands'] and
                       initial['environment_hand_accounting']['completed_hands'] == old, 'initial counter reset')
            ev.initial_reference('static', parent, initial, helper.equal)
            ev.require(all(helper.equal(initial[k], parent[k]) for k in RETAIN_KEYS), 'initial retained state changed')
            namespace = initial['fixed_deal_attempt']['receipt']['namespace']
            ev.require(namespace not in [r['namespace'] for r in self.results] + [self.partial['namespace']], 'namespace reused')
            ctl.logger_update('--artifact', str(path), '--note', 'Actual remainder initial checkpoint exactly matches interrupted iteration1525 model/optimizer/replay/pool/main RNG and counters; new namespace reserved. Worker continuation remains statistical.')

        command = ctl.training_command('static', 2, PARENT, old)
        # The original builder has a fixed run path, now redirected explicitly.
        ev.require(command[command.index('--out') + 1] == str(RUN / 'latest.pt'), 'recovery output not redirected')
        self.phase = 'TRAINING_static_stage2_REMAINDER'
        wall = self.execute(command, RUN, capture, training=True)
        final = torch.load(RUN / 'latest.pt', map_location='cpu', weights_only=False)
        for name, info in prefixes.items():
            with (RUN / name).open('rb') as handle:
                import hashlib
                digest = hashlib.sha256(handle.read(info['bytes'])).hexdigest()
            ev.require(digest == info['sha256'] == ctl.sha(info['path']), 'raw prefix modified')
        ctl.target_or_safe_boundary(final['environment_hand_accounting']['completed_hands'], ctl.TARGETS[2])
        helper.DELTA = ctl.TARGETS[2] - old
        result = helper.inspect_attempt(RUN, parent, PARENT, PARENT_SHA, wall)
        metrics, assignments = (exact_rows(RUN / name) for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'))
        result.update(audit_windows(RUN, PARENT, parent, final, metrics, assignments))
        result.update(arm='static', stage=2, attempt='remainder',
            overshoot_hands=final['environment_hand_accounting']['completed_hands'] - ctl.TARGETS[2],
            new_replay_rows=final['ppo_replay_cumulative_rows'] - parent['ppo_replay_cumulative_rows'],
            new_no_decision_hands=final['environment_hand_accounting']['no_trainable_decision_hands'] - parent['environment_hand_accounting']['no_trainable_decision_hands'],
            unknown_crash_suffix_hands=0, unknown_earlier_attempt_crash_suffix_hands=None,
            statistical_not_bitwise_worker_continuation=True)
        result['residual_worker_tail_hands'] = result['new_physical_hands'] - result['new_transition_hands'] - result['new_no_decision_hands']
        ctl.write_new(RUN / 'verification.json', result)
        self.results.append(result)
        self.inputs[str(RUN / 'latest.pt')] = result['checkpoint_sha256']
        ctl.logger_update('--artifact', str(RUN / 'verification.json'), '--artifact', str(RUN / 'termination.json'),
            '--artifact', str(RUN / 'latest.pt'), '--artifact', str(RUN / 'h1_training_metrics.jsonl'),
            '--artifact', str(RUN / 'opponent_assignments.jsonl'), '--note', 'Static remainder reached original target; resumed attempt verified. Earlier crash suffix remains unknown, not silently set to zero.')
        self.tick(force=True)

    def run(self):
        try:
            self.train_remainder()
            self.evaluate(2)
            self.phase = 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS'
            ctl.write_new(HERE / 'pipeline_result.json', {'phase': self.phase, 'completed_attempts': self.results,
                'interrupted_retained_attempt': self.partial, 'wall_seconds': time.perf_counter() - self.started,
                'static_stage2_endpoint': str(RUN / 'latest.pt'), 'unknown_crash_suffix_hands': None,
                'original_pipeline_result_not_fabricated': True, 'final_goal_qualified': False})
            ctl.logger_update('--artifact', str(HERE / 'pipeline_result.json'),
                '--note', 'Same experiment remaining training and both original stage2 evaluations complete. Researcher must aggregate interruption-aware costs/learning curve and finish record; no next experiment automatically started.')
        except BaseException as exc:
            ctl.write_new(HERE / 'controller_error.json', {'error': repr(exc), 'automatic_retry': False,
                'child_pid': self.child.pid if self.child else None})
            drain_current(self)
            self.phase = 'ERROR_PRESERVED_RESEARCH_REVIEW'
            raise
        finally:
            self.tick(force=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--audit-only', action='store_true')
    modes.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.audit_only:
        audit()
    else:
        Recovery().run()
