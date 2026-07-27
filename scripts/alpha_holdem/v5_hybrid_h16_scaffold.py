#!/usr/bin/env python3
"""One-shot mechanical H16 lifecycle scaffold from frozen H15 files."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "scripts/alpha_holdem"
FILES = [
    "v5_hybrid_h15_active_window.py",
    "v5_hybrid_h15_completion_watch.py",
    "v5_hybrid_h15_design_lock_audit.py",
    "v5_hybrid_h15_design_lock_build.py",
    "v5_hybrid_h15_endpoint_watch.py",
    "v5_hybrid_h15_health_watch.py",
    "v5_hybrid_h15_implementation_audit.py",
    "v5_hybrid_h15_judge.py",
    "v5_hybrid_h15_launch_control.ps1",
    "v5_hybrid_h15_launch_treatment.ps1",
    "v5_hybrid_h15_mirror.py",
    "v5_hybrid_h15_ordered_rearm.py",
    "v5_hybrid_h15_perf_cal.py",
    "v5_hybrid_h15_perf_cal_audit.py",
    "v5_hybrid_h15_preflight.py",
    "v5_hybrid_h15_protocol_watch.py",
    "v5_hybrid_h15_treatment_launch_watch.py",
    "test_v5_hybrid_h15_control_plane.py",
    "test_v5_hybrid_h15_control_plane_repairs.py",
    "test_v5_hybrid_h15_health_watch.py",
    "test_v5_hybrid_h15_implementation.py",
    "test_v5_hybrid_h15_judge_contract.py",
    "test_v5_hybrid_h15_ordered_rearm.py",
    "test_v5_hybrid_h15_perf_cal.py",
    "test_v5_hybrid_h15_perf_cal_audit.py",
    "test_v5_hybrid_h15_rearm_contract.py",
]


def main() -> int:
    for name in FILES:
        source = DIR / name
        destination = DIR / name.replace("h15", "h16")
        if destination.exists():
            raise SystemExit(f"refusing to overwrite {destination}")
        text = source.read_text(encoding="utf-8")
        text = text.replace("H15", "H16").replace("h15", "h16")
        text = text.replace(
            "5631c27c29f1379ea16c5b246dccc312e830a2e50d5335dfac531798c882582c",
            "51065761b6b291ef757ea467611203cbe79d45a5e4d54c163edaf79ef8fa1bb0",
        )
        text = text.replace("design_lock_v3_20260719", "design_lock_v1_20260719")
        text = text.replace("preflight_v3_20260719", "preflight_v1_20260719")
        destination.write_text(text, encoding="utf-8")
    print(f"created {len(FILES)} H16 lifecycle/test files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
