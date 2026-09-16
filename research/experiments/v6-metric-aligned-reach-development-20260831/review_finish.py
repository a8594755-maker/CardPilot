"""Independent terminal review of metric-aligned development selection."""
import json,math,sys,time
from pathlib import Path
import numpy as np,psutil,torch
import run_development as run
BASE=run.BASE
def gone(e):
 try:return abs(psutil.Process(e['pid']).create_time()-e['create_time'])>.001
 except psutil.NoSuchProcess:return True
def main():
 if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists():raise ValueError('No repeat')
 start=time.monotonic();e=run.read(BASE/'execution.json');assert e['status']=='COMPLETED_PENDING_REVIEW' and gone(e)
 rec=run.read(BASE/'experiment.json');assert rec['status']=='RUNNING'
 for p,x in rec['artifact_integrity'].items():assert run.sha(p)==x['sha256']
 for x in run.read(BASE/'input_manifest.json'):assert run.sha(x['path'])==x['sha256']
 source=torch.load(run.SOURCE/'initializer.pt',map_location='cpu',weights_only=False)
 weights=np.load(BASE/'hand_seat_weights.npy');actors=np.load(BASE/'retained_actors.npy')
 reservoir=torch.load(run.SOURCE/'reservoir.pt',map_location='cpu',weights_only=False)
 groups=reservoir['ids'][:,0].astype(np.int64)*2+actors
 _,inv=np.unique(groups,return_inverse=True);s=np.bincount(inv,weights=weights)
 assert np.allclose(s,s[0],rtol=0,atol=1e-10) and abs(weights.mean()-1)<1e-12
 q=np.load(run.REACH/'validation_relabel/validation_targets.npy');m=np.load(run.REACH/'validation_relabel/validation_metadata.npz')
 analysis=run.read(BASE/'analysis.json');arms={}
 for arm in ('unweighted_tv','balanced_tv','balanced_ce'):
  rows=[json.loads(x) for x in (BASE/f'{arm}_training_metrics.jsonl').read_text().splitlines()]
  assert len(rows)==2048 and [x['step'] for x in rows]==list(range(1,2049))
  assert all(x['rows']==1024 and math.isfinite(x['loss']) and math.isfinite(x['gradient_norm']) for x in rows)
  ck=torch.load(BASE/f'{arm}.pt',map_location='cpu',weights_only=False)
  changed=[k for k,v in ck['model'].items() if not torch.equal(v,source['model'][k])]
  assert len(changed)==80 and not any(k.startswith('value_head.') for k in changed)
  assert ck['optimizer_steps']==2048 and ck['total_hands']==ck['new_training_hands']==0
  assert len(ck['optimizer']['state'])==80 and all(float(x['step'])==2048 for x in ck['optimizer']['state'].values())
  p=np.load(BASE/f'{arm}_development_probabilities.npy');hand,_=run.hero_tv(p,q,m['hands'],m['actors'])
  stat=run.interval(hand);saved=analysis['arms'][arm]['development_hero_tv']
  assert np.allclose(stat['ci95'],saved['ci95'],atol=2e-12,rtol=0) and abs(stat['mean']-saved['mean'])<2e-12
  assert run.sha(BASE/f'{arm}.pt')==analysis['arms'][arm]['model_sha256'];arms[arm]=dict(development_hero_tv=stat,model_sha256=run.sha(BASE/f'{arm}.pt'))
 order=['balanced_tv','unweighted_tv','balanced_ce'];selected=min(order,key=lambda x:(arms[x]['development_hero_tv']['mean'],order.index(x)))
 assert selected==analysis['selected_arm'];parent=analysis['parent_development_hero_tv'];mean=arms[selected]['development_hero_tv']['mean']
 decision='FREEZE_FOR_UNTOUCHED_NATIVE_VALIDATION' if parent-mean>=.01 and mean<=.19 else 'METRIC_ALIGNED_DEVELOPMENT_NOT_PROMISING'
 assert decision==analysis['decision'] and e['model_state_queries']==3*69516
 report=dict(status='PASS',decision=decision,selected_arm=selected,parent_development_hero_tv=parent,arms=arms,
  selected_improvement=parent-mean,represented_hand_seat_groups=analysis['represented_hand_seat_groups'],
  optimizer_rows_processed=6291456,model_state_queries=e['model_state_queries'],new_training_hands=0,evaluation_hands=0,strength_hands=0,slumbot_hands=0,goal_achieved=False,
  wall_time_seconds=e['wall_time_seconds'],review_wall_time_seconds=time.monotonic()-start,
  interpretation='Development-set objective selection only; descriptive intervals are selection-biased and cannot admit strength evaluation.')
 run.write('reviewed_analysis.json',report)
 (BASE/'result_summary.md').write_text(f'# Metric-aligned development\n\n{decision}; selected {selected}.\n\nParent TV {parent:.6f}; selected development TV {mean:.6f}.\n\n0newhands/strength/Slumbot. {report["interpretation"]}\n')
 run.log('--command',f'python research/experiments/{BASE.name}/review_finish.py','--artifact',BASE/'reviewed_analysis.json','--artifact',BASE/'result_summary.md','--metric',f'review_wall_time_seconds={report["review_wall_time_seconds"]}')
 import subprocess
 nxt='Preregister untouched native validation of only the frozen selected endpoint versus parent.' if decision.startswith('FREEZE') else 'Prioritize sequence representation before further loss tuning.'
 subprocess.run([sys.executable,str(run.ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED','--summary',f'Fixed metric-aligned development completed: {decision}, selected {selected}.','--conclusion',report['interpretation'],'--decision',decision,'--next-step',nxt,'--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0'],cwd=run.ROOT,check=True)
 print(json.dumps(report),flush=True)
if __name__=='__main__':main()

