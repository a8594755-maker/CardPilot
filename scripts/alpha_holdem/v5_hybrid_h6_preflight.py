#!/usr/bin/env python3
"""Fail-closed H6 launch preflight. Performs no launch or behavior change."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import psutil
import torch


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    lock_path = args.design_lock.resolve()
    lock = load(lock_path)
    checks: dict[str, bool] = {}
    errors: list[str] = []

    def check(name: str, condition: bool, message: str) -> None:
        checks[name] = bool(condition)
        if not condition:
            errors.append(message)

    check("lock_hash", sha256(lock_path) == args.expected_lock_sha256.lower(), "lock hash mismatch")
    check("lock_status", lock.get("design_id") == "H6" and lock.get("status") == "LOCKED", "lock identity/status")
    source = Path(lock["source"]["path"])
    check("source_hash", source.is_file() and sha256(source) == lock["source"]["sha256"], "source hash mismatch")
    source_checkpoint = torch.load(source, map_location="cpu", weights_only=False) if source.is_file() else {}
    check("source_identity", int(source_checkpoint.get("iteration", -1)) == 31400 and int(source_checkpoint.get("total_hands", -1)) == 515989661, "source iter/hands mismatch")
    for relative, expected in lock.get("tools", {}).items():
        path = Path(relative)
        check("tool_" + path.name, path.is_file() and sha256(path) == expected, "tool mismatch " + relative)
    for item in lock.get("frozen_files", []):
        path = Path(item["path"])
        check("frozen_" + path.name, path.is_file() and sha256(path) == item["sha256"], "frozen artifact mismatch " + str(path))
    prereg = Path(lock["preregistration"]["path"])
    prereg_audit = Path(lock["preregistration"]["audit_path"])
    prereg_audit_value = load(prereg_audit) if prereg_audit.is_file() else {}
    check("prereg_hash", prereg.is_file() and sha256(prereg) == lock["preregistration"]["sha256"], "prereg mismatch")
    check("prereg_audit", prereg_audit.is_file() and sha256(prereg_audit) == lock["preregistration"]["audit_sha256"] and str(prereg_audit_value.get("overall", "")).startswith("PASS"), "prereg audit mismatch")
    implementation = Path(lock["implementation_audit"]["path"])
    implementation_value = load(implementation) if implementation.is_file() else {}
    check("implementation_audit", implementation.is_file() and sha256(implementation) == lock["implementation_audit"]["sha256"] and str(implementation_value.get("overall", "")).startswith("PASS"), "implementation audit mismatch")
    control = Path(lock["arms"]["control"]["checkpoint_path"])
    check("control_endpoint", control.is_file() and sha256(control) == lock["arms"]["control"]["checkpoint_sha256"], "control endpoint mismatch")
    treatment_dir = Path(lock["arms"]["treatment"]["run_dir"])
    check("treatment_dir_absent", not treatment_dir.exists(), "treatment run dir already exists")
    trainers = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
            if "train_v5.py" in command and "v5_hybrid_h6_" in command:
                trainers.append({"pid": process.pid, "command": command})
        except Exception:
            pass
    check("no_h6_trainer", not trainers, "H6 trainer already running")

    for tool_name, status_name in (
        ("v5_hybrid_h6_endpoint_watch.py", "endpoint.json"),
        ("v5_hybrid_h6_protocol_watch.py", "protocol.json"),
        ("v5_hybrid_h6_completion_watch.py", "completion.json"),
    ):
        with tempfile.TemporaryDirectory() as temporary:
            status_path = Path(temporary) / status_name
            command = [sys.executable, str(Path("scripts/alpha_holdem") / tool_name), "--design-lock", str(lock_path), "--expected-lock-sha256", sha256(lock_path), "--status-json", str(status_path), "--validate-only"]
            if tool_name == "v5_hybrid_h6_completion_watch.py":
                command[2:2] = ["--repo", str(Path.cwd())]
            completed = subprocess.run(command, text=True, capture_output=True, timeout=90)
            value = load(status_path) if status_path.is_file() else {}
            check("watcher_validate_" + tool_name, completed.returncode == 0 and value.get("overall") == "PASS", f"watcher validate failed {tool_name}: {completed.stderr}")

    result = {
        "schema_version": "v5.hybrid.h6.preflight.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS_READY_TREATMENT_LAUNCH" if not errors else "FAIL_CLOSED",
        "checks": checks,
        "errors": errors,
        "active_h6_trainers": trainers,
        "design_lock_sha256": sha256(lock_path),
        "source_sha256": sha256(source) if source.is_file() else None,
        "official_hands_authorized": 0,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
