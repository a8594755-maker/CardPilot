"""Same Seed3 recipe, preserved failed attempt, explicit consumed-prefix recovery."""
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
sys.path.insert(0, str(BASE))
import run_control as ctl
import control_evidence as ev

OLD = BASE / 'static_stage1'
VIEW = HERE / 'retained_parent'
RUN = HERE / 'static_stage1_remainder'
WRAPPER = HERE / 'train_with_checkpoint_io_v2.py'
SAVED_SHA = 'd5e9ca2e96f3cba6bcda6c64a58b6759b9d6f38872d52ec30de01cbb75482f59'
ORIGINAL_STAGE_DIRECTORY = ctl.stage_directory
ORIGINAL_COMMAND = ctl.training_command
ORIGINAL_ACCOUNTING = ctl.live_accounting
ORIGINAL_PARENT = ctl.PARENT


def require_dead():
    for path in (BASE / 'ownership.json', OLD / 'process.json'):
        ev.require(not ctl.owner_live(ev.read_json(path)), f'original owner live: {path}')
    terminal = ev.read_json(OLD / 'termination.json')
    for pid, created in terminal['observed_children'].items():
        ev.require(not ctl.owner_live({'pid': int(pid), 'create_time': created}), 'old descendant live')
    names = {'train_v5.py', 'train_with_checkpoint_io_v2.py', 'run_control.py', 'resume_control.py',
             'v6_public_opponent_matched_eval.py', 'v6_legacy_bridge_drift_audit.py', 'run_pair.py'}
    for proc in ctl.psutil.process_iter(['pid', 'cmdline']):
        if proc.pid != os.getpid():
            ev.require(not any(Path(arg).name in names for arg in proc.info['cmdline'] or []),
                       f'other poker job live: {proc.pid}')


def recovered_stage_directory(arm, stage):
    return RUN if (arm, stage) == ('static', 1) else ORIGINAL_STAGE_DIRECTORY(arm, stage)


def recovered_command(arm, stage, parent_path, parent_physical):
    argv = ORIGINAL_COMMAND(arm, stage, parent_path, parent_physical)
    ev.require(argv[2] == str(ctl.PRODUCTION), 'unexpected trainer command')
    argv[2] = str(WRAPPER)
    return argv


def recovery_accounting():
    totals, runs = ORIGINAL_ACCOUNTING()
    audit = ev.read_json(HERE / 'interruption_audit.json')
    totals['retained_training_hands'] = totals['new_training_hands'] + audit['new_retained_physical_hands']
    totals['retained_transition_hands'] = totals['new_transition_hands'] + audit['new_retained_transition_hands']
    totals['new_training_hands'] = totals['retained_training_hands'] + audit['observed_completed_but_uncheckpointed_physical_hands']
    totals['new_transition_hands'] = totals['retained_transition_hands'] + audit['observed_completed_but_uncheckpointed_transition_hands']
    totals['observed_uncheckpointed_training_hands'] = audit['observed_completed_but_uncheckpointed_physical_hands']
    runs['static_stage1_interrupted_retained'] = {
        'physical_hands': audit['retained_physical_hands'], 'iteration': audit['iteration'],
        'new_physical_hands': audit['new_retained_physical_hands'], 'checkpoint_sha256': SAVED_SHA}
    return totals, runs


def write_recovery_status(value):
    value['original_failure_status_preserved'] = str(BASE / 'status.json')
    value['unknown_additional_worker_tail_hands'] = None
    pending = HERE / 'status.pending.json'
    with pending.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(pending, HERE / 'status.json')


