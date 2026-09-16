"""Frozen-state fidelity-gap diagnostic; no new hands, training or network."""
from datetime import datetime,timezone
import hashlib,json,math,os,shutil,socket,sys,time,traceback
from pathlib import Path
from unittest.mock import patch
import numpy as np,psutil,torch
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PARENT=ROOT/'research/experiments/v6-reach-target-average-pilot-20260831'
SOURCE=ROOT/'research/experiments/v6-fictitious-average-phase2-20260831'
RUNTIME=PARENT/'execution_code/source_files/research/experiments/v6-fictitious-average-phase2-20260831/execution_code/source_files/scripts'
# The parent runtime copy contains alpha_holdem under its source_files/scripts root.
if not (RUNTIME/'alpha_holdem').exists():RUNTIME=ROOT/'research/experiments/v6-fictitious-average-phase2-20260831/execution_code/source_files/scripts'
sys.path[:0]=[str(ROOT),str(RUNTIME),str(PARENT),str(SOURCE)]
from research.experiment_log import atomic_json,capture_code_provenance,sha256_file
from alpha_holdem.execution_v6 import load_policy
from temporal_average import softmax_legal
from native_relabel import chunks
KEYS=('card_info','action_info','extra_info','legal_mask')
EXPECTED_PARENT_REVIEW='9c439acec863c6cbb02cf89c51356f14e4c676e8a5a6953844bb7a93b4f04890'
QUERY_COUNT=0

def sha(p):return sha256_file(Path(p))
def read(p):return json.loads(Path(p).read_text())
def write(name,value):atomic_json(BASE/name,value)
def logger(*args):import subprocess;subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*map(str,args)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
def interval(x):
    x=[float(v) for v in x];m=math.fsum(x)/len(x);se=math.sqrt(math.fsum((v-m)**2 for v in x)/(len(x)*(len(x)-1)))
    return dict(n=len(x),mean=m,standard_error=se,ci95=[m-1.96*se,m+1.96*se])
def metrics(p,q):
    p=np.asarray(p,dtype=np.float64);q=np.asarray(q,dtype=np.float64)
    tv=np.abs(p-q).sum(1)/2
    with np.errstate(divide='ignore',invalid='ignore'):
        ce=-np.sum(np.where(q>0,q*np.log(np.where(p>0,p,1)),0),axis=1)
        m=(p+q)/2
        klp=np.sum(np.where(p>0,p*np.log(np.where(p>0,p,1)/np.where(m>0,m,1)),0),axis=1)
        klq=np.sum(np.where(q>0,q*np.log(np.where(q>0,q,1)/np.where(m>0,m,1)),0),axis=1)
    return tv,ce,(klp+klq)/2
@torch.no_grad()
def infer(model,arrays):
    global QUERY_COUNT
    out=[];model.eval()
    for begin in range(0,len(arrays['legal_mask']),512):
        stop=min(begin+512,len(arrays['legal_mask']))
        t=[torch.as_tensor(arrays[k][begin:stop],dtype=torch.float32,device='cuda') for k in KEYS]
        out.append(softmax_legal(model(*t)[0].cpu().numpy(),arrays['legal_mask'][begin:stop]));QUERY_COUNT+=stop-begin
    return np.concatenate(out)
def hero(p,q,hands,actors):
    groups=[[] for _ in range(8192)]
    for i,(h,a) in enumerate(zip(hands,actors,strict=True)):
        if a==h%2:groups[int(h)].append(float(np.abs(p[i]-q[i]).sum()/2))
    return np.asarray([math.fsum(g)/len(g) if g else np.nan for g in groups])
def capture():
    out=BASE/'execution_code';out.mkdir()
    paths=['research/experiment_log.py']+[p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in ('.py','.md')]
    capture_code_provenance(ROOT,out,paths);copies=[]
    for rel in paths:
        target=out/'source_files'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,target)
        copies.append(dict(original=rel,copy=target.relative_to(ROOT).as_posix(),sha256=sha(target)))
    write('execution_code/copy_manifest.json',copies);return copies
