"""Bounded same-regimen four-branch continuation; inherited immutable execution core."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
OLD = ROOT / 'research/experiments/v6-preflop-actor-trunk-two-seed-geometric-20260906'
EXTERNAL = ROOT / 'research/experiments/v6-preflop-actor-route-two-seed-external-fresh80k-20260906'
sys.path.insert(0, str(OLD))
import run_actor_control as ctl

require, read, sha, write_new = ctl.require, ctl.read, ctl.sha, ctl.write_new
execution, evidence, PARENTS, PARENT_SHA = ctl.execution, ctl.evidence, ctl.PARENTS, ctl.PARENT_SHA
INITIAL_PHYSICAL = dict(ctl.INITIAL_PHYSICAL)
DOSES = {3: 2097152}
ORDER = ((1, 'detached'), (1, 'connected'), (3, 'connected'), (3, 'detached'))
CURRENT = {
    (1,'detached'): ('21d5c5b02477e93fd83add0e8c8fc519916dfa9515967e9a24143d1441205806',11547070,2437),
    (1,'connected'): ('d6a6c3433db95ca50e8d36120ada58c348589da68de7845c0a7781e22a497785',11551174,2441),
    (3,'detached'): ('b3ba8a3d56ed31c89c06ff2dfe2302c5f2fbb62dd82469ae084062a311f2ed1b',11542774,2446),
    (3,'connected'): ('132c76fdc593dd2b9655239c84f604073e2123d8e0fa042d26d7e1742ba660c9',11543121,2443),
}
OLD_CONTROLLER_SHA = '3459dff9c18c53340226aa4b75d02f80f031cb4429280eb91a3034526b0d744d'
EXPECTED_LR = 9.999999999999996e-05
EVAL_SEEDS = {1:20264411,3:20264431}
ALLOWED_COMMAND_CHANGES = ('--total-environment-hands','--resume','--run-dir','--out',
                           '--opponent-assignment-provenance-file','--deal-attempt-registry')


def directory(seed, arm, stage):
    require((seed,arm) in CURRENT and stage == 3, 'unknown continuation cell')
    return BASE / f'seed{seed}_{arm}_stage3'


def parent_path(seed, arm, stage):
    directory(seed, arm, stage)
    return OLD / f'seed{seed}_{arm}_stage2/latest.pt'


# Isolated module-global routing only. No old file, logger record or trainer edit.
ctl.BASE, ctl.DOSES, ctl.ORDERS = BASE, DOSES, {3:ORDER}
ctl.directory, ctl.parent_path = directory, parent_path
ctl.prior.INITIAL_PHYSICAL, ctl.prior.DOSES = INITIAL_PHYSICAL, DOSES
training_command, logger, collapse_gate = ctl.training_command, ctl.logger, ctl.collapse_gate


def normalized_training_command(argv):
    result = list(argv)
    for flag in ALLOWED_COMMAND_CHANGES:
        require(result.count(flag) == 1, 'ambiguous continuation flag: '+flag)
        result[result.index(flag)+1] = '<BOUND-CONTINUATION>'
    return result


def evaluate_command(seed, arm, stage):
    out = BASE / f'eval_seed{seed}_{arm}_stage{stage}'
    argv = [sys.executable,'-u',str(ROOT/'scripts/alpha_holdem/v6_public_opponent_matched_eval.py'),
            '--control',str(PARENTS[seed]),'--treatment',str(directory(seed,arm,stage)/'latest.pt')]
    for name,path in execution.ANCHORS.items():
        argv += ['--anchor',f'{name}={path}']
    return argv + ['--pairs-per-anchor','512','--seed',str(EVAL_SEEDS[seed]),
                   '--device','cuda','--out-dir',str(out)]


def reject_live_poker():
    scripts = {'train_v5.py','run_scale.py','run_actor_control.py','resume_actor.py',
               'train_candidate.py','run_pair.py','v6_public_opponent_matched_eval.py',
               'play_slumbot_v6_journaled.py','run_continuation.py','run_pilot.py'}
    conflicts = [p.pid for p in ctl.psutil.process_iter(['pid','cmdline']) if p.pid != os.getpid()
                 and any(Path(a).name in scripts for a in p.info['cmdline'] or [])]
    require(not conflicts, f'other poker owner live: {conflicts}')


def initial_gate(parent, initial, known):
    ctl.prior.initial_audit(parent, initial, True)
    expected = ctl.GRADIENT.checkpoint_flag(parent)
    ctl.route_audit(initial, expected, parent)
    receipt = initial['fixed_deal_attempt']
    namespace = receipt['receipt']['namespace']
    require(namespace not in known and namespace != parent['fixed_deal_attempt']['receipt']['namespace'],
            'namespace reused')
    require(ctl.HELPER.helpers.load_attempt(Path(receipt['path']),receipt['sha256']) == receipt['receipt'],
            'initial attempt receipt changed')
    return {'passed':True,'namespace':namespace,'preflop_trunk_gradient':expected,
            'initial_keys_verified':list(ctl.prior.INITIAL_KEYS),
            'statistical_not_bitwise_worker_continuation':True}


class Controller(ctl.Controller):
    def __init__(self):
        import torch
        torch.set_num_threads(1)
        reject_live_poker()
        require(read(BASE/'experiment.json')['status'] == 'RUNNING', 'record not running')
        require(not (BASE/'ownership.json').exists(), 'old attempt requires review; no auto retry')
        require(all(not directory(seed,arm,3).exists() for seed,arm in ORDER), 'existing run preserved')
        qualified = read(BASE/'qualification.json')
        require(qualified['passed'] and qualified['new_training_hands'] == 0, 'preflight incomplete')
        self.inputs = {**qualified['input_sha256'],str(BASE/'qualification.json'):sha(BASE/'qualification.json')}
        execution.check_hashes(self.inputs)
        self.sources = {p:h for p,h in self.inputs.items() if p.endswith('.py')}
        require(shutil.disk_usage(BASE).free > 15*1024**3, 'insufficient space')
        self.corpus = dict(qualified['prior_common_deck_corpus'])
        self.known_namespaces = set(qualified['known_attempt_namespaces'])
        self.started, self.last_tick, self.child = time.perf_counter(),0,None
        self.results, self.phase = [],'QUALIFIED_UNCHANGED_REGIMEN_READY'
        environment = {name:os.environ.get(name) for name in (
            'PYTHONDONTWRITEBYTECODE','OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS')}
        require(all(value == '1' for value in environment.values()),'wrong worker environment')
        self.owner = {'pid':os.getpid(),'create_time':ctl.psutil.Process().create_time(),
                      'started_at':datetime.now(timezone.utc).isoformat(),
                      'command':sys.orig_argv,'environment':environment}
        write_new(BASE/'ownership.json',self.owner)
        write_new(BASE/'input_contract.json',{'input_sha256':self.inputs,
            'prior_common_deck_corpus':self.corpus,'orders':{3:ORDER},'doses':DOSES,
            'original_split_physical_hands':INITIAL_PHYSICAL,
            'known_attempt_namespaces':sorted(self.known_namespaces),
            'earlier_unknown_lineage_tail_hands':None,
            'unchanged_training_regimen':True,'internal_evaluation_hands':32768,
            'automatic_external_or_larger_scale':False})
        logger('--command',subprocess.list2cmdline(sys.orig_argv),
               '--artifact',str(BASE/'ownership.json'),'--artifact',str(BASE/'input_contract.json'))

    def execute(self, argv, run, observer=None, training=False):
        def capture(line):
            if observer:
                observer(line)
            if not training or '[Save] initial resume checkpoint' not in line:
                return
            import torch
            parent = torch.load(read(run/'parent_contract.json')['path'],map_location='cpu',weights_only=False)
            initial = torch.load(run/'initial_resumed_state.pt',map_location='cpu',weights_only=False)
            gate = initial_gate(parent,initial,self.known_namespaces)
            gate['parent_sha256'] = read(run/'parent_contract.json')['sha256']
            gate['initial_sha256'] = sha(run/'initial_resumed_state.pt')
            self.known_namespaces.add(gate['namespace'])
            write_new(run/'initial_resume_gate.json',gate)
            logger('--artifact',str(run/'initial_resume_gate.json'))
        return ctl.Controller.execute(self,argv,run,capture if training else observer,training=training)

    def evaluate(self, stage):
        results, fresh_rows = {}, []
        for seed in (1, 3):
            arms = {}
            for arm in ('detached', 'connected'):
                out = BASE / f'eval_seed{seed}_{arm}_stage{stage}'
                job = BASE / f'job_{out.name}'
                job.mkdir()
                self.phase = f'EVALUATING_{out.name}'
                self.execute(evaluate_command(seed, arm, stage), job)
                summary, rows = read(out / 'summary.json'), evidence.read_rows(out / 'common_deck_pairs.jsonl.gz')
                require(summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 8192
                    and summary['policy_mode'] == 'greedy' and summary['starting_stack_bb'] == 200
                    and summary['observation_style'] == 'legacy_v4', 'evaluation contract/count mismatch')
                require(len(rows) == len(evidence.validated_map(rows)) == 2048, 'raw pair count')
                require(summary['raw_pairs_sha256'] == sha(out / 'common_deck_pairs.jsonl.gz'), 'raw SHA mismatch')
                require(summary['input_sha256'] == {'control': PARENT_SHA[seed],
                    'treatment': sha(directory(seed, arm, stage) / 'latest.pt'),
                    **{f'anchor:{k}': v for k, v in execution.ANCHOR_SHA256.items()}}, 'eval weights changed')
                for name in execution.ANCHORS:
                    selected = [r for r in rows if r['anchor'] == name]
                    require(len(selected) == 512 and sorted(r['pair_index'] for r in selected) == list(range(512)), 'anchor coverage')
                arms[arm] = rows
                for name in ('summary.json', 'common_deck_pairs.jsonl.gz'):
                    logger('--artifact', str(out / name))
            contrast = evidence.summarize_rows(evidence.join_arms(arms['detached'], arms['connected']))
            endpoints = {arm: evidence.summarize_rows(rows) for arm, rows in arms.items()}
            results[str(seed)] = {'connected_minus_detached': contrast, 'endpoint_minus_parent': endpoints,
                'absolute_vs_anchors': {arm: evidence.summarize_rows([
                    evidence.derived_row(r, [0., 0.], r['treatment_rewards_bb']) for r in rows]) for arm, rows in arms.items()},
                'broad_collapse': collapse_gate(contrast, endpoints)}
            fresh_rows += arms['detached']
        require(len({tuple(r['deck']) for r in fresh_rows}) == len(fresh_rows), 'cross-seed overlap')
        self.phase = f'AUDITING_FRESHNESS_stage{stage}'
        self.tick(force=True)
        freshness = evidence.check_prior_decks(fresh_rows, self.corpus)
        result = {'passed': True, 'stage': stage, 'evaluation_hands': 32768, 'seeds': results,
            'freshness': freshness, 'broad_collapse': any(r['broad_collapse'] for r in results.values()),
            'ci_scope': 'conditional nominal paired-deck means,not training-seed population or external strength',
            'automatic_final_qualification': False}
        write_new(BASE / f'stage{stage}_analysis.json', result)
        for path in BASE.glob(f'eval_*_stage{stage}/common_deck_pairs.jsonl.gz'):
            self.corpus[str(path)] = sha(path)
        logger('--artifact', str(BASE / f'stage{stage}_analysis.json'))
        self.tick(force=True)
        return result


    def run(self):
        try:
            for seed,arm in ORDER:
                self.train(seed,arm,3)
            final = self.evaluate(3)
            self.phase = 'FIXED_2M_COMPLETE_NEEDS_RESEARCH_REVIEW'
            write_new(BASE/'controller_result.json',{'phase':self.phase,'training':self.results,
                'internal_broad_collapse':final['broad_collapse'],
                'new_training_hands':sum(row['new_physical_hands'] for row in self.results),
                'new_replay_rows':sum(row['new_replay_rows'] for row in self.results),
                'evaluation_hands':32768,'slumbot_hands':0,'final_qualification_hands':0,
                'wall_seconds':time.perf_counter()-self.started,'goal_achieved':False,
                'automatic_next_scale':False,'earlier_unknown_lineage_tail_hands':None})
            logger('--artifact',str(BASE/'controller_result.json'))
        except BaseException as exc:
            self.phase = 'SAFE_BOUNDARY_NEEDS_REVIEW' if isinstance(exc,execution.SafeBoundary) else 'ERROR_PRESERVED_NEEDS_REVIEW'
            write_new(BASE/'controller_error.json',{'phase':self.phase,'error':repr(exc),
                'created_at':datetime.now(timezone.utc).isoformat(),'automatic_retry':False})
            if self.child is not None:
                while self.child.poll() is None:
                    time.sleep(2)
            self.child = None
            raise
        finally:
            self.tick(force=True)


if __name__ == '__main__':
    Controller().run()