class Recovery(ctl.Controller):
    def __init__(self):
        require_dead()
        qualified = ev.read_json(HERE / 'recovery_preflight.json')
        ev.require(qualified['passed'], 'recovery preflight failed')
        ev.require(not RUN.exists() and not (HERE / 'ownership.json').exists(), 'recovery attempt already reserved')
        ev.require(shutil.disk_usage(BASE).free > 12 * 1024**3, 'insufficient disk space')
        original = ev.read_json(BASE / 'input_contract.json')
        audit = ev.read_json(HERE / 'interruption_audit.json')
        self.inputs = dict(qualified['input_sha256'])
        self.inputs[str(HERE / 'recovery_preflight.json')] = ctl.sha(HERE / 'recovery_preflight.json')
        ctl.check_hashes(self.inputs)
        self.sources = {p: digest for p, digest in self.inputs.items() if p.endswith('.py')}
        self.anchors = original['anchors']
        self.corpus = dict(original['prior_common_deck_corpus'])
        self.results = []
        self.partial = audit
        self.started, self.last_tick, self.child = time.perf_counter(), 0, None
        self.phase = 'QUALIFIED_SEED3_REMAINDER_READY'
        self.owner = {'pid': os.getpid(), 'create_time': ctl.psutil.Process().create_time(),
                      'started_at': datetime.now(timezone.utc).isoformat(),
                      'command': [sys.executable, '-u', str(Path(__file__))]}
        ctl.write_new(HERE / 'ownership.json', self.owner)
        ctl.write_new(HERE / 'input_contract.json', {'input_sha256': self.inputs,
                      'prior_common_deck_corpus': self.corpus, 'anchors': self.anchors,
                      'retained_parent_sha256': SAVED_SHA, 'original_algorithm_and_targets_unchanged': True,
                      'runtime_io_override': str(WRAPPER)})
        ctl.stage_directory = recovered_stage_directory
        ctl.training_command = recovered_command
        ctl.live_accounting = recovery_accounting
        ctl.write_status = write_recovery_status
        ctl.logger_update('--command', subprocess.list2cmdline(self.owner['command']),
            '--artifact', str(HERE / 'ownership.json'), '--artifact', str(HERE / 'input_contract.json'),
            '--note', 'Qualified same-record recovery owns writes. Retained1117/5314037 parent, full pending1118 assignment chain and explicit consumed metric view; fresh namespace and bounded I/O override. Original failed attempt remains immutable. No algorithm/seed/target/evaluation change.')

    def execute(self, argv, run, observer=None, training=False):
        def checked_observer(line):
            if observer:
                observer(line)
            if not training or '[Save] initial resume checkpoint' not in line:
                return
            import torch
            parent_path = Path(ev.read_json(run / 'parent_contract.json')['path'])
            parent = torch.load(parent_path, map_location='cpu', weights_only=False)
            initial = torch.load(run / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
            helper = ctl.qualified_command_helper()
            keys = ('model', 'optimizer', 'ppo_replay_entries', 'ppo_replay_rng_state', 'ppo_replay_cumulative_rows',
                    'pool_snapshots', 'pool_strategy', 'pool_active_metadata', 'pool_candidate_history')
            gates = {key: helper.equal(parent[key], initial[key]) for key in keys}
            gates['iteration'] = parent['iteration'] == initial['iteration']
            gates['transition_counter'] = parent['total_hands'] == initial['total_hands']
            gates['physical_counter'] = parent['environment_hand_accounting']['completed_hands'] == initial['environment_hand_accounting']['completed_hands']
            gates['fresh_namespace'] = initial['fixed_deal_attempt']['receipt']['namespace'] != self.partial['namespace']
            if parent.get('main_process_rng_state') is not None:
                gates['main_rng_restored_exact'] = helper.equal(parent['main_process_rng_state'], initial['main_process_rng_state'])
            else:
                gates['legacy_rng_bootstrap_declared'] = initial['fixed_deal_attempt']['legacy_rng_bootstrap'] is True
            ctl.write_new(run / 'initial_resume_gate.json', {'passed': all(gates.values()), 'gates': gates,
                'parent_sha256': ev.sha(parent_path), 'initial_sha256': ev.sha(run / 'initial_resumed_state.pt')})
            ev.require(all(gates.values()), 'actual initial resume state mismatch')
            ctl.logger_update('--artifact', str(run / 'initial_resume_gate.json'),
                              '--note', f'{run.name}: actual captured initial state passed full optimizer/replay/pool/RNG/counter verification.')
        return super().execute(argv, run, checked_observer if training else observer, training=training)

    def train(self, arm, stage):
        if (arm, stage) == ('static', 1):
            ctl.PARENT = VIEW / 'latest.pt'
            try:
                super().train(arm, stage)
            finally:
                ctl.PARENT = ORIGINAL_PARENT
        else:
            super().train(arm, stage)
        ev.require(self.results[-1]['namespace'] != self.partial['namespace'], 'failed attempt namespace reused')

    def run(self):
        try:
            self.train('static', 1)
            self.train('moving256', 1)
            stage1 = self.evaluate(1)
            if stage1['broad_collapse']:
                self.phase = 'PREREGISTERED_BROAD_COLLAPSE_RESEARCH_REVIEW'
            else:
                self.train('moving256', 2)
                self.train('static', 2)
                self.evaluate(2)
                self.phase = 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS'
            ctl.write_new(HERE / 'pipeline_result.json', {'phase': self.phase,
                'completed_attempts': self.results, 'interrupted_retained_attempt_audit': str(HERE / 'interruption_audit.json'),
                'wall_seconds': time.perf_counter() - self.started, 'original_pipeline_result_not_fabricated': True,
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
    Recovery().run()
