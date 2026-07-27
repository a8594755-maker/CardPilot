#!/usr/bin/env python3
"""One-shot mechanical H18 lifecycle scaffold from frozen H17 files."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "scripts/alpha_holdem"
FILES = [
    "v5_hybrid_h17_active_window.py",
    "v5_hybrid_h17_completion_watch.py",
    "v5_hybrid_h17_design_lock_audit.py",
    "v5_hybrid_h17_design_lock_build.py",
    "v5_hybrid_h17_endpoint_watch.py",
    "v5_hybrid_h17_health_watch.py",
    "v5_hybrid_h17_implementation_audit.py",
    "v5_hybrid_h17_judge.py",
    "v5_hybrid_h17_launch_control.ps1",
    "v5_hybrid_h17_launch_treatment.ps1",
    "v5_hybrid_h17_mirror.py",
    "v5_hybrid_h17_ordered_rearm.py",
    "v5_hybrid_h17_perf_cal.py",
    "v5_hybrid_h17_perf_cal_audit.py",
    "v5_hybrid_h17_preflight.py",
    "v5_hybrid_h17_prearm_terminal_audit.py",
    "v5_hybrid_h17_protocol_watch.py",
    "v5_hybrid_h17_treatment_launch_watch.py",
    "v5_h17_control_plane_integration_audit.py",
    "test_v5_hybrid_h17_control_plane.py",
    "test_v5_hybrid_h17_control_plane_repairs.py",
    "test_v5_hybrid_h17_health_watch.py",
    "test_v5_hybrid_h17_implementation.py",
    "test_v5_hybrid_h17_judge_contract.py",
    "test_v5_hybrid_h17_ordered_rearm.py",
    "test_v5_hybrid_h17_perf_cal.py",
    "test_v5_hybrid_h17_perf_cal_audit.py",
    "test_v5_hybrid_h17_rearm_contract.py",
]


def main() -> int:
    created = 0
    for name in FILES:
        source = DIR / name
        destination = DIR / name.replace("h17", "h18")
        if destination.exists():
            raise SystemExit(f"refusing pre-existing H18 scaffold file: {destination}")
        text = source.read_text(encoding="utf-8")
        text = text.replace("H17", "H18").replace("h17", "h18")
        text = text.replace(
            "df256560d69928c9f70e6df5457c1575cc81124ba80f34f9b15261293cefe7fc",
            "8f1f3df1c7fee8c4f8990d5354313330d497f75b1d81de6ceb1f7aa9b4225481",
        )
        destination.write_text(text, encoding="utf-8")
        created += 1
    print(f"created {created} H18 lifecycle/test files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
