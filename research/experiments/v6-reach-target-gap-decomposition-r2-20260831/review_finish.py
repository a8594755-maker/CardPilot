"""Independent terminal review for the frozen-state gap diagnostic."""
import json,math,sys,time
from pathlib import Path
import numpy as np,psutil,torch
import run_diagnostic as run
BASE=run.BASE

def gone(e):
 try:return abs(psutil.Process(e['pid']).create_time()-e['create_time'])>.001
 except psutil.NoSuchProcess:return True
def stat(p,q):
 p=p.astype(np.float64);q=q.astype(np.float64)
 tv=np.abs(p-q).sum(1)/2
 with np.errstate(divide='ignore',invalid='ignore'):
  ce=-np.sum(np.where(q>0,q*np.log(np.where(p>0,p,1)),0),1);m=(p+q)/2
  js=(np.sum(np.where(p>0,p*np.log(np.where(p>0,p,1)/np.where(m>0,m,1)),0),1)+np.sum(np.where(q>0,q*np.log(np.where(q>0,q,1)/np.where(m>0,m,1)),0),1))/2
 return dict(mean_tv=math.fsum(tv.tolist())/len(tv),mean_ce=math.fsum(ce.tolist())/len(ce),mean_js=math.fsum(js.tolist())/len(js))
