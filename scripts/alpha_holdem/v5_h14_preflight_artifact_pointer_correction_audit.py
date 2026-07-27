#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "reports/v5_h14_preflight_artifact_pointer_correction_20260717.json"
OUT = ROOT / "reports/v5_h14_preflight_artifact_pointer_correction_audit_20260717.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    value = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    checks = {
        "schema": value.get("schema_version") == "v5.hybrid.h14.preflight_artifact_pointer_correction.v1",
        "classification": value.get("overall") == "PASS_PRELAUNCH_CONTROL_PLANE_CORRECTION_REQUIRES_SUPERSEDING_LOCK",
        "old_lock_preserved": sha(ROOT / "reports/v5_hybrid_h14_design_lock_v5_20260717.json") == value.get("superseded_lock_v5_sha256"),
        "old_lock_audit_preserved": sha(ROOT / "reports/v5_hybrid_h14_design_lock_audit_v5_20260717.json") == value.get("superseded_lock_v5_audit_sha256"),
        "failed_preflight_preserved": sha(ROOT / "reports/v5_hybrid_h14_preflight_20260717.json") == value.get("failed_preflight_sha256"),
        "launcher_new_hash": sha(ROOT / "scripts/alpha_holdem/v5_hybrid_h14_launch_control.ps1") == value.get("new_control_launcher_sha256"),
        "treatment_new_hash": sha(ROOT / "scripts/alpha_holdem/v5_hybrid_h14_launch_treatment.ps1") == value.get("new_treatment_launcher_sha256"),
        "rearm_new_hash": sha(ROOT / "scripts/alpha_holdem/v5_rearm_watchers.ps1") == value.get("new_rearm_sha256"),
        "builder_new_hash": sha(ROOT / "scripts/alpha_holdem/v5_hybrid_h14_design_lock_build.py") == value.get("new_builder_sha256"),
        "new_pointer": "v5_hybrid_h14_preflight_v6_20260717.json" in (ROOT / "scripts/alpha_holdem/v5_hybrid_h14_launch_control.ps1").read_text(encoding="utf-8-sig"),
        "v6_lock_pointer": all(
            "v5_hybrid_h14_design_lock_v6_20260717.json" in (ROOT / path).read_text(encoding="utf-8-sig")
            for path in (
                "scripts/alpha_holdem/v5_hybrid_h14_launch_control.ps1",
                "scripts/alpha_holdem/v5_hybrid_h14_launch_treatment.ps1",
                "scripts/alpha_holdem/v5_rearm_watchers.ps1",
            )
        ),
        "scope": value.get("scope") == "PRELAUNCH_CONTROL_PLANE_ONLY" and value.get("trainer_or_scientific_behavior") == "UNCHANGED",
        "no_trainer": value.get("trainer_launched") is False and value.get("official_hands") == 0,
        "fail_closed": value.get("launch_authority") == "NONE_UNTIL_V6_LOCK_AUDIT_FULL_TESTS_AND_V6_PREFLIGHT_PASS",
    }
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": "v5.hybrid.h14.preflight_artifact_pointer_correction_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "artifact_sha256": sha(ARTIFACT),
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "official_hands": 0,
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
