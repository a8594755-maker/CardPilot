"""Independent terminal review of sequence-residual development."""
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
 ck=torch.load(BASE/'latest.pt',map_location='cpu',weights_only=False)
 assert ck['architecture']=='position_sequence_residual_v1' and ck['source_weights_sha256']==run.SOURCE_SHA and run.sha(run.SOURCE/'latest.pt')==run.SOURCE_SHA
 assert ck['epoch']==8 and ck['optimizer_steps']==2048 and ck['total_hands']==ck['new_training_hands']==0
 assert ck['adapter'] and all(torch.isfinite(v).all() for v in ck['adapter'].values())
 assert len(ck['optimizer']['state'])==len([v for k,v in ck['adapter'].items() if not k.endswith('num_batches_tracked')])
 assert all(float(x['step'])==2048 for x in ck['optimizer']['state'].values())
 rows=[json.loads(x) for x in (BASE/'training_metrics.jsonl').read_text().splitlines()]
 assert len(rows)==2048 and [x['step'] for x in rows]==list(range(1,2049)) and all(x['rows']==1024 and math.isfinite(x['loss']) and math.isfinite(x['gradient_norm']) for x in rows)
 q=np.load(run.REACH/'validation_relabel/validation_targets.npy');m=np.load(run.REACH/'validation_relabel/validation_metadata.npz')
 p=np.load(BASE/'development_probabilities.npy');sourcep=np.load(run.SOURCE/'development_probabilities.npy')
 h,_=run.hero_tv(p,q,m['hands'],m['actors']);old,_=run.hero_tv(sourcep,q,m['hands'],m['actors']);use=np.isfinite(h)&np.isfinite(old)
 treatment=run.interval(h[use]);paired=run.interval(old[use]-h[use]);improvement=float(np.nanmean(old)-np.nanmean(h))
 a=run.read(BASE/'analysis.json')
 for name,value in [('treatment',treatment),('paired_source_minus_treatment',paired)]:
  assert np.allclose(value['ci95'],a[name]['ci95'],atol=2e-12,rtol=0) and abs(value['mean']-a[name]['mean'])<2e-12
 decision='ADMIT_SEQUENCE_RUNTIME_INTEGRATION' if paired['ci95'][0]>0 and improvement>=.01 and treatment['mean']<=.15 else 'SEQUENCE_RESIDUAL_DEVELOPMENT_NOT_PROMISING'
 assert decision==a['decision'] and run.sha(BASE/'latest.pt')==a['model_sha256']
 with np.load(run.REACH/'validation_relabel/validation_arrays.npz') as z:raw={k:z[k][:64] for k in z.files}
 va=run.arrays_actor(raw,m['actors'][:64]);cpu=run.build('cpu',ck['adapter']);cp=run.infer(cpu,va,'cpu',count=False)
 assert np.allclose(cp,p[:64],atol=2e-5,rtol=0)
 qual=run.read(BASE/'qualification.json');assert qual['status']=='PASS' and qual['model_queries']==128 and qual['cpu_gpu_delta']<=2e-5
 report=dict(status='PASS',decision=decision,treatment=treatment,paired_source_minus_treatment=paired,improvement=improvement,model_sha256=run.sha(BASE/'latest.pt'),source_weights_sha256=run.SOURCE_SHA,adapter_parameter_tensors=len(ck['adapter']),optimizer_steps=2048,optimizer_rows_processed=2097152,model_state_queries=e['model_state_queries'],qualification=qual,new_training_hands=0,evaluation_hands=0,strength_hands=0,slumbot_hands=0,goal_achieved=False,wall_time_seconds=e['wall_time_seconds'],review_wall_time_seconds=time.monotonic()-start,interpretation='Sequence residual was selected on a known development cohort and is not confirmatory strength evidence.')
 run.write('reviewed_analysis.json',report);(BASE/'result_summary.md').write_text(f'# Sequence residual development\n\n{decision}\n\nTV {treatment["mean"]:.6f}; improvement {improvement:.6f}; paired {paired}.\n\n0newhands/strength/Slumbot. {report["interpretation"]}\n')
 run.log('--command',f'python research/experiments/{BASE.name}/review_finish.py','--artifact',BASE/'reviewed_analysis.json','--artifact',BASE/'result_summary.md','--metric',f'review_wall_time_seconds={report["review_wall_time_seconds"]}')
 import subprocess
 nxt='Implement and independently test production loader/parity, then preregister untouched native validation.' if decision.startswith('ADMIT') else 'Move from frozen residuals to a full sequence-policy architecture or return to reward training.'
 subprocess.run([sys.executable,str(run.ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED','--summary',f'Sequence-residual development completed: {decision}.','--conclusion',report['interpretation'],'--decision',decision,'--next-step',nxt,'--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0'],cwd=run.ROOT,check=True)
 print(json.dumps(report),flush=True)
if __name__=='__main__':main()

