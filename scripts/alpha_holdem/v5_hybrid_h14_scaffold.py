#!/usr/bin/env python3
"""One-shot mechanical H14 lifecycle scaffold from the frozen H13 implementation."""
from __future__ import annotations
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DIR=ROOT/"scripts/alpha_holdem"
FILES=[
 "v5_hybrid_h13_active_window.py","v5_hybrid_h13_completion_watch.py",
 "v5_hybrid_h13_design_lock_audit.py","v5_hybrid_h13_design_lock_build.py",
 "v5_hybrid_h13_endpoint_watch.py","v5_hybrid_h13_health_watch.py",
 "v5_hybrid_h13_implementation_audit.py","v5_hybrid_h13_judge.py",
 "v5_hybrid_h13_launch_control.ps1","v5_hybrid_h13_launch_treatment.ps1",
 "v5_hybrid_h13_mirror.py","v5_hybrid_h13_ordered_rearm.py",
 "v5_hybrid_h13_perf_cal.py","v5_hybrid_h13_perf_cal_audit.py",
 "v5_hybrid_h13_preflight.py","v5_hybrid_h13_protocol_watch.py",
 "v5_hybrid_h13_treatment_launch_watch.py",
 "test_v5_hybrid_h13_control_plane.py","test_v5_hybrid_h13_control_plane_repairs.py",
 "test_v5_hybrid_h13_health_watch.py","test_v5_hybrid_h13_implementation.py",
 "test_v5_hybrid_h13_judge_contract.py","test_v5_hybrid_h13_ordered_rearm.py",
 "test_v5_hybrid_h13_perf_cal.py","test_v5_hybrid_h13_perf_cal_audit.py",
 "test_v5_hybrid_h13_rearm_contract.py",
]
def main()->int:
 for name in FILES:
  src=DIR/name; dst=DIR/name.replace("h13","h14")
  if dst.exists(): raise SystemExit(f"refusing to overwrite {dst}")
  text=src.read_text(encoding="utf-8")
  text=text.replace("H13","H14").replace("h13","h14").replace("20260716","20260717")
  dst.write_text(text,encoding="utf-8")
 print(f"created {len(FILES)} H14 lifecycle/test files")
 return 0
if __name__=="__main__":raise SystemExit(main())
