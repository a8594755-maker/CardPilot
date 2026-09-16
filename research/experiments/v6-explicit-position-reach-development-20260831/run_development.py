"""Frozen-base explicit-position development adapter; no new hands."""
from datetime import datetime,timezone
import json,math,os,shutil,sys,time,traceback
from pathlib import Path
import numpy as np,psutil,torch
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PREV=ROOT/'research/experiments/v6-metric-aligned-reach-development-20260831'
REACH=ROOT/'research/experiments/v6-reach-target-average-pilot-20260831'
SOURCE=ROOT/'research/experiments/v6-fictitious-average-phase2-20260831'
RUNTIME=SOURCE/'execution_code/source_files/scripts';sys.path[:0]=[str(ROOT),str(RUNTIME),str(REACH),str(SOURCE)]
from research.experiment_log import atomic_json,capture_code_provenance,sha256_file
from alpha_holdem.network import AlphaHoldemNet
from alpha_holdem.execution_v6 import load_policy,decide
from temporal_average import softmax_legal
from fit_metrics import hero_tv
from native_relabel import chunks,reconstruct
KEYS=('card_info','action_info','extra_info','legal_mask');QUERIES=0
SOURCE_SHA='01049fb680c2f675193e7e73b1bd08d8283ecbfcb21d34f20e49428cf4f05697'
def sha(p):return sha256_file(Path(p))
def read(p):return json.loads(Path(p).read_text())
def write(n,v):atomic_json(BASE/n,v)
def log(*a):import subprocess;subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*map(str,a)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
def capture():
 out=BASE/'execution_code';out.mkdir();paths=['research/experiment_log.py']+[p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in ('.py','.md')]
 capture_code_provenance(ROOT,out,paths)
 for r in paths:
  t=out/'source_files'/r;t.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/r,t)
def arrays_with_actor(arrays,actors):
 result={k:arrays[k] for k in KEYS};result['extra_info']=np.concatenate([arrays['extra_info'],np.asarray(actors,dtype=np.float32)[:,None]],1);return result
@torch.no_grad()
def infer(model,arrays,device='cuda',count=True):
 global QUERIES
 out=[];model.eval()
 for b in range(0,len(arrays['legal_mask']),512):
  e=min(b+512,len(arrays['legal_mask']));t=[torch.as_tensor(arrays[k][b:e],dtype=torch.float32,device=device) for k in KEYS]
  out.append(softmax_legal(model(*t)[0].cpu().numpy(),arrays['legal_mask'][b:e]))
  if count:QUERIES+=e-b
 return np.concatenate(out)
def interval(x):
 x=np.asarray(x);x=x[np.isfinite(x)];m=math.fsum(x.tolist())/len(x);se=math.sqrt(math.fsum((float(v)-m)**2 for v in x)/(len(x)*(len(x)-1)))
 return dict(n=len(x),mean=m,standard_error=se,ci95=[m-1.96*se,m+1.96*se])
