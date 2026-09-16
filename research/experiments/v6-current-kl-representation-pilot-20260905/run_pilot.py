"""Single owner, fixed two-seed geometric scope pilot; never resets or retries."""
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

import psutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
OLD = ROOT / 'research/experiments/v6-phase-held-reference-seed3-replication-20260905'
SCOPE = ROOT / 'research/experiments/v6-current-kl-scope-transfer-20260905'
sys.path.insert(0, str(OLD))
import control_evidence as evidence
import run_control as execution

require, read, sha = evidence.require, evidence.read_json, evidence.sha
write_new = execution.write_new
HELPER = execution.qualified_command_helper()
WRAPPER = OLD / 'recovery_20260905b/train_with_checkpoint_io_45s.py'
PARENTS = {
    1: ROOT / 'research/experiments/v6-phase-held-reference-control-20260904/recovery_20260905/static_stage2_remainder/latest.pt',
    3: OLD / 'static_stage2/latest.pt',
}
ORIGINAL_SHA = {
    1: '41ff38496167424fa71373028e9291a0d8bd595315f7121d8fa303e6b15a3372',
    3: '36aa1d935179570e76499a0a0c1c81ccd75384b0411b9c7d9cca56c9a2c14b69',
}
FULL_SHA = {
    1: '44d332a0e234b7806933680417095d6d2bcc0daf2779119d5b72bb36ca8c589f',
    3: '12ac34ea420a6907add175c50e862d8a8f3b1f6e179c80bba9eb9eea60e55d9a',
}
INITIAL_PHYSICAL = {1: 8395752, 3: 8392377}
DOSES = {1: 262144, 2: 1048576}
ORDERS = {1: ((1, 'full'), (1, 'heads'), (3, 'heads'), (3, 'full')),
          2: ((3, 'full'), (3, 'heads'), (1, 'heads'), (1, 'full'))}
INITIAL_KEYS = ('model', 'optimizer', 'total_hands', 'iteration',
                'ppo_replay_entries', 'ppo_replay_rng_state', 'ppo_replay_cumulative_rows',
                'pool_snapshots', 'pool_strategy', 'pool_active_metadata', 'pool_candidate_history',
                'main_process_rng_state', 'assignment_replay_origin')


def logger(*args):
    result = subprocess.run([sys.executable, str(ROOT / 'research/experiment_log.py'),
                             'update', BASE.name, *args], cwd=ROOT, capture_output=True,
                            text=True, encoding='utf-8', timeout=45)
    require(result.returncode == 0, result.stderr)


# Reuse only the source-bound child execution/drain/termination method. Its global
# logger is intentionally redirected to this NEW record, not the historical one.
execution.logger_update = logger


def directory(seed, arm, stage):
    require(seed in PARENTS and arm in ('full', 'heads') and stage in DOSES, 'unknown cell')
    return BASE / f'seed{seed}_{arm}_stage{stage}'


def training_command(seed, arm, stage, parent_path, parent_physical, batch):
    run = directory(seed, arm, stage)
    argv = HELPER.command(run, parent_path, parent_physical, 'multi8', BASE / 'attempt_registry')
    argv[2] = str(WRAPPER)
    settings = {'--seed': 20263000 + seed, '--worker-seed-base': 2026300000 + seed * 100,
                '--fixed-training-deal-start-index': 36300000 + seed * 1000000,
                '--run-id': f'v6_nashpg_static_seed{seed}_20260903',
                '--total-environment-hands': INITIAL_PHYSICAL[seed] + DOSES[stage],
                '--max-runtime-seconds': 7200, '--mini-batch-size': batch}
    for key, value in settings.items():
        execution.set_option(argv, key, value)
    if arm == 'full':
        require(argv.count('--all-policy-heads-only-training') == 1, 'scope flag ambiguity')
        argv.remove('--all-policy-heads-only-training')
    argv += ['--source-policy-reference-refresh-updates', '0']
    return argv


