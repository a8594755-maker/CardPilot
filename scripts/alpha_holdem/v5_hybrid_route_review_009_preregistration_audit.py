#!/usr/bin/env python3
"""Independent audit for Hybrid Route Review 009 registration."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "reports/v5_hybrid_route_review_009_preregistration_20260716.json"
OUT = ROOT / "reports/v5_hybrid_route_review_009_preregistration_audit_v2_20260716.json"

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()

def main() -> int:
    d=json.loads(P.read_text(encoding='utf-8')); c={}
    c['schema']=d.get('schema_version')=='v5.hybrid.route_review.preregistration.v9.v1'
    c['identity']=d.get('design_id')=='HYBRID-ROUTE-REVIEW-009'
    c['reporting_only']=d.get('status')=='REGISTERED_REPORTING_ONLY_NO_LAUNCH'
    refs={
      'h12_terminal_judgment':ROOT/'reports/v5_hybrid_h12_judgment_20260716.json',
      'h12_terminal_audit':ROOT/'reports/v5_hybrid_h12_terminal_audit_20260716.json',
      'cal_ext_002_completion':ROOT/'reports/v5_cal_ext_002_completion_20260716.json',
      'cal_ext_002_completion_audit':ROOT/'reports/v5_cal_ext_002_completion_audit_20260716.json'}
    for k,p in refs.items(): c[f'trigger_{k}']=sha(p)==d['trigger'][f'{k}_sha256']
    frozen={
      'route_review_008_result':ROOT/'reports/v5_hybrid_route_review_008_result_20260716.json',
      'route_review_008_audit':ROOT/'reports/v5_hybrid_route_review_008_audit_20260716.json',
      'h11_throughput_diagnosis':ROOT/'reports/v5_hybrid_h11_throughput_diagnosis_20260716.json',
      'cal_ext_002_loss_inference':ROOT/'reports/v5_cal_ext_002_loss_inference_20260716.json',
      'research_review':ROOT/'reports/v5_hybrid_route_review_009_research_review_20260716.json',
      'value_audit':ROOT/'reports/v5_value_audit_001_20260710.json',
      'asset_audit':ROOT/'reports/v5_asset_audit_001_20260710.json'}
    for k,p in frozen.items(): c[f'input_{k}']=sha(p)==d['frozen_inputs'][f'{k}_sha256']
    h12=json.loads(refs['h12_terminal_audit'].read_text(encoding='utf-8'))
    cal=json.loads(refs['cal_ext_002_completion_audit'].read_text(encoding='utf-8'))
    research=json.loads(frozen['research_review'].read_text(encoding='utf-8'))
    c['h12_terminal_pass']=h12.get('overall')=='PASS_COMPLETE_H12_TERMINAL_INCONCLUSIVE_RESOURCE_ISOLATION'
    c['cal_terminal_pass']=cal.get('overall')=='PASS_COMPLETE_CAL_EXT_002_TERMINAL_FAIL_CLOSED'
    c['cal_l0']=cal.get('latest_official_level')=='L0' and cal.get('official_hands')==5000
    c['research_no_action_tuning']=research.get('permissions',{}).get('may_register_action_specific_intervention') is False
    c['research_no_behavior_authority']=research.get('permissions',{}).get('new_behavior_change_authorized_by_this_review') is False
    t=d['truth_constraints']
    c['terminal_w1']=t.get('w1')=='TERMINAL_CLOSED_NEVER_REOPEN'
    c['terminal_exp005c']=t.get('exp005c')=='TERMINAL_CLOSED_NEVER_REOPEN'
    c['no_method_effect']='NO_METHOD_EFFECT' in t.get('h11','') and 'NO_METHOD_EFFECT' in t.get('h12','')
    c['action_regret_missing']=t.get('action_regret')=='MISSING' and t.get('action_specific_tuning')=='FORBIDDEN'
    c['candidate_order']=d.get('candidate_order',[None])[0]=='H13_CLEAN_ROBUST_VALUE_HEAD_CATCHUP_AFTER_H12_CONTROL_PLANE_FIX'
    rules=' '.join(d.get('decision_rule',[]))
    c['rule_terminal_closed']='Never select W1,EXP005-C' in rules
    c['rule_counterfactual']='validated counterfactual' in rules
    c['rule_h13_clean']='new clean H13' in rules and 'no h11/h12 partial reuse' in rules.lower()
    c['rule_route_exhaustion']='no hybrid candidate' in rules
    gates=d.get('mandatory_h13_control_plane_gate',[])
    c['six_control_plane_gates']=len(gates)==6
    c['startup_pending_gate']=any('startup log as PENDING' in x for x in gates)
    c['allowlist_gate']=any('ordered-rearm supervisor' in x for x in gates)
    c['rearm_exit_gate']=any('exits nonzero' in x for x in gates)
    c['launcher_survival_gate']=any('survival_pass true' in x for x in gates)
    c['adversarial_gate']=any('adversarial integration' in x for x in gates)
    c['prelaunch_gate']=any('before any sentinel or trainer' in x for x in gates)
    ep=d['evidence_policy']
    c['observational_only']=ep.get('loss_inference')=='OBSERVATIONAL_ASSOCIATIONAL_ONLY'
    c['w1_permission_ignored']='W1_PERMISSION_IGNORED_BECAUSE_W1_TERMINAL' in ep.get('value_audit','')
    c['official_adapter_gap']='COMPLETION_AUDIT_52_OF_52' in ep.get('official_schema_adapter_gap','')
    oc=d['output_contract']
    c['no_launch_authority']=oc.get('behavior_launch_authority')=='NONE_REVIEW_ONLY' and oc.get('official_hands_authority')==0
    failed=sorted(k for k,v in c.items() if not v)
    out={'schema_version':'v5.hybrid.route_review.preregistration_audit.v9.v2','checked_at':datetime.now(timezone.utc).isoformat(),'preregistration_sha256':sha(P),'supersedes_failed_audit_sha256':'27b70eaae96414924ad4b5081365f698e2516eb193f5961a53bc11f0aedb4cec','checks':c,'checks_passed':sum(c.values()),'checks_total':len(c),'failed':failed,'overall':'PASS' if not failed else 'FAIL_CLOSED','authority':'REPORTING_ONLY_NO_LAUNCH'}
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps(out,indent=2,sort_keys=True)); return 0 if not failed else 1

if __name__=='__main__': raise SystemExit(main())
