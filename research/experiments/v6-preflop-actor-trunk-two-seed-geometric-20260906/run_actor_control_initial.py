"""Fixed two-seed preflop actor-route control; single log owner."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import psutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PREVIOUS = ROOT / 'research/experiments/v6-current-kl-representation-pilot-20260905'
QUAL = ROOT / 'research/experiments/v6-preflop-actor-trunk-route-qualification-20260906'
PARENT_RUN = ROOT / 'research/experiments/v6-full-step-size-1m-continuation-20260905'
CANDIDATE = QUAL / 'candidate/scripts/alpha_holdem'
WRAPPER = BASE / 'train_candidate.py'
spec = importlib.util.spec_from_file_location('representation_helpers_for_lr', PREVIOUS / 'run_pilot.py')
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
evidence, execution, HELPER = prior.evidence, prior.execution, prior.HELPER
require, read, sha, write_new = prior.require, prior.read, prior.sha, prior.write_new
INITIAL_PHYSICAL = {1: 10498234, 3: 10492141}
DOSES = {1: 262144, 2: 1048576}
ORDERS = {1: ((1, 'detached'), (1, 'connected'), (3, 'connected'), (3, 'detached')),
          2: ((3, 'detached'), (3, 'connected'), (1, 'connected'), (1, 'detached'))}
PARENTS = {seed: PARENT_RUN / f'seed{seed}_full_stage2/latest.pt' for seed in INITIAL_PHYSICAL}
PARENT_SHA = {1: '8904f3b2e25baec5bc0bcb6556502c19b3fb213efdc9a32b16d55eee1284a3ef',
              3: 'f2249b0d19937ddadfc29fe5ba10cd7f07909d638dc0edeca89fae05b6f498e2'}
CONNECTED_SHA = {1: '799057d2d117302304e0c57bc6162840f2920c31623f8712b0c2125e26cceff5',
            3: '8c78563b97681c4af9b526fdeebcde704acee4e50cc0768cb9804e007e965c9c'}
QUAL_SHA = 'a5f6cfce6bc32535cc4f43231b69f30cd1d7e2ab748da175af4f65f7d88a705c'
# Only the reusable final training inspector reads these globals. No old paths,
# source files, old logger records, or production algorithms are changed.
prior.INITIAL_PHYSICAL, prior.DOSES = dict(INITIAL_PHYSICAL), dict(DOSES)
HELPER.PRODUCTION = CANDIDATE / 'train_v5.py'
HELPER.CANDIDATE_SHA = 'bcce947477fdcf6593b7a88ce6845bf5638ce6698b9462deeecf4133b05472e6'
GRADIENT = evidence.module_at('actor_route_contract', CANDIDATE / 'preflop_gradient_contract.py')


def route_audit(checkpoint, expected, parent):
    require(GRADIENT.checkpoint_flag(checkpoint) is expected, 'actual gradient route mismatch')
    GRADIENT.validate_resume(checkpoint['config'], checkpoint)
    require(checkpoint.get(GRADIENT.ORIGIN) == parent.get(GRADIENT.ORIGIN), 'gradient migration provenance lost')


def logger(*args):
    result = subprocess.run([sys.executable, str(ROOT / 'research/experiment_log.py'),
        'update', BASE.name, *args], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=45)
    require(result.returncode == 0, result.stderr)


execution.logger_update = logger


def directory(seed, arm, stage):
    require(seed in PARENTS and arm in ('detached', 'connected') and stage in DOSES, 'unknown cell')
    return BASE / f'seed{seed}_{arm}_stage{stage}'


def parent_path(seed, arm, stage):
    directory(seed, arm, stage)
    if stage == 2:
        return directory(seed, arm, 1) / 'latest.pt'
    return PARENTS[seed] if arm == 'detached' else QUAL / f'seed{seed}_connected_unstepped.pt'


def training_command(seed, arm, stage, parent, physical):
    run = directory(seed, arm, stage)
    argv = HELPER.command(run, parent, physical, 'multi8', BASE / 'attempt_registry')
    argv[2] = str(WRAPPER)
    require(argv.count('--all-policy-heads-only-training') == 1, 'ambiguous old head scope')
    argv.remove('--all-policy-heads-only-training')
    settings = {'--seed': 20263000 + seed, '--worker-seed-base': 2026300000 + seed * 100,
        '--fixed-training-deal-start-index': 36300000 + seed * 1000000,
        '--run-id': f'v6_nashpg_static_seed{seed}_20260903',
        '--total-environment-hands': INITIAL_PHYSICAL[seed] + DOSES[stage],
        '--max-runtime-seconds': 7200, '--mini-batch-size': 16384}
    for key, value in settings.items():
        execution.set_option(argv, key, value)
    argv += ['--source-policy-reference-refresh-updates', '0']
    if arm == 'connected':
        argv += ['--preflop-trunk-gradient']
    return argv


def evaluate_command(seed, arm, stage):
    checkpoint = directory(seed, arm, stage) / 'latest.pt'
    out = BASE / f'eval_seed{seed}_{arm}_stage{stage}'
    argv = [sys.executable, '-u', str(ROOT / 'scripts/alpha_holdem/v6_public_opponent_matched_eval.py'),
            '--control', str(PARENTS[seed]), '--treatment', str(checkpoint)]
    for name, path in execution.ANCHORS.items():
        argv += ['--anchor', f'{name}={path}']
    return argv + ['--pairs-per-anchor', '2048', '--seed', str(20264200 + seed * 10 + stage),
                   '--device', 'cuda', '--out-dir', str(out)]


def collapse_gate(contrast, endpoints):
    return evidence.broad_collapse(contrast) or any(evidence.broad_collapse(value) for value in endpoints.values())


class Controller:
    execute = execution.Controller.execute

    def __init__(self):
        import torch
        torch.set_num_threads(1)
        require(read(BASE / 'experiment.json')['status'] == 'RUNNING', 'record not running')
        require(not (BASE / 'ownership.json').exists(), 'prior owner needs review; no retry')
        scripts = {'train_v5.py', 'run_pilot.py', 'run_continuation.py', 'run_actor_control.py', 'train_candidate.py', 'train_with_checkpoint_io_45s.py',
                   'run_pair.py', 'v6_public_opponent_matched_eval.py', 'play_slumbot_v6_journaled.py'}
        conflicts = [p.pid for p in psutil.process_iter(['pid', 'cmdline']) if p.pid != os.getpid()
                     and any(Path(a).name in scripts for a in p.info['cmdline'] or [])]
        require(not conflicts, f'other poker owner: {conflicts}')
        require(shutil.disk_usage(BASE).free > 15 * 1024**3, 'less than15GiB free')
        require(sha(HELPER.PRODUCTION) == HELPER.CANDIDATE_SHA, 'production changed')
        require(read(QUAL / 'experiment.json')['status'] == 'COMPLETED' and sha(QUAL / 'qualification_v2.json') == QUAL_SHA,
                'actor-route qualification changed or incomplete')
        qualification = read(QUAL / 'qualification_v2.json')
        execution.check_hashes(qualification['input_sha256'])
        require(read(PARENT_RUN / 'experiment.json')['status'] == 'COMPLETED', 'parent not terminal')
        require(qualification['production_changed'] is False and qualification['passed'], 'route qualification failed')
        require(read(PREVIOUS / 'memory_16384.json')['passed'], 'previous same-regimen batch evidence failed')
        suites = list(ET.parse(BASE / 'controller_tests.xml').getroot().iter('testsuite'))
        require(suites and sum(int(s.get('tests', '0')) for s in suites) >= 20 and
                all(all(int(s.get(k, '0')) == 0 for k in ('failures', 'errors', 'skipped')) for s in suites), 'tests incomplete')
        self.started, self.last_tick = time.perf_counter(), 0
        self.owner = {'pid': os.getpid(), 'create_time': psutil.Process().create_time(),
                      'started_at': datetime.now(timezone.utc).isoformat()}
        self.child, self.results, self.phase = None, [], 'FREEZING_INPUTS'
        sources = list((ROOT / 'scripts/alpha_holdem').rglob('*.py')) + list(BASE.glob('*.py'))
        sources += list((QUAL / 'candidate/scripts').rglob('*.py')) + [WRAPPER]
        sources += [PREVIOUS / 'run_pilot.py', prior.OLD / 'run_control.py', prior.OLD / 'control_evidence.py',
            execution.GPU_HELPER, execution.GPU_HELPER.parent / 'run_cpu_resume_probe.py', execution.POOL_HELPER,
            prior.WRAPPER, prior.OLD / 'recovery_20260905/checkpoint_io_candidate.py', ROOT / 'research/experiment_log.py']
        self.sources = {str(p): sha(p) for p in sources}
        self.inputs = {**self.sources, **qualification['input_sha256'], str(QUAL / 'qualification_v2.json'): QUAL_SHA}
        for p in (BASE / 'protocol.md', BASE / 'controller_tests.xml', PREVIOUS / 'memory_16384.json'):
            self.inputs[str(p)] = sha(p)
        for seed, parent in PARENTS.items():
            connected = parent_path(seed, 'connected', 1)
            require(sha(parent) == PARENT_SHA[seed] and sha(connected) == CONNECTED_SHA[seed], 'parent changed')
            self.inputs.update({str(parent): PARENT_SHA[seed], str(connected): CONNECTED_SHA[seed]})
            checkpoint = torch.load(parent, map_location='cpu', weights_only=False)
            require(checkpoint['environment_hand_accounting']['completed_hands'] == INITIAL_PHYSICAL[seed], 'parent counter')
            require(len(checkpoint['optimizer']['state']) == 86, 'not full retained optimizer')
            self.inputs[checkpoint['fixed_deal_attempt']['path']] = checkpoint['fixed_deal_attempt']['sha256']
            origin = checkpoint.get('assignment_replay_origin')
            if origin and origin.get('migration_checkpoint'):
                self.inputs[origin['migration_checkpoint']] = origin['migration_checkpoint_sha256']
            for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl', 'run_manifest.json'):
                self.inputs[str(parent.parent / name)] = sha(parent.parent / name)
            del checkpoint
        for name, path in execution.ANCHORS.items():
            require(sha(path) == execution.ANCHOR_SHA256[name], 'anchor changed')
            self.inputs[str(path)] = sha(path)
        for name in ('slumbot_free_anchor_position10m.pt', 'corrected_cfr96_anchor10.pt'):
            path = ROOT.parent / 'CardPilot_legacy_20260829/selected_assets/opponents' / name
            self.inputs[str(path)] = sha(path)
        self.corpus = {str(p): sha(p) for p in (ROOT / 'research/experiments').rglob('common_deck_pairs.jsonl.gz')
                       if not p.is_relative_to(BASE)}
        execution.check_hashes(self.inputs)
        write_new(BASE / 'ownership.json', self.owner)
        write_new(BASE / 'input_contract.json', {'input_sha256': self.inputs, 'prior_common_deck_corpus': self.corpus,
            'orders': ORDERS, 'doses': DOSES, 'initial_physical_hands': INITIAL_PHYSICAL,
            'production_unchanged': True, 'statistical_not_bitwise_worker_continuation': True})
        logger('--artifact', str(BASE / 'input_contract.json'), '--artifact', str(BASE / 'ownership.json'),
               '--command', subprocess.list2cmdline([sys.executable, *sys.argv]))

    def tick(self, force=False):
        if not force and time.perf_counter() - self.last_tick < 60:
            return
        require(execution.owner_live(self.owner), 'ownership lost')
        execution.check_hashes(self.sources)
        totals = {'new_training_hands': 0, 'new_transition_hands': 0, 'evaluation_hands': 0,
                  'slumbot_hands': 0, 'final_qualification_hands': 0, 'offline_samples': 0}
        runs = {}
        for stage, order in ORDERS.items():
            for seed, arm in order:
                run = directory(seed, arm, stage)
                if not (run / 'parent_contract.json').exists():
                    continue
                parent = read(run / 'parent_contract.json')
                rows = execution.complete_jsonl(run / 'h1_training_metrics.jsonl')
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
                require(physical >= parent['physical_hands'] and trans >= parent['transition_hands'], 'live counter reset')
                totals['new_training_hands'] += physical - parent['physical_hands']
                totals['new_transition_hands'] += trans - parent['transition_hands']
                runs[run.name] = {'physical_hands': physical, 'iteration': rows[-1]['iteration'],
                                 'target': INITIAL_PHYSICAL[seed] + DOSES[stage]}
        for path in BASE.glob('eval_*/common_deck_pairs.jsonl.gz'):
            totals['evaluation_hands'] += 4 * execution.gzip_count(path)
        status = {**self.owner, 'phase': self.phase, 'updated_at': datetime.now(timezone.utc).isoformat(),
                  'active_child_pid': self.child.pid if self.child and self.child.poll() is None else None,
                  'accounting': totals, 'runs': runs, 'wall_seconds': time.perf_counter() - self.started}
        from research.experiment_log import atomic_json
        atomic_json(BASE / 'status.json', status)
        logger(*[part for key, value in totals.items() for part in ('--count', f'{key}={value}')],
               '--metric', f'controller_phase={self.phase}')
        print(json.dumps(status), flush=True)
        self.last_tick = time.perf_counter()

    def train(self, seed, arm, stage):
        import torch
        path = parent_path(seed, arm, stage)
        source_dir = PARENTS[seed].parent if stage == 1 else path.parent
        digest = sha(path)
        if stage == 2:
            require(digest == read(path.parent / 'verification.json')['checkpoint_sha256'], 'stage1 changed')
        parent = torch.load(path, map_location='cpu', weights_only=False)
        old = int(parent['environment_hand_accounting']['completed_hands'])
        require(old < INITIAL_PHYSICAL[seed] + DOSES[stage], 'target already satisfied')
        expected_lr = 9.999999999999996e-05
        route_audit(parent, arm == 'connected', parent)
        require(parent['optimizer']['param_groups'][0]['lr'] == expected_lr, 'wrong arm LR')
        run = directory(seed, arm, stage)
        run.mkdir()
        write_new(run / 'parent_contract.json', {'path': str(path), 'sha256': digest, 'physical_hands': old,
            'transition_hands': parent['total_hands'], 'iteration': parent['iteration'], 'actual_lr': expected_lr})
        prefixes = {}
        for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
            source = source_dir / name
            prefixes[name] = {'path': str(source), 'sha256': sha(source), 'bytes': source.stat().st_size}
            shutil.copy2(source, run / name)
        write_new(run / 'prefixes.json', prefixes)
        shutil.copy2(HELPER.PRODUCTION, run / 'trainer_source.py')

        def capture(line):
            if '[Save] initial resume checkpoint' in line:
                target = run / 'initial_resumed_state.pt'
                require(not target.exists(), 'initial evidence overwrite')
                shutil.copy2(run / 'latest.pt', target)
                initial = torch.load(target, map_location='cpu', weights_only=False)
                prior.initial_audit(parent, initial, True)
                route_audit(initial, arm == 'connected', parent)
                logger('--metric', 'training_started=true', '--artifact', str(target),
                       '--note', f'{run.name}: exact actual initial full-network model/optimizer/replay/counters/RNG/pool checked;LR={expected_lr}.')

        self.phase = f'TRAINING_{run.name}'
        wall = self.execute(training_command(seed, arm, stage, path, old), run, capture, training=True)
        for name, info in prefixes.items():
            with (run / name).open('rb') as handle:
                require(hashlib.sha256(handle.read(info['bytes'])).hexdigest() == info['sha256'] == sha(info['path']),
                        'raw prefix changed')
        # Both arms are full trainable scope. The reused inspector receives that scope,
        # while the result is explicitly labeled with its gradient-route arm.
        result = prior.inspect_training(run, parent, path, digest, seed, 'full', stage, wall)
        require(not result['optimizer_audit']['new_state_ids'], 'invented new full-network optimizer states')
        final = torch.load(run / 'latest.pt', map_location='cpu', weights_only=False)
        route_audit(final, arm == 'connected', parent)
        result.update(arm=arm, actual_lr=expected_lr, training_scope='full_network', preflop_trunk_gradient=(arm == 'connected'))
        del final
        require(result['namespace'] not in [r['namespace'] for r in self.results], 'namespace reused')
        write_new(run / 'verification.json', result)
        self.results.append(result)
        for name in ('latest.pt', 'verification.json', 'termination.json', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
            artifact = run / name
            self.inputs[str(artifact)] = sha(artifact)
            logger('--artifact', str(artifact))
        self.tick(force=True)

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
                require(summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 32768
                    and summary['policy_mode'] == 'greedy' and summary['starting_stack_bb'] == 200
                    and summary['observation_style'] == 'legacy_v4', 'evaluation contract/count mismatch')
                require(len(rows) == len(evidence.validated_map(rows)) == 8192, 'raw pair count')
                require(summary['raw_pairs_sha256'] == sha(out / 'common_deck_pairs.jsonl.gz'), 'raw SHA mismatch')
                require(summary['input_sha256'] == {'control': PARENT_SHA[seed],
                    'treatment': sha(directory(seed, arm, stage) / 'latest.pt'),
                    **{f'anchor:{k}': v for k, v in execution.ANCHOR_SHA256.items()}}, 'eval weights changed')
                for name in execution.ANCHORS:
                    selected = [r for r in rows if r['anchor'] == name]
                    require(len(selected) == 2048 and sorted(r['pair_index'] for r in selected) == list(range(2048)), 'anchor coverage')
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
        result = {'passed': True, 'stage': stage, 'evaluation_hands': 131072, 'seeds': results,
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
        for stage in (1, 2):
            for seed, arm in ORDERS[stage]:
                self.train(seed, arm, stage)
            if self.evaluate(stage)['broad_collapse']:
                self.phase = f'STAGE{stage}_BROAD_COLLAPSE_REVIEW'
                break
        else:
            self.phase = 'FIXED_DOSE_COMPLETE_NEEDS_RESEARCH_REVIEW'
        write_new(BASE / 'controller_result.json', {'phase': self.phase, 'training': self.results,
            'wall_seconds': time.perf_counter() - self.started, 'goal_achieved': False})
        logger('--artifact', str(BASE / 'controller_result.json'))
        self.tick(force=True)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    controller = Controller()
    try:
        controller.run()
    except Exception as exc:
        controller.phase = 'SAFE_BOUNDARY_NEEDS_REVIEW' if isinstance(exc, execution.SafeBoundary) else 'ERROR_PRESERVED_NEEDS_REVIEW'
        write_new(BASE / 'controller_error.json', {'error': repr(exc), 'phase': controller.phase,
            'created_at': datetime.now(timezone.utc).isoformat(), 'automatic_retry': False})
        controller.tick(force=True)
        raise


if __name__ == '__main__':
    main()