def validation_metadata():
    from alpha_holdem.rules_v6 import ChipState
    from alpha_holdem.policy_contract_v6 import apply_incr
    fields={k:[] for k in ('hand','actor','street','depth','legal','own_prior','truncated','posterior_max','teacher_disagreement','target_entropy')}
    offset=0
    for block,rows in enumerate(chunks(PARENT/'validation_hands.jsonl')):
        with np.load(PARENT/'validation_relabel'/f'block{block:04d}.npz') as z:cache={k:z[k] for k in z.files}
        p,q=cache['teacher_probabilities'],cache['targets'];local=0
        for row,_ in rows:
            weights=np.ones((2,3),dtype=np.longdouble)/3
            state=ChipState.new(row['deck']);own=[0,0]
            for event in row['events']:
                a=state.actor
                pair=[np.abs(p[x,local]-p[y,local]).sum()/2 for x,y in ((0,1),(0,2),(1,2))]
                qq=q[local]
                fields['hand'].append(row['index']);fields['actor'].append(a);fields['street'].append(state.street)
                fields['depth'].append(local);fields['legal'].append(int(cache['legal_mask'][local].sum()))
                fields['own_prior'].append(own[a]);fields['truncated'].append(sum(e.street==state.street for e in state.history)>6)
                fields['posterior_max'].append(float(weights[a].max()/weights[a].sum()))
                fields['teacher_disagreement'].append(math.fsum(map(float,pair))/3)
                fields['target_entropy'].append(-math.fsum(float(x)*math.log(float(x)) for x in qq if x>0))
                weights[a]*=p[:,local,event['action']];weights[a]/=weights[a].sum();own[a]+=1
                state=apply_incr(state,event['increment']);local+=1
            assert state.terminal
        assert local==len(q)
        offset+=local
    assert offset==69516
    result={k:np.asarray(v) for k,v in fields.items()};np.savez_compressed(BASE/'validation_metadata.npz',**result)
    return result
def stratum_summary(p,q,meta):
    tv,ce,js=metrics(p,q);out={}
    specs={'street':[(meta['street']==i) for i in range(4)],'truncated':[~meta['truncated'],meta['truncated']]}
    for key in ('posterior_max','teacher_disagreement','target_entropy'):
        cuts=np.quantile(meta[key],[.25,.5,.75]);specs[key]=[np.digitize(meta[key],cuts)==i for i in range(4)]
    for name,masks in specs.items():
        out[name]=[dict(n=int(m.sum()),mean_tv=float(tv[m].mean()) if m.any() else None,mean_ce=float(ce[m].mean()) if m.any() else None) for m in masks]
    return out
