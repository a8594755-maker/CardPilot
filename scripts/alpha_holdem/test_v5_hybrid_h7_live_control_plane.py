#!/usr/bin/env python3
"""Reporting-only regression checks for the live H7 control plane."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts" / "alpha_holdem"
LOCK = REPO / "reports" / "v5_hybrid_h7_design_lock_20260713.json"
LOCK_SHA = "88aea213e00614191b79496079ea8607aca67a0a7d9c582f47a93af011f325af"
CONTROL_LAUNCHER_SHA = "9d59131ef9b6231f6cab84128db0fbaa50770c2a07cc7347cfb1e0beb3711385"
TREATMENT_LAUNCHER_SHA = "8d3105a8c82f3e79303cb1d128f41a29045626f65a589439820db986d7ff0112"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def run_validate(tool: str, extra: list[str]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        status = Path(tmp) / "status.json"
        command = [
            sys.executable,
            str(SCRIPTS / tool),
            *extra,
            "--design-lock",
            str(LOCK),
            "--expected-lock-sha256",
            LOCK_SHA,
            "--status-json",
            str(status),
            "--validate-only",
        ]
        result = subprocess.run(command, cwd=REPO, text=True, capture_output=True, timeout=90)
        assert result.returncode == 0, (tool, result.stdout, result.stderr)
        value = load(status)
        assert value.get("overall") == "PASS", (tool, value)
        return value


def main() -> int:
    sys.path.insert(0, str(SCRIPTS))
    from v5_hybrid_h7_protocol_watch import effective, rows

    checks: dict[str, bool] = {}
    lock = load(LOCK)
    checks["design_lock_hash"] = sha(LOCK) == LOCK_SHA
    assert checks["design_lock_hash"]

    with tempfile.TemporaryDirectory() as tmp:
        audit = Path(tmp) / "audit.json"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "v5_hybrid_h7_design_lock_audit.py"),
                "--design-lock",
                str(LOCK),
                "--expected-lock-sha256",
                LOCK_SHA,
                "--out",
                str(audit),
            ],
            cwd=REPO,
            text=True,
            capture_output=True,
            timeout=90,
        )
        checks["independent_design_audit"] = result.returncode == 0 and load(audit).get("overall") == "PASS_IMMUTABLE_H7_DESIGN_LOCK"
        assert checks["independent_design_audit"], (result.stdout, result.stderr)

    for arm in ("control", "treatment"):
        value = run_validate("v5_hybrid_h7_endpoint_watch.py", ["--arm", arm])
        checks[f"endpoint_validate_{arm}"] = value.get("state") == "VALIDATE_ONLY_STATIC_CONTRACT_PASS"
        value = run_validate("v5_hybrid_h7_protocol_watch.py", ["--arm", arm])
        checks[f"protocol_validate_{arm}"] = value.get("state") == "VALIDATE_ONLY_STATIC_CONTRACT_PASS"
    completion = run_validate("v5_hybrid_h7_completion_watch.py", ["--repo", str(REPO)])
    checks["completion_validate"] = completion.get("state") == "VALIDATE_ONLY_STATIC_CONTRACT_PASS"
    assert all(checks.values()), checks

    control = lock["arms"]["control"]
    values = rows(Path(control["metrics_path"]))
    protocol = load(Path(control["run_dir"]) / "h7_control_protocol_status.json")
    frozen = protocol.get("first60", {})
    calculated = effective(values, first60=True)
    checks["first60_coverage"] = len(values) >= 61
    checks["first60_status"] = frozen.get("status") == "PASS_CONTROL_BASELINE_FROZEN"
    checks["first60_exact_recompute"] = calculated is not None and abs(calculated - float(frozen["effective_hps"])) <= 1e-9
    checks["resource_isolation_clean"] = protocol.get("resource_isolation_violations") == []

    control_launcher = SCRIPTS / "v5_hybrid_h7_launch_control.ps1"
    treatment_launcher = SCRIPTS / "v5_hybrid_h7_launch_treatment.ps1"
    checks["control_launcher_hash"] = sha(control_launcher) == CONTROL_LAUNCHER_SHA
    checks["treatment_launcher_hash"] = sha(treatment_launcher) == TREATMENT_LAUNCHER_SHA
    checks["control_launcher_lock_binding"] = LOCK_SHA in control_launcher.read_text(encoding="utf-8-sig")
    checks["treatment_launcher_lock_binding"] = LOCK_SHA in treatment_launcher.read_text(encoding="utf-8-sig")
    checks["no_launcher_placeholder"] = "__H7_DESIGN_LOCK_SHA256__" not in control_launcher.read_text(encoding="utf-8-sig") + treatment_launcher.read_text(encoding="utf-8-sig")

    mirror_dir = Path(lock["measurement"]["mirror_dir"])
    permitted = {"manifest.json", "measurement_lock.json"}
    checks["mirror_results_not_started"] = {path.name for path in mirror_dir.iterdir()} <= permitted
    checks["official_hands_zero"] = lock.get("official_hands") == 0
    assert all(checks.values()), {key: value for key, value in checks.items() if not value}

    result = {
        "overall": "PASS_H7_LIVE_CONTROL_PLANE",
        "checks": checks,
        "check_count": len(checks),
        "design_lock_sha256": sha(LOCK),
        "control_rows_seen": len(values),
        "control_first60_effective_hps": calculated,
        "official_hands": 0,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
