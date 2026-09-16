"""Reviewed same-record remainder; retain original attempts and fixed research plan."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import audit_interruption as audit

ctl, HERE, BASE, ROOT = audit.ctl, audit.HERE, audit.BASE, audit.ROOT
require, read, sha = ctl.require, ctl.read, ctl.sha
OLD = audit.RUN
RUN = HERE / 'seed1_connected_stage1_remainder'
SAVED_SHA = '9bc206c103b925ce7e77b62eadd0cc92575e1f35d6d7bfe59cee2fa9c274478b'
ORIGINAL_DIRECTORY = ctl.directory
ORIGINAL_PARENT_PATH = ctl.parent_path
REST_OF_STAGE1 = ((3, 'connected'), (3, 'detached'))


def recovered_directory(seed, arm, stage):
    original = ORIGINAL_DIRECTORY(seed, arm, stage)
    return RUN if (seed, arm, stage) == (1, 'connected', 1) else original


def recovered_parent_path(seed, arm, stage):
    if (seed, arm, stage) == (1, 'connected', 1):
        return OLD / 'latest.pt'
    return ORIGINAL_PARENT_PATH(seed, arm, stage)


def add_interrupted_accounting(totals, partial):
    result = dict(totals)
    result['retained_training_hands'] = result['new_training_hands'] + partial['new_retained_physical_hands']
    result['retained_transition_hands'] = result['new_transition_hands'] + partial['new_retained_transition_hands']
    result['observed_uncheckpointed_training_hands'] = partial['observed_completed_but_uncheckpointed_physical_hands']
    result['new_training_hands'] = result['retained_training_hands'] + result['observed_uncheckpointed_training_hands']
    result['new_transition_hands'] = result['retained_transition_hands'] + partial['observed_completed_but_uncheckpointed_transition_hands']
    return result


def initial_gate(parent, initial, known_namespaces):
    ctl.prior.initial_audit(parent, initial, True)
    expected = ctl.GRADIENT.checkpoint_flag(parent)
    ctl.route_audit(initial, expected, parent)
    namespace = initial['fixed_deal_attempt']['receipt']['namespace']
    require(namespace not in known_namespaces, 'attempt namespace reused')
    require(namespace != parent['fixed_deal_attempt']['receipt']['namespace'], 'parent namespace reused')
    return {'passed': True, 'initial_state_keys_verified': list(ctl.prior.INITIAL_KEYS),
            'gradient_route': expected, 'fresh_namespace': namespace,
            'statistical_not_bitwise_worker_continuation': True}


class Recovery(ctl.Controller):
    def __init__(self):
        import torch
        torch.set_num_threads(1)
        audit.require_dead()
        require(read(BASE / 'experiment.json')['status'] == 'RUNNING', 'record not running')
        require(not RUN.exists() and not (HERE / 'ownership.json').exists(), 'recovery already reserved; review')
        require(shutil.disk_usage(BASE).free > 15 * 1024**3, 'insufficient disk space')
        qualified = read(HERE / 'recovery_preflight.json')
        require(qualified['passed'] and qualified['checkpoint_sha256'] == SAVED_SHA, 'unqualified boundary')
        self.inputs = {**qualified['input_sha256'], str(HERE / 'recovery_preflight.json'): sha(HERE / 'recovery_preflight.json')}
        ctl.execution.check_hashes(self.inputs)
        self.sources = {p: digest for p, digest in self.inputs.items() if p.endswith('.py')}
        original = read(BASE / 'input_contract.json')
        require(not list(BASE.glob('stage*_analysis.json')), 'unexpected completed evaluation; do not rerun')
        self.corpus = dict(original['prior_common_deck_corpus'])
        self.partial = read(HERE / 'interruption_audit.json')
        completed = read(BASE / 'seed1_detached_stage1/verification.json')
        require(completed['passed'] and completed['new_physical_hands'] == 266415 and
                sha(BASE / 'seed1_detached_stage1/latest.pt') == completed['checkpoint_sha256'], 'completed control changed')
        self.results = [completed]
        self.started, self.last_tick, self.child = time.perf_counter(), 0, None
        self.phase = 'REVIEWED_CONNECTED_REMAINDER_READY'
        environment = {name: os.environ.get(name) for name in (
            'PYTHONDONTWRITEBYTECODE', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS')}
        require(all(value == '1' for value in environment.values()), 'unexpected execution environment')
        self.owner = {'pid': os.getpid(), 'create_time': ctl.psutil.Process().create_time(),
                      'started_at': datetime.now(timezone.utc).isoformat(),
                      'command': [sys.executable, *sys.orig_argv[1:]], 'environment': environment}
        ctl.directory, ctl.parent_path = recovered_directory, recovered_parent_path
        ctl.write_new(HERE / 'ownership.json', self.owner)
        ctl.write_new(HERE / 'input_contract.json', {'input_sha256': self.inputs,
            'prior_common_deck_corpus': self.corpus, 'orders': ctl.ORDERS, 'doses': ctl.DOSES,
            'initial_physical_hands': ctl.INITIAL_PHYSICAL, 'original_input_contract': str(BASE / 'input_contract.json'),
            'logical_endpoint_overrides': {'seed1_connected_stage1': str(RUN)},
            'interrupted_attempt_audit': str(HERE / 'interruption_audit.json'),
            'original_algorithm_and_evaluation_unchanged': True, 'unknown_additional_worker_tail_hands': None})
        ctl.logger('--command', subprocess.list2cmdline(self.owner['command']),
                   '--artifact', str(HERE / 'ownership.json'), '--artifact', str(HERE / 'input_contract.json'),
                   '--metric', f'active_recovery_directory={HERE}',
                   '--note', 'Qualified reviewed recovery owns this same record. Original attempts remain immutable; completed detached cell is not rerun. Connected remainder starts from exact2217 checkpoint with pending2218 evidence and a new managed namespace. Unknown in-flight tail remains unknown; no algorithm/seed/target/evaluation change.')

    def tick(self, force=False):
        if not force and time.perf_counter() - self.last_tick < 60:
            return
        require(ctl.execution.owner_live(self.owner), 'ownership lost')
        ctl.execution.check_hashes(self.sources)
        totals = {'new_training_hands': 0, 'new_transition_hands': 0, 'evaluation_hands': 0,
                  'slumbot_hands': 0, 'final_qualification_hands': 0, 'offline_samples': 0}
        runs = {}
        for stage, order in ctl.ORDERS.items():
            for seed, arm in order:
                run = recovered_directory(seed, arm, stage)
                if not (run / 'parent_contract.json').exists():
                    continue
                parent = read(run / 'parent_contract.json')
                rows = ctl.execution.complete_jsonl(run / 'h1_training_metrics.jsonl')
                if not rows:
                    continue
                physical, trans = rows[-1]['environment_hand_accounting']['completed_hands'], rows[-1]['hands']
                if (run / 'run_manifest.json').exists():
                    try:
                        manifest = read(run / 'run_manifest.json')
                        if manifest.get('status') == 'finished':
                            physical, trans = manifest['environment_hand_accounting']['completed_hands'], manifest['total_hands']
                    except json.JSONDecodeError:
                        pass
                require(physical >= parent['physical_hands'] and trans >= parent['transition_hands'], 'counter reset')
                totals['new_training_hands'] += physical - parent['physical_hands']
                totals['new_transition_hands'] += trans - parent['transition_hands']
                runs[f'seed{seed}_{arm}_stage{stage}'] = {'directory': str(run), 'physical_hands': physical,
                    'iteration': rows[-1]['iteration'], 'target': ctl.INITIAL_PHYSICAL[seed] + ctl.DOSES[stage]}
        for path in BASE.glob('eval_*/common_deck_pairs.jsonl.gz'):
            totals['evaluation_hands'] += 4 * ctl.execution.gzip_count(path)
        totals = add_interrupted_accounting(totals, self.partial)
        status = {**self.owner, 'phase': self.phase, 'updated_at': datetime.now(timezone.utc).isoformat(),
            'active_child_pid': self.child.pid if self.child and self.child.poll() is None else None,
            'accounting': totals, 'runs': runs, 'wall_seconds': time.perf_counter() - self.started,
            'original_status_preserved': str(BASE / 'status.json'), 'unknown_additional_worker_tail_hands': None,
            'interrupted_retained_physical_hands': self.partial['new_retained_physical_hands']}
        from research.experiment_log import atomic_json
        atomic_json(HERE / 'status.json', status)
        ctl.logger(*[part for key, value in totals.items() for part in ('--count', f'{key}={value}')],
                   '--metric', f'controller_phase={self.phase}')
        print(json.dumps(status), flush=True)
        self.last_tick = time.perf_counter()

    def execute(self, argv, run, observer=None, training=False):
        def capture(line):
            if observer:
                observer(line)
            if not training or '[Save] initial resume checkpoint' not in line:
                return
            import torch
            parent_path = Path(read(run / 'parent_contract.json')['path'])
            parent = torch.load(parent_path, map_location='cpu', weights_only=False)
            initial = torch.load(run / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
            known = {self.partial['namespace'], *(r['namespace'] for r in self.results)}
            gate = initial_gate(parent, initial, known)
            gate.update(parent_sha256=sha(parent_path), initial_sha256=sha(run / 'initial_resumed_state.pt'))
            ctl.write_new(run / 'initial_resume_gate.json', gate)
            ctl.logger('--artifact', str(run / 'initial_resume_gate.json'))
        return ctl.Controller.execute(self, argv, run, capture if training else observer, training=training)

    def train(self, seed, arm, stage):
        # Original train() takes stage1 log prefixes from PARENTS[seed].parent.
        # Redirect that source only for the interrupted cell, then restore it
        # even on failure so evaluation still uses the ORIGINAL preregistered parent.
        original = ctl.PARENTS[1]
        try:
            if (seed, arm, stage) == (1, 'connected', 1):
                require(sha(OLD / 'latest.pt') == SAVED_SHA, 'interrupted checkpoint changed')
                ctl.PARENTS[1] = OLD / 'latest.pt'
            super().train(seed, arm, stage)
        finally:
            ctl.PARENTS[1] = original
        require(self.results[-1]['namespace'] != self.partial['namespace'], 'interrupted namespace reused')
        if (seed, arm, stage) == (1, 'connected', 1):
            text = (RUN / 'latest_train.log').read_text(encoding='utf-8')
            # Detailed assignment RNG validation is in the preflight and retained
            # full prefix. The whole attempt remains available to terminal review.
            require('[ 2218]' in text or '[2218]' in text, 'missing first resumed update')

    def run(self):
        try:
            self.train(1, 'connected', 1)
            for seed, arm in REST_OF_STAGE1:
                self.train(seed, arm, 1)
            if self.evaluate(1)['broad_collapse']:
                self.phase = 'STAGE1_BROAD_COLLAPSE_REVIEW'
            else:
                for seed, arm in ctl.ORDERS[2]:
                    self.train(seed, arm, 2)
                final = self.evaluate(2)
                self.phase = 'STAGE2_BROAD_COLLAPSE_REVIEW' if final['broad_collapse'] else 'FIXED_DOSE_COMPLETE_NEEDS_RESEARCH_REVIEW'
            ctl.write_new(HERE / 'controller_result.json', {'phase': self.phase, 'training': self.results,
                'wall_seconds': time.perf_counter() - self.started, 'goal_achieved': False,
                'interrupted_attempt_audit': str(HERE / 'interruption_audit.json'),
                'original_controller_result_not_fabricated': True})
            ctl.logger('--artifact', str(HERE / 'controller_result.json'))
        except BaseException as exc:
            self.phase = 'SAFE_BOUNDARY_NEEDS_REVIEW' if isinstance(exc, ctl.execution.SafeBoundary) else 'ERROR_PRESERVED_NEEDS_REVIEW'
            ctl.write_new(HERE / 'controller_error.json', {'phase': self.phase, 'error': repr(exc),
                'created_at': datetime.now(timezone.utc).isoformat(), 'automatic_retry': False})
            if self.child is not None:
                while self.child.poll() is None:
                    time.sleep(2)
            self.child = None
            raise
        finally:
            self.tick(force=True)


if __name__ == '__main__':
    Recovery().run()