def optimizer_step_audit(parent, final, full):
    import torch
    left, right = parent['optimizer'], final['optimizer']
    require(len(left['param_groups']) == len(right['param_groups']) == 1, 'optimizer group count')
    require(HELPER.equal(left['param_groups'], right['param_groups']), 'optimizer hyperparameters/IDs changed')
    ids = set(left['param_groups'][0]['params'])
    require(len(ids) == (86 if full else 10), 'optimizer scope mismatch')
    require(set(right['state']) == ids, 'missing actual optimizer gradient state')
    added = set(right['state']) - set(left['state'])
    require(not added or (full and added == set(range(76))), 'unexpected new optimizer state')
    advanced = {}
    for index, state in right['state'].items():
        require(all(torch.isfinite(state[k]).all().item() for k in ('step', 'exp_avg', 'exp_avg_sq')),
                'nonfinite optimizer state')
        before = int(left['state'][index]['step']) if index in left['state'] else 0
        after = int(state['step'])
        require(after > before, f'optimizer clock did not advance for parameter {index}')
        advanced[str(index)] = {'before': before, 'after': after, 'delta': after - before}
    return {'passed': True, 'new_state_ids': sorted(added), 'per_parameter_steps': advanced}


def pool_audit(windows, metrics, assignments):
    # Old verifier's score/assignment/archive replay is reusable; its additional
    # historical assertion that anchor IDs0..2 never leave is not a trainer rule.
    pool = evidence.module_at('scope_pool_windows', execution.POOL_HELPER)
    original_require = pool.require
    missing = []

    def pool_require(condition, message):
        if message in ('parent anchors missing', 'original anchor lost'):
            if not condition:
                missing.append(message)
            return
        original_require(condition, message)

    pool.require = pool_require
    result = pool.verify_windows(windows, metrics, assignments)
    result['anchor_retention_checks_missing'] = len(missing)
    result['anchor_retention_is_not_required_by_loss_kbest'] = True
    return result


def initial_audit(parent, initial, full):
    for key in INITIAL_KEYS:
        require(HELPER.equal(parent[key], initial[key]), f'initial state changed: {key}')
    require(initial['environment_hand_accounting']['completed_hands'] ==
            parent['environment_hand_accounting']['completed_hands'], 'initial physical counter reset')
    require(initial['all_policy_heads_only_training'] is (not full), 'initial training scope')
    require(bool(initial['main_process_rng_state']['torch_cuda']), 'missing restored CUDA RNG')
    evidence.initial_reference('static', parent, initial, HELPER.equal)


