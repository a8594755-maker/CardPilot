#!/usr/bin/env python3
"""Independent fail-closed audit for the immutable H6 design lock."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads(args.design_lock.read_text(encoding="utf-8-sig"))
    checks: dict[str, bool] = {}
    errors: list[str] = []

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)
        if not condition:
            errors.append(name)

    check("lock_hash", sha256(args.design_lock) == args.expected_lock_sha256.lower())
    check("identity", lock.get("schema_version") == "v5.hybrid.h6.design_lock.v1" and lock.get("design_id") == "H6" and lock.get("status") == "LOCKED")
    check("source", lock.get("source", {}).get("iteration") == 31400 and lock.get("source", {}).get("hands") == 515989661 and Path(lock["source"]["path"]).is_file() and sha256(Path(lock["source"]["path"])) == lock["source"]["sha256"])
    check("single_variable", lock.get("single_variable") == {"name": "ppo_epoch_mean_kl_early_stop_threshold", "control": 0.0, "treatment": 0.03})
    check("budget", lock.get("arm_budget", {}).get("actual_hands") == 20_000_000 and lock.get("arm_budget", {}).get("minimum_endpoint_hands") == 535_989_661 and lock.get("arm_budget", {}).get("maximum_overshoot_hands") == 50_000)
    check("control_frozen", lock.get("arms", {}).get("control", {}).get("checkpoint_sha256") == "f35558536365006afee9b1311352d465144dfed715a1028362def333147d3d3b")
    check("treatment_identity", lock.get("arms", {}).get("treatment", {}).get("run_id") == "v5_hybrid_h6_treatment_kles003_same31400_20m_r1_20260713" and lock.get("arms", {}).get("treatment", {}).get("ppo_target_kl") == 0.03)
    gates = lock.get("gates", {})
    check("registered_gates", gates.get("kl_p95_max") == 0.03 and gates.get("kl_fraction_above_max") == 0.06044407894736842 and gates.get("early_stop_trigger_fraction_min") == 0.05 and gates.get("first60_hps_ratio_min") == 0.85 and gates.get("full_hps_ratio_min") == 0.85 and gates.get("mirror_ci95_lower_min_bb100") == -20.0)
    check("no_official", lock.get("official_hands") == 0 and lock.get("strength_claim") == "FORBIDDEN")
    prereg = lock.get("preregistration", {})
    check("preregistration", Path(prereg.get("path", "")).is_file() and sha256(Path(prereg["path"])) == prereg.get("sha256") and prereg.get("sha256") == "6b8ba0e4b396d74e1daf15bc9cb93a1018b671ec064f2ad591957c897ea46225")
    for relative, expected in lock.get("tools", {}).items():
        path = Path(relative)
        check("tool_" + path.name, path.is_file() and sha256(path) == expected)
    for item in lock.get("frozen_files", []):
        path = Path(item["path"])
        check("frozen_" + path.name, path.is_file() and sha256(path) == item["sha256"])
    result = {
        "schema_version": "v5.hybrid.h6.design_lock_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS_IMMUTABLE_H6_DESIGN_LOCK" if not errors else "FAIL_CLOSED",
        "checks": checks,
        "errors": errors,
        "design_lock_sha256": sha256(args.design_lock),
        "official_hands": 0,
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
