#!/usr/bin/env python3
"""One-shot mechanical H17 lifecycle scaffold from frozen H16 files."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "scripts/alpha_holdem"
FILES = [
    "v5_hybrid_h16_active_window.py",
    "v5_hybrid_h16_completion_watch.py",
    "v5_hybrid_h16_design_lock_audit.py",
    "v5_hybrid_h16_design_lock_build.py",
    "v5_hybrid_h16_endpoint_watch.py",
    "v5_hybrid_h16_health_watch.py",
    "v5_hybrid_h16_implementation_audit.py",
    "v5_hybrid_h16_judge.py",
    "v5_hybrid_h16_launch_control.ps1",
    "v5_hybrid_h16_launch_treatment.ps1",
    "v5_hybrid_h16_mirror.py",
    "v5_hybrid_h16_ordered_rearm.py",
    "v5_hybrid_h16_perf_cal.py",
    "v5_hybrid_h16_perf_cal_audit.py",
    "v5_hybrid_h16_preflight.py",
    "v5_hybrid_h16_prearm_terminal_audit.py",
    "v5_hybrid_h16_protocol_watch.py",
    "v5_hybrid_h16_treatment_launch_watch.py",
    "v5_h16_control_plane_integration_audit.py",
    "test_v5_hybrid_h16_control_plane.py",
    "test_v5_hybrid_h16_control_plane_repairs.py",
    "test_v5_hybrid_h16_health_watch.py",
    "test_v5_hybrid_h16_implementation.py",
    "test_v5_hybrid_h16_judge_contract.py",
    "test_v5_hybrid_h16_ordered_rearm.py",
    "test_v5_hybrid_h16_perf_cal.py",
    "test_v5_hybrid_h16_perf_cal_audit.py",
    "test_v5_hybrid_h16_rearm_contract.py",
]


def main() -> int:
    for name in FILES:
        source = DIR / name
        destination = DIR / name.replace("h16", "h17")
        if destination.exists():
            continue
        text = source.read_text(encoding="utf-8")
        text = text.replace("H16", "H17").replace("h16", "h17")
        text = text.replace(
            "51065761b6b291ef757ea467611203cbe79d45a5e4d54c163edaf79ef8fa1bb0",
            "df256560d69928c9f70e6df5457c1575cc81124ba80f34f9b15261293cefe7fc",
        )
        destination.write_text(text, encoding="utf-8")
    print(f"created {len(FILES)} H17 lifecycle/test files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
