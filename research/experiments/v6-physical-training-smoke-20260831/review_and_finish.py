"""Independent arithmetic and artifact review of the completed fixed v6 smoke."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import torch

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
from research.experiment_log import sha256_file
from alpha_holdem.policy_contract_v6 import validate_metadata


def main():
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists():
        raise ValueError('Fixed completed-evidence review; no overwrite')
    source=json.loads((BASE/'completed_analysis.json').read_text())
    assert source['status']=='COMPLETED_PENDING_REVIEW'
    record=json.loads((BASE/'experiment.json').read_text())
    assert record['status']=='RUNNING'
    import psutil
    trainer_pid=int(record['metrics']['trainer_pid'])
    assert not psutil.pid_exists(trainer_pid), 'Do not review while trainer lives'
    checkpoint=torch.load(BASE/'production/latest.pt',map_location='cpu',weights_only=False)
    validate_metadata(checkpoint)
    manifest=json.loads((BASE/'production/run_manifest.json').read_text())
    assert manifest['status']=='finished'
    metrics=[json.loads(line) for line in (BASE/'production/h1_training_metrics.jsonl').read_text().splitlines()]
    assert [row['iteration'] for row in metrics]==list(range(1,checkpoint['iteration']+1))
    final_accounting=checkpoint['environment_hand_accounting']
    count=final_accounting['completed_hands']
    assert final_accounting['prefix_complete'] and count>=8192
    assert final_accounting['origin_run_id']=='v6_physical_smoke_20260831'
    assert final_accounting['unknown_prefix_training_marker_hands']==0
    assert sum(row['completed_hands'] for row in final_accounting['session_worker_counts'])==count
    assert count==source['new_training_hands']==manifest['environment_hand_accounting']['completed_hands']
    counts=[row['environment_hand_accounting']['completed_hands'] for row in metrics]
    assert all(a<b for a,b in zip([0]+counts,counts+[count+1]))
    assert all(v<8192 for v in counts[:-1]), 'Missed first endpoint crossing'
    assert count>=counts[-1]
    states=checkpoint['optimizer']['state']
    assert len(states)==86
    steps=sorted(set(float(st['step']) for st in states.values()))
    assert min(steps)>0
    for state in states.values():
        for value in state.values():
            if isinstance(value,torch.Tensor): assert torch.isfinite(value).all()
    original=torch.load(ROOT/'models/baseline/standard10/latest.pt',map_location='cpu',weights_only=False)
    assert sum(not torch.equal(original['model'][k],v) for k,v in checkpoint['model'].items())==86
    for value in checkpoint['model'].values(): assert torch.isfinite(value).all()
    assert sha256_file(BASE/'production/latest.pt')==sha256_file(BASE/'frozen/final.pt')==source['final_sha256']
    source_copies=json.loads((BASE/'execution_code/copy_manifest.json').read_text())
    for item in source_copies:
        for key in ['original','copy']:
            assert sha256_file(ROOT/item[key])==item['sha256']
    cells=[]
    raw_values={}
    for label in ['source','final']:
        for anchor in range(3):
            directory=BASE/'matrix'/f'{label}_anchor{anchor}'
            summary=json.loads((directory/'summary.json').read_text())
            rows=[json.loads(line) for line in (directory/'pairs.jsonl').read_text().splitlines()]
            assert len(rows)==64 and [row['pair_index'] for row in rows]==list(range(64))
            values=[sum(row['rewards_bb'])/2*100 for row in rows]
            mean=statistics.mean(values)
            half=1.96*statistics.stdev(values)/math.sqrt(64)
            assert abs(mean-summary['bb_per_100'])<1e-8
            assert max(abs(a-b) for a,b in zip([mean-half,mean+half],summary['ci95']))<1e-8
            assert sha256_file(directory/'pairs.jsonl')==summary['pairs_sha256']
            candidate=BASE/'frozen'/('anchor0.pt' if label=='source' else 'final.pt')
            assert sha256_file(candidate)==summary['candidate_sha256']
            assert sha256_file(BASE/f'frozen/anchor{anchor}.pt')==summary['anchor_sha256']
            raw_values[label,anchor]=(rows,values)
            cells.append(dict(candidate=label,anchor=anchor,bb_per_100=mean,ci95=[mean-half,mean+half]))
    deltas=[]
    for anchor in range(3):
        a,x=raw_values['source',anchor]
        b,y=raw_values['final',anchor]
        assert [r['deck'] for r in a]==[r['deck'] for r in b]
        differences=[right-left for left,right in zip(x,y)]
        mean=statistics.mean(differences)
        half=1.96*statistics.stdev(differences)/8
        deltas.append(dict(anchor=anchor,bb_per_100=mean,ci95=[mean-half,mean+half]))
    assert all(value==0 for value in raw_values['source',0][1])
    summary=dict(status='PASS',decision='V6_TRAINING_PIPELINE_SMOKE_PASSED',new_training_hands=count,
        physical_overshoot=count-8192,legacy_training_marker_hands=checkpoint['total_hands'],
        evaluation_hands=768,slumbot_hands=0,iterations=checkpoint['iteration'],
        finite_changed_tensors=86,finite_optimizer_states=86,optimizer_steps=steps,
        source_pairs_verified=len(source_copies),cells=cells,descriptive_final_minus_source=deltas,
        qualification_admitted=False,reviewed_at=datetime.now(timezone.utc).isoformat())
    (BASE/'reviewed_analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
    (BASE/'result_summary.md').write_text(
        '# Corrected-contract training smoke passed\n\n'
        f'Completed{count}new physical training hands in{checkpoint["iteration"]}updates '
        f'(target8192,overshoot{count-8192}),{checkpoint["total_hands"]}legacy training markers, '
        'and768fresh internal diagnostic hands. All86tensors changed and86Adam states '
        'are finite. Physical worker sums,checkpoint/manifest/update prefix,fixed-pool '
        'session audit and source/frozen hashes agree.\n\n'
        'Six64pair cells are pipeline diagnostics only. Their raw pair-based intervals '
        'and matched descriptive differences were independently recomputed. Source '
        'self-match cancels exactly. No Slumbot hands or qualification admission.\n\n'
        'Next: preregister a substantive corrected-contract learned-weight curve from '
        'the same original source, with fixed physical budgets and separate held-out '
        'anchors. Do not promote this tiny smoke or pool legacy-contract outcomes.\n')
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,
        '--command','python research/experiments/v6-physical-training-smoke-20260831/review_and_finish.py',
        '--artifact',str(Path(__file__)),'--artifact',str(BASE/'reviewed_analysis.json'),
        '--artifact',str(BASE/'result_summary.md'),'--note',
        'Independent raw arithmetic/checkpoint/worker/source review passed. Tiny cell results are descriptive and do not select a policy or admit qualification.'],check=True)
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,
        '--status','COMPLETED','--summary',f'Correctedv6 PPO smoke completed{count}physical training hands and768diagnostic internal hands,with86finite changed tensors and validated accounting.',
        '--conclusion','The repaired production trainer and frozen-evaluation pipeline work on actual learned weights; strength improvement is not established by this tiny smoke.',
        '--decision','V6_TRAINING_PIPELINE_SMOKE_PASSED','--next-step',
        'Preregister a substantive v6 physical-budget learning curve and untouched multi-anchor evaluation from the original source, excluding prior smoke and legacy outcomes from confirmation.',
        '--count',f'new_training_hands={count}','--count','evaluation_hands=768','--count','slumbot_hands=0'],check=True)
    print(json.dumps(summary),flush=True)


if __name__=='__main__': main()
