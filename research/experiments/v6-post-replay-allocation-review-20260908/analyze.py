"""Bounded retained-evidence allocation review; no poker execution or source edits."""
from pathlib import Path
import hashlib
import json
import sys
import time

BASE=Path(__file__).resolve().parent
IDS=['v6-opponent-execution-mixture-two-seed-geometric-20260907','v6-expanded-family-two-seed-geometric-20260907','v6-family-allocation-two-seed-geometric-20260907','v6-fresh-only-two-seed-geometric-20260907']
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    started=time.monotonic(); hashes={str(Path(__file__)):sha(__file__)}; cells=[]; costs=[]
    for id in IDS:
        folder=BASE.parent/id
        paths=[folder/'experiment.json',folder/'post_terminal_review.json']
        for p in paths: hashes[str(p)]=sha(p)
        e,r=[json.loads(p.read_text(encoding='utf-8')) for p in paths]
        assert e['status']=='COMPLETED' and r['passed'] and r['jobs_terminal']==16 and r['overlap']==0
        costs.append(dict(id=id,physical=r['counts']['new_physical_hands'],training_wall_seconds=r['training_wall_seconds'],controller_wall_seconds=r['controller_wall_seconds'],physical_per_training_second=r['counts']['new_physical_hands']/r['training_wall_seconds']))
        for stage in ('1','2'):
            for seed in ('1','3'):
                v=r['stages'][stage][seed]
                groups={'preservation':v} if 'endpoint_minus_parent' in v else v
                for panel,g in groups.items():
                    for arm,b in g['endpoint_minus_parent'].items():
                        p=b['pooled']; ci=p['ci95']
                        assert len(ci)==2 and ci[0]<=p['bb100']<=ci[1] and p['paired_decks']>0
                        cells.append(dict(id=id,stage=int(stage),seed=int(seed),panel=panel,arm=arm,own_root_bb100=p['bb100'],ci95=ci,both_seats_positive=all(v['bb100']>0 for v in b['by_seat'].values()),positive_anchors=sum(v['bb100']>0 for v in b['by_anchor'].values()),anchors=len(b['by_anchor'])))
    assert len(cells)==48
    replicated=[]
    for c in cells:
        if c['stage']!=2 or c['seed']!=1: continue
        mate=next(v for v in cells if all(v[k]==c[k] for k in ('id','stage','panel','arm')) and v['seed']==3)
        replicated.append(dict(id=c['id'],panel=c['panel'],arm=c['arm'],both_seed_point_positive=c['own_root_bb100']>0 and mate['own_root_bb100']>0,both_seed_lower_positive=c['ci95'][0]>0 and mate['ci95'][0]>0))
    report=dict(passed=True,command=sys.orig_argv,input_sha256=hashes,cells=cells,costs=costs,stage2_replication=replicated,new_training_hands=0,evaluation_hands=0,final_qualification_hands=0,wall_seconds=time.monotonic()-started,limitations=['Retained audited summaries, not a second raw-hand audit.','Changing parents/configurations and dependent seed lineages cannot be pooled into one stationary long-run curve.','Different stage decks prevent a paired stage2-minus-stage1 inference from summary means.','Conditional unadjusted intervals; no multiple-comparison or training-seed population claim.','Snapshot temporal stability remains an untested hypothesis, not established cycling or a proven averaging benefit.'])
    assert all(sha(p)==h for p,h in hashes.items())
    with (BASE/'analysis.json').open('x',encoding='utf-8') as f: json.dump(report,f,indent=2,allow_nan=False)
    print(json.dumps(dict(cells=len(cells),replication=replicated,costs=costs)))
if __name__=='__main__': main()
