"""Independent terminal arithmetic/evidence review; no model inference or new hands."""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
import psutil
import torch
import run_pilot as run
from native_relabel import chunks, reconstruct, KEYS

BASE=run.BASE

def independent_targets(probabilities,lengths,actors,slots):
    p=np.asarray(probabilities,dtype=np.longdouble)
    a,s=np.asarray(actors),np.asarray(slots)
    if p.ndim!=3 or p.shape[0]!=3 or p.shape[2]!=9 or a.shape!=(p.shape[1],) or s.shape!=a.shape:
        raise ValueError('Invalid independent reference arrays')
    if not np.isfinite(p).all() or (p<0).any() or not np.allclose(p.sum(2),1,atol=1e-10,rtol=0):
        raise ValueError('Invalid reference distribution')
    if not np.isin(a,[0,1]).all() or not np.isin(s,range(9)).all():
        raise ValueError('Invalid action identity')
    out=np.empty((p.shape[1],9),dtype=np.float64)
    offset=0
    for length in lengths:
        if int(length)!=length or length<=0:raise ValueError('Invalid hand length')
        weights=np.ones((2,3),dtype=np.longdouble)
        for i in range(offset,offset+int(length)):
            seat=int(a[i])
            out[i]=np.sum(weights[seat,:,None]*p[:,i],axis=0)/weights[seat].sum()
            weights[seat]*=p[:,i,int(s[i])]
            total=weights[seat].sum()
            if not total>0:raise ValueError('Impossible observed own history')
            weights[seat]/=total
        offset+=int(length)
    if offset!=p.shape[1]:raise ValueError('Incomplete hand coverage')
    return out

def independently_grouped_tv(p,q,hands,actors,physical_hands=8192):
    groups=[[] for _ in range(physical_hands)]
    for pi,qi,h,a in zip(p,q,hands,actors,strict=True):
        assert 0<=h<physical_hands and a in (0,1)
        assert np.isfinite(pi).all() and np.isfinite(qi).all() and (pi>=0).all() and (qi>=0).all()
        assert abs(math.fsum(pi)-1)<1e-10 and abs(math.fsum(qi)-1)<1e-10
        if a==h%2:groups[int(h)].append(math.fsum(abs(float(x)-float(y)) for x,y in zip(pi,qi))/2)
    return np.asarray([math.fsum(g)/len(g) if g else np.nan for g in groups]),np.asarray([len(g) for g in groups])

def independent_interval(values):
    x=[float(v) for v in values]
    assert len(x)>1 and all(math.isfinite(v) for v in x)
    mean=math.fsum(x)/len(x)
    se=math.sqrt(math.fsum((v-mean)**2 for v in x)/(len(x)*(len(x)-1)))
    return dict(n=len(x),mean=mean,standard_error=se,ci95=[mean-1.96*se,mean+1.96*se])

def not_alive(execution):
    try:return abs(psutil.Process(execution['pid']).create_time()-execution['create_time'])>.001
    except psutil.NoSuchProcess:return True

def eager(path):
    with np.load(path,allow_pickle=False) as archive:return {k:archive[k] for k in archive.files}

