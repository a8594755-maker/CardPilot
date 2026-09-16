"""Outcome-free preserved-state mixture fidelity analysis; no training/gameplay."""
from datetime import datetime,timezone
import copy
import json
import math
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

import numpy as np
import psutil
import torch
from mixture import Posterior,distances,hand_summary

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
AVERAGE=ROOT/'research/experiments/v6-fictitious-average-phase2-20260831'
EXTERNAL=ROOT/'research/experiments/v6-fictitious-average-phase2-fresh20k-slumbot-20260831'
RUNTIME=AVERAGE/'execution_code/source_files/scripts'
AVERAGE_REVIEW='9f76cf2c0ae6109ee366f05839d98d0e578e5a7dce994aae9d58fe8a62674293'
EXTERNAL_REVIEW='7bfa2ac10f555fc0585c3ab6e4375c8db9fce50806351645214a948542153b3b'
MODEL_SHAS=['cd7ce2b27cf3a86e96141432c92c6f92a3eb923dce519d1f1128af5acbb2364b',
 '58ef62e875ce8ad1ecf518a1a65c8f54ba711b3bc1ea1a3ab3a00ed1e1a3540d',
 '393fb9e119ba73864ee76f6732c468d3e09c1329da3625f167f53de8321eea17',
 'c60dfc881ff1b97245219b226eabb5f4c00c1a3d421f71681b63097f45bfa3ea']
KEYS=('card_info','action_info','extra_info','legal_mask')
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(RUNTIME))
sys.path.insert(0,str(AVERAGE))
from research.experiment_log import atomic_json,capture_code_provenance,sha256_file
from alpha_holdem.execution_v6 import load_policy,decide
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.policy_contract_v6 import observation,from_external,apply_incr
from temporal_average import observation_digest,softmax_legal

def read(path):return json.loads(Path(path).read_text())
def sha(path):return sha256_file(Path(path))
def write(name,value):atomic_json(BASE/name,value)
def log(*args):
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*map(str,args)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)

def require_parents():
    assert sha(AVERAGE/'reviewed_analysis.json')==AVERAGE_REVIEW
    assert sha(EXTERNAL/'reviewed_analysis.json')==EXTERNAL_REVIEW
    for directory in (AVERAGE,EXTERNAL):
        assert read(directory/'experiment.json')['status']=='COMPLETED'
        assert read(directory/'reviewed_analysis.json')['status']=='PASS'
    report=read(EXTERNAL/'reviewed_analysis.json')
    assert report['evaluation_hands']==report['slumbot_hands']==20000
    assert report['model_sha256']==MODEL_SHAS[3] and report['decision']=='PILOT_POINT_NOT_POSITIVE'
    assert read(AVERAGE/'reviewed_analysis.json')['model_sha256']==MODEL_SHAS[3]
    assert sha(AVERAGE/'temporal_average.py')=='836ad2770bd1ec725c57cf53757c26bb81ea813f72bb506e0ca71759e3c2b0db'
    for row in read(AVERAGE/'execution_code/copy_manifest.json'):
        assert sha(ROOT/row['copy'])==sha(ROOT/row['original'])==row['sha256']

def inputs():
    require_parents()
    paths=[AVERAGE/'teachers'/f'teacher{i:02d}.pt' for i in range(3)]+[AVERAGE/'latest.pt']
    models=[]
    for i,(path,digest) in enumerate(zip(paths,MODEL_SHAS)):
        assert sha(path)==digest
        models.append(dict(index=i,path=str(path),sha256=digest))
    data=[AVERAGE/'validation_hands.jsonl']+[EXTERNAL/'sessions'/f's{i:02d}'/'hands.jsonl' for i in range(1,9)]
    records={str(d):read(d/'experiment.json') for d in (AVERAGE,EXTERNAL)}
    for path in data:
        record=records[str(AVERAGE if path.parent==AVERAGE else EXTERNAL)]
        item=next(v for p,v in record['artifact_integrity'].items() if Path(p).resolve()==path.resolve())
        assert sha(path)==item['sha256']
    deps=[*data,AVERAGE/'reviewed_analysis.json',EXTERNAL/'reviewed_analysis.json',
        EXTERNAL/'combined_audit.json',AVERAGE/'execution_code/copy_manifest.json',AVERAGE/'temporal_average.py']
    return dict(models=models,dependencies=[dict(path=str(p),sha256=sha(p)) for p in deps],
        native_physical_hands=8192,external_physical_hands=20000,new_unique_hands=0)