def main():
 if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists():raise ValueError('No repeated review')
 started=time.monotonic();e=run.read(BASE/'execution.json');assert e['status']=='COMPLETED_PENDING_REVIEW' and gone(e)
 record=run.read(BASE/'experiment.json');assert record['status']=='RUNNING'
 for label,item in record['artifact_integrity'].items():assert run.sha(label)==item['sha256']
 for row in run.read(BASE/'input_manifest.json'):assert run.sha(row['path'])==row['sha256']
 analysis=run.read(BASE/'analysis.json');q=np.load(run.PARENT/'training_relabel/reach_targets.npy')
 training={}
 for epoch in (0,1,4,8):
  p=np.load(BASE/f'training_epoch{epoch:02d}_probabilities.npy');assert p.shape==(262144,9) and np.isfinite(p).all()
  assert np.allclose(p.sum(1),1,atol=2e-6,rtol=0);training[epoch]=stat(p,q)
  for key in training[epoch]:assert abs(training[epoch][key]-analysis['training'][str(epoch)][key])<2e-8
 # Link every saved probability file to its frozen checkpoint on an independent fixed prefix.
 source=torch.load(run.SOURCE/'reservoir.pt',map_location='cpu',weights_only=False)
 paths={0:run.PARENT/'initializer.pt',1:run.PARENT/'checkpoints/epoch01.pt',4:run.PARENT/'checkpoints/epoch04.pt',8:run.PARENT/'latest.pt'}
 from alpha_holdem.execution_v6 import load_policy
 from temporal_average import softmax_legal
 for epoch,path in paths.items():
  model,_,digest=load_policy(path,'cpu');assert digest==run.sha(path)
  arrays={k:source['arrays'][k][:64] for k in run.KEYS};t=[torch.as_tensor(arrays[k],dtype=torch.float32) for k in run.KEYS]
  with torch.no_grad():p=softmax_legal(model(*t)[0].numpy(),arrays['legal_mask'])
  assert np.allclose(p,np.load(BASE/f'training_epoch{epoch:02d}_probabilities.npy')[:64],atol=2e-5,rtol=0)
 valq=np.load(run.PARENT/'validation_relabel/validation_targets.npy');meta=np.load(run.PARENT/'validation_relabel/validation_metadata.npz')
 validation={};prob={}
 for epoch in paths:
  prob[epoch]=np.load(run.PARENT/f'validation_epoch{epoch:02d}_probabilities.npy');validation[epoch]=stat(prob[epoch],valq)
  for key in validation[epoch]:assert abs(validation[epoch][key]-analysis['validation'][str(epoch)][key])<2e-12
 h4,h8=run.hero(prob[4],valq,meta['hands'],meta['actors']),run.hero(prob[8],valq,meta['hands'],meta['actors'])
 use=np.isfinite(h4)&np.isfinite(h8);paired=run.interval((h8-h4)[use])
 for key in ('mean','standard_error','ci95'):assert np.allclose(paired[key],analysis['paired_epoch08_minus_epoch04_hero_tv'][key],atol=2e-12,rtol=0)
 vm=np.load(BASE/'validation_metadata.npz');assert all(len(vm[k])==69516 for k in vm.files)
 assert np.isin(vm['street'],range(4)).all() and np.isin(vm['actor'],[0,1]).all() and vm['truncated'].dtype==bool
 flags=dict(TRAINING_FIT_UNDER_THRESHOLD=training[8]['mean_tv']>.15,
  GENERALIZATION_GAP=validation[8]['mean_tv']-training[8]['mean_tv']>.03,
  CE_TV_OBJECTIVE_CONFLICT=validation[8]['mean_ce']<validation[4]['mean_ce'] and paired['ci95'][0]>0)
 a,b=analysis['strata']['truncated'];flags['HISTORY_TRUNCATION_CONCENTRATION']=bool(a['n'] and b['n'] and b['mean_tv']-a['mean_tv']>=.03)
 assert flags==analysis['flags']
 priority=['TRAINING_FIT_UNDER_THRESHOLD','GENERALIZATION_GAP','CE_TV_OBJECTIVE_CONFLICT','HISTORY_TRUNCATION_CONCENTRATION']
 decision=next((x for x in priority if flags[x]),'GAP_NOT_LOCALIZED');assert decision==analysis['decision']
 report=dict(status='PASS',decision=decision,flags=flags,training=training,validation=validation,
  paired_epoch08_minus_epoch04_hero_tv=paired,strata=analysis['strata'],model_state_queries=e['model_state_queries'],
  independent_review_model_queries=256,old_training_states=262144,old_validation_hands=8192,new_training_hands=0,
  evaluation_hands=0,strength_hands=0,slumbot_hands=0,goal_achieved=False,wall_time_seconds=e['wall_time_seconds'],
  review_wall_time_seconds=time.monotonic()-started,
  interpretation='Frozen-state fit diagnostic only. It localizes fidelity error and does not measure poker strength, exploitability or external transfer.')
 run.write('reviewed_analysis.json',report)
 (BASE/'result_summary.md').write_text(f'# Reach-target gap decomposition\n\n{decision}\n\nFlags: {flags}.\n\n'
  f'Training epoch08 TV {training[8]["mean_tv"]:.6f}; validation row TV {validation[8]["mean_tv"]:.6f}; '
  f'paired hero epoch08-minus-epoch04 {paired}.\n\n0 new hands/training/network. {report["interpretation"]}\n')
 run.logger('--command',f'python research/experiments/{BASE.name}/review_finish.py','--artifact',BASE/'reviewed_analysis.json','--artifact',BASE/'result_summary.md',
  '--count','review_model_state_queries=256','--metric',f'review_wall_time_seconds={report["review_wall_time_seconds"]}')
 import subprocess
 nxt='Preregister a metric-aligned hand/seat-balanced TV-family learned fit on old reach targets, then evaluate only its frozen endpoint on a fresh native cohort.' if flags['TRAINING_FIT_UNDER_THRESHOLD'] and flags['CE_TV_OBJECTIVE_CONFLICT'] else 'Use localized gap flags to choose the next representation or optimization diagnostic.'
 subprocess.run([sys.executable,str(run.ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED','--summary',f'Frozen reach-target gap decomposition completed: {decision}.','--conclusion',report['interpretation'],'--decision',decision,'--next-step',nxt,'--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0'],cwd=run.ROOT,check=True)
 print(json.dumps(report),flush=True)
if __name__=='__main__':main()