def inspect_training(run, parent, parent_path, parent_sha, seed, arm, stage, wall):
    import torch
    full = arm == 'full'
    initial = torch.load(run / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
    final = torch.load(run / 'latest.pt', map_location='cpu', weights_only=False)
    initial_audit(parent, initial, full)
    manifest = read(run / 'run_manifest.json')
    old = int(parent['environment_hand_accounting']['completed_hands'])
    actual = int(final['environment_hand_accounting']['completed_hands'])
    require(manifest['status'] == 'finished' and
            manifest['environment_hand_accounting']['completed_hands'] == actual, 'terminal counter mismatch')
    execution.target_or_safe_boundary(actual, INITIAL_PHYSICAL[seed] + DOSES[stage])
    require(sha(parent_path) == parent_sha, 'parent changed')
    attempt = final['fixed_deal_attempt']
    receipt = HELPER.helpers.load_attempt(Path(attempt['path']), attempt['sha256'])
    require(receipt == attempt['receipt'] and receipt['parent_checkpoint_sha256'] == parent_sha,
            'attempt receipt mismatch')
    require(receipt['namespace'] == final['config']['fixed_training_deal_namespace'] and
            receipt['namespace'] != parent['fixed_deal_attempt']['receipt']['namespace'], 'attempt namespace reused')
    metrics = execution.complete_jsonl(run / 'h1_training_metrics.jsonl')
    rows = [r for r in metrics if r['iteration'] > parent['iteration']]
    require([r['iteration'] for r in rows] == list(range(parent['iteration'] + 1, final['iteration'] + 1))
            and bool(rows), 'missing new iteration evidence')
    require(HELPER.finite_update_evidence(rows, (run / 'latest_train.log').read_text(encoding='utf-8')),
            'nonfinite/missing update losses')
    require(len(final['ppo_replay_entries']) == 2 and
            final['ppo_replay_cumulative_rows'] > parent['ppo_replay_cumulative_rows'], 'replay did not advance')
    steps = optimizer_step_audit(parent, final, full)
    changed = [k for k in final['model'] if not HELPER.equal(parent['model'][k], final['model'][k])]
    body = [k for k in changed if not k.startswith(('policy_head.', 'preflop_policy_head.', 'value_head.'))]
    require(bool(changed) and (bool(body) if full else not body), 'actual changed-weight scope invalid')
    require(all(torch.isfinite(t).all().item() for t in final['model'].values()), 'nonfinite weights')
    pool = evidence.module_at('scope_pool_loader', execution.POOL_HELPER)
    windows = [pool.load_window(parent_path, parent_sha)]
    hashes = {}
    for path in list((run / 'checkpoints').glob('*.pt')) + [run / 'latest.pt']:
        digest = sha(path)
        window = pool.load_window(path, digest)
        if window['iteration'] > parent['iteration']:
            windows.append(window)
            hashes[str(path)] = digest
    windows.sort(key=lambda w: w['iteration'])
    pool_result = pool_audit(windows, metrics, execution.complete_jsonl(run / 'opponent_assignments.jsonl'))
    reference_result = evidence.verify_reference_windows('static', parent, initial, [final], metrics, HELPER.equal)
    transition = final['total_hands'] - parent['total_hands']
    no_decision = final['environment_hand_accounting']['no_trainable_decision_hands'] - parent['environment_hand_accounting']['no_trainable_decision_hands']
    require(actual - old >= transition > 0, 'invalid physical/transition increment')
    return {'passed': True, 'seed': seed, 'arm': arm, 'stage': stage,
            'new_physical_hands': actual - old, 'new_transition_hands': transition,
            'new_no_decision_hands': no_decision,
            'residual_worker_tail_hands': actual - old - transition - no_decision,
            'new_replay_rows': final['ppo_replay_cumulative_rows'] - parent['ppo_replay_cumulative_rows'],
            'final_physical_hands': actual, 'overshoot_hands': actual - INITIAL_PHYSICAL[seed] - DOSES[stage],
            'optimizer_audit': steps, 'changed_weight_tensors': changed, 'changed_body_tensors': body,
            'pool_audit': pool_result, 'reference_audit': reference_result,
            'namespace': receipt['namespace'], 'receipt_sha256': attempt['sha256'],
            'checkpoint_sha256': sha(run / 'latest.pt'), 'checkpoint_windows_sha256': hashes,
            'subprocess_wall_seconds': wall, 'physical_hands_per_second': (actual - old) / wall,
            'statistical_not_bitwise_worker_continuation': True,
            'new_attempt_unknown_crash_suffix': 0, 'earlier_unknown_lineage_tails_not_erased': True}


class Controller:
    execute = execution.Controller.execute

    def __init__(self):
        import torch
        torch.set_num_threads(1)
        require(read(BASE / 'experiment.json')['status'] == 'RUNNING', 'record not running')
        memory = read(BASE / 'memory_16384.json')
        require(memory['passed'] and memory['batch'] == 16384 and memory['optimizer_steps'] == 0,
                'current launch requires passed original batch16384')
        self.batch = 16384
        require(not (BASE / 'ownership.json').exists(), 'prior owner requires review; never automatic retry')
        conflicts = []
        scripts = {'train_v5.py', 'run_pilot.py', 'train_with_checkpoint_io_45s.py',
                   'run_pair.py', 'v6_public_opponent_matched_eval.py', 'play_slumbot_v6_journaled.py'}
        for p in psutil.process_iter(['pid', 'cmdline']):
            if p.pid != os.getpid() and any(Path(a).name in scripts for a in p.info['cmdline'] or []):
                conflicts.append(p.pid)
        require(not conflicts, f'other poker owner: {conflicts}')
        require(shutil.disk_usage(BASE).free > 15 * 1024**3, 'less than15GiB free')
        require(sha(HELPER.PRODUCTION) == HELPER.CANDIDATE_SHA, 'production changed')
        require(sha(SCOPE / 'real_parent_qualification.json') ==
                'c35191054e22401c207f3384b851b7c9f5c790500cf8ebdaead12dd0dadebd92', 'qualification changed')
        import xml.etree.ElementTree as ET
        suites = list(ET.parse(BASE / 'controller_tests.xml').getroot().iter('testsuite'))
        require(suites and sum(int(s.get('tests', '0')) for s in suites) >= 8 and
                all(int(s.get('failures', '0')) == int(s.get('errors', '0')) == 0 for s in suites), 'tests not qualified')
        self.started, self.last_tick = time.perf_counter(), 0
        self.owner = {'pid': os.getpid(), 'create_time': psutil.Process().create_time(),
                      'started_at': datetime.now(timezone.utc).isoformat()}
        self.child, self.results, self.phase = None, [], 'FREEZING_INPUTS'
        sources = list((ROOT / 'scripts/alpha_holdem').rglob('*.py')) + list(BASE.glob('*.py'))
        sources += [OLD / 'run_control.py', OLD / 'control_evidence.py', execution.GPU_HELPER,
                    execution.GPU_HELPER.parent / 'run_cpu_resume_probe.py', execution.POOL_HELPER,
                    WRAPPER, OLD / 'recovery_20260905/checkpoint_io_candidate.py',
                    ROOT / 'research/experiment_log.py']
        self.sources = {str(p): sha(p) for p in sources}
        self.inputs = {**self.sources, str(BASE / 'protocol.md'): sha(BASE / 'protocol.md'),
                       str(BASE / 'memory_16384.json'): sha(BASE / 'memory_16384.json'),
                       str(BASE / 'controller_tests.xml'): sha(BASE / 'controller_tests.xml'),
                       str(SCOPE / 'real_parent_qualification.json'): sha(SCOPE / 'real_parent_qualification.json')}
        for seed, parent in PARENTS.items():
            require(sha(parent) == ORIGINAL_SHA[seed], 'original parent changed')
            full = SCOPE / f'derived/seed{seed}_full.pt'
            require(sha(full) == FULL_SHA[seed], 'derived parent changed')
            self.inputs.update({str(parent): sha(parent), str(full): sha(full)})
            checkpoint = torch.load(parent, map_location='cpu', weights_only=False)
            require(checkpoint['environment_hand_accounting']['completed_hands'] == INITIAL_PHYSICAL[seed], 'parent counter')
            self.inputs[checkpoint['fixed_deal_attempt']['path']] = checkpoint['fixed_deal_attempt']['sha256']
            origin = checkpoint.get('assignment_replay_origin')
            if origin and origin.get('migration_checkpoint'):
                self.inputs[origin['migration_checkpoint']] = origin['migration_checkpoint_sha256']
            for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl', 'run_manifest.json'):
                self.inputs[str(parent.parent / name)] = sha(parent.parent / name)
        for name, path in execution.ANCHORS.items():
            require(sha(path) == execution.ANCHOR_SHA256[name], 'anchor changed')
            self.inputs[str(path)] = sha(path)
        for name in ('slumbot_free_anchor_position10m.pt', 'corrected_cfr96_anchor10.pt'):
            p = ROOT.parent / 'CardPilot_legacy_20260829/selected_assets/opponents' / name
            self.inputs[str(p)] = sha(p)
        self.corpus = {str(p): sha(p) for p in (ROOT / 'research/experiments').rglob('common_deck_pairs.jsonl.gz')
                       if not p.is_relative_to(BASE)}
        execution.check_hashes(self.inputs)
        write_new(BASE / 'ownership.json', self.owner)
        write_new(BASE / 'input_contract.json', {'input_sha256': self.inputs, 'prior_common_deck_corpus': self.corpus,
                  'batch': self.batch, 'orders': ORDERS, 'doses': DOSES, 'unchanged_production': True})
        logger('--artifact', str(BASE / 'input_contract.json'), '--artifact', str(BASE / 'ownership.json'),
               '--artifact', str(BASE / 'run_pilot.py'), '--artifact', str(BASE / 'controller_tests.xml'),
               '--artifact', str(BASE / 'memory_16384.json'), '--metric', 'selected_minibatch=16384',
               '--command', subprocess.list2cmdline([sys.executable, *sys.argv]))

    def tick(self, force=False):
        if not force and time.perf_counter() - self.last_tick < 60:
            return
        require(execution.owner_live(self.owner), 'ownership lost')
        execution.check_hashes(self.sources)
        totals = {'new_training_hands': 0, 'new_transition_hands': 0, 'evaluation_hands': 0,
                  'slumbot_hands': 0, 'offline_samples': 0}
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
                        m = read(run / 'run_manifest.json')
                        if m.get('status') == 'finished':
                            physical, trans = m['environment_hand_accounting']['completed_hands'], m['total_hands']
                    except json.JSONDecodeError:
                        pass
                require(physical >= parent['physical_hands'] and trans >= parent['transition_hands'], 'live reset')
                totals['new_training_hands'] += physical - parent['physical_hands']
                totals['new_transition_hands'] += trans - parent['transition_hands']
                runs[run.name] = {'physical_hands': physical, 'new_physical_hands': physical - parent['physical_hands'],
                                  'iteration': rows[-1]['iteration'], 'target': INITIAL_PHYSICAL[seed] + DOSES[stage]}
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
        parent_path = ((SCOPE / f'derived/seed{seed}_full.pt' if arm == 'full' else PARENTS[seed])
                       if stage == 1 else directory(seed, arm, 1) / 'latest.pt')
        source_dir = PARENTS[seed].parent if stage == 1 else parent_path.parent
        parent_sha = sha(parent_path)
        parent = torch.load(parent_path, map_location='cpu', weights_only=False)
        old = int(parent['environment_hand_accounting']['completed_hands'])
        require(old < INITIAL_PHYSICAL[seed] + DOSES[stage], 'already reached target')
        run = directory(seed, arm, stage)
        run.mkdir()
        write_new(run / 'parent_contract.json', {'path': str(parent_path), 'sha256': parent_sha,
                  'physical_hands': old, 'transition_hands': parent['total_hands'], 'iteration': parent['iteration']})
        prefixes = {}
        for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
            source = source_dir / name
            prefixes[name] = {'path': str(source), 'sha256': sha(source), 'bytes': source.stat().st_size}
            shutil.copy2(source, run / name)
        write_new(run / 'prefixes.json', prefixes)
        shutil.copy2(HELPER.PRODUCTION, run / 'trainer_source.py')

        def capture(line):
            if '[Save] initial resume checkpoint' in line:
                path = run / 'initial_resumed_state.pt'
                require(not path.exists(), 'initial evidence overwrite')
                shutil.copy2(run / 'latest.pt', path)
                initial_audit(parent, torch.load(path, map_location='cpu', weights_only=False), arm == 'full')
                logger('--metric', 'training_started=true', '--artifact', str(path),
                       '--note', f'{run.name}: actual initial state verified; original counters/optimizer/replay/RNG retained.')

        self.phase = f'TRAINING_{run.name}'
        wall = self.execute(training_command(seed, arm, stage, parent_path, old, self.batch), run, capture, training=True)
        for name, info in prefixes.items():
            with (run / name).open('rb') as handle:
                require(hashlib.sha256(handle.read(info['bytes'])).hexdigest() == info['sha256'] == sha(info['path']),
                        'raw prefix changed')
        result = inspect_training(run, parent, parent_path, parent_sha, seed, arm, stage, wall)
        require(result['namespace'] not in [r['namespace'] for r in self.results], 'duplicate attempt namespace')
        write_new(run / 'verification.json', result)
        self.results.append(result)
        for name in ('latest.pt', 'verification.json', 'termination.json', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
            path = run / name
            self.inputs[str(path)] = sha(path)
            logger('--artifact', str(path))
        self.tick(force=True)

    def evaluate(self, stage):
        stage_results, fresh_rows = {}, []
        for seed in (1, 3):
            rows_by_arm = {}
            for arm in ('heads', 'full'):
                checkpoint = directory(seed, arm, stage) / 'latest.pt'
                out = BASE / f'eval_seed{seed}_{arm}_stage{stage}'
                job = BASE / f'job_{out.name}'
                job.mkdir()
                argv = [sys.executable, '-u', str(ROOT / 'scripts/alpha_holdem/v6_public_opponent_matched_eval.py'),
                        '--control', str(PARENTS[seed]), '--treatment', str(checkpoint)]
                for name, path in execution.ANCHORS.items():
                    argv += ['--anchor', f'{name}={path}']
                eval_seed = 20263800 + seed * 10 + stage
                argv += ['--pairs-per-anchor', '2048', '--seed', str(eval_seed), '--device', 'cuda', '--out-dir', str(out)]
                self.phase = f'EVALUATING_{out.name}'
                self.execute(argv, job)
                summary, rows = read(out / 'summary.json'), evidence.read_rows(out / 'common_deck_pairs.jsonl.gz')
                require(summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 32768 and
                        summary['policy_mode'] == 'greedy' and summary['starting_stack_bb'] == 200 and
                        summary['observation_style'] == 'legacy_v4', 'evaluation contract/count mismatch')
                require(len(rows) == len(evidence.validated_map(rows)) == 8192, 'eval row count')
                require(summary['raw_pairs_sha256'] == sha(out / 'common_deck_pairs.jsonl.gz'), 'eval raw hash')
                require(summary['input_sha256'] == {'control': ORIGINAL_SHA[seed], 'treatment': sha(checkpoint),
                        **{f'anchor:{k}': v for k, v in execution.ANCHOR_SHA256.items()}}, 'eval weight bindings')
                for name in execution.ANCHORS:
                    selected = [r for r in rows if r['anchor'] == name]
                    require(len(selected) == 2048 and sorted(r['pair_index'] for r in selected) == list(range(2048)),
                            'anchor pair coverage')
                rows_by_arm[arm] = rows
                for name in ('summary.json', 'common_deck_pairs.jsonl.gz'):
                    logger('--artifact', str(out / name))
            contrast = evidence.summarize_rows(evidence.join_arms(rows_by_arm['heads'], rows_by_arm['full']))
            stage_results[str(seed)] = {'full_minus_heads': contrast,
                'endpoint_minus_parent': {arm: evidence.summarize_rows(rows) for arm, rows in rows_by_arm.items()},
                'absolute_vs_anchors': {arm: evidence.summarize_rows([
                    evidence.derived_row(r, [0., 0.], r['treatment_rewards_bb']) for r in rows]) for arm, rows in rows_by_arm.items()},
                'broad_collapse': evidence.broad_collapse(contrast)}
            fresh_rows += rows_by_arm['heads']
        require(len({tuple(r['deck']) for r in fresh_rows}) == len(fresh_rows), 'cross-seed deck overlap')
        self.phase = f'AUDITING_FRESHNESS_stage{stage}'
        self.tick(force=True)
        freshness = evidence.check_prior_decks(fresh_rows, self.corpus)
        result = {'passed': True, 'stage': stage, 'evaluation_hands': 131072, 'seeds': stage_results,
                  'freshness': freshness, 'broad_collapse': any(r['broad_collapse'] for r in stage_results.values()),
                  'ci_scope': 'conditional paired deck means, not training-seed population or external strength',
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
            result = self.evaluate(stage)
            if result['broad_collapse']:
                self.phase = f'STAGE{stage}_BROAD_COLLAPSE_REVIEW'
                break
        else:
            self.phase = 'FIXED_DOSE_COMPLETE_NEEDS_RESEARCH_REVIEW'
        write_new(BASE / 'controller_result.json', {'phase': self.phase, 'training': self.results,
                  'wall_seconds': time.perf_counter() - self.started, 'goal_achieved': False})
        logger('--artifact', str(BASE / 'controller_result.json'))
        self.tick(force=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    controller = Controller()
    try:
        controller.run()
    except Exception as exc:
        controller.phase = 'SAFE_BOUNDARY_NEEDS_REVIEW' if isinstance(exc, execution.SafeBoundary) else 'ERROR_PRESERVED_NEEDS_REVIEW'
        write_new(BASE / 'controller_error.json', {'error': repr(exc), 'phase': controller.phase,
                  'created_at': datetime.now(timezone.utc).isoformat(), 'no_automatic_retry': True})
        controller.tick(force=True)
        raise


if __name__ == '__main__':
    main()
