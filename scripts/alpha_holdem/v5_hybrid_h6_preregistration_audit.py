#!/usr/bin/env python3
"""Independent fail-closed audit of the immutable H6 preregistration."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--preregistration", required=True)
    p.add_argument("--expected-sha256", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    path, out = Path(a.preregistration).resolve(), Path(a.out).resolve()
    errors: list[str] = []
    try:
        if sha(path) != a.expected_sha256.lower():
            errors.append("preregistration SHA mismatch")
        x = load(path)
        checks = {
            "identity": x.get("experiment_id") == "H6" and x.get("status") == "REGISTERED_NO_LAUNCH" and x.get("immutable") is True,
            "single_variable": x.get("single_variable", {}).get("one_behavior_change") is True and x["single_variable"].get("treatment") == "ppo_target_kl=0.03",
            "source": sha(Path(x["source"]["path"])) == x["source"]["sha256"] and int(x["source"]["iteration"]) == 31400,
            "control_frozen": sha(Path(x["arms"]["control"]["checkpoint_path"])) == x["arms"]["control"]["checkpoint_sha256"],
            "fixed_window": int(x["arms"]["treatment"]["actual_hands"]) == 20000000 and int(x["arms"]["treatment"]["maximum_overshoot_hands"]) == 50000,
            "kl_contract": x["implementation_contract"]["threshold_comparison"] == "strict greater-than" and x["registered_measurements"]["kl_stability"]["threshold"] == 0.03,
            "gates": x["registered_measurements"]["throughput"]["first60_ratio_min"] == 0.85 and x["registered_measurements"]["internal_mirror"]["common_deal_pairs"] == 40000,
            "no_adaptive": all(value is False for value in x["no_adaptive_changes"].values()),
            "route": sha(Path(x["route_selection"]["path"])) == x["route_selection"]["sha256"],
            "roadmap": sha(Path(x["roadmap"]["path"])) == x["roadmap"]["sha256"],
            "authority": x["authority"]["launch"].startswith("BLOCKED_UNTIL_") and x["official_hands_authorized"] == 0,
            "no_bundle": len(x["implementation_contract"]["forbidden_bundles"]) >= 5,
        }
        errors.extend(name for name, ok in checks.items() if not ok)
        payload = {
            "schema_version": "v5.hybrid.h6.preregistration_audit.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "PASS_IMMUTABLE_H6_PREREGISTRATION" if not errors else "FAIL_CLOSED",
            "checks": checks,
            "errors": errors,
            "preregistration_sha256": sha(path),
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
            "strength_claim": "FORBIDDEN",
        }
        rc = 0 if not errors else 2
    except Exception as exc:
        payload = {
            "schema_version": "v5.hybrid.h6.preregistration_audit.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "FAIL_CLOSED",
            "errors": errors + [f"{type(exc).__name__}: {exc}"],
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
            "strength_claim": "FORBIDDEN",
        }
        rc = 2
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
