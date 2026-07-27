#!/usr/bin/env python3
"""One-shot mechanical H15 lifecycle scaffold from frozen H14 files."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "scripts/alpha_holdem"
FILES = [
    "v5_hybrid_h14_active_window.py",
    "v5_hybrid_h14_completion_watch.py",
    "v5_hybrid_h14_design_lock_audit.py",
    "v5_hybrid_h14_design_lock_build.py",
    "v5_hybrid_h14_endpoint_watch.py",
    "v5_hybrid_h14_health_watch.py",
    "v5_hybrid_h14_implementation_audit.py",
    "v5_hybrid_h14_judge.py",
    "v5_hybrid_h14_launch_control.ps1",
    "v5_hybrid_h14_launch_treatment.ps1",
    "v5_hybrid_h14_mirror.py",
    "v5_hybrid_h14_ordered_rearm.py",
    "v5_hybrid_h14_perf_cal.py",
    "v5_hybrid_h14_perf_cal_audit.py",
    "v5_hybrid_h14_preflight.py",
    "v5_hybrid_h14_protocol_watch.py",
    "v5_hybrid_h14_treatment_launch_watch.py",
    "test_v5_hybrid_h14_control_plane.py",
    "test_v5_hybrid_h14_control_plane_repairs.py",
    "test_v5_hybrid_h14_health_watch.py",
    "test_v5_hybrid_h14_implementation.py",
    "test_v5_hybrid_h14_judge_contract.py",
    "test_v5_hybrid_h14_ordered_rearm.py",
    "test_v5_hybrid_h14_perf_cal.py",
    "test_v5_hybrid_h14_perf_cal_audit.py",
    "test_v5_hybrid_h14_rearm_contract.py",
]


def main() -> int:
    for name in FILES:
        source = DIR / name
        destination = DIR / name.replace("h14", "h15")
        if destination.exists():
            raise SystemExit(f"refusing to overwrite {destination}")
        text = source.read_text(encoding="utf-8")
        text = text.replace("H14", "H15").replace("h14", "h15").replace("20260717", "20260719")
        destination.write_text(text, encoding="utf-8")
    print(f"created {len(FILES)} H15 lifecycle/test files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