def capture():
    directory=BASE/'execution_code'
    directory.mkdir()
    paths=['research/experiment_log.py']+[p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in ('.py','.md')]
    capture_code_provenance(ROOT,directory,paths)
    copies=[]
    for relative in paths:
        target=directory/'source_files'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target)
        copies.append(dict(original=relative,copy=target.relative_to(ROOT).as_posix(),sha256=sha(target)))
    write('execution_code/copy_manifest.json',copies)
    log(*[v for n in ('source_manifest.json','code.patch','copy_manifest.json') for v in ('--artifact',directory/n)])
    return copies

def verify(copies,manifest):
    require_parents()
    for row in copies:
        assert sha(ROOT/row['original'])==sha(ROOT/row['copy'])==row['sha256']
    for row in manifest['models']+manifest['dependencies']:
        assert sha(row['path'])==row['sha256']

def preserved_inputs():
    arrays={k:[] for k in KEYS}
    metadata,known,qualification_states=[],[],[]
    counts=dict(native_physical_hands=0,native_all_decisions=0,native_hero_decisions=0,
                external_physical_hands=0,external_hero_decisions=0)
    def add(state,row,recorded):
        obs,table=observation(state)
        assert table[row['action_slot']]==row.pop('increment')
        for key in KEYS:arrays[key].append(obs[key])
        row['observation_sha256']=observation_digest(obs)
        metadata.append(row)
        known.append(recorded)
        if row['cohort']=='native' and len(qualification_states)<32 or row['cohort']=='slumbot' and len(qualification_states)<64:
            qualification_states.append(copy.deepcopy(state))
    with (AVERAGE/'validation_hands.jsonl').open() as handle:
        for index,line in enumerate(handle):
            assert line.endswith('\n')
            raw=json.loads(line)
            assert raw['index']==index
            state=ChipState.new(raw['deck'])
            hero,own=index%2,0
            for event in raw['events']:
                obs,table=observation(state)
                assert state.actor==event['seat'] and table[event['action']]==event['increment']
                assert event['teacher']==raw['teachers'][state.actor]
                assert observation_digest(obs)==event['observation_sha256']
                counts['native_all_decisions']+=1
                if state.actor==hero:
                    add(state,dict(cohort='native',session=-1,hand=index,seat=hero,street=state.street,
                        decision=own,action_slot=event['action'],known_model_index=event['teacher'],
                        increment=event['increment']),event['probabilities'])
                    own+=1
                    counts['native_hero_decisions']+=1
                state=apply_incr(state,event['increment'])
            assert state.terminal
            counts['native_physical_hands']+=1
    assert counts['native_physical_hands']==8192 and counts['native_all_decisions']==70081 and len(qualification_states)==32
    for session in range(8):
        with (EXTERNAL/'sessions'/f's{session+1:02d}'/'hands.jsonl').open() as handle:
            for index,line in enumerate(handle):
                assert line.endswith('\n')
                raw=json.loads(line)
                assert raw['successful_hand']==raw['attempted_hand']==index+1 and raw['model_sha256']==MODEL_SHAS[3]
                assert raw['session_id']==f'v6_fictitious_average_phase2_fresh20k_20260831_s{session+1:02d}'
                for di,event in enumerate(raw['decisions']):
                    response=event['response']
                    state=from_external(response['action'],response['hole_cards'],response['board'],response['client_pos'])
                    obs,table=observation(state)
                    assert table==event['action_table'] and np.array_equal(obs['legal_mask'],event['legal_mask'])
                    add(state,dict(cohort='slumbot',session=session,hand=session*2500+index,seat=response['client_pos'],
                        street=state.street,decision=di,action_slot=event['selected_action_slot'],
                        known_model_index=3,increment=event['direct_increment']),event['behavior_probs'])
                    counts['external_hero_decisions']+=1
                counts['external_physical_hands']+=1
            assert index+1==2500
    assert counts['external_physical_hands']==20000 and counts['external_hero_decisions']==61011
    assert len(qualification_states)==64 and len(metadata)==sum(counts[k] for k in ('native_hero_decisions','external_hero_decisions'))
    return {k:np.stack(v) for k,v in arrays.items()},metadata,np.asarray(known,dtype=np.float64),qualification_states,counts

