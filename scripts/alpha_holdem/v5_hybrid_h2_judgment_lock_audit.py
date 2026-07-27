#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from v5_hybrid_h2_judge import PREREG_SHA,sha
def main():
 p=argparse.ArgumentParser();p.add_argument('--lock',required=True);p.add_argument('--out',required=True);a=p.parse_args();lp=Path(a.lock).resolve();x=json.loads(lp.read_text(encoding='utf-8'));e=[];c={}
 def ck(n,ok,msg):c[n]=bool(ok);e.append(msg) if not ok else None
 ck('identity',x.get('design_id')=='H2-JUDGMENT-001' and x.get('status')=='LOCKED','identity')
 ck('prereg',x.get('preregistration_sha256')==PREREG_SHA,'prereg')
 tp=Path(x.get('tool_path',''));ck('tool',tp.is_file() and sha(tp)==x.get('tool_sha256'),'tool')
 fs=x.get('frozen_files',[]);ck('frozen_files',len(fs)>=11 and all(Path(v['path']).is_file() and sha(v['path'])==v['sha256'] for v in fs),'frozen files')
 g=x.get('gates',{});ck('mse_gate',g.get('endpoint_mse_relative_degradation_point_max')==.05 and g.get('endpoint_mse_relative_degradation_ci95_upper_max')==.10 and g.get('endpoint_mse_bootstrap_seed')==2026071405,'MSE gate')
 ck('throughput_gate',g.get('throughput_warmup_rows_excluded')==1 and g.get('throughput_first_rows')==60 and g.get('throughput_first60_ratio_min')==.85 and g.get('throughput_full_ratio_min')==.85,'throughput gate')
 ck('entropy_gate',g.get('entropy_median_last200_min')==.3 and g.get('entropy_treatment_minus_control_min')==-.1,'entropy gate')
 ck('mirror_gate',g.get('mirror_pairs')==40000 and g.get('mirror_lower_min_bb100')==-20.0,'mirror gate')
 ck('route_review_rule',x.get('route_review_rule')=='required_after_terminal_FAIL_or_fixed_sample_INCONCLUSIVE','route review rule')
 ck('official',x.get('official_hands')==0 and x.get('strength_claim')=='FORBIDDEN','official')
 o={'schema_version':'v5.hybrid.h2.judgment_lock_audit.v1','checked_at':datetime.now(timezone.utc).isoformat(),'overall':'PASS_IMMUTABLE_H2_JUDGMENT_LOCK' if not e else 'FAIL_CLOSED','checks':c,'errors':e,'lock_sha256':sha(lp),'official_hands':0};Path(a.out).write_text(json.dumps(o,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(o,indent=2,sort_keys=True));return 0 if not e else 2
if __name__=='__main__':raise SystemExit(main())
