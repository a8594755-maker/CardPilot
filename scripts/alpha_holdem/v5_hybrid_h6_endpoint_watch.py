#!/usr/bin/env python3
"""Fail-closed H6 treatment endpoint freezer. Launches no training/evaluation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import torch

from v5_assignment_provenance_audit import audit as audit_provenance


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def same_path(left: object, right: object) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--status-json", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--endpoint-readiness-timeout-seconds", type=int, default=300)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    lock_path = args.design_lock.resolve()
    status_path = args.status_json.resolve()
    lock = load(lock_path)
    treatment = lock.get("arms", {}).get("treatment", {})
    errors: list[str] = []
    if not lock_path.is_file() or sha256(lock_path) != args.expected_lock_sha256.lower():
        errors.append("lock SHA mismatch")
    if lock.get("design_id") != "H6" or lock.get("status") != "LOCKED":
        errors.append("lock identity/status")
    if not treatment or int(lock.get("arm_budget", {}).get("minimum_endpoint_hands", -1)) != 535989661:
        errors.append("treatment/budget incomplete")
    if errors:
        write(status_path, {"overall": "FAIL", "state": "STATIC_CONTRACT_FAILURE", "errors": errors})
        return 2
    if args.validate_only:
        write(status_path, {"overall": "PASS", "state": "VALIDATE_ONLY_STATIC_CONTRACT_PASS", "arm": "treatment"})
        return 0

    run_dir = Path(treatment["run_dir"])
    deadline: float | None = None
    while True:
        manifest = load(run_dir / "run_manifest.json")
        if not manifest:
            write(status_path, {"overall": "PENDING", "state": "WAITING_FOR_TREATMENT"})
            time.sleep(max(1, args.poll_seconds))
            continue
        config = manifest.get("config", {})
        expected = lock["common_config"]
        errors = []
        for key, value in expected.items():
            if key == "resume":
                continue
            actual = config.get(key)
            ok = abs(float(actual) - value) <= 1e-12 if isinstance(value, float) and isinstance(actual, (int, float)) else actual == value
            if not ok:
                errors.append(f"config {key}: actual={actual!r} expected={value!r}")
        if manifest.get("run_id") != treatment["run_id"]:
            errors.append("run_id mismatch")
        if config.get("h6_window_arm") != "treatment" or abs(float(config.get("ppo_target_kl", -1)) - 0.03) > 1e-12:
            errors.append("H6 treatment identity mismatch")
        if not same_path(manifest.get("lineage_parent_checkpoint", ""), lock["source"]["path"]):
            errors.append("lineage mismatch")
        if errors:
            write(status_path, {"overall": "FAIL", "state": "ARM_IDENTITY_FAILURE", "errors": errors})
            return 2

        state = manifest.get("status")
        if state in {"initialized", "running"}:
            pid = int(manifest.get("process_id", -1))
            command = ""
            try:
                command = " ".join(psutil.Process(pid).cmdline())
            except Exception:
                pass
            if treatment["run_id"] not in command or "train_v5.py" not in command:
                write(status_path, {"overall": "FAIL", "state": "PROCESS_IDENTITY_FAILURE", "pid": pid})
                return 2
            write(status_path, {"overall": "PENDING", "state": "TREATMENT_RUNNING", "pid": pid, "hands": manifest.get("total_hands")})
            time.sleep(max(1, args.poll_seconds))
            continue
        if state != "finished":
            write(status_path, {"overall": "FAIL", "state": "UNEXPECTED_STATUS", "manifest_status": state})
            return 2

        checkpoint_path = run_dir / "latest.pt"
        if not checkpoint_path.is_file():
            write(status_path, {"overall": "FAIL", "state": "ENDPOINT_MISSING"})
            return 2
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        hands = int(checkpoint.get("total_hands", -1))
        iteration = int(checkpoint.get("iteration", -1))
        low = int(lock["arm_budget"]["minimum_endpoint_hands"])
        high = low + int(lock["arm_budget"]["maximum_overshoot_hands"])
        errors = []
        if not low <= hands <= high:
            errors.append("endpoint hands outside locked range")
        if checkpoint.get("h6_window_arm") != "treatment" or abs(float(checkpoint.get("ppo_target_kl", -1)) - 0.03) > 1e-12:
            errors.append("checkpoint H6 treatment contract mismatch")
        checkpoint_config = checkpoint.get("config") or {}
        if checkpoint_config.get("h6_preregistration_sha256") != lock["preregistration"]["sha256"]:
            errors.append("checkpoint preregistration mismatch")
        if checkpoint_config.get("h6_design_lock_sha256") != sha256(lock_path):
            errors.append("checkpoint design-lock mismatch")
        if errors:
            write(status_path, {"overall": "FAIL", "state": "ENDPOINT_IDENTITY_FAILURE", "errors": errors})
            return 2

        readiness: list[str] = []
        health = load(run_dir / "health_status.json")
        latest = health.get("latest", {})
        if health.get("overall") != "PASS" or int(latest.get("iteration", -1)) != iteration or int(latest.get("hands", -1)) != hands:
            readiness.append("exact endpoint health PASS missing")
        stderr = run_dir / "console.err.log"
        if not stderr.is_file() or stderr.stat().st_size:
            readiness.append("stderr missing/nonempty")
        try:
            provenance = audit_provenance(
                Path(treatment["provenance_path"]),
                expected_run_id=treatment["run_id"],
                expected_mode="per-iteration",
                expected_workers=22,
                expected_groups=5,
                expected_worker_seed_base=73000,
                expected_first_iteration=31401,
                expected_last_iteration=iteration,
            )
        except Exception as exc:
            provenance = {"overall": "FAIL", "errors": [str(exc)]}
        write(run_dir / "h6_treatment_assignment_provenance_audit.json", provenance)
        if provenance.get("overall") != "PASS":
            readiness.append("provenance audit failed")
        if readiness:
            if deadline is None:
                deadline = time.monotonic() + args.endpoint_readiness_timeout_seconds
            if time.monotonic() < deadline:
                write(status_path, {"overall": "PENDING", "state": "WAITING_FOR_EXACT_ENDPOINT_ARTIFACTS", "errors": readiness})
                time.sleep(max(1, args.poll_seconds))
                continue
            write(status_path, {"overall": "FAIL", "state": "ENDPOINT_AUDIT_TIMEOUT", "errors": readiness})
            return 2

        frozen = run_dir / "h6_treatment_endpoint.pt"
        if frozen.exists():
            write(status_path, {"overall": "FAIL", "state": "FROZEN_ENDPOINT_ALREADY_EXISTS"})
            return 2
        shutil.copy2(checkpoint_path, frozen)
        if sha256(checkpoint_path) != sha256(frozen):
            frozen.unlink(missing_ok=True)
            write(status_path, {"overall": "FAIL", "state": "COPY_HASH_FAILURE"})
            return 2
        write(status_path, {
            "schema_version": "v5.hybrid.h6.endpoint_status.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "PASS",
            "state": "ARM_ENDPOINT_FROZEN",
            "arm": "treatment",
            "run_id": treatment["run_id"],
            "iteration": iteration,
            "hands": hands,
            "checkpoint_path": str(frozen.resolve()),
            "checkpoint_sha256": sha256(frozen),
            "design_lock_sha256": sha256(lock_path),
            "official_hands": 0,
            "strength_claim": "FORBIDDEN",
        })
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
