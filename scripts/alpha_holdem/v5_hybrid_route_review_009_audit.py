#!/usr/bin/env python3
"""Independent terminal audit for Hybrid Route Review 009."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
R=ROOT/'reports/v5_hybrid_route_review_009_result_20260716.json'
OUT=ROOT/'reports/v5_hybrid_route_review_009_audit_20260716.json'
def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main()->int:
 d=json.loads(R.read_text(encoding='utf-8'));c={}
 c['schema']=d.get('schema_version')=='v5.hybrid.route_review.result.v9.v1';c['identity']=d.get('design_id')=='HYBRID-ROUTE-REVIEW-009';c['pass_review']=d.get('overall')=='PASS_ROUTE_REVIEW'
 c['prereg_hash']=sha(ROOT/'reports/v5_hybrid_route_review_009_preregistration_20260716.json')==d['registration_sha256']
 c['prereg_audit_hash']=sha(ROOT/'reports/v5_hybrid_route_review_009_preregistration_audit_v2_20260716.json')==d['registration_audit_v2_sha256']
 c['prereg_audit_pass']=json.loads((ROOT/'reports/v5_hybrid_route_review_009_preregistration_audit_v2_20260716.json').read_text(encoding='utf-8')).get('overall')=='PASS'
 e=d['evidence_matrix'];h11=e['H11'];h12=e['H12'];cal=e['CAL_EXT_002']
 c['h11_source_hash']=sha(ROOT/h11.get('checkpoint_path','models/alpha_holdem_v5_hybrid/v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715/h11_control_endpoint.pt'))==h11['control_checkpoint_sha256'] if h11.get('checkpoint_path') else sha(ROOT/'models/alpha_holdem_v5_hybrid/v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715/h11_control_endpoint.pt')==h11['control_checkpoint_sha256']
 c['h11_no_method']=h11.get('treatment_endpoint') is False and h11.get('method_effect_evidence')=='NONE'
 c['h12_judgment_hash']=sha(ROOT/'reports/v5_hybrid_h12_judgment_20260716.json')==h12['judgment_sha256']
 c['h12_audit_hash']=sha(ROOT/'reports/v5_hybrid_h12_terminal_audit_20260716.json')==h12['terminal_audit_sha256']
 c['h12_zero_progress']=h12.get('control_training_progress_hands')==0 and h12.get('control_endpoint') is False and h12.get('treatment_launched') is False and h12.get('method_effect_evidence')=='NONE'
 c['four_root_causes']=len(h12.get('root_causes',[]))==4
 c['cal_completion_hash']=sha(ROOT/'reports/v5_cal_ext_002_completion_20260716.json')==cal['completion_sha256']
 c['cal_audit_hash']=sha(ROOT/'reports/v5_cal_ext_002_completion_audit_20260716.json')==cal['completion_audit_sha256']
 c['cal_l0']=cal.get('official_hands')==5000 and cal.get('level')=='L0' and cal.get('promotion_or_formal100k_authorized') is False
 c['cal_ci']=cal.get('bb_per_100')==-146.17260000000002 and cal.get('ci95')==[-238.59789051053525,-53.7473094894648]
 c['selector_fails']=cal.get('unexpected_promotion_failures')==['selector_replay_played_postflop_aggression','selector_replay_greedy_postflop_aggression']
 x=e['external_comparison'];c['point_delta']=abs(x.get('point_delta_bb100')-61.0078)<1e-9;c['no_external_causal_claim']=x.get('method_or_checkpoint_improvement_inference')=='FORBIDDEN_UNPAIRED_WIDE_CI'
 rr=e['research_review'];c['loss_hash']=sha(ROOT/'reports/v5_cal_ext_002_loss_inference_20260716.json')==rr['loss_inference_sha256'];c['research_hash']=sha(ROOT/'reports/v5_hybrid_route_review_009_research_review_20260716.json')==rr['research_review_sha256']
 c['no_action_regret']=rr.get('action_regret')=='MISSING' and rr.get('action_specific_intervention') is False;c['w1_ignored']=rr.get('w1_permission')=='IGNORED_W1_TERMINAL_CLOSED';c['official_adapter_handled']='COMPLETION_AUDIT_52_OF_52' in rr.get('official_missing_in_generic_review','')
 alt=e['alternatives'];c['terminal_branches']=alt.get('W1')=='TERMINAL_CLOSED_NEVER_REOPEN' and alt.get('EXP005_C')=='TERMINAL_CLOSED_NEVER_REOPEN';c['other_branches_deferred']=all('DEFERRED' in alt[k] for k in ['opponent_pool','cfr_distillation','play_time_resolving'])
 dec=d['decision'];c['selected_h13']=dec.get('selected_next')=='H13_CLEAN_ROBUST_VALUE_HEAD_CATCHUP_AFTER_H12_CONTROL_PLANE_FIX';c['route_not_exhausted']=dec.get('route_exhausted') is False
 src=dec['source'];c['source_identity']=src.get('checkpoint_sha256')=='96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13' and src.get('iteration')==35051 and src.get('hands')==576021901
 sv=dec['single_variable'];c['single_variable']=sv.get('control')=='MSE' and 'SmoothL1 beta=1.0' in sv.get('treatment','') and sv.get('standard_ppo_critic_loss')=='MSE_UNCHANGED'
 w=dec['window'];c['fixed_windows']=w.get('fresh_same_start') is True and w.get('control_hands')==w.get('treatment_hands')==20000000 and w.get('no_extension') is True and w.get('no_second_seed') is True and w.get('no_later_endpoint') is True;c['no_partial_reuse']=w.get('h11_h12_partial_reuse')=='FORBIDDEN'
 gates=dec.get('mandatory_prelaunch_control_plane_gate',[]);c['six_repair_gates']=len(gates)==6;c['pending_fix']=any('PENDING' in x for x in gates);c['allowlist_fix']=any('allowlisted' in x for x in gates);c['rearm_exit_fix']=any('nonzero' in x for x in gates);c['launcher_survival_fix']=any('survival_pass=true' in x for x in gates);c['adversarial_fix']=any('adversarial regression' in x for x in gates);c['full_prelaunch']=any('implementation audit' in x for x in gates)
 c['no_resume']=d['candidate_dispositions'].get('resume_h11_or_h12')=='FORBIDDEN';c['no_action_tune']='NO_COUNTERFACTUAL' in d['candidate_dispositions'].get('tune_postflop_aggression','');c['no_launch_authority']=d.get('behavior_launch_authorized','').startswith('NONE_UNTIL_');c['official_zero']=d.get('official_hands_authorized')==0;c['no_strength']=d.get('strength_claim')=='FORBIDDEN'
 failed=sorted(k for k,v in c.items() if not v);out={'schema_version':'v5.hybrid.route_review.audit.v9.v1','checked_at':datetime.now(timezone.utc).isoformat(),'result_sha256':sha(R),'checks':c,'checks_passed':sum(c.values()),'checks_total':len(c),'failed':failed,'overall':'PASS' if not failed else 'FAIL_CLOSED','selected_next':dec.get('selected_next') if not failed else None,'route_exhausted':dec.get('route_exhausted') if not failed else None,'behavior_launch_authority':'NONE_REVIEW_AUDIT_ONLY','strength_claim':'FORBIDDEN'}
 OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(out,indent=2,sort_keys=True));return 0 if not failed else 1
if __name__=='__main__':raise SystemExit(main())
