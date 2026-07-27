#!/usr/bin/env python3
"""Independent audit for the reporting-only H11 terminal-health recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} root is not an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--health", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, actual: Any = None) -> None:
        checks.append({"name": name, "status": "PASS" if passed else "FAIL", "actual": actual})

    try:
        recovery = load(args.recovery.resolve())
        health = load(args.health.resolve())
        check("classification", recovery.get("classification") == "CENSURE_REPORTING_ONLY_MISSING_EXACT_ENDPOINT_HEALTH_RECOVERED", recovery.get("classification"))
        check("no_behavior_change", recovery.get("behavior_change") is False)
        check("no_checkpoint_change", recovery.get("checkpoint_changed") is False)
        check("no_gate_change", recovery.get("gate_changed") is False)
        check("no_forced_verdict", recovery.get("verdict_forced") is False)
        for label, path_key, hash_key in (
            ("design_lock", "design_lock_path", "design_lock_sha256"),
            ("monitor", "monitor_path", "monitor_sha256"),
        ):
            path = Path(recovery[path_key])
            check(f"{label}_exists", path.is_file(), str(path))
            check(f"{label}_sha", path.is_file() and sha256(path) == recovery[hash_key], recovery.get(hash_key))
        source_paths = {
            "manifest": Path(recovery["preserved_failed_artifacts"][0]["path"]).parent / "run_manifest.json",
            "log": Path(recovery["preserved_failed_artifacts"][0]["path"]).parent / "latest_train.log",
            "checkpoint": Path(recovery["preserved_failed_artifacts"][0]["path"]).parent / "latest.pt",
            "stderr": Path(recovery["preserved_failed_artifacts"][0]["path"]).parent / "console.err.log",
        }
        for label, path in source_paths.items():
            expected = recovery[f"source_{label}_sha256"]
            check(f"source_{label}_sha", path.is_file() and sha256(path) == expected, expected)
        recovery_tool = Path(__file__).with_name("v5_hybrid_h11_terminal_health_recovery.py")
        check("recovery_tool_sha", sha256(recovery_tool) == recovery.get("recovery_tool_sha256"), recovery.get("recovery_tool_sha256"))
        check("published_health_sha", sha256(args.health.resolve()) == recovery.get("published_health_status_sha256"), recovery.get("published_health_status_sha256"))
        latest = health.get("latest") if isinstance(health.get("latest"), dict) else {}
        check("health_overall", health.get("overall") == "PASS", health.get("overall"))
        check("health_iteration", int(latest.get("iteration", -1)) == int(recovery.get("iteration", -2)), latest.get("iteration"))
        check("health_hands", int(latest.get("hands", -1)) == int(recovery.get("hands", -2)), latest.get("hands"))
        health_checks = health.get("checks") if isinstance(health.get("checks"), list) else []
        check("health_checks_present", bool(health_checks), len(health_checks))
        check("all_health_checks_pass", bool(health_checks) and all(row.get("status") == "PASS" for row in health_checks), [row.get("status") for row in health_checks])
        check("health_embeds_recovery", isinstance(health.get("reporting_recovery"), dict) and health["reporting_recovery"].get("source_checkpoint_sha256") == recovery.get("source_checkpoint_sha256"))
        preserved = recovery.get("preserved_failed_artifacts") if isinstance(recovery.get("preserved_failed_artifacts"), list) else []
        check("preserved_artifacts_present", len([row for row in preserved if row.get("present")]) >= 6, len(preserved))
        for index, row in enumerate(preserved):
            if not row.get("present"):
                continue
            snapshot = Path(row["snapshot_path"])
            check(f"preserved_{index}_sha", snapshot.is_file() and sha256(snapshot) == row.get("sha256") == row.get("snapshot_sha256"), row.get("snapshot_path"))
        endpoint_snapshot = next((Path(row["snapshot_path"]) for row in preserved if row.get("present") and Path(row["path"]).name.endswith("endpoint_status.json")), None)
        endpoint_value = load(endpoint_snapshot) if endpoint_snapshot else {}
        check("original_endpoint_failure_preserved", endpoint_value.get("overall") == "FAIL" and endpoint_value.get("state") == "ENDPOINT_AUDIT_TIMEOUT", endpoint_value)
    except Exception as exc:
        checks.append({"name": "audit_exception", "status": "FAIL", "actual": f"{type(exc).__name__}: {exc}"})
    overall = "PASS_H11_TERMINAL_HEALTH_RECOVERY_AUDIT" if checks and all(row["status"] == "PASS" for row in checks) else "FAIL_CLOSED"
    payload = {
        "schema_version": "v5.hybrid.h11.terminal_health_recovery_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "passed": sum(row["status"] == "PASS" for row in checks),
        "total": len(checks),
        "recovery_path": str(args.recovery.resolve()),
        "recovery_sha256": sha256(args.recovery.resolve()) if args.recovery.is_file() else None,
        "checks": checks,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": overall, "passed": payload["passed"], "total": payload["total"]}))
    return 0 if overall.startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
