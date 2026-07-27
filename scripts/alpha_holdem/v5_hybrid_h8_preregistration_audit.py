#!/usr/bin/env python3
"""Independent fail-closed audit of the immutable H8 preregistration."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    checks: dict[str, bool] = {}
    errors: list[str] = []

    def check(name: str, passed: bool) -> None:
        checks[name] = bool(passed)
        if not passed:
            errors.append(name)

    try:
        value = json.loads(args.preregistration.read_text(encoding="utf-8-sig"))
        check("hash", sha256(args.preregistration) == args.expected_sha256.lower())
        check(
            "identity",
            value.get("experiment_id") == "H8"
            and value.get("status") == "REGISTERED_NO_LAUNCH"
            and value.get("immutable") is True,
        )
        route = value["route_selection"]
        check(
            "route",
            sha256(Path(route["path"])) == route["sha256"]
            and route["selected_next"] == "H8_VALUE_HEAD_ONLY_CATCHUP_AFTER_KL_STOP"
            and route["route_exhausted"] is False,
        )
        source = value["source"]
        check(
            "source",
            sha256(Path(source["path"])) == source["sha256"]
            and source["iteration"] == 32617
            and source["hands"] == 536001286
            and source["optimizer_preserved"] is True,
        )
        arms = value["arms"]
        check(
            "fresh_fixed_arms",
            all(
                arms[arm]["actual_hands"] == 20_000_000
                and arms[arm]["target_endpoint_hands"] == source["hands"] + 20_000_000
                and arms[arm]["maximum_overshoot_hands"] == 50_000
                and arms[arm]["ppo_target_kl"] == 0.03
                for arm in ("control", "treatment")
            ),
        )
        variable = value["single_variable"]
        check(
            "single_variable",
            variable["one_behavior_change"] is True
            and variable["control"] is False
            and variable["treatment"] is True
            and variable["common_ppo_target_kl"] == 0.03,
        )
        catchup = value["catchup_contract"]
        check(
            "catchup_contract",
            catchup["trainable_parameters"] == "model.value_head parameters only"
            and "parameters with grad None must retain state bitwise" in catchup["optimizer"]
            and "consumes no global RNG" in catchup["minibatch_order"]
            and len(catchup["logging_required"]) == 5,
        )
        resource = value["resource_isolation_contract"]
        check(
            "resource_isolation",
            resource["arm_order"] == ["control", "treatment"]
            and resource["mirror_or_holdout_evaluation_while_any_arm_trainer_active"] == "FORBIDDEN"
            and resource["endpoint_evaluations_start"] == "ONLY_AFTER_BOTH_ENDPOINTS_FROZEN_PASS",
        )
        measurements = value["registered_measurements"]
        check(
            "fixed_measurements",
            measurements["endpoint_critic_mse_primary"]["bootstrap_repetitions"] == 10_000
            and measurements["endpoint_critic_mse_primary"]["reduction_point_min"] == 0.075
            and measurements["internal_mirror"]["common_deal_pairs"] == 40_000
            and measurements["internal_mirror"]["adaptive_extension_allowed"] is False
            and measurements["throughput"]["first60_ratio_min"] == 0.85,
        )
        check("no_adaptive_changes", all(item is False for item in value["no_adaptive_changes"].values()))
        check(
            "authority",
            value["authority"]["launch"].startswith("BLOCKED_UNTIL_")
            and value["official_hands_authorized"] == 0
            and value["strength_claim"] == "FORBIDDEN",
        )
        result = {
            "schema_version": "v5.hybrid.h8.preregistration_audit.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "PASS_IMMUTABLE_H8_PREREGISTRATION" if not errors else "FAIL_CLOSED",
            "checks": checks,
            "errors": errors,
            "preregistration_sha256": sha256(args.preregistration),
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
            "strength_claim": "FORBIDDEN",
        }
        return_code = 0 if not errors else 2
    except Exception as exc:
        result = {
            "schema_version": "v5.hybrid.h8.preregistration_audit.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "FAIL_CLOSED",
            "checks": checks,
            "errors": errors + [f"{type(exc).__name__}: {exc}"],
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
            "strength_claim": "FORBIDDEN",
        }
        return_code = 2
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