def main():
    if sys.argv[1:] or any((BASE/n).exists() for n in ('execution.json','execution_code','training_epoch00_probabilities.npy')):raise ValueError('No restart')
    assert read(PARENT/'experiment.json')['status']=='COMPLETED' and sha(PARENT/'reviewed_analysis.json')==EXPECTED_PARENT_REVIEW
    parent_pid=os.getppid()
    assert not any(Path(a).name in ('train_v5.py','run_pilot.py','review_finish.py') for p in psutil.process_iter(['pid','name','cmdline']) if p.pid not in (os.getpid(),parent_pid) for a in p.info['cmdline'] or [])
    assert torch.cuda.is_available();torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    started=time.monotonic();execution=dict(status='RUNNING',pid=os.getpid(),create_time=psutil.Process().create_time(),started_at=datetime.now(timezone.utc).isoformat(),model_state_queries=0,new_training_hands=0,new_hands=0,network_attempts=0);write('execution.json',execution)
    success=False
    try:
        copies=capture()
        inputs=[PARENT/'reviewed_analysis.json',SOURCE/'reservoir.pt',PARENT/'training_relabel/reach_targets.npy',
            PARENT/'validation_relabel/validation_targets.npy',PARENT/'validation_relabel/validation_metadata.npz',
            PARENT/'initializer.pt',PARENT/'checkpoints/epoch01.pt',PARENT/'checkpoints/epoch04.pt',PARENT/'latest.pt']
        manifest=[dict(path=str(p),sha256=sha(p)) for p in inputs];write('input_manifest.json',manifest)
        reservoir=torch.load(SOURCE/'reservoir.pt',map_location='cpu',weights_only=False)
        # Parent diagnostic retained the same bitwise reservoir but references it through its manifest.
        assert sha(SOURCE/'reservoir.pt')==read(PARENT/'input_manifest.json')['dependencies'][2]['sha256']
        q=np.load(PARENT/'training_relabel/reach_targets.npy');assert len(q)==len(reservoir['ids'])==262144
        checkpoints={0:PARENT/'initializer.pt',1:PARENT/'checkpoints/epoch01.pt',4:PARENT/'checkpoints/epoch04.pt',8:PARENT/'latest.pt'}
        train={}
        for epoch,path in checkpoints.items():
            model,_,digest=load_policy(path,'cuda');assert digest==sha(path)
            p=infer(model,reservoir['arrays']).astype(np.float32);np.save(BASE/f'training_epoch{epoch:02d}_probabilities.npy',p)
            tv,ce,js=metrics(p,q);train[epoch]=dict(mean_tv=float(tv.mean()),mean_ce=float(ce.mean()),mean_js=float(js.mean()))
            del model;torch.cuda.empty_cache()
            execution['model_state_queries']=QUERY_COUNT;execution['checkpoint_epoch']=epoch;write('execution.json',execution)
        metadata=validation_metadata();vtarget=np.load(PARENT/'validation_relabel/validation_targets.npy')
        vmeta=np.load(PARENT/'validation_relabel/validation_metadata.npz')
        val={};prob={}
        for epoch in checkpoints:
            prob[epoch]=np.load(PARENT/f'validation_epoch{epoch:02d}_probabilities.npy')
            tv,ce,js=metrics(prob[epoch],vtarget);val[epoch]=dict(mean_tv=float(tv.mean()),mean_ce=float(ce.mean()),mean_js=float(js.mean()))
        h4,h8=hero(prob[4],vtarget,vmeta['hands'],vmeta['actors']),hero(prob[8],vtarget,vmeta['hands'],vmeta['actors'])
        use=np.isfinite(h4)&np.isfinite(h8);paired=interval((h8-h4)[use])
        flags=dict(TRAINING_FIT_UNDER_THRESHOLD=train[8]['mean_tv']>.15,
            GENERALIZATION_GAP=val[8]['mean_tv']-train[8]['mean_tv']>.03,
            CE_TV_OBJECTIVE_CONFLICT=val[8]['mean_ce']<val[4]['mean_ce'] and paired['ci95'][0]>0)
        strata=stratum_summary(prob[8],vtarget,metadata)
        a,b=strata['truncated'];flags['HISTORY_TRUNCATION_CONCENTRATION']=bool(a['n'] and b['n'] and b['mean_tv']-a['mean_tv']>=.03)
        priority=['TRAINING_FIT_UNDER_THRESHOLD','GENERALIZATION_GAP','CE_TV_OBJECTIVE_CONFLICT','HISTORY_TRUNCATION_CONCENTRATION']
        decision=next((x for x in priority if flags[x]),'GAP_NOT_LOCALIZED')
        analysis=dict(status='COMPLETED_PENDING_REVIEW',decision=decision,flags=flags,training=train,validation=val,
            paired_epoch08_minus_epoch04_hero_tv=paired,strata=strata,model_state_queries=QUERY_COUNT,
            old_training_states=262144,old_validation_hands=8192,new_training_hands=0,new_hands=0,strength_hands=0,slumbot_hands=0,goal_achieved=False)
        write('analysis.json',analysis);success=True
    except BaseException:
        (BASE/'failure.txt').write_text(traceback.format_exc());print(traceback.format_exc(),flush=True)
    finally:
        execution.update(status='COMPLETED_PENDING_REVIEW' if success else 'FAILED_PRESERVED',model_state_queries=QUERY_COUNT,
            finished_at=datetime.now(timezone.utc).isoformat(),wall_time_seconds=time.monotonic()-started);write('execution.json',execution)
        artifacts=[p for p in BASE.iterdir() if p.is_file() and p.name not in ('experiment.json','source_manifest.json','code.patch')]
        logger(*[x for p in artifacts for x in ('--artifact',p)],'--count','new_training_hands=0','--count','evaluation_hands=0',
            '--count','slumbot_hands=0','--count',f'model_state_queries={QUERY_COUNT}','--metric',f'wall_time_seconds={execution["wall_time_seconds"]}')
    if not success:raise SystemExit(1)
if __name__=='__main__':main()


