"""Terminal evidence review of both real expanded-pool smokes."""
import hashlib
import json
import sys
import time
from pathlib import Path
import psutil
import torch
import run_smoke_v3 as s
from pool_gate import normalized_pool

def live(pid,ct):
    try: return abs(psutil.Process(int(pid)).create_time()-ct)<.001
    except psutil.NoSuchProcess: return False
def main():
    torch.set_num_threads(1); start=time.perf_counter()
    owner=s.read(s.BASE/'smoke_ownership_v3.json')
    s.require(not live(owner['pid'],owner['create_time']),'owner live')
    result=s.read(s.BASE/'smoke_result_v3.json'); s.require(result['passed'] and len(result['runs'])==2,'incomplete')
    hashes=dict(s.read(s.BASE/'smoke_input_contract_v3.json')['input_sha256'])
    s.ctl.execution.check_hashes(hashes)
    for p in (Path(__file__),s.BASE/'smoke_result_v3.json',s.BASE/'smoke_ownership_v3.json'): hashes[str(p)]=s.sha(p)
    reports={}; physical=transitions=replay=0; namespaces=set(); wall=0
    expected=s.read(s.BASE.parent/'v6-expanded-assignment-boundary-20260907/report.json')
    for seed in (1,3):
        run=s.BASE/f'seed{seed}_smoke_v3'; term=s.read(run/'termination.json'); proc=s.read(run/'process.json')
        s.require(term['exit_code']==0 and not term['observer_errors'] and not term['remaining_observed_child_pids'],'unclean')
        s.require(not live(proc['pid'],proc['create_time']) and all(not live(p,c) for p,c in term['observed_children'].items()),'children live')
        s.require(len(term['observed_children'])>=12,'worker identities missing')
        binding=s.read(run/'parent_contract.json'); p=torch.load(binding['path'],map_location='cpu',weights_only=False)
        initial=torch.load(run/'initial_resumed_state.pt',map_location='cpu',weights_only=False)
        final=torch.load(run/'latest.pt',map_location='cpu',weights_only=False)
        normalized=normalized_pool(p,200); gate=s.read(run/'initial_resume_gate.json')
        s.require(gate['passed'] and all(s.state_equal(normalized[k],initial[k]) for k in gate['exact_keys']),'initial state')
        s.require(s.sha(binding['path'])==binding['sha256'] and s.sha(run/'initial_resumed_state.pt')==gate['initial_sha256'],'initial SHA')
        for name,info in s.read(run/'prefixes.json').items():
            with (run/name).open('rb') as f:
                s.require(hashlib.sha256(f.read(info['bytes'])).hexdigest()==info['sha256'],'prefix changed')
        with (run/'opponent_assignments.jsonl').open(encoding='utf-8') as f: records=[json.loads(x) for x in f if x.strip()]
        new=[x for x in records if p['iteration']<x['applies_to_iteration']<=final['iteration']]
        s.require(len(new)==final['iteration']-p['iteration'],'assignment suffix incomplete')
        s.require([w['opponent']['local_index'] for w in new[0]['workers']]==expected['parents'][str(seed)]['first_nine_slot_assignment'],'first assignment changed')
        added=set(p['expanded_family_pool_contract']['new_ids']); observed={w['opponent'].get('snapshot_id') for row in new for w in row['workers']}
        s.require(bool(added&observed),'no added family assigned')
        metrics=s.ctl.execution.complete_jsonl(run/'h1_training_metrics.jsonl')
        actual_added=set()
        for row in new:
            metric=next(x for x in metrics if x['iteration']==row['applies_to_iteration'])
            ids={x['local_index']:x['snapshot_id'] for x in row['pool_snapshot_refs']}
            actual_added.update(ids[g['opponent_id']] for g in metric['adaptive_opponent_league'] if g['iteration_hands']>0 and ids[g['opponent_id']] in added)
        s.require(actual_added,'no added-family transition evidence')
        fixed={x['id'] for x in p['pool_snapshots'] if x['score_components'].get('kind')=='initial_external_opponent'}
        s.require(len(final['pool_snapshots'])==9 and fixed.issubset({x['id'] for x in final['pool_snapshots']}),'anchors lost')
        verify=s.read(run/'verification.json'); s.require(s.sha(run/'latest.pt')==verify['checkpoint_sha256'],'final SHA')
        s.require(s.ctl.prior.optimizer_step_audit(p,final,True)==verify['optimizer'],'optimizer audit')
        ns=final['fixed_deal_attempt']['receipt']['namespace']; s.require(ns not in namespaces and ns!=p['fixed_deal_attempt']['receipt']['namespace'],'namespace reuse'); namespaces.add(ns)
        physical+=verify['new_physical_hands']; transitions+=verify['new_transition_hands']; replay+=verify['new_replay_rows']; wall+=term['wall_seconds']
        s.require(verify['new_physical_hands']==final['environment_hand_accounting']['completed_hands']-p['environment_hand_accounting']['completed_hands'],'physical count')
        reports[str(seed)]={'passed':True,'new_assigned_family_ids':sorted(added&observed),'new_family_ids_with_transition_evidence':sorted(actual_added),'namespace':ns}
        for name in ('latest.pt','initial_resumed_state.pt','verification.json','initial_resume_gate.json','termination.json','process.json','command.json','h1_training_metrics.jsonl','opponent_assignments.jsonl','mixture_runtime.json','mixture_observation.json'): hashes[str(run/name)]=s.sha(run/name)
    s.require(physical==result['new_physical_hands'],'total mismatch'); s.ctl.execution.check_hashes(hashes)
    s.write_new(s.BASE/'terminal_review.json',{'passed':True,'command':sys.orig_argv,'input_sha256':hashes,'seeds':reports,'new_physical_hands':physical,'new_transition_hands':transitions,'new_replay_rows':replay,'training_wall_seconds':wall,'review_wall_seconds':time.perf_counter()-start,'evaluation_hands':0,'final_qualification_hands':0,'scope':'Mechanism and statistical continuation, not strength evidence or full unique training deck coverage.'})
    print(json.dumps({'passed':True,'new_physical_hands':physical,'seeds':reports}))
if __name__=='__main__': main()
