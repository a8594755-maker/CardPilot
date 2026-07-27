#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];A=ROOT/'reports/v5_h13_control_plane_repair_20260716.json';OUT=ROOT/'reports/v5_h13_control_plane_repair_audit_20260716.json'
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def main()->int:
 d=json.loads(A.read_text(encoding='utf-8'));c={};c['schema']=d.get('schema_version')=='v5.hybrid.h13.control_plane_repair.v1';c['overall']=d.get('overall')=='PASS_READY_FOR_H13_PREREGISTRATION'
 refs={'route_review_009_result':ROOT/'reports/v5_hybrid_route_review_009_result_20260716.json','route_review_009_audit':ROOT/'reports/v5_hybrid_route_review_009_audit_20260716.json'}
 for k,p in refs.items():c[f'authority_{k}']=sha(p)==d['authority'][f'{k}_sha256']
 inc={'h12_incident':ROOT/'reports/v5_hybrid_h12_resource_isolation_incident_20260716.json','h12_judgment':ROOT/'reports/v5_hybrid_h12_judgment_20260716.json','h12_terminal_audit':ROOT/'reports/v5_hybrid_h12_terminal_audit_20260716.json'}
 for k,p in inc.items():c[k]=sha(p)==d['incident_source'][f'{k}_sha256']
 for rel,expected in d['tool_sha256'].items():c[f'tool_{Path(rel).name}']=sha(ROOT/rel)==expected
 health=(ROOT/'scripts/alpha_holdem/v5_hybrid_h12_health_watch.py').read_text(encoding='utf-8');protocol=(ROOT/'scripts/alpha_holdem/v5_hybrid_h12_protocol_watch.py').read_text(encoding='utf-8');ordered=(ROOT/'scripts/alpha_holdem/v5_hybrid_h12_ordered_rearm.py').read_text(encoding='utf-8');rearm=(ROOT/'scripts/alpha_holdem/v5_rearm_watchers.ps1').read_text(encoding='utf-8-sig')
 c['startup_pending']='WAITING_FOR_STARTUP_LOG' in health and 'startup-log-timeout-seconds' in health and 'TimeoutError' in health
 c['exact_supervisor_args']='--allowed-supervisor-pid' in protocol and '--allowed-supervisor-command-sha256' in protocol and 'allowed_supervisor_identity_mismatch' in protocol
 c['ordered_passes_identity']='--allowed-supervisor-pid' in ordered and 'current_command_identity' in ordered
 c['rearm_exit3']='if (-not $survivalPass) {\n    exit 3\n}' in rearm
 for name in ['v5_hybrid_h12_launch_control.ps1','v5_hybrid_h12_launch_treatment.ps1']:
  source=(ROOT/'scripts/alpha_holdem'/name).read_text(encoding='utf-8-sig');c[f'{name}_survival']='watcher_rearm_status.json' in source and 'rearm survival_pass=false' in source
 v=d['verification'];c['tests']=v.get('focused_and_regression_tests')=='PASS_48_OF_48' and v.get('adversarial_incident_tests')==6;c['no_execution']=v.get('trainer_processes')==v.get('slumbot_processes')==v.get('mirror_processes')==v.get('official_hands')==0 and v.get('behavior_change') is False
 s=d['scope'];c['h12_closed']=s.get('h12_terminal_verdict')=='UNCHANGED' and s.get('h12_resume_authority')=='NONE';c['h13_no_launch']=s.get('h13_launch_authority')=='NONE_REPAIR_SUPPORTS_PREREGISTRATION_ONLY';c['path1']=s.get('path1')=='UNTOUCHED'
 failed=sorted(k for k,v in c.items() if not v);out={'schema_version':'v5.hybrid.h13.control_plane_repair_audit.v1','checked_at':datetime.now(timezone.utc).isoformat(),'repair_sha256':sha(A),'checks':c,'checks_passed':sum(c.values()),'checks_total':len(c),'failed':failed,'overall':'PASS' if not failed else 'FAIL_CLOSED','launch_authority':'NONE_REPAIR_AUDIT_ONLY'};OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(out,indent=2,sort_keys=True));return 0 if not failed else 1
if __name__=='__main__':raise SystemExit(main())
