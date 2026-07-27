#!/usr/bin/env python3
"""Independent fail-closed audit of immutable H7 preregistration."""
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
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    errors: list[str] = []
    try:
        value = json.loads(args.preregistration.read_text(encoding="utf-8-sig"))
        checks = {
            "hash": sha256(args.preregistration) == args.expected_sha256.lower(),
            "identity": value.get("experiment_id") == "H7" and value.get("status") == "REGISTERED_NO_LAUNCH" and value.get("immutable") is True,
            "route": sha256(Path(value["route_selection"]["path"])) == value["route_selection"]["sha256"] and value["route_selection"]["h6_status"] == "TERMINAL_FAIL_PROTOCOL_ABORT_NO_METHOD_JUDGMENT",
            "source": sha256(Path(value["source"]["path"])) == value["source"]["sha256"] and value["source"]["iteration"] == 31400,
            "fresh_arms": all(value["arms"][arm]["actual_hands"] == 20_000_000 and value["arms"][arm]["maximum_overshoot_hands"] == 50_000 for arm in ("control", "treatment")),
            "single_variable": value["single_variable"]["one_behavior_change"] is True and value["single_variable"]["control"] == "ppo_target_kl=0.0" and value["single_variable"]["treatment"] == "ppo_target_kl=0.03",
            "resource_isolation": value["resource_isolation_contract"]["mirror_or_holdout_evaluation_while_any_arm_trainer_active"] == "FORBIDDEN" and value["resource_isolation_contract"]["endpoint_evaluations_start"] == "ONLY_AFTER_BOTH_ENDPOINTS_FROZEN_PASS",
            "fresh_throughput": value["registered_measurements"]["throughput"]["baseline"] == "fresh H7 control only" and value["registered_measurements"]["throughput"]["first60_ratio_min"] == 0.85,
            "fixed_mirror": value["registered_measurements"]["internal_mirror"]["common_deal_pairs"] == 40_000 and value["registered_measurements"]["internal_mirror"]["adaptive_extension_allowed"] is False,
            "no_adaptive": all(item is False for item in value["no_adaptive_changes"].values()),
            "authority": value["authority"]["launch"].startswith("BLOCKED_UNTIL_") and value["official_hands_authorized"] == 0,
        }
        errors.extend(name for name, passed in checks.items() if not passed)
        result = {
            "schema_version": "v5.hybrid.h7.preregistration_audit.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "PASS_IMMUTABLE_H7_PREREGISTRATION" if not errors else "FAIL_CLOSED",
            "checks": checks,
            "errors": errors,
            "preregistration_sha256": sha256(args.preregistration),
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
            "strength_claim": "FORBIDDEN"
        }
        return_code = 0 if not errors else 2
    except Exception as exc:
        result = {"schema_version": "v5.hybrid.h7.preregistration_audit.v1", "checked_at": datetime.now(timezone.utc).isoformat(), "overall": "FAIL_CLOSED", "errors": errors + [f"{type(exc).__name__}: {exc}"], "behavior_launch_authorized": False, "official_hands_authorized": 0, "strength_claim": "FORBIDDEN"}
        return_code = 2
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