def main():
 if sys.argv[1:] or (BASE/'execution.json').exists():raise ValueError('No restart')
 assert sha(PREV/'unweighted_tv.pt')==SOURCE_SHA and read(PREV/'experiment.json')['status']=='COMPLETED'
 assert not any(Path(a).name in ('train_v5.py','run_pilot.py','run_development.py','review_finish.py') for p in psutil.process_iter(['pid','cmdline']) if p.pid not in (os.getpid(),os.getppid()) for a in p.info['cmdline'] or [])
 torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
 start=time.monotonic();execution=dict(status='RUNNING',pid=os.getpid(),create_time=psutil.Process().create_time(),started_at=datetime.now(timezone.utc).isoformat(),new_training_hands=0,new_hands=0,model_state_queries=0,network_attempts=0);write('execution.json',execution);success=False
 try:
  capture();inputs=[PREV/'unweighted_tv.pt',SOURCE/'reservoir.pt',REACH/'training_relabel/reach_targets.npy',PREV/'retained_actors.npy',REACH/'validation_relabel/validation_arrays.npz',REACH/'validation_relabel/validation_targets.npy',REACH/'validation_relabel/validation_metadata.npz']
  write('input_manifest.json',[dict(path=str(p),sha256=sha(p)) for p in inputs])
  source=torch.load(PREV/'unweighted_tv.pt',map_location='cpu',weights_only=False)
  torch.manual_seed(2026102601);torch.cuda.manual_seed_all(2026102601)
  model=AlphaHoldemNet(norm_layer=source.get('norm_layer','gn'),separate_preflop_head=True,position_adapter_hidden=128,critic_contract=source.get('critic_contract','critic_v2')).cuda()
  with torch.no_grad():model(torch.zeros(2,6,4,13,device='cuda'),torch.zeros(2,25,4,5,device='cuda'),torch.zeros(2,3,device='cuda'),torch.ones(2,9,device='cuda'))
  result=model.load_state_dict(source['model'],strict=False)
  assert not result.unexpected_keys and result.missing_keys and all(k.startswith('position_policy_adapters.') for k in result.missing_keys)
  base={k:v.clone() for k,v in model.state_dict().items() if not k.startswith('position_policy_adapters.')}
  params=[]
  for n,p in model.named_parameters():p.requires_grad_(n.startswith('position_policy_adapters.'));params.append(p) if p.requires_grad else None
  assert len(params)==8
  reservoir=torch.load(SOURCE/'reservoir.pt',map_location='cpu',weights_only=False);actors=np.load(PREV/'retained_actors.npy');ta=arrays_with_actor(reservoir['arrays'],actors);q=np.load(REACH/'training_relabel/reach_targets.npy').astype(np.float32)
  with np.load(REACH/'validation_relabel/validation_arrays.npz') as z:raw={k:z[k] for k in z.files}
  vm=np.load(REACH/'validation_relabel/validation_metadata.npz');va=arrays_with_actor(raw,vm['actors']);vq=np.load(REACH/'validation_relabel/validation_targets.npy')
  source_probs=np.load(PREV/'unweighted_tv_development_probabilities.npy')
  epoch0=infer(model,va,count=False);assert np.allclose(epoch0,source_probs,atol=2e-5,rtol=0)
  opt=torch.optim.Adam(params,lr=1e-4);gen=np.random.default_rng(2026102601);rows=[];steps=0
  for epoch in range(1,9):
   order=gen.permutation(len(q));model.train()
   for b in range(0,len(q),1024):
    idx=order[b:b+1024];t=[torch.as_tensor(ta[k][idx],dtype=torch.float32,device='cuda') for k in KEYS];target=torch.as_tensor(q[idx],device='cuda')
    logits=model(*t)[0].masked_fill(t[-1]<=0,-1e9);loss=(torch.softmax(logits,1)-target).abs().sum(1).mean()/2
    opt.zero_grad(set_to_none=True);loss.backward();norm=torch.nn.utils.clip_grad_norm_(params,1);opt.step();steps+=1
    assert torch.isfinite(loss) and torch.isfinite(norm);rows.append(dict(epoch=epoch,step=steps,rows=len(idx),loss=float(loss),gradient_norm=float(norm)))
  assert all(torch.equal(v,model.state_dict()[k]) for k,v in base.items())
  probs=infer(model,va);np.save(BASE/'development_probabilities.npy',probs);hand,_=hero_tv(probs,vq,vm['hands'],vm['actors']);np.save(BASE/'development_hero_tv.npy',hand)
  source_hand,_=hero_tv(source_probs,vq,vm['hands'],vm['actors']);valid=np.isfinite(hand)&np.isfinite(source_hand);paired=interval(source_hand[valid]-hand[valid]);treatment=interval(hand[valid]);improvement=float(np.nanmean(source_hand)-np.nanmean(hand))
  ck=dict(source);ck.update(model={k:v.cpu() for k,v in model.state_dict().items()},optimizer=opt.state_dict(),position_adapter_hidden=128,epoch=8,iteration=8,total_hands=0,optimizer_steps=2048,run_id=BASE.name,training_algorithm='explicit_position_reach_tv_v1',source_weights_sha256=SOURCE_SHA,new_training_hands=0)
  ck['config']={**source.get('config',{}),'position_adapter_hidden':128};torch.save(ck,BASE/'latest.pt')
  cpu,_,digest=load_policy(BASE/'latest.pt','cpu');gpu,_,_=load_policy(BASE/'latest.pt','cuda');assert digest==sha(BASE/'latest.pt')
  first=next(chunks(REACH/'validation_hands.jsonl'));states=reconstruct(first,0)['qualification_states'];assert len(states)==64
  direct=[]
  for state in states:
   direct.append(decide(cpu,state,uniform=.371)[1]['behavior_probs']);globals()['QUERIES']+=1
  small={k:va[k][:64] for k in KEYS};cb=infer(cpu,small,'cpu');gb=infer(gpu,small,'cuda')
  qualification=dict(status='PASS',states=64,model_queries=192,cpu_delta=float(np.abs(cb-direct).max()),gpu_delta=float(np.abs(gb-direct).max()),model_sha256=digest)
  assert max(qualification['cpu_delta'],qualification['gpu_delta'])<=2e-5;write('qualification.json',qualification)
  (BASE/'training_metrics.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows))
  decision='FREEZE_POSITION_ADAPTER_FOR_UNTOUCHED_NATIVE_VALIDATION' if paired['ci95'][0]>0 and treatment['mean']<=.17 and improvement>=.01 else 'POSITION_ADAPTER_DEVELOPMENT_NOT_PROMISING'
  analysis=dict(status='COMPLETED_PENDING_REVIEW',decision=decision,treatment=treatment,paired_source_minus_treatment=paired,improvement=improvement,model_sha256=sha(BASE/'latest.pt'),adapter_tensors=8,frozen_base_tensors=86,optimizer_steps=2048,optimizer_rows_processed=2097152,model_state_queries=QUERIES,qualification=qualification,new_training_hands=0,new_hands=0,strength_hands=0,slumbot_hands=0,goal_achieved=False)
  write('analysis.json',analysis);success=True
 except BaseException:
  (BASE/'failure.txt').write_text(traceback.format_exc());print(traceback.format_exc(),flush=True)
 finally:
  execution.update(status='COMPLETED_PENDING_REVIEW' if success else 'FAILED_PRESERVED',model_state_queries=QUERIES,finished_at=datetime.now(timezone.utc).isoformat(),wall_time_seconds=time.monotonic()-start);write('execution.json',execution)
  log(*[x for p in BASE.iterdir() if p.is_file() and p.name not in ('experiment.json','source_manifest.json','code.patch') for x in ('--artifact',p)],'--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0','--count',f'model_state_queries={QUERIES}','--metric',f'wall_time_seconds={execution["wall_time_seconds"]}')
 if not success:raise SystemExit(1)
if __name__=='__main__':main()