def review_blocks(directory,source,hands,decisions,reservoir=None):
    manifest=run.read(directory/'block_manifest.json')
    index=None if reservoir is None else {tuple(map(int,key)):i for i,key in enumerate(reservoir['ids'])}
    assert index is None or len(index)==len(reservoir['ids'])
    retained=None if index is None else np.full((len(index),9),np.nan)
    seen=None if index is None else np.zeros(len(index),dtype=bool)
    arrays=eager(directory/'validation_arrays.npz') if index is None else None
    meta=eager(directory/'validation_metadata.npz') if index is None else None
    validation_q=np.load(directory/'validation_targets.npy') if index is None else None
    completed=offset=blocks=0
    largest=teacher_delta=0.
    for block,rows in enumerate(chunks(source)):
        item=manifest[block]
        assert item['block']==block and item['first_hand']==completed and item['hands']==len(rows)
        assert item['normalized_lines_sha256']==hashlib.sha256(''.join(line for _,line in rows).encode()).hexdigest()
        path=directory/f'block{block:04d}.npz'
        assert Path(item['path']).resolve()==path.resolve() and run.sha(path)==item['sha256']
        cache=eager(path)
        parsed=reconstruct(rows,completed,index,reservoir)
        n=len(parsed['actors'])
        assert n==item['decisions'] and len(parsed['retained_matches'])==item['retained_rows']
        for key in ('lengths','actors','slots','hand_ids','observation_sha256'):
            assert np.array_equal(cache[key],parsed[key])
        assert np.array_equal(cache['legal_mask'],parsed['arrays']['legal_mask'])
        p=cache['teacher_probabilities']
        assert np.all(p[:,cache['legal_mask']==0]==0)
        actual=p[parsed['known_teachers'],np.arange(n)]
        delta=float(np.abs(actual-parsed['known_probs']).max())
        assert delta<=1e-4 and delta==item['actual_teacher_max_delta']
        teacher_delta=max(teacher_delta,delta)
        q=independent_targets(p,cache['lengths'],cache['actors'],cache['slots'])
        error=float(np.abs(q-cache['targets']).max())
        assert error<2e-12
        largest=max(largest,error)
        if retained is not None:
            for local,position in parsed['retained_matches']:
                assert not seen[position]
                retained[position]=q[local];seen[position]=True
        else:
            for key in KEYS:assert np.array_equal(arrays[key][offset:offset+n],parsed['arrays'][key])
            assert np.array_equal(meta['hands'][offset:offset+n],parsed['hand_ids'])
            assert np.array_equal(meta['actors'][offset:offset+n],parsed['actors'])
            assert np.allclose(validation_q[offset:offset+n],q,atol=2e-12,rtol=0)
        completed+=len(rows);offset+=n;blocks+=1
        if blocks%16==0:print(json.dumps(dict(review=directory.name,old_or_validation_hands=completed)),flush=True)
    assert completed==hands and offset==decisions and blocks==len(manifest)==(hands+1023)//1024
    saved=run.read(directory/'relabel_analysis.json')
    assert saved['status']=='PASS' and saved['hands']==hands and saved['decisions']==decisions
    assert saved['source_sha256']==run.sha(source)
    assert saved['block_manifest_sha256']==run.sha(directory/'block_manifest.json')
    if retained is not None:
        assert seen.all() and np.isfinite(retained).all()
        assert np.array_equal(np.load(directory/'retained_ids.npy'),reservoir['ids'])
        assert np.allclose(np.load(directory/'reach_targets.npy'),retained,atol=2e-12,rtol=0)
    else:
        assert len(validation_q)==len(meta['hands'])==len(meta['actors'])==decisions
        assert all(len(v)==decisions for v in arrays.values())
    return dict(status='PASS',hands=hands,decisions=decisions,blocks=blocks,
        independent_reference_max_delta=largest,actual_teacher_max_delta=teacher_delta,
        retained_rows_verified=0 if index is None else len(index))

