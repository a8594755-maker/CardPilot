"""Continue only the unpublished-candidate remainder; preserve both interruptions."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
PREVIOUS = BASE / 'recovery_20260905'
VIEW = HERE / 'retained_parent'
RUN = HERE / 'moving256_stage1_remainder'
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(PREVIOUS))
import resume_control as first
import audit_pending_checkpoint as audit_tools

ctl, ev = first.ctl, first.ev
ORIGINAL_PARENT = ctl.PARENT
WRAPPER = HERE / 'train_with_checkpoint_io_45s.py'
CANDIDATE_SHA = '2a8e795e84c18321e2b940e805b2d5d1fd699407bc6ea38a3cf223036d3e7185'


def require_dead():
    audit_tools.require_terminal()
    names = {'train_v5.py', 'train_with_checkpoint_io_v2.py', 'train_with_checkpoint_io_45s.py',
             'resume_control.py', 'resume_control_second.py', 'run_control.py', 'run_pair.py',
             'v6_public_opponent_matched_eval.py', 'v6_legacy_bridge_drift_audit.py'}
    for proc in ctl.psutil.process_iter(['pid', 'cmdline']):
        if proc.pid != os.getpid():
            ev.require(not any(Path(a).name in names for a in proc.info['cmdline'] or []),
                       f'other poker job live: {proc.pid}')


def stage_directory(arm, stage):
    if (arm, stage) == ('static', 1):
        return PREVIOUS / 'static_stage1_remainder'
    if (arm, stage) == ('moving256', 1):
        return RUN
    return first.ORIGINAL_STAGE_DIRECTORY(arm, stage)


def training_command(arm, stage, parent_path, parent_physical):
    argv = first.ORIGINAL_COMMAND(arm, stage, parent_path, parent_physical)
    ev.require(argv[2] == str(ctl.PRODUCTION), 'unexpected trainer argv')
    argv[2] = str(WRAPPER)
    return argv


def live_accounting():
    totals, runs = first.ORIGINAL_ACCOUNTING()
    static = ev.read_json(PREVIOUS / 'interruption_audit.json')
    moving = ev.read_json(HERE / 'pending_checkpoint_audit.json')
    totals['retained_training_hands'] = totals['new_training_hands'] + static['new_retained_physical_hands'] + moving['recoverable_new_physical_hands']
    totals['retained_transition_hands'] = totals['new_transition_hands'] + static['new_retained_transition_hands'] + moving['recoverable_new_transition_hands']
    totals['new_training_hands'] = totals['retained_training_hands'] + static['observed_completed_but_uncheckpointed_physical_hands']
    totals['new_transition_hands'] = totals['retained_transition_hands'] + static['observed_completed_but_uncheckpointed_transition_hands']
    totals['observed_uncheckpointed_training_hands'] = static['observed_completed_but_uncheckpointed_physical_hands']
    totals['recovered_unpublished_physical_hands_already_in_retained'] = moving['unpublished_completed_update_physical_hands']
    runs['static_stage1_interrupted_retained'] = {'physical_hands': static['retained_physical_hands'],
        'iteration': static['iteration'], 'new_physical_hands': static['new_retained_physical_hands']}
    runs['moving_stage1_recovered_candidate'] = {'physical_hands': moving['candidate_physical_hands'],
        'iteration': moving['candidate_iteration'], 'new_physical_hands': moving['recoverable_new_physical_hands'],
        'checkpoint_sha256': moving['candidate_sha256']}
    return totals, runs


def write_status(value):
    value['unknown_additional_worker_tail_hands'] = None
    value['preserved_failure_status_paths'] = [str(BASE / 'status.json'), str(PREVIOUS / 'status.json')]
    pending = HERE / 'status.pending.json'
    with pending.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(pending, HERE / 'status.json')


def extra_resume_gates(parent, initial, prior_namespaces, equal):
    return {'fresh_namespace_excludes_every_prior_attempt':
            initial['fixed_deal_attempt']['receipt']['namespace'] not in prior_namespaces,
            'moving_reference_payload_not_rebased_or_reset':
            equal(parent.get('moving_source_policy_reference'), initial.get('moving_source_policy_reference'))}


class SecondRecovery(first.Recovery):
    def __init__(self):
        require_dead()
        qualified = ev.read_json(HERE / 'recovery_preflight.json')
        ev.require(qualified['passed'] and not RUN.exists() and not (HERE / 'ownership.json').exists(), 'recovery not unused/qualified')
        ev.require(shutil.disk_usage(HERE).free > 12 * 1024**3, 'insufficient disk space')
        self.inputs = dict(qualified['input_sha256'])
        self.inputs[str(HERE / 'recovery_preflight.json')] = ev.sha(HERE / 'recovery_preflight.json')
        ctl.check_hashes(self.inputs)
        self.sources = {p: digest for p, digest in self.inputs.items() if p.endswith('.py')}
        original = ev.read_json(BASE / 'input_contract.json')
        self.anchors, self.corpus = original['anchors'], dict(original['prior_common_deck_corpus'])
        self.partial = ev.read_json(PREVIOUS / 'interruption_audit.json')
        self.moving_partial = ev.read_json(HERE / 'pending_checkpoint_audit.json')
        static = ev.read_json(PREVIOUS / 'static_stage1_remainder/verification.json')
        ev.require(static['passed'] and static['arm'] == 'static' and static['stage'] == 1, 'completed static stage missing')
        self.results = [static]
        self.prior_namespaces = {self.partial['namespace'], static['namespace'], self.moving_partial['namespace']}
        ev.require(len(self.prior_namespaces) == 3, 'prior namespace conflict')
        self.started, self.last_tick, self.child = time.perf_counter(), 0, None
        self.phase = 'QUALIFIED_SECOND_RECOVERY_READY'
        self.owner = {'pid': os.getpid(), 'create_time': ctl.psutil.Process().create_time(),
                      'started_at': datetime.now(timezone.utc).isoformat(),
                      'command': [sys.executable, '-u', str(Path(__file__))]}
        ctl.write_new(HERE / 'ownership.json', self.owner)
        ctl.write_new(HERE / 'input_contract.json', {'input_sha256': self.inputs,
            'anchors': self.anchors, 'prior_common_deck_corpus': self.corpus,
            'candidate_parent_sha256': CANDIDATE_SHA, 'original_algorithm_seeds_targets_unchanged': True,
            'completed_static_stage1_reused': str(PREVIOUS / 'static_stage1_remainder/verification.json'),
            'prior_attempt_namespaces': sorted(self.prior_namespaces), 'runtime_io_override': str(WRAPPER)})
        ctl.stage_directory, ctl.training_command = stage_directory, training_command
        ctl.live_accounting, ctl.write_status = live_accounting, write_status
        ctl.logger_update('--command', subprocess.list2cmdline(self.owner['command']),
            '--artifact', str(HERE / 'ownership.json'), '--artifact', str(HERE / 'input_contract.json'),
            '--note', 'Second qualified recovery owns writes. Validated candidate1215/5776996, unchanged optimizer/replay/main RNG/reference round1 and full1215-row assignment chain; new namespace. Static stage1 reused without rerun. Original sources/errors/candidates remain immutable. I/O grace45s only; algorithm/seeds/targets/evaluation unchanged.')

    def execute(self, argv, run, observer=None, training=False):
        def extra(line):
            if observer:
                observer(line)
            if training and '[Save] initial resume checkpoint' in line:
                import torch
                parent_path = Path(ev.read_json(run / 'parent_contract.json')['path'])
                parent = torch.load(parent_path, map_location='cpu', weights_only=False)
                initial = torch.load(run / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
                gates = extra_resume_gates(parent, initial, self.prior_namespaces, ctl.qualified_command_helper().equal)
                ctl.write_new(run / 'second_resume_gate.json', {'passed': all(gates.values()), 'gates': gates,
                    'parent_sha256': ev.sha(parent_path), 'initial_sha256': ev.sha(run / 'initial_resumed_state.pt')})
                ev.require(all(gates.values()), 'second-recovery namespace/reference restoration failed')
                ctl.logger_update('--artifact', str(run / 'second_resume_gate.json'))
        return first.Recovery.execute(self, argv, run, extra if training else observer, training=training)

    def train(self, arm, stage):
        ev.require((arm, stage) != ('static', 1), 'completed static stage1 must never be rerun')
        if (arm, stage) == ('moving256', 1):
            ctl.PARENT = VIEW / 'latest.pt'
            try:
                ctl.Controller.train(self, arm, stage)
            finally:
                ctl.PARENT = ORIGINAL_PARENT
        else:
            ctl.Controller.train(self, arm, stage)
        ev.require(self.results[-1]['namespace'] not in self.prior_namespaces, 'prior attempt namespace reused')

    def run(self):
        try:
            self.train('moving256', 1)
            stage1 = self.evaluate(1)
            if stage1['broad_collapse']:
                self.phase = 'PREREGISTERED_BROAD_COLLAPSE_RESEARCH_REVIEW'
            else:
                self.train('moving256', 2)
                self.train('static', 2)
                self.evaluate(2)
                self.phase = 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS'
            ctl.write_new(HERE / 'pipeline_result.json', {'phase': self.phase, 'completed_attempts': self.results,
                'new_attempts_in_second_recovery': self.results[1:],
                'preserved_interruption_audits': [str(PREVIOUS / 'interruption_audit.json'), str(HERE / 'pending_checkpoint_audit.json')],
                'wall_seconds': time.perf_counter() - self.started, 'earlier_failed_pipeline_results_not_fabricated': True,
                'final_goal_qualified': False})
        except ctl.SafeBoundary as error:
            self.phase = 'SAFE_BOUNDARY_REQUIRES_RESEARCHER_RESUME_REVIEW'
            ctl.write_new(HERE / 'safe_boundary.json', {'reason': str(error), 'automatic_retry': False})
        except BaseException as error:
            ctl.write_new(HERE / 'controller_error.json', {'error': repr(error), 'automatic_retry': False})
            self.phase = 'ERROR_DRAINING_EXISTING_BOUNDED_JOB_NO_NEXT_JOB'
            if self.child is not None:
                while self.child.poll() is None:
                    time.sleep(2)
            self.child = None
            self.phase = 'ERROR_PRESERVED_RESEARCH_REVIEW'
            raise
        finally:
            self.tick(force=True)


if __name__ == '__main__':
    SecondRecovery().run()
