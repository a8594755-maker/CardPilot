"""Outcome-blind independent raw-evidence review, run only after all jobs exit."""
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
from research.experiment_log import sha256_file


def interval(values,level=.95):
    if len(values)<2 or not all(math.isfinite(x) for x in values):
        raise ValueError('Invalid independent-pair observations')
    mean=math.fsum(values)/len(values)
    squared=math.fsum((x-mean)**2 for x in values)
    se=(squared/(len(values)-1)/len(values))**.5
    z=statistics.NormalDist().inv_cdf((1+level)/2)
    # Runtime uses the conventional1.96 value for the95% normal approximation.
    if level==.95: z=1.96
    return dict(bb_per_100=mean,ci=[mean-z*se,mean+z*se],standard_error=se)


def verify_rows(rows,expected):
    if len(rows)!=expected or [row['pair_index'] for row in rows]!=list(range(expected)):
        raise ValueError('Missing/duplicate/out-of-order pairs')
    for row in rows:
        if len(row['deck'])!=52 or set(row['deck'])!=set(range(52)):
            raise ValueError('Invalid deal permutation')
        if len(row['rewards_bb'])!=2 or not all(math.isfinite(x) and abs(x)<=200 for x in row['rewards_bb']):
            raise ValueError('Invalid zero-rake200bb hand outcome')
        if len(row['decisions'])!=2 or not all(type(x) is int and x>0 for x in row['decisions']):
            raise ValueError('Invalid completed-hand decision counts')
    return [statistics.mean(row['rewards_bb'])*100 for row in rows]


def raw_gate(contrasts):
    if len(contrasts)!=5 or [r['anchor'] for r in contrasts]!=list(range(5)):
        raise ValueError('Wrong primary contrast family')
    significant={r['anchor'] for r in contrasts if r['ci99'][0]>0}
    return all(r['bb_per_100']>0 for r in contrasts) and len(significant)>=3 and 0 in significant and bool(significant & {3,4})


