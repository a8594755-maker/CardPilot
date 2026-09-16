"""Independent terminal review of explicit-position development adapter."""
import json,math,sys,time
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
 source=torch.load(run.PREV/'latest.pt',map_location='cpu',weights_only=False);final=torch.load(BASE/'latest.pt',map_location='cpu',weights_only=False)
 adapter=[k for k in final['model'] if k.startswith('position_policy_adapters.')]
 changed=[k for k,v in final['model'].items() if not torch.equal(v,source['model'][k])]
 assert len(adapter)==8 and len(changed)==88 and not any(k.startswith('value_head.') for k in changed)
 assert all(torch.isfinite(final['model'][k]).all() for k in final['model']) and final['position_adapter_hidden']==128
 assert len(final['optimizer']['state'])==88 and all(float(x['step'])==2048 for x in final['optimizer']['state'].values())
 rows=[json.loads(x) for x in (BASE/'training_metrics.jsonl').read_text().splitlines()]
 assert len(rows)==2048 and [x['step'] for x in rows]==list(range(1,2049)) and all(x['rows']==1024 and math.isfinite(x['loss']) for x in rows)
 q=np.load(run.REACH/'validation_relabel/validation_targets.npy');m=np.load(run.REACH/'validation_relabel/validation_metadata.npz')
 p=np.load(BASE/'development_probabilities.npy');sourcep=np.load(run.PREV/'development_probabilities.npy')
 h,_=run.hero_tv(p,q,m['hands'],m['actors']);old,_=run.hero_tv(sourcep,q,m['hands'],m['actors']);use=np.isfinite(h)&np.isfinite(old)
 treatment=run.interval(h[use]);paired=run.interval(old[use]-h[use]);improvement=float(np.nanmean(old)-np.nanmean(h))
 analysis=run.read(BASE/'analysis.json')
 for name,value in [('treatment',treatment),('paired_source_minus_treatment',paired)]:
  assert np.allclose(value['ci95'],analysis[name]['ci95'],atol=2e-12,rtol=0) and abs(value['mean']-analysis[name]['mean'])<2e-12
 decision='FREEZE_JOINT_POSITION_FOR_UNTOUCHED_NATIVE_VALIDATION' if paired['ci95'][0]>0 and treatment['mean']<=.17 and improvement>=.01 else 'JOINT_POSITION_DEVELOPMENT_NOT_PROMISING'
 assert decision==analysis['decision'] and run.sha(BASE/'latest.pt')==analysis['model_sha256']
 qual=run.read(BASE/'qualification.json');assert qual['status']=='PASS' and qual['model_queries']==192 and max(qual['cpu_delta'],qual['gpu_delta'])<=2e-5
 report=dict(status='PASS',decision=decision,treatment=treatment,paired_source_minus_treatment=paired,improvement=improvement,model_sha256=run.sha(BASE/'latest.pt'),adapter_tensors=8,changed_trainable_tensors=88,frozen_value_tensors=6,optimizer_steps=2048,optimizer_rows_processed=2097152,model_state_queries=e['model_state_queries'],qualification=qual,new_training_hands=0,evaluation_hands=0,strength_hands=0,slumbot_hands=0,goal_achieved=False,wall_time_seconds=e['wall_time_seconds'],review_wall_time_seconds=time.monotonic()-start,interpretation='Joint-position development result uses a known development cohort and is not confirmatory strength evidence.')
 run.write('reviewed_analysis.json',report);(BASE/'result_summary.md').write_text(f'# Joint-position development\n\n{decision}\n\nTV {treatment["mean"]:.6f}; improvement {improvement:.6f}; paired {paired}.\n\n0newhands/strength/Slumbot. {report["interpretation"]}\n')
 run.log('--command',f'python research/experiments/{BASE.name}/review_finish.py','--artifact',BASE/'reviewed_analysis.json','--artifact',BASE/'result_summary.md','--metric',f'review_wall_time_seconds={report["review_wall_time_seconds"]}')
 import subprocess
 nxt='Preregister untouched native validation of only this frozen endpoint versus its frozen source.' if decision.startswith('FREEZE') else 'Implement full-history sequence representation before further fidelity tuning.'
 subprocess.run([sys.executable,str(run.ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED','--summary',f'Explicit-position development completed: {decision}.','--conclusion',report['interpretation'],'--decision',decision,'--next-step',nxt,'--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0'],cwd=run.ROOT,check=True)
 print(json.dumps(report),flush=True)
if __name__=='__main__':main()



