"""Fixed three-arm metric-aligned development fit; no new hands."""
from datetime import datetime,timezone
import json,math,os,shutil,sys,time,traceback
from pathlib import Path
import numpy as np,psutil,torch
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
REACH=ROOT/'research/experiments/v6-reach-target-average-pilot-20260831'
SOURCE=ROOT/'research/experiments/v6-fictitious-average-phase2-20260831'
RUNTIME=SOURCE/'execution_code/source_files/scripts'
sys.path[:0]=[str(ROOT),str(RUNTIME),str(REACH),str(SOURCE)]
from research.experiment_log import atomic_json,capture_code_provenance,sha256_file
from alpha_holdem.execution_v6 import load_policy
from temporal_average import softmax_legal
from fit_metrics import hero_tv
KEYS=('card_info','action_info','extra_info','legal_mask');QUERIES=0
REVIEW_SHA='b878cb894c0199ad40b1da5aee1f6b8ca52ffe9cd5c5728f9dce7959255619fe'
def sha(p):return sha256_file(Path(p))
def read(p):return json.loads(Path(p).read_text())
def write(n,v):atomic_json(BASE/n,v)
def log(*a):import subprocess;subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*map(str,a)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
def capture():
 out=BASE/'execution_code';out.mkdir();paths=['research/experiment_log.py']+[p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in ('.py','.md')]
 capture_code_provenance(ROOT,out,paths)
 copies=[]
 for r in paths:
  t=out/'source_files'/r;t.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/r,t);copies.append(dict(original=r,copy=t.relative_to(ROOT).as_posix(),sha256=sha(t)))
 write('execution_code/copy_manifest.json',copies);return copies
def row_actors(ids):
 index={tuple(map(int,x)):i for i,x in enumerate(ids)};assert len(index)==len(ids)
 actors=np.full(len(ids),-1,dtype=np.int8);seen=np.zeros(len(ids),bool)
 for path in sorted((REACH/'training_relabel').glob('block*.npz')):
  with np.load(path) as z:h,a=z['hand_ids'],z['actors']
  last=-1;decision=-1
  for hand,actor in zip(h,a,strict=True):
   hand=int(hand);decision=decision+1 if hand==last else 0;last=hand
   pos=index.get((hand,decision))
   if pos is not None:assert not seen[pos];actors[pos]=actor;seen[pos]=True
 assert seen.all() and np.isin(actors,[0,1]).all()
 return actors
@torch.no_grad()
def infer(model,arrays):
 global QUERIES
 out=[];model.eval()
 for b in range(0,len(arrays['legal_mask']),512):
  e=min(b+512,len(arrays['legal_mask']));t=[torch.as_tensor(arrays[k][b:e],dtype=torch.float32,device='cuda') for k in KEYS]
  out.append(softmax_legal(model(*t)[0].cpu().numpy(),arrays['legal_mask'][b:e]));QUERIES+=e-b
 return np.concatenate(out)
def interval(x):
 x=np.asarray(x);x=x[np.isfinite(x)];m=math.fsum(x.tolist())/len(x);se=math.sqrt(math.fsum((float(v)-m)**2 for v in x)/(len(x)*(len(x)-1)))
 return dict(n=len(x),mean=m,standard_error=se,ci95=[m-1.96*se,m+1.96*se])
