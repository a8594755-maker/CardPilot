"""Terminal-only repeatable state/raw audit; never requests poker hands or edits inputs."""
import gzip
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import torch

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[2]
SOURCE = ROOT/'research/experiments/v6-preflop-actor-trunk-two-seed-geometric-20260906/post_analysis/review.py'
spec = importlib.util.spec_from_file_location('prior_terminal_review', SOURCE)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
read, sha, require = old.read, old.sha, old.require
sys.path.insert(0,str(ROOT/'research/experiments/v6-expanded-family-worker-smoke-20260907'))
from pool_gate import normalized_pool
sys.path.insert(0,str(ROOT/'research/experiments/v6-expanded-family-pool-qualification-20260907'))
from real_parent_check import equal as state_equal


def main():
    started = time.monotonic()
    output = BASE/'post_terminal_review.json'
    require(not output.exists(), 'preserve prior audit')
    owner = read(BASE/'ownership.json')
    require(owner['pid'] == 46616 and abs(owner['create_time']-1788799721.5119417) < .001, 'owner identity')
    require(not old.live(owner['pid'], owner['create_time']), 'owner live')
    require(not (BASE/'controller_error.json').exists(), 'controller failure')
    result = read(BASE/'controller_result.json')
    require(result['phase'] == 'FIXED_1M_COMPLETE_RESEARCH_REVIEW', 'wrong boundary')
    hashes = dict(read(BASE/'input_contract.json')['input_sha256'])
    for path in (Path(__file__), SOURCE, old.SOURCE, BASE/'controller_result.json', BASE/'ownership.json'):
        hashes[str(path)] = sha(path)
    require(all(sha(p) == h for p, h in hashes.items()), 'source changed')
    terms = list(BASE.glob('*/termination.json'))
    require(len(terms) == 16, 'job coverage')
    train_wall = job_wall = 0.
    for path in terms:
        terminal, process = read(path), read(path.parent/'process.json')
        require(terminal['exit_code'] == 0 and not terminal['observer_errors']
                and not terminal['remaining_observed_child_pids'], 'unclean termination')
        require(not old.live(process['pid'], process['create_time']), 'job live')
        require(all(not old.live(pid, ct) for pid, ct in terminal['observed_children'].items()), 'worker live')
        job_wall += terminal['wall_seconds']
        if (path.parent/'verification.json').exists():
            require(len(terminal['observed_children']) >= 12, 'missing worker evidence')
            train_wall += terminal['wall_seconds']
        for name in ('termination.json', 'process.json', 'command.json'):
            hashes[str(path.parent/name)] = sha(path.parent/name)
    torch.set_num_threads(1)
    counts, namespaces, health = {}, set(), {}
    roots = {1:14695135, 3:14694500}
    order = [(1,'control'), (1,'expanded'), (3,'expanded'), (3,'control')]
    require([(r['seed'],r['arm'],r['stage']) for r in result['training']] ==
            [(s,a,t) for t in (1,2) for s,a in (order if t == 1 else list(reversed(order)))], 'cell order')
    for row in result['training']:
        run = BASE/f"seed{row['seed']}_{row['arm']}_stage{row['stage']}"
        require(row == read(run/'verification.json') and row['passed'], 'reported verification')
        binding = read(run/'parent_contract.json')
        require(sha(binding['path']) == binding['sha256'] and sha(run/'latest.pt') == row['checkpoint_sha256'], 'checkpoint SHA')
        runtime, observed = read(run/'mixture_runtime.json'), read(run/'mixture_observation.json')
        weight = {'control':0., 'expanded':0.}[row['arm']]
        require(sha(run/'mixture_runtime.json') == row['mixture_runtime_sha256'] == observed['runtime_sha256'], 'runtime SHA')
        require(sha(run/'mixture_observation.json') == row['mixture_observation_sha256'], 'observation SHA')
        require(runtime['greedy_weight'] == binding['opponent_greedy_mixture'] == weight and
                runtime['parent_sha256'] == binding['sha256'], 'mixture setting/parent changed')
        require(runtime['wrapper_sha256'] == sha(ROOT/'research/experiments/v6-opponent-execution-mixture-two-seed-geometric-20260907/train_candidate.py'), 'mixture wrapper changed')
        if row['stage'] == 2:
            require(sha(binding['prior_mixture_runtime']) == binding['prior_mixture_runtime_sha256'], 'parent runtime changed')
            require(read(binding['prior_mixture_runtime'])['greedy_weight'] == weight, 'mixture reset on resume')
        require(observed['clean_return'] and observed['opponent_forward_rows'] > 0, 'no actual opponent execution')
        batch = observed['first_batch']
        for original, actual, greedy, mask in zip(batch['original_probabilities'],batch['mixture_probabilities'],batch['greedy_actions'],batch['legal_masks']):
            require(all(abs(p - ((1-weight)*q + (weight if i == greedy else 0))) < 1e-6 for i,(p,q) in enumerate(zip(actual,original))), 'actual mixture formula')
            require(all(p == 0 for p,legal in zip(actual,mask) if not legal), 'illegal mass')
        for filename in ('mixture_runtime.json','mixture_observation.json'):
            hashes[str(run/filename)] = sha(run/filename)
        parent = torch.load(binding['path'], map_location='cpu', weights_only=False)
        initial = torch.load(run/'initial_resumed_state.pt', map_location='cpu', weights_only=False)
        final = torch.load(run/'latest.pt', map_location='cpu', weights_only=False)
        keys = list(old.INITIAL_KEYS) + [
            'adaptive_opponent_ema_rewards', 'adaptive_opponent_weights', 'adaptive_opponent_observations']
        require(all(state_equal(normalized_pool(parent,200)[k], initial[k]) for k in keys), 'initial state changed')
        require(parent['environment_hand_accounting']['completed_hands'] ==
                initial['environment_hand_accounting']['completed_hands'] == binding['physical_hands'], 'counter reset')
        strategy = 'anchor-latest'
        require(initial['pool_strategy'] == final['pool_strategy'] == strategy, 'strategy')
        require(all(c['all_policy_heads_only_training'] is False for c in (parent, initial, final)), 'scope')
        old.gradient_route(parent, initial, final, 'connected')
        delta = old.counter_deltas(parent, final)
        require(all(delta[k] == row[k] for k in ('new_physical_hands','new_transition_hands','new_replay_rows')), 'counts')
        require(final['environment_hand_accounting']['completed_hands'] >= roots[row['seed']] +
                {1:262144,2:1048576}[row['stage']], 'dose')
        steps = old.adam_steps(parent, final, row['optimizer'], 9.999999999999996e-05)
        attempt = final['fixed_deal_attempt']
        ns = attempt['receipt']['namespace']
        require(ns == row['namespace'] and ns not in namespaces and ns != parent['fixed_deal_attempt']['receipt']['namespace']
                and ns not in read(BASE/'qualification.json')['known_namespaces'], 'namespace reuse')
        require(sha(attempt['path']) == attempt['sha256'] and read(attempt['path']) == attempt['receipt']
                and attempt['receipt']['parent_checkpoint_sha256'] == binding['sha256'], 'receipt binding')
        namespaces.add(ns)
        for name, info in read(run/'prefixes.json').items():
            with (run/name).open('rb') as handle:
                require(hashlib.sha256(handle.read(info['bytes'])).hexdigest() == info['sha256'] ==
                        sha(Path(binding['path']).parent/name), 'prefix changed')
        with (run/'h1_training_metrics.jsonl').open(encoding='utf-8') as handle:
            metrics = [json.loads(line) for line in handle if line.strip()]
        health[run.name] = old.training_health(metrics, (run/'latest_train.log').read_text(encoding='utf-8'),
                                               parent['iteration'], final['iteration'])
        health[run.name]['adam_step_deltas'] = steps
        gate=read(run/'initial_resume_gate.json')
        require(gate['passed'] and sha(run/'initial_resumed_state.pt')==gate['initial_sha256'],'initial SHA')
        with (run/'opponent_assignments.jsonl').open(encoding='utf-8') as handle:
            assignments=[json.loads(line) for line in handle if line.strip()]
        suffix=[a for a in assignments if a['applies_to_iteration']>parent['iteration']]
        require([a['applies_to_iteration'] for a in suffix]==list(range(parent['iteration']+1,final['iteration']+1)),'assignment coverage')
        fixed={p['id'] for p in parent['pool_snapshots'] if p['score_components'].get('kind')=='initial_external_opponent'}
        require(len(fixed)==({'control':3,'expanded':7}[row['arm']]),'fixed family count')
        require(len(final['pool_snapshots'])==({'control':5,'expanded':9}[row['arm']]) and
                fixed.issubset({p['id'] for p in final['pool_snapshots']}),'fixed anchor retention')
        metric_map={m['iteration']:m for m in metrics}
        exposure={i:0 for i in fixed}
        for assignment in suffix:
            refs={p['local_index']:p['snapshot_id'] for p in assignment['pool_snapshot_refs']}
            for group in metric_map[assignment['applies_to_iteration']]['adaptive_opponent_league']:
                snapshot=refs[group['opponent_id']]
                if snapshot in exposure:
                    exposure[snapshot]+=group['iteration_hands']
        require(all(v>0 for v in exposure.values()),'fixed family lacks training evidence')
        health[run.name]['fixed_family_transition_exposure']=exposure
        for k, v in delta.items():
            counts[k] = counts.get(k, 0) + v
        for name in ('latest.pt','initial_resumed_state.pt','verification.json','parent_contract.json','prefixes.json',
                     'h1_training_metrics.jsonl','opponent_assignments.jsonl','run_manifest.json','latest_train.log'):
            hashes[str(run/name)] = sha(run/name)
        del parent, initial, final
    seen, stages = set(), {}
    for stage in (1,2):
        reported = read(BASE/f'stage{stage}_analysis.json')
        require(reported['passed'] and reported['evaluation_hands'] == 131072, 'stage count')
        stages[str(stage)] = {}
        for seed in (1,3):
            arms = {}
            for arm in ('control','expanded'):
                folder = BASE/f'eval_seed{seed}_{arm}_stage{stage}'
                summary, raw = read(folder/'summary.json'), folder/'common_deck_pairs.jsonl.gz'
                require(summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 32768
                        and summary['raw_pairs_sha256'] == sha(raw), 'eval summary')
                require(summary['policy_mode'] == 'greedy' and summary['starting_stack_bb'] == 200
                        and summary['observation_style'] == 'legacy_v4', 'execution contract')
                require(all(sha(p) == summary['input_sha256'][n] for n,p in summary['input_paths'].items()), 'eval SHA')
                arms[arm] = old.raw_map(raw)
                for anchor in {k[0] for k in arms[arm]}:
                    require(sorted(k[2] for k in arms[arm] if k[0] == anchor) == list(range(2048)), 'anchor coverage')
                for p in (raw, folder/'summary.json'):
                    hashes[str(p)] = sha(p)
            contrast = old.compare_arms(arms['control'], arms['expanded'], seen)
            expected = reported['seeds'][str(seed)]
            old.check_reported(contrast['connected_minus_detached'], expected['expanded_minus_control'])
            for group in ('endpoint_minus_parent','absolute_vs_anchors'):
                for a,b in (('detached','control'),('connected','expanded')):
                    old.check_reported(contrast[group][a], expected[group][b])
            require(contrast['broad_collapse'] == expected['broad_collapse'], 'safety gate')
            # Imported helper's historical labels are explicitly translated here.
            stages[str(stage)][str(seed)] = {'expanded_minus_control':contrast['connected_minus_detached'],
                **{g:{b:contrast[g][a] for a,b in (('detached','control'),('connected','expanded'))}
                   for g in ('endpoint_minus_parent','absolute_vs_anchors')}, 'broad_collapse':contrast['broad_collapse']}
        require(not reported['broad_collapse'] and not any(x['broad_collapse'] for x in stages[str(stage)].values()), 'stop gate')
        hashes[str(BASE/f'stage{stage}_analysis.json')] = sha(BASE/f'stage{stage}_analysis.json')
    require(len(seen) == 32768, 'unique evaluation decks')
    prior = read(BASE/'qualification.json')['prior_corpus']
    prior_rows = 0
    for path,digest in prior.items():
        require(sha(path) == digest, 'prior changed')
        with gzip.open(path,'rt',encoding='utf-8') as handle:
            for line in handle:
                require(tuple(json.loads(line)['deck']) not in seen, 'prior overlap')
                prior_rows += 1
        hashes[path] = digest
    require(all(sha(p) == h for p,h in hashes.items()), 'evidence changed during review')
    report = {'passed':True, 'created_at':datetime.now(timezone.utc).isoformat(), 'command':sys.orig_argv,
        'jobs_terminal':len(terms), 'counts':counts, 'unique_evaluation_decks':len(seen),
        'prior_files':len(prior), 'prior_rows':prior_rows, 'overlap':0, 'namespaces':sorted(namespaces),
        'evaluation_hands':262144, 'final_qualification_hands':0, 'stages':stages, 'health':health,
        'input_sha256':hashes, 'training_wall_seconds':train_wall, 'job_wall_seconds':job_wall,
        'controller_wall_seconds':result['wall_seconds'], 'review_wall_seconds':time.monotonic()-started,
        'scope':'Statistical continuation, not bitwise worker resume. Unique training deck coverage not proven. Internal CIs conditional on paired evaluation decks, not seed population or Slumbot strength.',
        'goal_achieved':False}
    with output.open('x',encoding='utf-8') as handle:
        json.dump(report,handle,indent=2,allow_nan=False)
    print(json.dumps({k:report[k] for k in ('passed','counts','evaluation_hands','training_wall_seconds','review_wall_seconds')}))


if __name__ == '__main__':
    main()
