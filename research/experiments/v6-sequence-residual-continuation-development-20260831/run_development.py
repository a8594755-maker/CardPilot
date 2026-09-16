"""Frozen-base position-aware sequence residual development."""
from datetime import datetime,timezone
import json,math,os,shutil,sys,time,traceback
from pathlib import Path
import numpy as np,psutil,torch
from torch import nn
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
SOURCE=ROOT/'research/experiments/v6-explicit-position-reach-development-20260831'
PARENT=ROOT/'research/experiments/v6-sequence-residual-reach-development-20260831'
ACTORS=ROOT/'research/experiments/v6-metric-aligned-reach-development-20260831'
REACH=ROOT/'research/experiments/v6-reach-target-average-pilot-20260831'
DATA=ROOT/'research/experiments/v6-fictitious-average-phase2-20260831'
RUNTIME=DATA/'execution_code/source_files/scripts';sys.path[:0]=[str(ROOT),str(RUNTIME),str(REACH),str(DATA)]
from research.experiment_log import atomic_json,capture_code_provenance,sha256_file
from alpha_holdem.execution_v6 import load_policy
from temporal_average import softmax_legal
from fit_metrics import hero_tv
PARENT_SHA='96913cf9ae4a0574ab2e5f95bc93abd4b39fdad43395a7882050cc95781172b2'
KEYS=('card_info','action_info','extra_info','legal_mask');SOURCE_SHA='3b33549547bd1792f2a17b8981976ce560247f787ebd0d2ca1cf837e80ed9526';QUERIES=0
def sha(p):return sha256_file(Path(p))
def read(p):return json.loads(Path(p).read_text())
def write(n,v):atomic_json(BASE/n,v)
def log(*a):import subprocess;subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*map(str,a)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
def arrays_actor(a,actors):r={k:a[k] for k in KEYS};r['extra_info']=np.concatenate([a['extra_info'][:,:2],np.asarray(actors,dtype=np.float32)[:,None]],1);return r
class SequenceResidual(nn.Module):
 def __init__(self,base,seed=2026102801):
  super().__init__();self.base=base
  for p in base.parameters():p.requires_grad_(False)
  torch.manual_seed(seed)
  self.token=nn.Linear(20,128);self.position=nn.Parameter(torch.empty(25,128));nn.init.normal_(self.position,std=.02)
  layer=nn.TransformerEncoderLayer(128,4,256,dropout=0,batch_first=True,norm_first=True,activation='gelu')
  self.sequence=nn.TransformerEncoder(layer,2,enable_nested_tensor=False);self.trunk_norm=nn.LayerNorm(256)
  self.experts=nn.ModuleList([nn.Sequential(nn.Linear(386,128),nn.ReLU(),nn.Linear(128,9)) for _ in range(2)])
  for x in self.experts:nn.init.zeros_(x[-1].weight);nn.init.zeros_(x[-1].bias)
  self._h=None;self._hook=self.base.trunk.register_forward_hook(lambda module,args,out:setattr(self,'_h',out.detach()))
 def train(self,mode=True):super().train(mode);self.base.eval();return self
 def forward(self,card,action,extra,mask):
  logits,value=self.base(card,action,extra,mask);assert self._h is not None
  tokens=self.token(action.flatten(2))+self.position
  padding=torch.zeros((len(action),25),dtype=torch.bool,device=action.device);padding[:,:24]=action[:,:24,3,0]<=0
  seq=self.sequence(tokens,src_key_padding_mask=padding)[:,24]
  seat=extra[:,2].round().long().clamp(0,1);f=torch.cat([self.trunk_norm(self._h),seq,torch.nn.functional.one_hot(seat,2).to(seq.dtype)],1)
  deltas=torch.stack([x(f) for x in self.experts],1).gather(1,seat[:,None,None].expand(-1,1,9)).squeeze(1)
  return logits+deltas,value
 def adapter_state(self):return {k:v.cpu() for k,v in self.state_dict().items() if not k.startswith('base.')}