def main():
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists():
        raise ValueError('Fixed completed review; no overwrite')
    import psutil
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    execution=json.loads((BASE/'execution.json').read_text())
    if execution['status']!='COMPLETED_PENDING_REVIEW' or psutil.pid_exists(execution['pid']):
        raise ValueError('Wrapper is not confirmed terminal')
    children=execution['children']
    assert len(children)==21 and all(row['exit_code']==0 for row in children)
    assert all(not psutil.pid_exists(row['pid']) for row in children)
    writer=json.loads((BASE/'completed_analysis.json').read_text())
    assert writer['status']=='COMPLETED_PENDING_REVIEW'
    checkpoint=torch.load(BASE/'production/latest.pt',map_location='cpu',weights_only=False)
    validate_metadata(checkpoint)
    manifest=json.loads((BASE/'production/run_manifest.json').read_text())
    assert manifest['status']=='finished'
    accounting=checkpoint['environment_hand_accounting']
    count=accounting['completed_hands']
    assert count>=262144 and accounting['prefix_complete']
    assert accounting['unknown_prefix_training_marker_hands']==0
    assert accounting['origin_run_id']=='v6_full_curve_20260831'
    assert sum(row['completed_hands'] for row in accounting['session_worker_counts'])==count
    assert count==manifest['environment_hand_accounting']['completed_hands']==writer['new_training_hands']
    metrics=[json.loads(line) for line in (BASE/'production/h1_training_metrics.jsonl').read_text().splitlines()]
    assert [row['iteration'] for row in metrics]==list(range(1,checkpoint['iteration']+1))
    counts=[row['environment_hand_accounting']['completed_hands'] for row in metrics]
    assert all(a<b for a,b in zip([0]+counts[:-1],counts))
    assert all(v<262144 for v in counts[:-1]) and counts[-1]>=262144 and count>=counts[-1]
    state=checkpoint['optimizer']['state']
    assert len(state)==86
    for row in state.values():
        assert float(row['step'])>0
        assert all(torch.isfinite(v).all() for v in row.values() if isinstance(v,torch.Tensor))
    source=torch.load(ROOT/'models/baseline/standard10/latest.pt',map_location='cpu',weights_only=False)
    assert len(checkpoint['model'])==86
    changed=sum(not torch.equal(v,source['model'][key]) for key,v in checkpoint['model'].items())
    assert changed==86 and all(torch.isfinite(v).all() for v in checkpoint['model'].values())
    pool=[row['score_components']['checkpoint_sha256'] for row in checkpoint['pool_snapshots']]
    anchors=json.loads((BASE/'anchor_manifest.json').read_text())
    assert pool==[row['sha256'] for row in anchors[:3]]
    selection=json.loads((BASE/'checkpoint_selection.json').read_text())
    assert list(selection)==['source','mid65','mid131','final']
    assert selection['final']['physical_hands']==count
    assert sha256_file(BASE/'production/latest.pt')==selection['final']['sha256']
    for label,threshold in [('mid65',65536),('mid131',131072)]:
        first=next(row for row in metrics if row['iteration']%4==0 and row['environment_hand_accounting']['completed_hands']>=threshold)
        assert selection[label]['iteration']==first['iteration']
        assert selection[label]['physical_hands']==first['environment_hand_accounting']['completed_hands']
    for item in selection.values():
        assert sha256_file(Path(item['path']))==item['sha256']
        validate_metadata(torch.load(item['path'],map_location='cpu',weights_only=False))
    for item in anchors:
        assert sha256_file(Path(item['path']))==item['sha256']
        assert sha256_file(Path(item['source']))==item['source_sha256']
    copies=json.loads((BASE/'execution_code/copy_manifest.json').read_text())
    for item in copies:
        for key in ['original','copy']: assert sha256_file(ROOT/item[key])==item['sha256']
    audit=json.loads((BASE/'session_audit.json').read_text())
    assert audit['status']=='PASS' and audit['actual_environment_hands']==count
    audit_files={'checkpoint':'latest.pt','manifest':'run_manifest.json','metrics':'h1_training_metrics.jsonl',
                 'assignments':'opponent_assignments.jsonl','train_log':'latest_train.log'}
    for key,name in audit_files.items():
        assert sha256_file(BASE/'production'/name)==audit['artifact_integrity'][key]['sha256']
    cells=[]
    paired={}
    for label in selection:
        for anchor in range(5):
            directory=BASE/'matrix'/f'{label}_anchor{anchor}'
            row_path=directory/'pairs.jsonl'
            rows=[json.loads(line) for line in row_path.read_text().splitlines()]
            values=verify_rows(rows,2048)
            summary=json.loads((directory/'summary.json').read_text())
            assert summary['status']=='COMPLETED' and summary['seed']==20260919
            assert summary['candidate_sha256']==selection[label]['sha256']
            assert summary['anchor_sha256']==anchors[anchor]['sha256']
            assert summary['evaluation_hands']==4096 and sha256_file(row_path)==summary['pairs_sha256']
            estimate=interval(values)
            assert abs(estimate['bb_per_100']-summary['bb_per_100'])<1e-8
            assert max(abs(x-y) for x,y in zip(estimate['ci'],summary['ci95']))<1e-7
            cells.append(dict(candidate=label,anchor=anchor,**estimate))
            paired[label,anchor]=(rows,values)
    contrasts=[]
    curve_deltas=[]
    for anchor in range(5):
        raw_source,source_values=paired['source',anchor]
        for label in ['mid65','mid131','final']:
            raw,values=paired[label,anchor]
            assert [row['deck'] for row in raw]==[row['deck'] for row in raw_source]
            differences=[new-old for old,new in zip(source_values,values)]
            ordinary=interval(differences)
            adjusted=interval(differences,.99)
            row=dict(candidate=label,anchor=anchor,bb_per_100=ordinary['bb_per_100'],ci95=ordinary['ci'],ci99=adjusted['ci'])
            curve_deltas.append(row)
            if label=='final': contrasts.append(row)
    assert all(value==0 for value in paired['source',0][1])
    for actual,recorded in zip(contrasts,writer['primary_contrasts']):
        assert actual['anchor']==recorded['anchor']
        assert abs(actual['bb_per_100']-recorded['bb_per_100'])<1e-7
        assert max(abs(x-y) for x,y in zip(actual['ci99'],recorded['ci99']))<1e-7
    gate=raw_gate(contrasts)
    assert gate==writer['confirmation_gate_pass']
    summary=dict(status='PASS',decision='ADMIT_INDEPENDENT_CONFIRMATION' if gate else 'FINAL_BREADTH_GATE_NOT_PASSED',
        confirmation_gate_pass=gate,qualification_admitted=False,new_training_hands=count,
        physical_overshoot=count-262144,legacy_training_marker_hands=checkpoint['total_hands'],
        evaluation_hands=81920,slumbot_hands=0,iterations=checkpoint['iteration'],changed_tensors=changed,
        optimizer_state_count=len(state),optimizer_step_values=sorted(set(float(row['step']) for row in state.values())),
        ppo_epochs_completed_histogram=dict(Counter(row['ppo_epochs_completed'] for row in metrics)),
        max_reference_policy_kl=max(row['reference_policy_kl'] for row in metrics),
        max_approx_kl=max(row['approx_kl'] for row in metrics),
        source_pairs_verified=len(copies),clean_child_exits=len(children),selection=selection,
        cells=cells,descriptive_curve_deltas=curve_deltas,primary_contrasts=contrasts,
        reviewed_at=datetime.now(timezone.utc).isoformat())
    (BASE/'reviewed_analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# Corrected-v6 full-network curve result','',
        f'Completed{count}new physical training hands ({checkpoint["iteration"]}updates,overshoot{count-262144}), '
        'and81920new internal evaluation hands. All21children exited0; physical accounting, '
        'fixed-pool session audit,86changed finite tensors/Adam states and frozen/source hashes verified.',
        '',f'Primary final-minus-source decision: {summary["decision"]}.',
        '', '| Anchor | bb/100 difference |95%CI|Bonferroni99%CI|', '|---|---:|---|---|']
    names=['Standard10','slumbot_free','corrected_cfr96','heldout_weak','heldout_full']
    for row in contrasts:
        lines.append(f'|{names[row["anchor"]]}|{row["bb_per_100"]:+.4f}|[{row["ci95"][0]:+.4f},{row["ci95"][1]:+.4f}]|[{row["ci99"][0]:+.4f},{row["ci99"][1]:+.4f}]|')
    lines += ['', 'Midpoints are descriptive and are not alternative promotion candidates. '
        'Two anchors were held out of this run,not wholly unseen strategy families. '
        'No legacy or smoke performance is pooled; no Slumbot hands or100k qualification.']
    (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n')
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,
        '--command','python research/experiments/v6-full-network-learning-curve-20260831/review_completed_curve.py',
        '--artifact',str(Path(__file__)),'--artifact',str(BASE/'reviewed_analysis.json'),'--artifact',str(BASE/'result_summary.md'),
        '--note','Independent raw-pair arithmetic,source/checkpoint/counter and process review passed; only the preregistered final breadth gate controls confirmation.'],check=True)
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,
        '--status','COMPLETED','--summary',f'Correctedv6 full-network curve completed{count}physical training hands and81920internal hands with valid evidence;{summary["decision"]}.',
        '--conclusion','The fixed corrected-contract curve and final breadth test completed; internal evidence alone does not establish external or Nash strength.',
        '--decision',summary['decision'],'--next-step',
        ('Preregister separate independent-deal confirmation of the exact final checkpoint before external admission.' if gate else
         'Analyze fixed curve and optimizer health to choose a separate learning mechanism; do not promote a midpoint or extend this failed final gate.'),
        '--count',f'new_training_hands={count}','--count','evaluation_hands=81920','--count','slumbot_hands=0'],check=True)
    print(json.dumps(summary),flush=True)


if __name__=='__main__': main()
