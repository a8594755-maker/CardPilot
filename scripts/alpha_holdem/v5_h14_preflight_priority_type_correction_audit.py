#!/usr/bin/env python3
"""Independent audit of H14 preflight Windows-priority type correction."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];R=ROOT/"reports/v5_h14_preflight_priority_type_correction_20260717.json";OUT=ROOT/"reports/v5_h14_preflight_priority_type_correction_audit_20260717.json"
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def main()->int:
 d=json.loads(R.read_text(encoding="utf-8"));c={};c["schema"]=d.get("schema_version")=="v5.hybrid.h14.preflight_priority_type_correction.v1";c["overall"]=d.get("overall")=="PASS_REPORTING_ONLY_CORRECTION_REQUIRES_SUPERSEDING_LOCK"
 f=d["failed_preflight"];c["failed_hash"]=sha(ROOT/f["path"])==f["sha256"];fv=json.loads((ROOT/f["path"]).read_text(encoding="utf-8"));c["single_fail"]=fv.get("overall")=="FAIL_CLOSED" and fv.get("errors")==["Path-1 existing six-worker job"] and fv.get("checks",{}).get("path1_existing_six_worker_job") is False;c["observed_identity"]=f.get("observed")=={"coordinator_pid":23720,"worker_count":6,"priority_raw":"16384","ignored_nonworker":"conhost.exe"} and f.get("trainer_launched") is False
 s=d["superseded_lock"];c["v2_lock_hash"]=sha(ROOT/s["path"])==s["sha256"];c["v2_audit_hash"]=sha(ROOT/"reports/v5_hybrid_h14_design_lock_audit_20260717.json")==s["audit_sha256"]
 lock=json.loads((ROOT/s["path"]).read_text(encoding="utf-8"));c["old_tool_binding"]=lock.get("tools",{}).get("scripts/alpha_holdem/v5_hybrid_h14_preflight.py")==s["preflight_tool_sha256"]
 x=d["correction"];tool=ROOT/"scripts/alpha_holdem/v5_hybrid_h14_preflight.py";src=tool.read_text(encoding="utf-8");c["new_tool_hash"]=sha(tool)==x["preflight_tool_sha256"];c["numeric_constant_check"]="int(path1[0][\"nice\"]) == int(psutil.BELOW_NORMAL_PRIORITY_CLASS)" in src and x.get("windows_constant")==16384;c["scope_only"]=x.get("scope")=="REPORTING_TYPE_NORMALIZATION_ONLY" and x.get("run_identity_worker_count_and_priority_requirement")=="UNCHANGED" and x.get("scientific_behavior")=="UNCHANGED";c["v3_required"]=x.get("requires_new_lock")=="v5_hybrid_h14_design_lock_v3_20260717.json";c["no_launch"]=d.get("launch_authority")=="NONE_UNTIL_V3_LOCK_AUDIT_AND_PREFLIGHT_PASS";c["official_zero"]=d.get("official_hands")==0;c["no_strength"]=d.get("strength_claim")=="FORBIDDEN"
 failed=sorted(k for k,v in c.items() if not v);out={"schema_version":"v5.hybrid.h14.preflight_priority_type_correction_audit.v1","checked_at":datetime.now(timezone.utc).isoformat(),"correction_sha256":sha(R),"checks":c,"checks_passed":sum(c.values()),"checks_total":len(c),"failed":failed,"overall":"PASS" if not failed else "FAIL_CLOSED","launch_authority":"NONE_AUDIT_ONLY","official_hands":0};OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(json.dumps(out,indent=2,sort_keys=True));return 0 if not failed else 1
if __name__=="__main__":raise SystemExit(main())
