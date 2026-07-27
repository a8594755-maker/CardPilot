#!/usr/bin/env python3
"""Fail-closed H9 control launch preflight."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import psutil
import torch


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def is_path1_worker_command(command: str) -> bool:
    """Count solver workers, not console-host children owned by the coordinator."""
    normalized = command.replace("\\", "/").lower()
    return "node" in normalized and "cfr-solver/src/orchestration/solve-worker.ts" in normalized


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    lock = load(args.design_lock)
    checks: dict[str, bool] = {}
    errors: list[str] = []

    def check(name: str, passed: bool, message: str) -> None:
        checks[name] = bool(passed)
        if not passed:
            errors.append(message)

    check("lock_hash", sha(args.design_lock) == args.expected_lock_sha256.lower(), "lock hash")
    check("identity", lock.get("design_id") == "H9" and lock.get("status") == "LOCKED", "lock identity")
    source = Path(lock["source"]["path"])
    check("source_hash", source.is_file() and sha(source) == lock["source"]["sha256"], "source hash")
    checkpoint = torch.load(source, map_location="cpu", weights_only=False) if source.is_file() else {}
    check(
        "source_identity",
        int(checkpoint.get("iteration", -1)) == 33834
        and int(checkpoint.get("total_hands", -1)) == 556011085
        and checkpoint.get("h8_window_arm") == "treatment"
        and abs(float(checkpoint.get("ppo_target_kl", -1)) - 0.03) <= 1e-12
        and len((checkpoint.get("optimizer") or {}).get("state", {})) == 80,
        "source identity/optimizer",
    )
    anchor = Path(lock["source_anchor"]["path"])
    check("anchor_hash", anchor.is_file() and sha(anchor) == lock["source_anchor"]["sha256"], "anchor hash")
    for relative, expected in lock.get("tools", {}).items():
        path = Path(relative)
        check("tool_" + path.name, path.is_file() and sha(path) == expected, "tool " + relative)
    for item in lock.get("frozen_files", []):
        path = Path(item["path"])
        check("frozen_" + path.name, path.is_file() and sha(path) == item["sha256"], "frozen " + str(path))
    for arm in ("control", "treatment"):
        check(
            "run_dir_absent_" + arm,
            not Path(lock["arms"][arm]["run_dir"]).exists(),
            arm + " dir exists",
        )
    active = []
    forbidden = []
    path1 = []
    for process in psutil.process_iter(["pid", "cmdline", "nice"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
            if "train_v5.py" in command and "v5_hybrid_h9_" in command:
                active.append(process.pid)
            if "v5_hybrid_h9_mirror.py" in command or "slumbot" in command.lower():
                forbidden.append({"pid": process.pid, "token": "h9_mirror_or_slumbot"})
            if "solve-v3-parallel" in command and "pipeline_v3_hu_srp_200bb" in command:
                children = process.children(recursive=False)
                worker_children = []
                ignored_children = []
                for child in children:
                    try:
                        child_command = " ".join(child.cmdline())
                    except Exception:
                        child_command = ""
                    if is_path1_worker_command(child_command):
                        worker_children.append(child.pid)
                    else:
                        ignored_children.append({"pid": child.pid, "command": child_command})
                path1.append(
                    {
                        "pid": process.pid,
                        "children": len(worker_children),
                        "worker_pids": worker_children,
                        "all_direct_children": len(children),
                        "ignored_nonworker_children": ignored_children,
                        "nice": str(process.info.get("nice")),
                    }
                )
        except Exception:
            pass
    check("no_h9_trainer", not active, "H9 trainer")
    check("no_forbidden_evaluator", not forbidden, "forbidden evaluator")
    check(
        "path1_existing_six_worker_job",
        len(path1) == 1 and path1[0]["children"] == 6,
        "Path-1 existing six-worker job",
    )
    temporary_root = Path.cwd() / ".test_tmp" / "h9_preflight"
    temporary_root.mkdir(parents=True, exist_ok=True)
    for index, (tool, extra) in enumerate((
        ("v5_hybrid_h9_endpoint_watch.py", ["--arm", "control"]),
        ("v5_hybrid_h9_endpoint_watch.py", ["--arm", "treatment"]),
        ("v5_hybrid_h9_protocol_watch.py", ["--arm", "control"]),
        ("v5_hybrid_h9_protocol_watch.py", ["--arm", "treatment"]),
        ("v5_hybrid_h9_completion_watch.py", ["--repo", str(Path.cwd())]),
    )):
        status = temporary_root / f"validate_{index}.json"
        command = [
            sys.executable,
            str(Path("scripts/alpha_holdem") / tool),
            *extra,
            "--design-lock",
            str(args.design_lock.resolve()),
            "--expected-lock-sha256",
            sha(args.design_lock),
            "--status-json",
            str(status),
            "--validate-only",
        ]
        completed = subprocess.run(command, text=True, capture_output=True, timeout=90)
        value = load(status) if status.is_file() else {}
        check(
            "validate_" + tool + "_" + "_".join(extra),
            completed.returncode == 0 and value.get("overall") == "PASS",
            "validate " + tool,
        )
    result = {
        "schema_version": "v5.hybrid.h9.preflight.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS_READY_H9_CONTROL_LAUNCH" if not errors else "FAIL_CLOSED",
        "checks": checks,
        "errors": errors,
        "active_h9_trainers": active,
        "forbidden_evaluators": forbidden,
        "path1_existing_job": path1,
        "design_lock_sha256": sha(args.design_lock),
        "official_hands_authorized": 0,
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
