"""Independent posterior product and hand/cluster arithmetic; zero model calls."""
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import subprocess
import sys
import numpy as np
import psutil
import run_diagnostic as run

def estimate(values,critical=1.96):
    n=len(values)
    mean=math.fsum(map(float,values))/n
    se=math.sqrt(math.fsum((float(v)-mean)**2 for v in values)/(n-1)/n)
    return dict(n=n,mean=mean,standard_error=se,ci95=[mean-critical*se,mean+critical*se])

def close(a,b):
    if isinstance(a,dict):
        assert set(a)==set(b)
        for k in a:close(a[k],b[k])
    elif isinstance(a,(list,tuple)):
        assert len(a)==len(b)
        for x,y in zip(a,b):close(x,y)
    elif isinstance(a,(int,float)):
        assert math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-10),(a,b)
    else:assert a==b

def main():
    if sys.argv[1:] or (run.BASE/'reviewed_analysis.json').exists():raise ValueError('Preserve completed review')
    execution=run.read(run.BASE/'execution.json')
    assert execution['status']=='COMPLETED_PENDING_REVIEW'
    try:assert abs(psutil.Process(execution['pid']).create_time()-execution['create_time'])>.001
    except psutil.NoSuchProcess:pass
    manifest=run.read(run.BASE/'input_manifest.json')
    copies=run.read(run.BASE/'execution_code/copy_manifest.json')
    run.verify(copies,manifest)
    record=run.read(run.BASE/'experiment.json')
    assert record['status']=='RUNNING'
    def recorded(path):
        item=next(v for p,v in record['artifact_integrity'].items() if Path(p).resolve()==path.resolve())
        assert run.sha(path)==item['sha256']
    names=['execution.json','input_manifest.json','observations.npz','metadata.jsonl','coverage.json','batch_qualification.json',
        'full_reference_probability_check.json','mixture_metrics.npz','completed_analysis.json']+[f'probabilities_model{i}.npy' for i in range(4)]
    for name in names:recorded(run.BASE/name)
    arrays,metadata,known,_,coverage=run.preserved_inputs()
    saved=[json.loads(line) for line in (run.BASE/'metadata.jsonl').read_text().splitlines()]
    assert metadata==saved and coverage==run.read(run.BASE/'coverage.json')
    observations=np.load(run.BASE/'observations.npz')
    assert set(observations.files)==set(run.KEYS)
    for key in run.KEYS:assert np.array_equal(arrays[key],observations[key])
    p=np.asarray([np.load(run.BASE/f'probabilities_model{i}.npy') for i in range(4)])
    n=len(metadata)
    assert p.shape==(4,n,9) and np.isfinite(p).all() and (p>=0).all()
    assert np.allclose(p.sum(-1),1,rtol=0,atol=1e-12)
    assert np.all(p[:,arrays['legal_mask']==0]==0)
    actual=p[np.asarray([r['known_model_index'] for r in metadata]),np.arange(n)]
    delta=np.max(np.abs(actual-known),axis=1)
    assert delta.max()<=1e-4
    qualification=run.read(run.BASE/'batch_qualification.json')
    assert qualification['status']=='PASS' and qualification['model_queries']==768
    assert len(qualification['evidence'])==4
    assert all(max(r['cpu_batch_delta'],r['gpu_batch_delta'])<=2e-5 and r['states']==64 for r in qualification['evidence'])
    metrics=np.load(run.BASE/'mixture_metrics.npz')
    by_hand={}
    current=None
    for i,row in enumerate(metadata):
        key=row['cohort'],row['hand']
        if key!=current:
            weight=np.ones(3,dtype=np.longdouble)/3
            current=key
        teacher=p[:3,i].astype(np.longdouble)
        q=np.asarray(np.sum(weight[:,None]*teacher,axis=0),dtype=np.float64)
        assert np.allclose(np.asarray(weight,dtype=np.float64),metrics['posterior'][i],atol=1e-10,rtol=1e-9)
        assert np.allclose(q,metrics['mixture'][i],atol=1e-10,rtol=1e-9)
        tv=math.fsum(abs(float(a)-float(b)) for a,b in zip(q,p[3,i]))/2
        midpoint=(q+p[3,i])/2
        js=.5*sum(math.fsum(float(a)*math.log(float(a)/float(b)) for a,b in zip(dist,midpoint) if a>0) for dist in (q,p[3,i]))
        close(tv,float(metrics['tv'][i]));close(js,float(metrics['js'][i]))
        naive=teacher.mean(0).astype(np.float64)
        close(math.fsum(abs(float(a)-float(b)) for a,b in zip(naive,p[3,i]))/2,float(metrics['naive_tv'][i]))
        by_hand.setdefault(key,[]).append(tv)
        weight*=teacher[:,row['action_slot']]
        assert weight.sum()>0
        weight/=weight.sum()
    hand_values={cohort:[math.fsum(v)/len(v) for (c,_),v in by_hand.items() if c==cohort] for cohort in ('native','slumbot')}
    native,external=[estimate(hand_values[c]) for c in ('native','slumbot')]
    session_means=[]
    for session in range(8):
        values=[math.fsum(v)/len(v) for (c,h),v in by_hand.items() if c=='slumbot' and h//2500==session]
        session_means.append(math.fsum(values)/len(values))
    clusters=estimate(session_means,2.3646242515927853)
    shift=clusters['mean']-native['mean']
    se=math.hypot(clusters['standard_error'],native['standard_error'])
    shift_ci=[shift-2.3646242515927853*se,shift+2.3646242515927853*se]
    decision=('EXTERNAL_DISTRIBUTION_FIDELITY_GAP' if shift_ci[0]>.05 else
        'LARGE_AVERAGING_FIDELITY_GAP' if clusters['ci95'][0]>.10 else 'NO_LARGE_FIDELITY_GAP_CONFIRMED')
    completed=run.read(run.BASE/'completed_analysis.json')
    stats=completed['statistics']
    for cohort,independent in [('native',native),('slumbot',external)]:
        close(independent,{k:stats[cohort][k] for k in independent})
    close(clusters,stats['slumbot_session_t7'])
    close(session_means,stats['slumbot_session_means'])
    close(shift_ci,stats['descriptive_shift']['conservative_t7_ci95'])
    assert decision==stats['decision']
    assert completed['model_queries']==execution['completed_model_queries']==execution['attempted_model_queries']==4*n+768
    assert execution['network_connection_attempts']==0
    assert completed['new_training_hands']==completed['evaluation_hands']==completed['slumbot_hands']==0
    assert not completed['goal_achieved'] and not completed['external_data_used_for_training'] and not completed['counterfactual_returns_estimated']
    run.verify(copies,manifest)
    report=dict(status='PASS',reviewed_at=datetime.now(timezone.utc).isoformat(),decision=decision,
        native_hand_tv=native,external_hand_tv=external,external_session_t7_tv=clusters,
        external_minus_native_tv=shift,shift_ci95=shift_ci,coverage=coverage,model_queries=4*n+768,
        additional_review_model_queries=0,posterior_rows_independently_recomputed=n,
        model_sha256=run.MODEL_SHAS[3],teacher_shas=run.MODEL_SHAS[:3],new_training_hands=0,
        evaluation_hands=0,slumbot_hands=0,qualification_hands=0,goal_achieved=False,
        external_data_used_for_training=False,counterfactual_returns_estimated=False,
        own_source_copy_pairs=len(copies),wall_time_seconds=execution['wall_time_seconds'])
    run.write('reviewed_analysis.json',report)
    (run.BASE/'result_summary.md').write_text('# Preserved-data realization-average fidelity\n\n'+decision+'\n\n'
        +f'Native handmeanTV {native["mean"]:.6f}; external handmeanTV {external["mean"]:.6f}; externalsession95%CI {clusters["ci95"]}.\n\n'
        +f'Descriptive external-minus-native TV {shift:.6f}, conservativeCI {shift_ci}.\n\n'
        +'Zero newhands,training or network. Full-ownhistory posterior compared to truncated-history student; numerical GPUbatch tolerances documented. '
        +'These are behaviorfidelity metrics, not counterfactualwinrates, teacherstrength, exploitability or causaldistributioneffects. '
        +'Do not train on externaltrajectories or claim Goal completion.\n')
    run.log('--command',f'python research/experiments/{run.BASE.name}/review_finish.py','--artifact',run.BASE/'reviewed_analysis.json','--artifact',run.BASE/'result_summary.md')
    subprocess.run([sys.executable,str(run.ROOT/'research/experiment_log.py'),'finish',run.BASE.name,'--status','COMPLETED',
        '--summary',f'Preserved-state reach-mixture fidelity: nativeTV{native["mean"]:.4f},externalTV{external["mean"]:.4f};{decision};0newhands.',
        '--conclusion','Independent full-ownhistory posterior andhand/session arithmetic passed; no counterfactualreturn or generalstrength identification.',
        '--decision',decision,'--next-step','Use fidelity evidence to choose separately preregistered nativeaveraging/coverage or generalteacher/selfplay experiment; no externaldata training.',
        '--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0',
        '--count',f'diagnostic_model_queries={4*n+768}'],cwd=run.ROOT,check=True)
    print(json.dumps(report))

if __name__=='__main__':main()

