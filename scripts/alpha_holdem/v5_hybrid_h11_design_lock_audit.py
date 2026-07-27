#!/usr/bin/env python3
"""Independent fail-closed H11 design-lock audit."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    value = json.loads(args.design_lock.read_text(encoding="utf-8-sig"))
    checks: dict[str, bool] = {}
    errors: list[str] = []

    def check(name: str, passed: bool) -> None:
        checks[name] = bool(passed)
        if not passed:
            errors.append(name)

    check("hash", sha(args.design_lock) == args.expected_lock_sha256.lower())
    check("identity", value.get("design_id") == "H11" and value.get("status") == "LOCKED")
    source = value.get("source", {})
    check(
        "source",
        source.get("iteration") == 33834
        and source.get("hands") == 556011085
        and Path(source["path"]).is_file()
        and sha(Path(source["path"])) == source["sha256"],
    )
    anchor = value.get("source_anchor", {})
    check(
        "anchor",
        anchor.get("iteration") == 33834
        and anchor.get("hands") == 556011085
        and Path(anchor["path"]).is_file()
        and sha(Path(anchor["path"])) == anchor["sha256"],
    )
    check(
        "single_variable",
        value.get("single_variable")
        == {
            "name": "catchup_value_loss",
            "control": "mse",
            "treatment": "smooth_l1_beta_1.0",
            "common_value_head_catchup": True,
            "common_ppo_target_kl": 0.03,
        },
    )
    check(
        "fresh_arms",
        value.get("arm_budget", {}).get("actual_hands_each") == 20_000_000
        and value["arm_budget"].get("order") == ["control", "treatment"]
        and value["common_config"].get("reset_optimizer") is False,
    )
    check(
        "resource_isolation",
        value.get("resource_isolation", {}).get("evaluation_during_arm") == "FORBIDDEN"
        and value["resource_isolation"].get("evaluation_start") == "AFTER_BOTH_ENDPOINTS_FROZEN_PASS_AND_NO_TRAINER_ACTIVE",
    )
    check(
        "no_observer_active_arm",
        value.get("resource_isolation", {}).get("parent_or_delegated_observer_commands")
        == "FORBIDDEN_WHILE_EITHER_ARM_ACTIVE_INCLUDING_FILE_READ_HASH_PROCESS_LIST",
    )
    check(
        "full_trigger_provenance",
        value.get("resource_isolation", {}).get("full_trigger_provenance")
        == ["pid", "parent_pid", "creation_time", "executable", "command_line", "command_line_sha256"],
    )
    check(
        "either_arm_abort_terminalization",
        value.get("resource_isolation", {}).get("abort_terminalization")
        == "MUST_SUPPORT_CONTROL_OR_TREATMENT_PROTOCOL_ABORT",
    )
    check(
        "gates",
        value.get("gates", {}).get("endpoint_mse_primary_reduction_point_min") == 0.075
        and value["gates"].get("first60_hps_ratio_min") == 0.85
        and value["gates"].get("mirror_ci95_lower_min_bb100") == -20.0,
    )
    check("no_official", value.get("official_hands") == 0 and value.get("strength_claim") == "FORBIDDEN")
    measurement = value.get("measurement", {})
    mirror_manifest = Path(measurement.get("mirror_dir", "")) / "manifest.json"
    mirror_lock = Path(measurement.get("mirror_dir", "")) / "measurement_lock.json"
    check(
        "mirror_measurement_lock",
        measurement.get("mirror_pairs") == 40000
        and mirror_manifest.is_file()
        and sha(mirror_manifest) == measurement.get("mirror_manifest_sha256")
        and mirror_lock.is_file()
        and sha(mirror_lock) == measurement.get("mirror_lock_sha256"),
    )
    for relative, expected in value.get("tools", {}).items():
        path = Path(relative)
        check("tool_" + path.name, path.is_file() and sha(path) == expected)
    for item in value.get("frozen_files", []):
        path = Path(item["path"])
        check("frozen_" + path.name, path.is_file() and sha(path) == item["sha256"])
    result = {
        "schema_version": "v5.hybrid.h11.design_lock_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS_IMMUTABLE_H11_DESIGN_LOCK" if not errors else "FAIL_CLOSED",
        "checks": checks,
        "errors": errors,
        "design_lock_sha256": sha(args.design_lock),
        "official_hands": 0,
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
