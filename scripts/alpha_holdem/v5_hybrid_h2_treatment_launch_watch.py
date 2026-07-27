#!/usr/bin/env python3
"""Duplicate-safe control-to-treatment H2 launch supervisor."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def readiness(endpoint: dict, protocol: dict) -> tuple[str, list[str]]:
    if endpoint.get("overall") == "FAIL" or protocol.get("overall") == "FAIL":
        return "TERMINAL_BLOCKED", ["control endpoint or protocol failed"]
    ready = (
        endpoint.get("overall") == "PASS"
        and endpoint.get("state") == "ARM_ENDPOINT_FROZEN"
        and protocol.get("overall") == "PASS"
        and protocol.get("first60", {}).get("status") == "PASS_CONTROL_BASELINE_FROZEN"
    )
    return ("READY", []) if ready else ("WAITING", [])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--control-dir", required=True)
    p.add_argument("--treatment-dir", required=True)
    p.add_argument("--launcher", required=True)
    p.add_argument("--status-json", required=True)
    p.add_argument("--poll-seconds", type=int, default=30)
    args = p.parse_args()
    control = Path(args.control_dir).resolve()
    treatment = Path(args.treatment_dir).resolve()
    launcher = Path(args.launcher).resolve()
    status = Path(args.status_json).resolve()
    endpoint_path = control / "h2_control_endpoint_status.json"
    protocol_path = control / "h2_control_protocol_status.json"

    if not launcher.is_file():
        write(status, {"overall": "FAIL", "state": "STATIC_LAUNCHER_MISSING"})
        return 2
    while True:
        if treatment.exists():
            manifest = load(treatment / "run_manifest.json")
            if manifest.get("run_id") == "v5_hybrid_h2_treatment_showdownk200_same31400_20m_r1_20260713":
                write(status, {"overall": "PASS", "state": "TREATMENT_ALREADY_LAUNCHED", "run_id": manifest["run_id"]})
                return 0
            write(status, {"overall": "FAIL", "state": "TREATMENT_DIR_IDENTITY_CONFLICT"})
            return 2
        endpoint, protocol = load(endpoint_path), load(protocol_path)
        state, errors = readiness(endpoint, protocol)
        if state == "TERMINAL_BLOCKED":
            write(status, {"overall": "FAIL", "state": state, "errors": errors})
            return 2
        if state == "WAITING":
            write(status, {
                "overall": "PENDING", "state": "WAITING_FOR_CONTROL_ENDPOINT",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "endpoint": endpoint.get("state"), "protocol": protocol.get("state"),
            })
            time.sleep(max(1, args.poll_seconds))
            continue
        write(status, {"overall": "RUNNING", "state": "INVOKING_EXACT_TREATMENT_LAUNCHER"})
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(launcher)],
            cwd=launcher.parents[2], text=True, capture_output=True, check=False,
        )
        payload = {
            "overall": "PASS" if proc.returncode == 0 else "FAIL",
            "state": "TREATMENT_LAUNCHED_REARM_PASS" if proc.returncode == 0 else "TREATMENT_LAUNCH_FAILED",
            "returncode": proc.returncode,
            "stdout": proc.stdout[-8000:], "stderr": proc.stderr[-8000:],
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        write(status, payload)
        return 0 if proc.returncode == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