@torch.no_grad()
def infer(model,arrays,device,query,batch=512):
    pieces=[]
    for begin in range(0,len(arrays['legal_mask']),batch):
        stop=min(begin+batch,len(arrays['legal_mask']))
        tensors=[torch.as_tensor(arrays[k][begin:stop],dtype=torch.float32,device=device) for k in KEYS]
        logits=query(lambda:model(*tensors)[0],stop-begin)
        pieces.append(softmax_legal(logits.detach().cpu().numpy(),arrays['legal_mask'][begin:stop]))
    return np.concatenate(pieces)

def qualify(models,manifest,states,query):
    obs=[observation(state)[0] for state in states]
    arrays={k:np.stack([o[k] for o in obs]) for k in KEYS}
    rows=[]
    for i,model in enumerate(models):
        cpu,_,digest=load_policy(manifest['models'][i]['path'],'cpu')
        assert digest==MODEL_SHAS[i]
        scalar=np.asarray([query(lambda:decide(cpu,state,uniform=.371)[1]['behavior_probs'],1) for state in states])
        cb=infer(cpu,arrays,'cpu',query,64)
        gb=infer(model,arrays,'cuda',query,64)
        ce,ge=float(np.max(np.abs(cb-scalar))),float(np.max(np.abs(gb-scalar)))
        assert max(ce,ge)<=2e-5
        rows.append(dict(model=i,states=64,cpu_batch_delta=ce,gpu_batch_delta=ge))
        del cpu
    result=dict(status='PASS',model_queries=768,new_unique_hands=0,evidence=rows)
    write('batch_qualification.json',result)
    return result

def analyze(metadata,p):
    size=len(metadata)
    post=np.zeros((size,3));mixtures=np.zeros((size,9));tvs=np.zeros(size);js=np.zeros(size);naive_tvs=np.zeros(size)
    current=None
    for i,row in enumerate(metadata):
        key=row['cohort'],row['hand']
        if key!=current:
            posterior=Posterior()
            current=key
        teacher=p[:3,i]
        q,w=posterior.before(teacher)
        mixtures[i],post[i]=q,w
        tvs[i],js[i]=distances(q,p[3,i])
        naive_tvs[i]=distances(teacher.mean(0),p[3,i])[0]
        posterior.observe_own_action(teacher,row['action_slot'])
    summary=hand_summary(metadata,tvs)
    for cohort in ('native','slumbot'):
        indexes=np.asarray([i for i,r in enumerate(metadata) if r['cohort']==cohort])
        summary[cohort].update(decision_count=len(indexes),decision_mean_tv=float(tvs[indexes].mean()),
            decision_mean_js=float(js[indexes].mean()),decision_mean_naive_tv=float(naive_tvs[indexes].mean()))
    strata={}
    for cohort in ('native','slumbot'):
        for seat in (0,1):
            for street in range(4):
                ix=[i for i,r in enumerate(metadata) if r['cohort']==cohort and r['seat']==seat and r['street']==street]
                if ix:strata[f'{cohort}_seat{seat}_street{street}']=dict(decisions=len(ix),mean_tv=float(tvs[ix].mean()))
    summary['strata']=strata
    return dict(posterior=post,mixture=mixtures,tv=tvs,js=js,naive_tv=naive_tvs),summary

