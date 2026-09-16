"""Independent review for the low-temperature on-policy smoke."""

from datetime import datetime, timezone
import hashlib, json, math, shutil, sys
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import torch

BASE=Path(__file__).resolve().parent; ROOT=BASE.parents[2]
PRIOR=ROOT/'research/experiments/v6-greedy-advantage-margin-smoke-20260901'
SOURCE=ROOT/'models/baseline/standard10/latest.pt'
SOURCE_SHA='91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
CONTROL_SHA='d806394bc8f8068f8b72e19153d6f96c14f09e8c41c1418091e8441a977c8e29'
TREATMENT_SHA='895bb8d090eff2533d3dfd65244d8ac0ed8a7f29521e22ef778610c4edc26753'
sys.path.insert(0,str(ROOT)); from research.experiment_log import capture_code_provenance

def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for c in iter(lambda:f.read(1048576),b''): h.update(c)
    return h.hexdigest()
def pairs(p):
    decks=[]; values=[]
    for i,line in enumerate(Path(p).read_text(encoding='utf-8').splitlines()):
        row=json.loads(line); assert row['pair_index']==i
        decks.append(row['deck']); values.append(float(np.mean(row['rewards_bb'])*100))
    return decks,np.asarray(values,dtype=np.float64)
def stats(x):
    m=float(x.mean()); h=float(1.96*x.std(ddof=1)/math.sqrt(x.size)); return m,[m-h,m+h]
def write(p,v): Path(p).write_text(json.dumps(v,indent=2,sort_keys=True)+'\n',encoding='utf-8')

def main():
    assert sha(SOURCE)==SOURCE_SHA and sha(PRIOR/'control/latest.pt')==CONTROL_SHA
    assert sha(BASE/'treatment/latest.pt')==TREATMENT_SHA
    assert read(PRIOR/'control/session_audit.json')['status']=='PASS'
    audit=read(BASE/'treatment/session_audit.json')
    assert audit['status']=='PASS' and audit['actual_environment_hands']==10705
    assert audit['legacy_training_marker_hands']==8228 and audit['kl_early_stop_count']==0
    metrics=[json.loads(x) for x in (BASE/'treatment/h1_training_metrics.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(metrics)==2 and all(x['hero_policy_temperature']==0.5 for x in metrics)
    assert all(not x['kl_early_stop_triggered'] for x in metrics)
    source=torch.load(SOURCE,map_location='cpu',weights_only=False)['model']
    model=torch.load(BASE/'treatment/latest.pt',map_location='cpu',weights_only=False)['model']
    assert all(torch.isfinite(v).all() for v in model.values())
    changed=sorted(k for k in source if not torch.equal(source[k],model[k])); assert len(changed)==10
    ca=[json.loads(x) for x in (PRIOR/'control/opponent_assignments.jsonl').read_text(encoding='utf-8').splitlines()]
    ta=[json.loads(x) for x in (BASE/'treatment/opponent_assignments.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(ca)==len(ta)==2 and ca[0]['workers']==ta[0]['workers']
    assert ca[0]['pool_sampling_weights']==ta[0]['pool_sampling_weights']
    assert all(c['worker_seed_base']==t['worker_seed_base']==2026111400 for c,t in zip(ca,ta))
    recorded=read(BASE/'eval/paired_delta.json'); recomputed=[]; pooled=[]
    for expected in recorded['anchors']:
        name=expected['anchor']; cp=PRIOR/'eval'/f'control_{name}/pairs.jsonl'; tp=BASE/'eval'/f'treatment_{name}/pairs.jsonl'
        cd,c=pairs(cp); td,t=pairs(tp); assert len(c)==len(t)==1024 and cd==td
        delta=t-c; mean,ci=stats(delta); pooled.extend(delta.tolist())
        assert math.isclose(mean,expected['treatment_minus_control_bb100'],abs_tol=1e-12)
        assert np.allclose(ci,expected['paired_ci95'],atol=1e-12,rtol=0)
        assert sha(cp)==expected['prior_control_pairs_sha256'] and sha(tp)==expected['treatment_pairs_sha256']
        recomputed.append({'anchor':name,'delta_bb100':mean,'paired_ci95':ci})
    mean,ci=stats(np.asarray(pooled)); assert math.isclose(mean,recorded['pooled']['treatment_minus_control_bb100'],abs_tol=1e-12)
    assert np.allclose(ci,recorded['pooled']['paired_ci95'],atol=1e-12,rtol=0) and sum(x['delta_bb100']>0 for x in recomputed)==2
    xml=ET.parse(BASE/'tests.xml').getroot(); suites=[xml] if xml.tag=='testsuite' else list(xml)
    tests=sum(int(s.attrib.get('tests',0)) for s in suites); failures=sum(int(s.attrib.get('failures',0))+int(s.attrib.get('errors',0)) for s in suites)
    assert tests==17 and failures==0
    paths=['scripts/alpha_holdem/train_mp3_hybrid_h1.py','scripts/alpha_holdem/train_v5.py','scripts/alpha_holdem/test_hero_policy_temperature.py','scripts/alpha_holdem/v6_mirror_eval.py','research/experiment_log.py',f'research/experiments/{BASE.name}/run_eval.py',f'research/experiments/{BASE.name}/audit_review.py','research/experiments/v6-source-greedy-margin-preservation-smoke-20260901/run_eval.py']
    code=BASE/'execution_code'; capture_code_provenance(ROOT,code,paths)
    for rel in paths:
        target=code/'source_files'/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/rel,target)
    report={'schema':'cardpilot.low_temperature_smoke_review.v1','status':'PASS','reviewed_at':datetime.now(timezone.utc).isoformat(),'decision':'ADMIT_MATCHED_65K_LOW_TEMPERATURE_PILOT','control_sha256':CONTROL_SHA,'treatment_sha256':TREATMENT_SHA,'temperature':0.5,'treatment_physical_hands':10705,'treatment_transition_hands':8228,'final_entropy':metrics[-1]['entropy'],'final_reference_policy_kl':metrics[-1]['reference_policy_kl'],'anchors':recomputed,'pooled_delta_bb100':mean,'pooled_paired_ci95':ci,'positive_anchors':2,'new_environment_training_hands':10705,'new_evaluation_hands':6144,'reused_control_evaluation_hands':6144,'slumbot_hands':0,'tests_passed':tests,'goal_achieved':False}
    write(BASE/'reviewed_analysis.json',report); write(BASE/'analysis.json',{**report,'status':'COMPLETED'})
    (BASE/'result_summary.md').write_text(f"# Low-temperature on-policy smoke\n\nDecision: `ADMIT_MATCHED_65K_LOW_TEMPERATURE_PILOT`. T=0.5 pooled treatment-control {mean:+.6f} bb/100, paired 95% CI [{ci[0]:+.6f}, {ci[1]:+.6f}], 2/3 positive anchors. No Slumbot; Goal not achieved.\n",encoding='utf-8')
    print(json.dumps(report,sort_keys=True))
if __name__=='__main__': main()
