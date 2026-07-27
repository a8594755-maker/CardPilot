#!/usr/bin/env python3
"""Fail-closed H11 endpoint freezer for fresh contemporaneous arms."""
from __future__ import annotations

import argparse, hashlib, json, os, shutil, time
from datetime import datetime, timezone
from pathlib import Path

import psutil, torch
from v5_assignment_provenance_audit import audit as audit_provenance


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
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
    parser.add_argument("--arm", choices=["control", "treatment"], required=True)
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--status-json", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--endpoint-readiness-timeout-seconds", type=int, default=300)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    lock_path = args.design_lock.resolve()
    lock = load(lock_path)
    status_path = args.status_json.resolve()
    arm = lock.get("arms", {}).get(args.arm, {})
    errors = []
    if not lock_path.is_file() or sha(lock_path) != args.expected_lock_sha256.lower(): errors.append("lock SHA mismatch")
    if lock.get("design_id") != "H11" or lock.get("status") != "LOCKED": errors.append("lock identity/status")
    if not arm or lock.get("arm_budget", {}).get("minimum_endpoint_hands") != 576011085: errors.append("arm/budget incomplete")
    if errors:
        write(status_path, {"overall": "FAIL", "state": "STATIC_CONTRACT_FAILURE", "errors": errors}); return 2
    if args.validate_only:
        write(status_path, {"overall": "PASS", "state": "VALIDATE_ONLY_STATIC_CONTRACT_PASS", "arm": args.arm}); return 0
    run_dir = Path(arm["run_dir"])
    deadline = None
    while True:
        manifest = load(run_dir / "run_manifest.json")
        if not manifest:
            write(status_path, {"overall": "PENDING", "state": "WAITING_FOR_ARM", "arm": args.arm}); time.sleep(max(1, args.poll_seconds)); continue
        config = manifest.get("config", {})
        expected = lock["common_config"]
        errors = []
        for key, value in expected.items():
            if key == "resume": continue
            actual = config.get(key)
            ok = abs(float(actual) - value) <= 1e-12 if isinstance(value, float) and isinstance(actual, (int, float)) else actual == value
            if not ok: errors.append(f"config {key}: actual={actual!r} expected={value!r}")
        target = 0.03
        expected_loss = "mse" if args.arm == "control" else "smooth_l1"
        if manifest.get("run_id") != arm["run_id"]: errors.append("run_id mismatch")
        if config.get("h11_window_arm") != args.arm or abs(float(config.get("ppo_target_kl", -1)) - target) > 1e-12: errors.append("H11 arm identity mismatch")
        if not bool(config.get("h8_value_head_catchup_after_kl_stop")): errors.append("H11 catch-up must be enabled in both arms")
        if config.get("h11_catchup_loss") != expected_loss or float(config.get("h11_catchup_smooth_l1_beta", -1)) != 1.0: errors.append("H11 catch-up loss identity mismatch")
        if not same_path(manifest.get("lineage_parent_checkpoint", ""), lock["source"]["path"]): errors.append("lineage mismatch")
        if errors:
            write(status_path, {"overall": "FAIL", "state": "ARM_IDENTITY_FAILURE", "errors": errors}); return 2
        state = manifest.get("status")
        if state in {"initialized", "running"}:
            pid = int(manifest.get("process_id", -1)); command = ""
            try: command = " ".join(psutil.Process(pid).cmdline())
            except Exception: pass
            if arm["run_id"] not in command or "train_v5.py" not in command:
                write(status_path, {"overall": "FAIL", "state": "PROCESS_IDENTITY_FAILURE", "pid": pid}); return 2
            write(status_path, {"overall": "PENDING", "state": "ARM_RUNNING", "arm": args.arm, "pid": pid, "hands": manifest.get("total_hands")}); time.sleep(max(1, args.poll_seconds)); continue
        if state != "finished":
            write(status_path, {"overall": "FAIL", "state": "UNEXPECTED_STATUS", "manifest_status": state}); return 2
        checkpoint_path = run_dir / "latest.pt"
        if not checkpoint_path.is_file(): write(status_path, {"overall": "FAIL", "state": "ENDPOINT_MISSING"}); return 2
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        hands, iteration = int(checkpoint.get("total_hands", -1)), int(checkpoint.get("iteration", -1))
        low = lock["arm_budget"]["minimum_endpoint_hands"]; high = low + lock["arm_budget"]["maximum_overshoot_hands"]
        errors = []
        if not low <= hands <= high: errors.append("endpoint hands outside locked range")
        if checkpoint.get("h11_window_arm") != args.arm or abs(float(checkpoint.get("ppo_target_kl", -1)) - target) > 1e-12: errors.append("checkpoint H11 arm mismatch")
        if not bool(checkpoint.get("h8_value_head_catchup_after_kl_stop")): errors.append("checkpoint H11 catch-up disabled")
        if checkpoint.get("h11_catchup_loss") != expected_loss or float(checkpoint.get("h11_catchup_smooth_l1_beta", -1)) != 1.0: errors.append("checkpoint H11 loss mismatch")
        if len((checkpoint.get("optimizer") or {}).get("state", {})) != 80: errors.append("checkpoint optimizer state count mismatch")
        checkpoint_config = checkpoint.get("config") or {}
        if checkpoint_config.get("h11_preregistration_sha256") != lock["preregistration"]["sha256"]: errors.append("checkpoint prereg mismatch")
        if checkpoint_config.get("h11_design_lock_sha256") != sha(lock_path): errors.append("checkpoint lock mismatch")
        if errors:
            write(status_path, {"overall": "FAIL", "state": "ENDPOINT_IDENTITY_FAILURE", "errors": errors}); return 2
        readiness = []
        health = load(run_dir / "health_status.json"); latest = health.get("latest", {})
        if health.get("overall") != "PASS" or int(latest.get("iteration", -1)) != iteration or int(latest.get("hands", -1)) != hands: readiness.append("exact endpoint health PASS missing")
        stderr = run_dir / "console.err.log"
        if not stderr.is_file() or stderr.stat().st_size: readiness.append("stderr missing/nonempty")
        try:
            provenance = audit_provenance(Path(arm["provenance_path"]), expected_run_id=arm["run_id"], expected_mode="per-iteration", expected_workers=22, expected_groups=5, expected_worker_seed_base=73000, expected_first_iteration=33835, expected_last_iteration=iteration)
        except Exception as exc: provenance = {"overall": "FAIL", "errors": [str(exc)]}
        write(run_dir / f"h11_{args.arm}_assignment_provenance_audit.json", provenance)
        if provenance.get("overall") != "PASS": readiness.append("provenance audit failed")
        resource = load(run_dir / f"h11_{args.arm}_protocol_status.json")
        if resource.get("resource_isolation_violations") not in ([], None) or resource.get("overall") not in {"PASS", "PENDING"}: readiness.append("resource isolation status invalid")
        if readiness:
            if deadline is None: deadline = time.monotonic() + args.endpoint_readiness_timeout_seconds
            if time.monotonic() < deadline:
                write(status_path, {"overall": "PENDING", "state": "WAITING_FOR_EXACT_ENDPOINT_ARTIFACTS", "errors": readiness}); time.sleep(max(1, args.poll_seconds)); continue
            write(status_path, {"overall": "FAIL", "state": "ENDPOINT_AUDIT_TIMEOUT", "errors": readiness}); return 2
        frozen = run_dir / f"h11_{args.arm}_endpoint.pt"
        if frozen.exists(): write(status_path, {"overall": "FAIL", "state": "FROZEN_ENDPOINT_ALREADY_EXISTS"}); return 2
        shutil.copy2(checkpoint_path, frozen)
        if sha(checkpoint_path) != sha(frozen): frozen.unlink(missing_ok=True); write(status_path, {"overall": "FAIL", "state": "COPY_HASH_FAILURE"}); return 2
        write(status_path, {"schema_version": "v5.hybrid.h11.endpoint_status.v1", "checked_at": datetime.now(timezone.utc).isoformat(), "overall": "PASS", "state": "ARM_ENDPOINT_FROZEN", "arm": args.arm, "run_id": arm["run_id"], "iteration": iteration, "hands": hands, "checkpoint_path": str(frozen.resolve()), "checkpoint_sha256": sha(frozen), "design_lock_sha256": sha(lock_path), "official_hands": 0, "strength_claim": "FORBIDDEN"})
        return 0


if __name__ == "__main__": raise SystemExit(main())