def main():
    require_parents()
    if sys.argv[1:] or (BASE/'execution.json').exists():raise ValueError('No repeated diagnostic or overwrite')
    for p in psutil.process_iter(['name','cmdline']):
        if p.pid!=os.getpid() and (p.info['name'] or '').lower().startswith('python') and any(
            Path(a).name in ('train_v5.py','run_distillation.py','run_pilot.py','run_readiness.py','v6_mirror_eval.py','play_slumbot_v6_journaled.py')
            for a in p.info['cmdline'] or []):raise ValueError('Another poker workload is active')
    assert torch.cuda.is_available()
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform=='win32' else 5)
    begin=time.monotonic()
    execution=dict(status='PREPARING',pid=os.getpid(),create_time=psutil.Process().create_time(),
        started_at=datetime.now(timezone.utc).isoformat(),attempted_model_queries=0,completed_model_queries=0,
        new_training_hands=0,evaluation_hands=0,slumbot_hands=0,network_connection_attempts=0)
    write('execution.json',execution)
    success=False
    def query(fn,n):
        execution['attempted_model_queries']+=n
        value=fn()
        execution['completed_model_queries']+=n
        return value
    def deny(*args,**kwargs):
        execution['network_connection_attempts']+=1
        raise RuntimeError('Offline diagnostic prohibits network')
    try:
        copies=capture();manifest=inputs();write('input_manifest.json',manifest)
        cmd=['-m','pytest',str(BASE/'test_mixture.py'),'-q',f'--junitxml={BASE/"prerun_tests.xml"}']
        log('--command',subprocess.list2cmdline(['python',*cmd]))
        subprocess.run([sys.executable,*cmd],cwd=ROOT,check=True)
        verify(copies,manifest)
        execution['status']='RECONSTRUCTING_PRESERVED_STATES';write('execution.json',execution)
        arrays,metadata,known,states,coverage=preserved_inputs()
        np.savez_compressed(BASE/'observations.npz',**arrays)
        with (BASE/'metadata.jsonl').open('x') as handle:
            for row in metadata:handle.write(json.dumps(row)+'\n')
        write('coverage.json',coverage)
        execution.update(status='FROZEN_MODEL_INFERENCE',states=len(metadata));write('execution.json',execution)
        with patch.object(socket.socket,'connect',deny),patch.object(socket.socket,'connect_ex',deny),patch.object(socket,'create_connection',deny):
            models=[load_policy(row['path'],'cuda')[0] for row in manifest['models']]
            qualify(models,manifest,states,query)
            probabilities=[]
            for i,model in enumerate(models):
                p=infer(model,arrays,'cuda',query)
                np.save(BASE/f'probabilities_model{i}.npy',p)
                probabilities.append(p)
                execution['models_inferred']=i+1;write('execution.json',execution)
                log('--count',f'diagnostic_model_queries={execution["completed_model_queries"]}')
            p=np.asarray(probabilities)
        assert execution['network_connection_attempts']==0
        n=len(metadata)
        actual=p[np.asarray([r['known_model_index'] for r in metadata]),np.arange(n)]
        native=n-61011
        deltas=dict(native_teacher_max=float(np.max(np.abs(actual[:native]-known[:native]))),
                    external_student_max=float(np.max(np.abs(actual[native:]-known[native:]))))
        assert max(deltas.values())<=1e-4
        write('full_reference_probability_check.json',dict(status='PASS',tolerance=1e-4,**deltas))
        result,summary=analyze(metadata,p)
        np.savez_compressed(BASE/'mixture_metrics.npz',**result)
        assert execution['completed_model_queries']==execution['attempted_model_queries']==4*n+768
        verify(copies,manifest)
        write('completed_analysis.json',dict(status='COMPLETED_PENDING_REVIEW',statistics=summary,coverage=coverage,
            model_queries=4*n+768,new_training_hands=0,evaluation_hands=0,slumbot_hands=0,
            counterfactual_returns_estimated=False,external_data_used_for_training=False,goal_achieved=False))
        success=True
    except BaseException:
        (BASE/'failure.txt').write_text(traceback.format_exc())
        print(traceback.format_exc(),flush=True)
    finally:
        execution.update(status='COMPLETED_PENDING_REVIEW' if success else 'FAILED_PRESERVED',
            finished_at=datetime.now(timezone.utc).isoformat(),wall_time_seconds=time.monotonic()-begin)
        write('execution.json',execution)
        artifacts=[p for p in BASE.iterdir() if p.is_file() and p.name not in ('experiment.json','source_manifest.json','code.patch')]
        log(*[v for p in artifacts for v in ('--artifact',p)],'--count','new_training_hands=0',
            '--count','evaluation_hands=0','--count','slumbot_hands=0','--count',f'diagnostic_model_queries={execution["completed_model_queries"]}')
        print(json.dumps(execution),flush=True)
    if not success:raise SystemExit(1)

if __name__=='__main__':main()
