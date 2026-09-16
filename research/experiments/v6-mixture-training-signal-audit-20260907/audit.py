"""Bounded, zero-new-hand descriptive audit of immutable completed trial suffixes."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import math
import statistics
import sys

BASE = Path(__file__).resolve().parent
TRIAL = BASE.parent/'v6-opponent-execution-mixture-two-seed-geometric-20260907'
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def require(v, m):
    if not v: raise ValueError(m)
def summary(values):
    require(values and all(math.isfinite(x) for x in values), 'invalid numeric metric')
    n=max(1,len(values)//4)
    return dict(mean=statistics.mean(values), first_quarter=statistics.mean(values[:n]),
                last_quarter=statistics.mean(values[-n:]), minimum=min(values), maximum=max(values))
def main():
    require(not (BASE/'report.json').exists(), 'preserve output')
    review=read(TRIAL/'post_terminal_review.json')
    require(review['passed'] and read(TRIAL/'experiment.json')['status']=='COMPLETED','not terminal')
    hashes={str(Path(__file__)):sha(Path(__file__)),str(TRIAL/'post_terminal_review.json'):sha(TRIAL/'post_terminal_review.json')}
    branches={}
    for stage in (1,2):
        for seed in (1,3):
            for arm in ('control','mixture'):
                name=f'seed{seed}_{arm}_stage{stage}'; folder=TRIAL/name
                rows_by_file={}; prefixes=read(folder/'prefixes.json')
                for filename in ('h1_training_metrics.jsonl','opponent_assignments.jsonl'):
                    p=folder/filename; digest=sha(p)
                    require(review['input_sha256'][str(p)]==digest,'unbound input')
                    hashes[str(p)]=digest
                    with p.open('rb') as f:
                        require(hashlib.sha256(f.read(prefixes[filename]['bytes'])).hexdigest()==prefixes[filename]['sha256'],'prefix mismatch')
                        rows_by_file[filename]=[json.loads(x) for x in f if x.strip()]
                rows=rows_by_file['h1_training_metrics.jsonl']
                assignments={r['applies_to_iteration']:r for r in rows_by_file['opponent_assignments.jsonl']}
                require(len(rows)==review['health'][name]['completed_training_iterations'],'iteration coverage')
                require([r['iteration'] for r in rows]==list(range(rows[0]['iteration'],rows[-1]['iteration']+1)),'iteration gap')
                slots=Counter(); ids=Counter(); worker_exposure=Counter(); seat_street=Counter()
                for r in rows:
                    a=assignments.get(r['iteration'])
                    require(a is not None,'missing assignment for completed iteration')
                    refs={x['local_index']:x['snapshot_id'] for x in a['pool_snapshot_refs']}
                    for g in r['adaptive_opponent_league']:
                        n=g['iteration_hands']; slot=g['opponent_id']; slots[str(slot)]+=n
                        if n:
                            require(slot in refs,'unresolved observed slot')
                            ids[str(refs[slot])]+=n
                    for w in a['workers']:
                        o=w['opponent']; key='self_play' if o['kind']=='self_play' else str(o['snapshot_id'])
                        worker_exposure[key]+=1
                    for group,actions in r['advantage_by_position_street_action_slot'].items():
                        seat_street[group]+=sum(v['rows'] for v in actions.values())
                scalar_keys=('entropy','approx_kl','reference_policy_kl','clip_frac','preupdate_critic_mse','reward_per_hand','policy_advantage_clip_fraction','actor_terminal_reward_variance')
                metrics={k:summary([r[k] for r in rows]) for k in scalar_keys if all(isinstance(r.get(k),(float,int)) for r in rows)}
                fresh=sum(r['fresh_policy_rows'] for r in rows); replay=sum(r['ppo_replay_rows'] for r in rows)
                branches[name]={'iterations':len(rows),'metrics':metrics,'missing_scalar_metrics':[k for k in scalar_keys if k not in metrics],
                    'transition_hand_observations_by_snapshot_id':dict(ids),'worker_iteration_assignments_by_snapshot_id':dict(worker_exposure),
                    'anchor_observations':sum(ids[str(i)] for i in (0,1,2)), 'recent_observations':sum(v for k,v in ids.items() if int(k)>2),
                    'distinct_observed_recent_ids':sum(int(k)>2 and v>0 for k,v in ids.items()),
                    'seat_street_advantage_rows_including_replay':dict(seat_street),'fresh_policy_rows':fresh,'replay_rows':replay,
                    'kl_early_stops':sum(bool(r['kl_early_stop_triggered']) for r in rows)}
    require(all(sha(Path(p))==h for p,h in hashes.items()),'input changed')
    output={'passed':True,'command':sys.orig_argv,'input_sha256':hashes,'branches':branches,'new_training_hands':0,'evaluation_hands':0,
       'limitations':['Iteration reward and critic MSE are descriptive, not causal strength or calibrated value accuracy.',
          'Worker assignments are not physical hand counts. Adaptive observations are transition-bearing observations, not unique deals.',
          'Seat/street rows include replay; no joint opponent-by-seat hand exposure or gradient mass is reconstructed.',
          'Recent snapshot diversity is not strategic diversity. Four repeated evaluation anchors are not proof of unseen-opponent generalization.',
          'Quarter means are serially dependent, uncontrolled summaries, not significance tests.']}
    with (BASE/'report.json').open('x',encoding='utf-8') as f: json.dump(output,f,indent=2,allow_nan=False)
    print(json.dumps({'passed':True,'branches':len(branches),'new_training_hands':0}))
if __name__=='__main__': main()