def main():
 if sys.argv[1:] or (BASE/'execution.json').exists():raise ValueError('No restart')
 assert sha(ROOT/'research/experiments/v6-reach-target-gap-decomposition-r3-20260831/reviewed_analysis.json')==REVIEW_SHA
 assert not any(Path(a).name in ('train_v5.py','run_pilot.py','run_development.py','review_finish.py') for p in psutil.process_iter(['pid','cmdline']) if p.pid not in (os.getpid(),os.getppid()) for a in p.info['cmdline'] or [])
 torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
 start=time.monotonic();execution=dict(status='RUNNING',pid=os.getpid(),create_time=psutil.Process().create_time(),started_at=datetime.now(timezone.utc).isoformat(),new_training_hands=0,new_hands=0,model_state_queries=0,network_attempts=0)
 write('execution.json',execution);success=False
 try:
  copies=capture();inputs=[SOURCE/'reservoir.pt',SOURCE/'initializer.pt',REACH/'training_relabel/reach_targets.npy',REACH/'validation_relabel/validation_arrays.npz',REACH/'validation_relabel/validation_targets.npy',REACH/'validation_relabel/validation_metadata.npz',REACH/'latest.pt']
  write('input_manifest.json',[dict(path=str(p),sha256=sha(p)) for p in inputs])
  reservoir=torch.load(SOURCE/'reservoir.pt',map_location='cpu',weights_only=False);q=np.load(REACH/'training_relabel/reach_targets.npy').astype(np.float32)
  actors=row_actors(reservoir['ids']);groups=reservoir['ids'][:,0].astype(np.int64)*2+actors
  unique,inverse,counts=np.unique(groups,return_inverse=True,return_counts=True);balanced=1/counts[inverse];balanced/=balanced.mean()
  assert np.allclose(np.bincount(inverse,weights=balanced),np.bincount(inverse,weights=balanced)[0])
  np.save(BASE/'retained_actors.npy',actors);np.save(BASE/'hand_seat_weights.npy',balanced)
  with np.load(REACH/'validation_relabel/validation_arrays.npz') as z:va={k:z[k] for k in z.files}
  vq=np.load(REACH/'validation_relabel/validation_targets.npy');vm=np.load(REACH/'validation_relabel/validation_metadata.npz')
  arms=[('unweighted_tv','tv',np.ones(len(q))),('balanced_tv','tv',balanced),('balanced_ce','ce',balanced)]
  results={}
  for arm,kind,weights in arms:
   torch.manual_seed(2026102501);torch.cuda.manual_seed_all(2026102501);gen=np.random.default_rng(2026102501)
   model,source,digest=load_policy(SOURCE/'initializer.pt','cuda');initial={k:v.cpu().clone() for k,v in model.state_dict().items()}
   params=[]
   for n,p in model.named_parameters():p.requires_grad_(not n.startswith('value_head.'));params.append(p) if p.requires_grad else None
   assert len(params)==80;opt=torch.optim.Adam(params,lr=1e-4);steps=0;rowslog=[]
   for epoch in range(1,9):
    order=gen.permutation(len(q))
    for b in range(0,len(q),1024):
     idx=order[b:b+1024];t=[torch.as_tensor(reservoir['arrays'][k][idx],dtype=torch.float32,device='cuda') for k in KEYS]
     target=torch.as_tensor(q[idx],device='cuda');w=torch.as_tensor(weights[idx],dtype=torch.float32,device='cuda')
     logits=model(*t)[0].masked_fill(t[-1]<=0,-1e9);prob=torch.softmax(logits,1)
     per=torch.abs(prob-target).sum(1)/2 if kind=='tv' else -(target*torch.log_softmax(logits,1)).sum(1)
     loss=(per*w).mean();opt.zero_grad(set_to_none=True);loss.backward();norm=torch.nn.utils.clip_grad_norm_(params,1);opt.step();steps+=1
     assert torch.isfinite(loss) and torch.isfinite(norm);rowslog.append(dict(arm=arm,epoch=epoch,step=steps,rows=len(idx),loss=float(loss),gradient_norm=float(norm)))
   p=infer(model,va);np.save(BASE/f'{arm}_development_probabilities.npy',p)
   hand,_=hero_tv(p,vq,vm['hands'],vm['actors']);np.save(BASE/f'{arm}_development_hero_tv.npy',hand)
   changed=[k for k,v in model.state_dict().items() if not torch.equal(v.cpu(),initial[k])]
   ck=dict(source);ck.update(model={k:v.cpu() for k,v in model.state_dict().items()},optimizer=opt.state_dict(),epoch=8,iteration=8,total_hands=0,optimizer_steps=2048,
    run_id=BASE.name,training_algorithm=f'reach_{arm}_development_v1',source_weights_sha256=sha(SOURCE/'initializer.pt'),reach_targets_sha256=sha(REACH/'training_relabel/reach_targets.npy'),new_training_hands=0)
   torch.save(ck,BASE/f'{arm}.pt')
   results[arm]=dict(development_hero_tv=interval(hand),changed=len(changed),optimizer_steps=steps,model_sha256=sha(BASE/f'{arm}.pt'))
   (BASE/f'{arm}_training_metrics.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rowslog))
   del model,opt;torch.cuda.empty_cache()
   execution.update(arm=arm,model_state_queries=QUERIES);write('execution.json',execution)
  order=['balanced_tv','unweighted_tv','balanced_ce'];selected=min(order,key=lambda x:(results[x]['development_hero_tv']['mean'],order.index(x)))
  parent=float(read(REACH/'reviewed_analysis.json')['treatment']['mean']);mean=results[selected]['development_hero_tv']['mean']
  decision='FREEZE_FOR_UNTOUCHED_NATIVE_VALIDATION' if parent-mean>=.01 and mean<=.19 else 'METRIC_ALIGNED_DEVELOPMENT_NOT_PROMISING'
  analysis=dict(status='COMPLETED_PENDING_REVIEW',decision=decision,selected_arm=selected,parent_development_hero_tv=parent,arms=results,
   selected_improvement=parent-mean,represented_hand_seat_groups=len(unique),optimizer_rows_processed=3*2097152,model_state_queries=QUERIES,new_training_hands=0,new_hands=0,strength_hands=0,slumbot_hands=0,goal_achieved=False)
  write('analysis.json',analysis);success=True
 except BaseException:
  (BASE/'failure.txt').write_text(traceback.format_exc());print(traceback.format_exc(),flush=True)
 finally:
  execution.update(status='COMPLETED_PENDING_REVIEW' if success else 'FAILED_PRESERVED',model_state_queries=QUERIES,finished_at=datetime.now(timezone.utc).isoformat(),wall_time_seconds=time.monotonic()-start);write('execution.json',execution)
  log(*[x for p in BASE.iterdir() if p.is_file() and p.name not in ('experiment.json','source_manifest.json','code.patch') for x in ('--artifact',p)],'--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0','--count',f'model_state_queries={QUERIES}','--metric',f'wall_time_seconds={execution["wall_time_seconds"]}')
 if not success:raise SystemExit(1)
if __name__=='__main__':main()