def main():
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists():raise ValueError('No repeated terminal review')
    started=time.monotonic()
    torch.set_num_threads(1)
    execution=run.read(BASE/'execution.json')
    assert execution['status']=='COMPLETED_PENDING_REVIEW' and not_alive(execution)
    inputs=run.read(BASE/'input_manifest.json');copies=run.read(BASE/'execution_code/copy_manifest.json')
    run.verify(copies,inputs)
    record=run.read(BASE/'experiment.json');assert record['status']=='RUNNING'
    for label,entry in record['artifact_integrity'].items():
        assert run.sha(Path(label))==entry['sha256'],label
    completed=run.read(BASE/'completed_analysis.json');fit=run.read(BASE/'fit_analysis.json')
    assert completed['status']=='COMPLETED_PENDING_REVIEW' and fit['status']=='PASS'
    reservoir=torch.load(run.PARENT/'reservoir.pt',map_location='cpu',weights_only=False)
    assert reservoir['seen']==2242056 and len(reservoir['ids'])==262144
    train_review=review_blocks(BASE/'training_relabel',run.PARENT/'training_hands.jsonl',262144,2242056,reservoir)
    del reservoir
    audit=run.audit_trace(BASE/'validation_hands.jsonl',seed=2026102401,hands=8192,teacher_count=3)
    saved_audit=run.read(BASE/'validation_collection_audit.json')
    assert audit==saved_audit and audit['status']=='PASS'
    n=audit['decisions']
    validation_review=review_blocks(BASE/'validation_relabel',BASE/'validation_hands.jsonl',8192,n)
    # Independent global deal identity pass (no artifact writer reused).
    unique=set()
    for path,expected in [(run.PARENT/'training_hands.jsonl',262144),(run.PARENT/'validation_hands.jsonl',8192),(BASE/'validation_hands.jsonl',8192)]:
        count=0
        for rows in chunks(path):
            for row,_ in rows:
                assert row['index']==count and sorted(row['deck'])==list(range(52))
                deck=tuple(row['deck']);assert deck not in unique;unique.add(deck);count+=1
        assert count==expected
    assert len(unique)==278528 and run.read(BASE/'fresh_deck_audit.json')['unique_decks_checked']==278528
    del unique
    metrics=[json.loads(line) for line in (BASE/'training_metrics.jsonl').read_text().splitlines()]
    assert len(metrics)==2048 and [r['step'] for r in metrics]==list(range(1,2049))
    generator=np.random.default_rng(2026102004)
    for epoch in range(1,9):
        expected=hashlib.sha256(generator.permutation(262144).tobytes()).hexdigest()
        rows=metrics[(epoch-1)*256:epoch*256]
        assert all(r['epoch']==epoch and r['rows']==1024 and r['epoch_order_sha256']==expected and r['new_training_hands']==0 for r in rows)
        assert all(math.isfinite(r['loss']) and math.isfinite(r['gradient_norm']) for r in rows)
    source=torch.load(inputs['initializer']['path'],map_location='cpu',weights_only=False)
    final=torch.load(BASE/'latest.pt',map_location='cpu',weights_only=False)
    assert final['epoch']==final['iteration']==8 and final['optimizer_steps']==2048 and final['total_hands']==0
    assert final['training_algorithm']=='reach_posterior_distillation_v1'
    assert final['source_weights_sha256']==run.INITIALIZER_SHA and final['source_dataset_sha256']==run.RESERVOIR_SHA
    assert final['input_manifest_sha256']==run.sha(BASE/'input_manifest.json')
    assert final['reach_targets_sha256']==run.sha(BASE/'training_relabel/reach_targets.npy')
    assert final['offline_source_hands']==final['offline_training_rows']==262144
    assert final['environment_hand_accounting']['completed_hands']==0
    assert final['numpy_generator_state']==generator.bit_generator.state
    assert len(final['model'])==86 and set(final['model'])==set(source['model'])
    changed=[k for k,v in final['model'].items() if not torch.equal(v,source['model'][k])]
    expected_changed=[k for k in source['model'] if not k.startswith('value_head.')]
    assert len(changed)==80 and set(changed)==set(expected_changed)==set(fit['changed_policy_parameters'])
    assert all(torch.isfinite(v).all() for v in final['model'].values())
    states=final['optimizer']['state']
    assert len(states)==80 and all(float(v['step'])==2048 for v in states.values())
    assert all(torch.isfinite(t).all() for v in states.values() for t in v.values() if torch.is_tensor(t))
    assert len(final['optimizer']['param_groups'])==1 and final['optimizer']['param_groups'][0]['lr']==1e-4
    digest=run.sha(BASE/'latest.pt')
    assert digest==run.sha(BASE/'checkpoints/epoch08.pt')==fit['model_sha256']
    q=np.load(BASE/'validation_relabel/validation_targets.npy')
    meta=eager(BASE/'validation_relabel/validation_metadata.npz')
    control=np.load(BASE/'control_validation_probabilities.npy')
    candidate=np.load(BASE/'validation_epoch08_probabilities.npy')
    old,counts=independently_grouped_tv(control,q,meta['hands'],meta['actors'])
    new,new_counts=independently_grouped_tv(candidate,q,meta['hands'],meta['actors'])
    assert np.array_equal(counts,new_counts) and np.array_equal(counts,np.load(BASE/'validation_hero_counts.npy'))
    assert np.allclose(old,np.load(BASE/'control_hero_tv.npy'),rtol=0,atol=2e-12,equal_nan=True)
    assert np.allclose(new,np.load(BASE/'validation_epoch08_hero_tv.npy'),rtol=0,atol=2e-12,equal_nan=True)
    use=counts>0
    statistics=dict(control=independent_interval(old[use]),treatment=independent_interval(new[use]),
        paired_control_minus_treatment=independent_interval(old[use]-new[use]))
    for key,value in statistics.items():
        assert value['n']==fit[key]['n']
        for metric in ('mean','standard_error','ci95'):assert np.allclose(value[metric],fit[key][metric],atol=2e-12,rtol=0)
    decision='ADMIT_SEPARATE_STRATEGIC_ASSESSMENT' if statistics['paired_control_minus_treatment']['ci95'][0]>0 and statistics['treatment']['mean']<=.15 else 'REACH_TARGET_FIDELITY_GATE_NOT_PASSED'
    assert decision==fit['decision']
    diagnostics=[]
    for epoch in (0,1,4,8):
        p=np.load(BASE/f'validation_epoch{epoch:02d}_probabilities.npy')
        positive=q>0
        assert np.all(p[positive]>0)
        ce=-np.sum(np.where(positive,q*np.log(np.where(p>0,p,1)),0),axis=1)
        assert np.allclose(ce,np.load(BASE/f'validation_epoch{epoch:02d}_ce.npy'),rtol=0,atol=2e-12)
        middle=(p+q)/2
        def kl(x):
            valid=x>0
            return np.sum(np.where(valid,x*np.log(np.where(valid,x,1)/np.where(middle>0,middle,1)),0),axis=1)
        js=(kl(p)+kl(q))/2
        diagnostics.append(dict(epoch=epoch,all_decision_ce=float(ce.mean()),all_decision_js=float(js.mean())))
    expected=dict(initial_qualification=768,training_relabel=6726168,validation_collection=n,
        validation_relabel=3*n,control_validation=n,student_validation=4*n,final_qualification=192)
    assert {k:v['completed'] for k,v in execution['query_categories'].items()}==expected
    assert all(v['attempted']==v['completed'] for v in execution['query_categories'].values())
    assert execution['completed_model_queries']==completed['model_state_queries']==sum(expected.values())
    assert execution['new_training_hands']==execution['network_connection_attempts']==0 and execution['new_native_validation_hands']==8192
    assert completed['optimizer_rows_processed']==2097152
    assert all(completed[k]==0 for k in ('new_training_hands','strength_evaluation_hands','slumbot_hands','qualification_hands'))
    initial=run.read(BASE/'initial_qualification.json');endpoint=run.read(BASE/'final_qualification.json')
    assert initial['status']==endpoint['status']=='PASS' and initial['model_queries']==768 and endpoint['model_queries']==192
    assert [v['model_sha256'] for v in initial['evidence']]==run.TEACHER_SHAS+[run.CONTROL_SHA]
    assert endpoint['model_sha256']==digest
    assert all(max(v['cpu_delta'],v['gpu_delta'])<=2e-5 for v in initial['evidence']+[endpoint])
    run.verify(copies,inputs)
    report=dict(status='PASS',decision=decision,**statistics,model_sha256=digest,
        physical_validation_hands=8192,hands_with_hero_decisions=int(use.sum()),hands_without_hero_decisions=int((~use).sum()),
        training_relabel=train_review,validation_relabel=validation_review,unique_decks_checked=278528,
        source_native_hands_reused=262144,new_training_hands=0,evaluation_hands=8192,supervised_validation_hands=8192,
        strength_evaluation_hands=0,slumbot_hands=0,qualification_hands=0,goal_achieved=False,
        optimizer_steps=2048,optimizer_rows_processed=2097152,changed_policy_parameter_tensors=80,frozen_value_parameter_tensors=6,
        model_state_queries=sum(expected.values()),independent_review_model_queries=0,diagnostics=diagnostics,
        wall_time_seconds=execution['wall_time_seconds'],review_wall_time_seconds=time.monotonic()-started,
        interpretation='Matched historical-control native fidelity experiment, not a strength result. Full-own-history reference exceeds truncated student history; GPU control was nonconcurrent. No Slumbot data used in learning.')
    run.write('reviewed_analysis.json',report)
    (BASE/'result_summary.md').write_text(f'# Native own-reach target average\n\n{decision}\n\n'
        f'Control hero TV {statistics["control"]["mean"]:.8f}; treatment {statistics["treatment"]["mean"]:.8f}. '
        f'Paired improvement {statistics["paired_control_minus_treatment"]}.\n\n'
        f'8192 fresh native validation hands, {int(use.sum())} with hero decisions; 0 new training hands. '
        f'262144 old reservoir rows reused for 2048 Adam steps; only final epoch08.\n\n'
        f'Independent full-row target/identity/optimizer/hash review PASS. Model SHA256: {digest}.\n\n'
        f'{report["interpretation"]}\n')
    run.log('--command',f'python research/experiments/{BASE.name}/review_finish.py','--artifact',BASE/'reviewed_analysis.json','--artifact',BASE/'result_summary.md',
        '--metric',f'wall_time_seconds={execution["wall_time_seconds"]}','--metric',f'review_wall_time_seconds={report["review_wall_time_seconds"]}')
    subprocess.run([sys.executable,str(run.ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED',
        '--summary',f'Matched native own-reach target fit completed2048steps/8192validationhands: {decision}.',
        '--conclusion',report['interpretation'],'--decision',decision,
        '--next-step','Separately preregister strategic assessment of only the fixed epoch08.' if decision.startswith('ADMIT') else 'Analyze representation/capacity and target fitting before increasing response budget.',
        '--count','new_training_hands=0','--count','evaluation_hands=8192','--count','supervised_validation_hands=8192',
        '--count','slumbot_hands=0','--count','qualification_hands=0','--count','optimizer_rows_processed=2097152'],cwd=run.ROOT,check=True)
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