def build(device,state=None):
 base,_,digest=load_policy(SOURCE/'latest.pt',device);assert digest==SOURCE_SHA
 model=SequenceResidual(base).to(device)
 if state is not None:model.load_state_dict({'base.'+k:v for k,v in base.state_dict().items()}|state)
 return model
@torch.no_grad()
def infer(model,a,device='cuda',count=True):
 global QUERIES
 out=[];model.eval()
 for b in range(0,len(a['legal_mask']),512):
  e=min(b+512,len(a['legal_mask']));t=[torch.as_tensor(a[k][b:e],dtype=torch.float32,device=device) for k in KEYS]
  out.append(softmax_legal(model(*t)[0].cpu().numpy(),a['legal_mask'][b:e]))
  if count:QUERIES+=e-b
 return np.concatenate(out)
def interval(x):
 x=np.asarray(x);x=x[np.isfinite(x)];m=math.fsum(x.tolist())/len(x);se=math.sqrt(math.fsum((float(v)-m)**2 for v in x)/(len(x)*(len(x)-1)))
 return dict(n=len(x),mean=m,standard_error=se,ci95=[m-1.96*se,m+1.96*se])
def capture():
 out=BASE/'execution_code';out.mkdir();paths=['research/experiment_log.py']+[p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in ('.py','.md')]
 capture_code_provenance(ROOT,out,paths)
 for r in paths:t=out/'source_files'/r;t.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/r,t)
