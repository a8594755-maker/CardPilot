"""Independent terminal evidence review; refuses unfinished experiments."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import time
import torch
import run_probe as trial

BASE, old = trial.BASE, trial.old


def stats(values):
    assert len(values)>1 and all(math.isfinite(v) for v in values)
    mean=statistics.mean(values)*100
    se=statistics.stdev(values)*100/math.sqrt(len(values))
    return dict(bb100=mean,ci95=[mean-1.96*se,mean+1.96*se],se_bb100=se,paired_decks=len(values))


def summarize(rows, anchors):
    def differences(selected, seat=None):
        return [statistics.mean(r['treatment_rewards_bb'])-statistics.mean(r['control_rewards_bb']) if seat is None else r['treatment_rewards_bb'][seat]-r['control_rewards_bb'][seat] for r in selected]
    return dict(pooled=stats(differences(rows)),by_anchor={a:stats(differences([r for r in rows if r['anchor']==a])) for a in anchors},by_seat={str(s):stats(differences(rows,s)) for s in (0,1)},by_panel={name:dict(pooled=stats(differences([r for r in rows if r['anchor'] in names])),by_seat={str(s):stats(differences([r for r in rows if r['anchor'] in names],s)) for s in (0,1)}) for name,names in [('preservation',anchors[:4]),('transfer',anchors[4:])]})


def main():
    started=time.monotonic()
    terminal=old.read(BASE/'terminal.json')
    assert terminal['status']=='FIXED_2M_COMPLETE_REVIEW_REQUIRED'
    contract=old.read(BASE/'evaluation_contract.json')
    hashes=dict(contract['input_sha256'])
    for name in ('terminal.json','evaluation_contract.json','review.py'):
        hashes[str(BASE/name)]=old.sha(BASE/name)
    old.ctl.execution.check_hashes(hashes)
    training=[]; namespaces=set(); seen=set(); evaluation={}; anchors=list(contract['anchors'])
    for seed in (1,3):
        folder=BASE/f'seed{seed}_control_stage1'
        parent_contract=old.read(folder/'parent_contract.json')
        parent=torch.load(parent_contract['path'],map_location='cpu',weights_only=False)
        initial=torch.load(folder/'initial_resumed_state.pt',map_location='cpu',weights_only=False)
        final=torch.load(folder/'latest.pt',map_location='cpu',weights_only=False)
        gate=old.read(folder/'initial_resume_gate.json')
        assert gate['passed'] and old.sha(Path(parent_contract['path']))==gate['parent_sha256']
        assert old.sha(folder/'initial_resumed_state.pt')==gate['initial_sha256']
        normalized=old.normalized_pool(parent,200)
        for key in gate['exact_keys']:assert old.state_equal(normalized[key],initial[key]),key
        old.ctl.route_audit(initial,True,parent)
        old.ctl.evidence.initial_reference('static',parent,initial,old.ctl.HELPER.equal)
        optimizer=old.ctl.prior.optimizer_step_audit(parent,final,True)
        assert not optimizer['new_state_ids']
        assert [g['lr'] for g in parent['optimizer']['param_groups']]==[g['lr'] for g in final['optimizer']['param_groups']]
        namespace=final['fixed_deal_attempt']['receipt']['namespace']
        assert namespace==gate['namespace'] and namespace not in namespaces
        assert namespace!=parent['fixed_deal_attempt']['receipt']['namespace']
        namespaces.add(namespace)
        assert old.ctl.HELPER.helpers.load_attempt(Path(final['fixed_deal_attempt']['path']),final['fixed_deal_attempt']['sha256'])==final['fixed_deal_attempt']['receipt']
        for name,prefix in old.read(folder/'prefixes.json').items():
            with (folder/name).open('rb') as stream:assert hashlib.sha256(stream.read(prefix['bytes'])).hexdigest()==prefix['sha256']
        rows=[r for r in old.ctl.execution.complete_jsonl(folder/'h1_training_metrics.jsonl') if r['iteration']>parent['iteration']]
        iterations=list(range(parent['iteration']+1,final['iteration']+1))
        assert [r['iteration'] for r in rows]==iterations
        assignments=[r for r in old.ctl.execution.complete_jsonl(folder/'opponent_assignments.jsonl') if r['applies_to_iteration']>parent['iteration']]
        assert [r['applies_to_iteration'] for r in assignments]==iterations
        assert all(r['ppo_replay_ratio']==.5 and r['ppo_replay_buffer_iterations']==2 and not r['gradient_diagnostics'] for r in rows)
        physical=final['environment_hand_accounting']['completed_hands']-parent_contract['physical_hands']
        transitions=final['total_hands']-parent['total_hands']
        replay=final['ppo_replay_cumulative_rows']-parent['ppo_replay_cumulative_rows']
        assert physical>=1048576 and transitions>0 and replay==sum(r['ppo_replay_rows'] for r in rows)>0
        assert len(final['ppo_replay_entries'])==2 and len(final['pool_snapshots'])==9
        verification=old.read(folder/'verification.json')
        assert verification['checkpoint_sha256']==old.sha(folder/'latest.pt')
        assert verification['new_physical_hands']==physical and verification['new_transition_hands']==transitions
        assert old.read(folder/'mixture_observation.json')['clean_return']
        training.append(dict(seed=seed,physical_hands=physical,transition_hands=transitions,replay_rows=replay,iterations=len(rows),optimizer=optimizer,namespace=namespace,wall_seconds=verification['wall_seconds']))
        for name in ('latest.pt','initial_resumed_state.pt','h1_training_metrics.jsonl','opponent_assignments.jsonl','verification.json','initial_resume_gate.json'):
            hashes[str(folder/name)]=old.sha(folder/name)
        del parent, initial, final
        evaluation[str(seed)]={}; repeated=[]
        for label in ('extension_start','earlier_root'):
            out=BASE/f'eval_seed{seed}_{label}';path=out/'common_deck_pairs.jsonl.gz'
            digest=old.sha(path); report=old.read(out/'summary.json')
            assert digest==report['raw_pairs_sha256'] and report['evaluation_hands']==32768 and report['status']=='COMPLETED'
            baseline=Path(parent_contract['path']) if label=='extension_start' else Path(contract['roots'][str(seed)])
            assert report['input_sha256']=={'control':old.sha(baseline),'treatment':old.sha(folder/'latest.pt'),**{f'anchor:{name}':old.sha(Path(p)) for name,p in contract['anchors'].items()}}
            assert report['policy_mode']=='greedy' and report['starting_stack_bb']==200 and report['observation_style']=='legacy_v4'
            with gzip.open(path,'rt',encoding='utf-8') as stream:rows=[json.loads(line) for line in stream]
            assert len(rows)==8192
            mapping={(r['anchor'],r['pair_index']):r for r in rows};assert len(mapping)==8192
            endpoint_map={}
            for ai,anchor in enumerate(anchors):
                rng=random.Random(202609082000+100*seed+1000003*ai)
                for index in range(1024):
                    deck=list(range(52));rng.shuffle(deck)
                    row=mapping[anchor,index]
                    assert row['deck']==deck
                    assert row['anchor_seed']==202609082000+100*seed+1000003*ai
                    for key in ('control_rewards_bb','treatment_rewards_bb'):
                        assert len(row[key])==2 and all(math.isfinite(v) and abs(v)<=200 for v in row[key])
                    if label=='extension_start':assert tuple(deck) not in seen;seen.add(tuple(deck))
                    endpoint_map[anchor,index]=(deck,row['treatment_rewards_bb'])
            repeated.append(endpoint_map)
            evaluation[str(seed)][label]=summarize(rows,anchors)
            hashes[str(path)]=digest;hashes[str(out/'summary.json')]=old.sha(out/'summary.json')
        assert repeated[0]==repeated[1]
    assert len(seen)==16384
    prior_rows=0
    for corpus,opener in ((contract['prior_gzip'],gzip.open),(contract['prior_plain'],open)):
        for path,digest in corpus.items():
            assert old.sha(Path(path))==digest
            with opener(path,'rt',encoding='utf-8') as stream:
                for line in stream:assert tuple(json.loads(line)['deck']) not in seen;prior_rows+=1
            assert old.sha(Path(path))==digest
    assert prior_rows==contract['historical_rows']
    directional=all(r['pooled']['bb100']>0 and all(s['bb100']>0 for s in r['by_seat'].values()) and all(p['pooled']['bb100']>0 for p in r['by_panel'].values()) for seed in evaluation.values() for r in seed.values())
    old.ctl.execution.check_hashes(hashes)
    old.write_new(BASE/'post_terminal_review.json',dict(passed=True,training=training,training_hands=sum(r['physical_hands'] for r in training),transition_hands=sum(r['transition_hands'] for r in training),replay_rows=sum(r['replay_rows'] for r in training),evaluation_hands=131072,final_qualification_hands=0,unique_evaluation_decks=len(seen),prior_rows=prior_rows,overlap=0,evaluation=evaluation,directional_breadth_condition=directional,input_sha256=hashes,controller_wall_seconds=terminal['wall_seconds'],review_wall_seconds=time.monotonic()-started,scope='Conditional unadjusted paired-deck CIs; internal shared-ancestry panels. Directional condition alone does not authorize further scale; review collapse and cost. Statistical training continuation, not bitwise worker equivalence or proof of unique training decks.'))
    print(json.dumps(dict(passed=True,directional_breadth_condition=directional)))


if __name__=='__main__':main()
