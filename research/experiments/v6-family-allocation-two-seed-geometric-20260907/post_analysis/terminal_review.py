"""Terminal-only raw/state review. No poker execution and no input modifications."""
from pathlib import Path
import gzip
import hashlib
import importlib.util
import json
import random
import sys
import time
import torch

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[2]
QUAL = BASE.parent / 'v6-family-stratified-qualification-20260907'

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

# Bind the frozen runtime before helper imports can load the workspace package.
wrapper = module('allocation_review_trainer', BASE.parent/'v6-anchor-recent-trainer-integration-20260907/train_candidate.py')
trainer, _ = wrapper.install()
prior = module('allocation_terminal_prior', BASE.parent / 'v6-expanded-family-two-seed-geometric-20260907/post_analysis/terminal_review.py')
old = prior.old
read, sha, require = old.read, old.sha, old.require

def family_mass(weights, ids, original, added):
    require(len(weights) == len(ids) == 9 and len(set(ids)) == 9, 'capacity/IDs')
    require(original | added <= set(ids), 'missing fixed IDs')
    for group, target in ((original, .5), (added, .25), (set(ids)-original-added, .25)):
        require(abs(sum(w for w,i in zip(weights,ids) if i in group)-target) < 1e-8, 'family mass')

def main():
    started = time.monotonic()
    output = BASE / 'post_terminal_review.json'
    require(not output.exists(), 'preserve prior review')
    owner = read(BASE/'ownership.json')
    require(owner['pid'] == 186908 and abs(owner['create_time']-1788821046.8103075)<.001, 'owner identity')
    require(not old.live(owner['pid'],owner['create_time']), 'owner live')
    result = read(BASE/'controller_result.json')
    require(result['phase']=='FIXED_1M_COMPLETE_RESEARCH_REVIEW' and not (BASE/'controller_error.json').exists(), 'terminal boundary')
    hashes = dict(read(BASE/'input_contract.json')['input_sha256'])
    for m in (prior, old, old.old): hashes[str(Path(m.__file__))] = sha(m.__file__)
    hashes[str(Path(__file__))] = sha(__file__)
    require(all(sha(p)==h for p,h in hashes.items()), 'input changes')
    train_wall = job_wall = 0.
    terms = list(BASE.glob('*/termination.json'))
    require(len(terms)==16, 'terminal coverage')
    for p in terms:
        t, proc = read(p), read(p.parent/'process.json')
        require(t['exit_code']==0 and not t['observer_errors'] and not t['remaining_observed_child_pids'], 'unclean terminal')
        require(not old.live(proc['pid'],proc['create_time']) and all(not old.live(i,c) for i,c in t['observed_children'].items()), 'live child')
        job_wall += t['wall_seconds']
        if (p.parent/'verification.json').exists():
            require(len(t['observed_children'])>=12, 'worker evidence')
            train_wall += t['wall_seconds']
        for n in ('termination.json','process.json','command.json'): hashes[str(p.parent/n)] = sha(p.parent/n)
    torch.set_num_threads(1)
    counts, health, namespaces = {}, {}, set()
    order = [(1,'control'),(1,'expanded'),(3,'expanded'),(3,'control')]
    require([(r['seed'],r['arm'],r['stage']) for r in result['training']]==[(s,a,t) for t in (1,2) for s,a in (order if t==1 else list(reversed(order)))], 'cell order')
    for row in result['training']:
        seed, arm, stage = row['seed'],row['arm'],row['stage']
        run = BASE/f'seed{seed}_{arm}_stage{stage}'
        require(row==read(run/'verification.json') and row['passed'], 'reported verification')
        binding = read(run/'parent_contract.json')
        expected_parent = BASE/f'seed{seed}_{arm}_stage1/latest.pt' if stage==2 else (QUAL if arm=='expanded' else BASE.parent/'v6-expanded-family-worker-smoke-20260907')/f'derived/seed{seed}_recent_stage2/latest.pt'
        require(Path(binding['path']).resolve()==expected_parent.resolve() and sha(expected_parent)==binding['sha256'], 'wrong/changed parent')
        p = torch.load(expected_parent,map_location='cpu',weights_only=False)
        initial = torch.load(run/'initial_resumed_state.pt',map_location='cpu',weights_only=False)
        final = torch.load(run/'latest.pt',map_location='cpu',weights_only=False)
        keys = list(old.INITIAL_KEYS)+['adaptive_opponent_ema_rewards','adaptive_opponent_weights','adaptive_opponent_observations']
        norm = prior.normalized_pool(p,200)
        require(all(prior.state_equal(norm[k],initial[k]) for k in keys), 'initial state mismatch')
        gate = read(run/'initial_resume_gate.json')
        require(gate['passed'] and sha(run/'initial_resumed_state.pt')==gate['initial_sha256'], 'initial binding')
        require(initial['environment_hand_accounting']['completed_hands']==binding['physical_hands']==p['environment_hand_accounting']['completed_hands'], 'counter reset')
        require(all(c['pool_strategy']=='anchor-latest' and c['all_policy_heads_only_training'] is False for c in (p,initial,final)), 'scope/strategy')
        old.gradient_route(p,initial,final,'connected')
        delta = old.counter_deltas(p,final)
        require(all(delta[k]==row[k] for k in ('new_physical_hands','new_transition_hands','new_replay_rows')), 'counts')
        require(final['environment_hand_accounting']['completed_hands'] >= {1:14695135,3:14694500}[seed]+{1:262144,2:1048576}[stage], 'dose')
        steps = old.adam_steps(p,final,row['optimizer'],9.999999999999996e-05)
        require(sha(run/'latest.pt')==row['checkpoint_sha256'], 'final SHA')
        for name,info in read(run/'prefixes.json').items():
            with (run/name).open('rb') as f: require(hashlib.sha256(f.read(info['bytes'])).hexdigest()==info['sha256']==sha(expected_parent.parent/name), 'prefix changed')
        metrics = [json.loads(x) for x in (run/'h1_training_metrics.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
        assignments = [json.loads(x) for x in (run/'opponent_assignments.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
        suffix = [r for r in assignments if r['applies_to_iteration']>p['iteration']]
        require([r['applies_to_iteration'] for r in suffix]==list(range(p['iteration']+1,final['iteration']+1)), 'assignment coverage')
        args = read(run/'command.json')
        option = lambda k: args[args.index(k)+1]
        rng = random.Random()
        restored = trainer.restore_group_assignment_rng_from_evidence([r for r in assignments if r['applies_to_iteration']<=p['iteration']], [r for r in metrics if r['iteration']<=p['iteration']], rng=rng,seed=int(option('--seed')),worker_count=int(option('--workers')),group_count=int(option('--opponent-groups')),self_play_fraction=float(option('--self-play-fraction')),checkpoint_iteration=p['iteration'],checkpoint_total_hands=p['total_hands'],replay_origin=p['assignment_replay_origin'],pool_size=9,pool_snapshot_ids=[x['id'] for x in p['pool_snapshots']])
        require(restored['pending_assignments'] is None, 'pending parent work')
        first,_ = trainer.build_group_opponent_assignments(worker_count=int(option('--workers')),pool_size=9,group_count=int(option('--opponent-groups')),self_play_fraction=float(option('--self-play-fraction')),rng=rng,pool_weights=p['adaptive_opponent_weights'])
        require(first.tolist()==[w['opponent']['local_index'] for w in suffix[0]['workers']], 'first assignment RNG replay')
        fixed = {x['id'] for x in p['pool_snapshots'] if x['score_components'].get('kind')=='initial_external_opponent'}
        require(len(fixed)==7 and len(final['pool_snapshots'])==9 and fixed <= {x['id'] for x in final['pool_snapshots']}, 'fixed retention')
        exposure = {i:0 for i in fixed}
        mm = {m['iteration']:m for m in metrics}
        for r in suffix:
            refs = {x['local_index']:x['snapshot_id'] for x in r['pool_snapshot_refs']}
            for g in mm[r['applies_to_iteration']]['adaptive_opponent_league']:
                i = refs[g['opponent_id']]
                if i in exposure: exposure[i] += g['iteration_hands']
        require(all(v>0 for v in exposure.values()), 'unexposed fixed opponent')
        runtime, observed = read(run/'mixture_runtime.json'),read(run/'mixture_observation.json')
        require(runtime['greedy_weight']==binding['opponent_greedy_mixture']==0 and runtime['parent_sha256']==binding['sha256'], 'execution mixture')
        require(sha(run/'mixture_runtime.json')==row['mixture_runtime_sha256']==observed['runtime_sha256'] and sha(run/'mixture_observation.json')==row['mixture_observation_sha256'], 'mixture hashes')
        require(observed['clean_return'] and observed['opponent_forward_rows']>0, 'actual opponent execution')
        if arm=='expanded':
            fc, fr = read(run/'family_contract.json'),read(run/'family_runtime.json')
            require(fr['contract_sha256']==sha(run/'family_contract.json') and fr['parent_sha256']==binding['sha256'], 'family runtime')
            require(all(sha(k)==v for k,v in fc['input_sha256'].items()), 'family sources')
            original,added = set(fc['original_ids']),set(fc['added_ids'])
            require(len(original)==3 and len(added)==4 and not original & added and original|added==fixed, 'family IDs')
            for r in suffix: family_mass(r['pool_sampling_weights'],[x['snapshot_id'] for x in r['pool_snapshot_refs']],original,added)
            family_mass(final['adaptive_opponent_weights'],[x['id'] for x in final['pool_snapshots']],original,added)
        else: require(not (run/'family_runtime.json').exists(), 'control contamination')
        attempt = final['fixed_deal_attempt']; ns = attempt['receipt']['namespace']
        require(ns==row['namespace'] and ns not in namespaces and ns not in read(BASE/'qualification.json')['known_namespaces'] and ns!=p['fixed_deal_attempt']['receipt']['namespace'], 'namespace reuse')
        require(sha(attempt['path'])==attempt['sha256'] and read(attempt['path'])==attempt['receipt'] and attempt['receipt']['parent_checkpoint_sha256']==binding['sha256'], 'attempt binding')
        namespaces.add(ns)
        health[run.name] = old.training_health(metrics,(run/'latest_train.log').read_text(encoding='utf-8'),p['iteration'],final['iteration'])
        health[run.name].update(adam_step_deltas=steps,fixed_transition_exposure=exposure,first_assignment_replayed=first.tolist(),assignments_checked=len(suffix))
        for k,v in delta.items(): counts[k] = counts.get(k,0)+v
        for name in ('latest.pt','initial_resumed_state.pt','verification.json','parent_contract.json','prefixes.json','h1_training_metrics.jsonl','opponent_assignments.jsonl','run_manifest.json','latest_train.log','initial_resume_gate.json','mixture_runtime.json','mixture_observation.json','family_contract.json','family_runtime.json'):
            if (run/name).exists(): hashes[str(run/name)] = sha(run/name)
        del p,initial,final
    seen, stages, reporting_deviations = set(), {}, []
    anchors = read(BASE/'qualification.json')['anchors']
    groups = {'preservation':list(anchors)[:4],'adaptation':list(anchors)[4:]}
    for stage in (1,2):
        reported = read(BASE/f'stage{stage}_analysis.json'); stages[str(stage)] = {}
        require(reported['passed'] and reported['evaluation_hands']==131072, 'stage incomplete')
        for seed in (1,3):
            arms = {}
            for arm in ('control','expanded'):
                folder = BASE/f'eval_seed{seed}_{arm}_stage{stage}'
                summary, raw = read(folder/'summary.json'),folder/'common_deck_pairs.jsonl.gz'
                require(summary['status']=='COMPLETED' and summary['evaluation_hands']==32768 and summary['raw_pairs_sha256']==sha(raw), 'raw summary')
                require(summary['policy_mode']=='greedy' and summary['starting_stack_bb']==200 and summary['observation_style']=='legacy_v4', 'eval contract')
                expected = {'control':sha(BASE.parent/f'v6-expanded-family-worker-smoke-20260907/derived/seed{seed}_recent_stage2/latest.pt'),'treatment':sha(BASE/f'seed{seed}_{arm}_stage{stage}/latest.pt'),**{f'anchor:{k}':sha(v) for k,v in anchors.items()}}
                require(summary['input_sha256']==expected and all(sha(p)==expected[n] for n,p in summary['input_paths'].items()), 'eval checkpoints')
                args = summary['command']; require(args[args.index('--seed')+1]==str(20267000+10*seed+stage), 'eval seed')
                arms[arm] = old.raw_map(raw)
                require({k[0] for k in arms[arm]}==set(anchors), 'anchor coverage')
                for j,anchor in enumerate(anchors):
                    rng = random.Random(20267000+10*seed+stage+j*1000003)
                    for i in range(1024):
                        deck = list(range(52)); rng.shuffle(deck)
                        key = (anchor,20267000+10*seed+stage+j*1000003,i)
                        require(key in arms[arm] and arms[arm][key]['deck']==deck, 'deck reconstruction')
                for f in (raw,folder/'summary.json'): hashes[str(f)] = sha(f)
            stages[str(stage)][str(seed)] = {}
            for group,names in groups.items():
                a = {arm:{k:r for k,r in rows.items() if k[0] in names} for arm,rows in arms.items()}
                contrast = old.compare_arms(a['control'],a['expanded'],seen)
                expected = reported['seeds'][str(seed)][group]
                pairs = [(contrast['connected_minus_detached'],expected['stratified_minus_flat'])]+[(contrast['endpoint_minus_parent'][a],expected['endpoint_minus_root'][b]) for a,b in (('detached','control'),('connected','expanded'))]
                for recomputed, prior_summary in pairs:
                    if group=='preservation': old.check_reported(recomputed,prior_summary)
                    else:
                        # Preserve and explicitly diagnose the frozen legacy summarizer defect.
                        require(set(prior_summary['by_anchor'])==set(groups['preservation']) and all(v['samples']==0 and v['bb100']==0 and v['ci95_low_bb100']==v['ci95_high_bb100']==0 for v in prior_summary['by_anchor'].values()), 'unexplained adaptation mismatch')
                        old.check_reported({**recomputed,'by_anchor':{}},{**prior_summary,'by_anchor':{}})
                if group=='preservation': require(contrast['broad_collapse']==expected['broad_collapse'], 'collapse recomputation')
                else: reporting_deviations.append(dict(stage=stage,seed=seed,issue='Legacy hardcoded preservation anchor labels produce zero-sample adaptation buckets; pooled and seat statistics independently match.',reported_broad_collapse=expected['broad_collapse'],corrected_broad_collapse=contrast['broad_collapse']))
                stages[str(stage)][str(seed)][group] = contrast
        corrected_gate = any(v['broad_collapse'] for s in stages[str(stage)].values() for v in s.values())
        reporting_deviations.append(dict(stage=stage,reported_stage_gate=reported['broad_collapse'],corrected_stage_gate=corrected_gate))
        hashes[str(BASE/f'stage{stage}_analysis.json')] = sha(BASE/f'stage{stage}_analysis.json')
    require(len(seen)==32768, 'deck coverage')
    prior_rows = 0
    for p,h in read(BASE/'qualification.json')['prior_corpus'].items():
        require(sha(p)==h, 'prior hash')
        with gzip.open(p,'rt',encoding='utf-8') as f:
            for line in f:
                require(tuple(json.loads(line)['deck']) not in seen, 'prior overlap'); prior_rows += 1
        hashes[p] = h
    require(counts['new_physical_hands']==4201398 and counts['new_transition_hands']==3742904, 'total accounting')
    for f in ('ownership.json','controller_result.json','qualification.json','input_contract.json'): hashes[str(BASE/f)] = sha(BASE/f)
    require(all(sha(p)==h for p,h in hashes.items()), 'evidence changed during review')
    report = dict(passed=True,original_reports_valid=False,reporting_deviations=reporting_deviations,stage2_continuation_supported_by_corrected_gate=not any(v['broad_collapse'] for s in stages['1'].values() for v in s.values()),command=sys.orig_argv,counts=counts,evaluation_hands=262144,final_qualification_hands=0,jobs_terminal=len(terms),namespaces=sorted(namespaces),unique_evaluation_decks=len(seen),prior_rows=prior_rows,overlap=0,stages=stages,health=health,input_sha256=hashes,training_wall_seconds=train_wall,job_wall_seconds=job_wall,controller_wall_seconds=result['wall_seconds'],review_wall_seconds=time.monotonic()-started,scope='Passed means independent evidence review completed with disclosed report defects, not original reports correct or policy improved. Statistical continuation, not bitwise worker RNG equivalence. Unique training decks not proven. Conditional deck CIs, not seed-population inference. Internal development panels, not unseen opponents or Slumbot qualification.')
    with output.open('x',encoding='utf-8') as f: json.dump(report,f,indent=2,allow_nan=False)
    print(json.dumps({k:report[k] for k in ('passed','counts','evaluation_hands','review_wall_seconds')}))

if __name__=='__main__': main()