def main():
 if sys.argv[1:] or (BASE/'execution.json').exists():raise ValueError('No restart')
 assert sha(SOURCE/'latest.pt')==SOURCE_SHA and sha(PARENT/'latest.pt')==PARENT_SHA and read(PARENT/'experiment.json')['status']=='COMPLETED'
 assert not any(Path(a).name in ('train_v5.py','run_pilot.py','run_development.py','review_finish.py') for p in psutil.process_iter(['pid','cmdline']) if p.pid not in (os.getpid(),os.getppid()) for a in p.info['cmdline'] or [])
 torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
 start=time.monotonic();e=dict(status='RUNNING',pid=os.getpid(),create_time=psutil.Process().create_time(),started_at=datetime.now(timezone.utc).isoformat(),new_training_hands=0,new_hands=0,model_state_queries=0,network_attempts=0);write('execution.json',e);success=False
 try:
  capture();inputs=[SOURCE/'latest.pt',PARENT/'latest.pt',DATA/'reservoir.pt',REACH/'training_relabel/reach_targets.npy',ACTORS/'retained_actors.npy',REACH/'validation_relabel/validation_arrays.npz',REACH/'validation_relabel/validation_targets.npy',REACH/'validation_relabel/validation_metadata.npz']
  write('input_manifest.json',[dict(path=str(p),sha256=sha(p)) for p in inputs])
  reservoir=torch.load(DATA/'reservoir.pt',map_location='cpu',weights_only=False);actors=np.load(ACTORS/'retained_actors.npy');ta=arrays_actor(reservoir['arrays'],actors);q=np.load(REACH/'training_relabel/reach_targets.npy').astype(np.float32)
  with np.load(REACH/'validation_relabel/validation_arrays.npz') as z:raw={k:z[k] for k in z.files}
  vm=np.load(REACH/'validation_relabel/validation_metadata.npz');va=arrays_actor(raw,vm['actors']);vq=np.load(REACH/'validation_relabel/validation_targets.npy');sourcep=np.load(PARENT/'development_probabilities.npy')
  parent=torch.load(PARENT/'latest.pt',map_location='cpu',weights_only=False)
  model=build('cuda',parent['adapter']);epoch0=infer(model,va,count=False);assert np.allclose(epoch0,sourcep,atol=2e-5,rtol=0)
  params=[p for n,p in model.named_parameters() if not n.startswith('base.')];assert params and all(p.requires_grad for p in params)
  opt=torch.optim.Adam(params,lr=1e-4);opt.load_state_dict(parent['optimizer'])
  gen=np.random.default_rng(2026102801)
  for _ in range(8):gen.permutation(len(q))
  rows=[];steps=2048
  for epoch in range(9,17):
   order=gen.permutation(len(q));model.train()
   for b in range(0,len(q),1024):
    idx=order[b:b+1024];t=[torch.as_tensor(ta[k][idx],dtype=torch.float32,device='cuda') for k in KEYS];target=torch.as_tensor(q[idx],device='cuda')
    logits=model(*t)[0].masked_fill(t[-1]<=0,-1e9);loss=(torch.softmax(logits,1)-target).abs().sum(1).mean()/2
    opt.zero_grad(set_to_none=True);loss.backward();norm=torch.nn.utils.clip_grad_norm_(params,1);opt.step();steps+=1
    assert torch.isfinite(loss) and torch.isfinite(norm);rows.append(dict(epoch=epoch,step=steps,rows=len(idx),loss=float(loss),gradient_norm=float(norm)))
  probs=infer(model,va);np.save(BASE/'development_probabilities.npy',probs);hand,_=hero_tv(probs,vq,vm['hands'],vm['actors']);old,_=hero_tv(sourcep,vq,vm['hands'],vm['actors']);use=np.isfinite(hand)&np.isfinite(old)
  treatment,paired=interval(hand[use]),interval(old[use]-hand[use]);improvement=float(np.nanmean(old)-np.nanmean(hand))
  adapter=model.adapter_state();torch.save(dict(architecture='position_sequence_residual_v1',adapter=adapter,source_weights_sha256=SOURCE_SHA,parent_weights_sha256=PARENT_SHA,seed=2026102801,optimizer=opt.state_dict(),epoch=16,optimizer_steps=4096,total_hands=0,new_training_hands=0),BASE/'latest.pt')
  cpu=build('cpu',adapter);gpu=build('cuda',adapter);small={k:va[k][:64] for k in KEYS};cp=infer(cpu,small,'cpu');gp=infer(gpu,small,'cuda');qualification=dict(status='PASS',states=64,model_queries=128,cpu_gpu_delta=float(np.abs(cp-gp).max()));assert qualification['cpu_gpu_delta']<=2e-5;write('qualification.json',qualification)
  (BASE/'training_metrics.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows))
  decision='ADMIT_SEQUENCE_RUNTIME_INTEGRATION' if paired['ci95'][0]>0 and improvement>=.005 and treatment['mean']<=.15 else 'SEQUENCE_CONTINUATION_NOT_PROMISING'
  write('analysis.json',dict(status='COMPLETED_PENDING_REVIEW',decision=decision,treatment=treatment,paired_source_minus_treatment=paired,improvement=improvement,model_sha256=sha(BASE/'latest.pt'),source_weights_sha256=SOURCE_SHA,parent_weights_sha256=PARENT_SHA,adapter_parameter_tensors=len(adapter),optimizer_steps=4096,optimizer_rows_processed=2097152,model_state_queries=QUERIES,qualification=qualification,new_training_hands=0,new_hands=0,strength_hands=0,slumbot_hands=0,goal_achieved=False));success=True
 except BaseException:
  (BASE/'failure.txt').write_text(traceback.format_exc());print(traceback.format_exc(),flush=True)
 finally:
  e.update(status='COMPLETED_PENDING_REVIEW' if success else 'FAILED_PRESERVED',model_state_queries=QUERIES,finished_at=datetime.now(timezone.utc).isoformat(),wall_time_seconds=time.monotonic()-start);write('execution.json',e)
  log(*[x for p in BASE.iterdir() if p.is_file() and p.name not in ('experiment.json','source_manifest.json','code.patch') for x in ('--artifact',p)],'--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0','--count',f'model_state_queries={QUERIES}','--metric',f'wall_time_seconds={e["wall_time_seconds"]}')
 if not success:raise SystemExit(1)
if __name__=='__main__':main()



