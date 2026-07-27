#!/usr/bin/env python3
"""Duplicate-safe H6 post-treatment mirror and judgment supervisor."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


PAIRS = 40_000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def status(path: Path, **payload: object) -> None:
    value = {
        "schema_version": "v5.hybrid.h6.completion_watch_status.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def count_rows(path: Path) -> int:
    with path.open("rb") as stream:
        return sum(1 for line in stream if line.strip())


def mirror_complete(path: Path, mirror_lock_sha: str, tool_sha: str) -> bool:
    summary_path = path.with_suffix(".summary.json")
    if not path.is_file() or not summary_path.is_file():
        return False
    summary = load(summary_path)
    return (
        summary.get("pairs") == PAIRS
        and summary.get("rows_sha256") == sha256(path)
        and count_rows(path) == PAIRS
        and summary.get("measurement_lock_sha256") == mirror_lock_sha
        and summary.get("tool_sha256") == tool_sha
    )


def preserve(path: Path) -> list[str]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    preserved = []
    for candidate in (path, path.with_suffix(".summary.json")):
        if candidate.exists():
            destination = candidate.with_name(candidate.name + f".interrupted-{stamp}")
            candidate.replace(destination)
            preserved.append(str(destination.resolve()))
    return preserved


def run(command: list[str], status_path: Path, stage: str) -> None:
    status(status_path, overall="RUNNING", state=stage, command=command)
    process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[2])
    status(status_path, overall="RUNNING", state=stage, child_pid=process.pid, command=command)
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"{stage}_exit_{return_code}")


def wait_or_preserve(path: Path, complete, poll_seconds: int, stable_polls: int) -> list[str]:
    if complete(path):
        return []
    if not path.exists() and not path.with_suffix(".summary.json").exists():
        return []
    previous = -1
    stable = 0
    while path.exists() and not complete(path):
        size = path.stat().st_size
        if size == previous:
            stable += 1
        else:
            previous = size
            stable = 0
        if stable >= stable_polls:
            break
        time.sleep(max(1, poll_seconds))
    return [] if complete(path) else preserve(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--status-json", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--stable-polls", type=int, default=10)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    os.chdir(repo)
    status_path = args.status_json.resolve()
    design_path = args.design_lock.resolve()
    try:
        if not design_path.is_file() or sha256(design_path) != args.expected_lock_sha256.lower():
            raise ValueError("design lock SHA mismatch")
        design = load(design_path)
        if design.get("design_id") != "H6" or design.get("status") != "LOCKED":
            raise ValueError("design lock identity/status")
        treatment_dir = Path(design["arms"]["treatment"]["run_dir"])
        control_checkpoint = Path(design["arms"]["control"]["checkpoint_path"])
        mirror_dir = Path(design["measurement"]["mirror_dir"])
        mirror_tool = repo / "scripts" / "alpha_holdem" / "v5_hybrid_h6_mirror.py"
        judge_tool = repo / "scripts" / "alpha_holdem" / "v5_hybrid_h6_judge.py"
        tools = design["tools"]
        mirror_tool_sha = tools["scripts/alpha_holdem/v5_hybrid_h6_mirror.py"]
        judge_tool_sha = tools["scripts/alpha_holdem/v5_hybrid_h6_judge.py"]
        if sha256(mirror_tool) != mirror_tool_sha or sha256(judge_tool) != judge_tool_sha:
            raise ValueError("completion child tool hash mismatch")
        manifest = mirror_dir / "manifest.json"
        measurement_lock = mirror_dir / "measurement_lock.json"
        mirror_lock_sha = design["measurement"]["mirror_lock_sha256"]
        if sha256(measurement_lock) != mirror_lock_sha or sha256(manifest) != design["measurement"]["mirror_manifest_sha256"]:
            raise ValueError("mirror manifest/lock mismatch")
        if args.validate_only:
            status(status_path, overall="PASS", state="VALIDATE_ONLY_STATIC_CONTRACT_PASS")
            return 0

        endpoint_status_path = treatment_dir / "h6_treatment_endpoint_status.json"
        protocol_status_path = treatment_dir / "h6_treatment_protocol_status.json"
        control_output = mirror_dir / "control_pairs.jsonl"
        treatment_output = mirror_dir / "treatment_pairs.jsonl"
        mirror_audit = mirror_dir / "audit.json"
        mirror_judgment = mirror_dir / "judgment.json"
        h6_judgment = repo / "reports" / "v5_hybrid_h6_judgment_20260713.json"

        while True:
            if h6_judgment.is_file():
                existing = load(h6_judgment)
                if existing.get("design_lock_sha256") == sha256(design_path) and existing.get("overall") in {"PASS", "FAIL", "INCONCLUSIVE"}:
                    status(status_path, overall="PASS", state="TERMINAL_RESULT_READY_HANDOFF_UPDATE_REQUIRED", verdict=existing["overall"], h6_judgment=str(h6_judgment.resolve()))
                    return 0
            if not protocol_status_path.is_file():
                status(status_path, overall="PENDING", state="WAITING_FOR_PROTOCOL_STATUS")
                time.sleep(max(1, args.poll_seconds))
                continue
            protocol = load(protocol_status_path)
            if protocol.get("overall") == "FAIL" and str(protocol.get("state", "")).startswith("H6_FAIL_PROTOCOL_ABORT_"):
                run([
                    sys.executable, "-u", str(judge_tool),
                    "--design-lock", str(design_path), "--expected-lock-sha256", sha256(design_path),
                    "--treatment-status", str(endpoint_status_path), "--protocol-status", str(protocol_status_path),
                    "--mirror-judgment", str(mirror_judgment), "--out", str(h6_judgment), "--device", "cuda",
                ], status_path, "RUNNING_H6_PROTOCOL_ABORT_JUDGMENT")
                continue
            if protocol.get("overall") != "PASS":
                status(status_path, overall="PENDING", state="WAITING_FOR_TERMINAL_PROTOCOL", protocol_state=protocol.get("state"))
                time.sleep(max(1, args.poll_seconds))
                continue
            if not endpoint_status_path.is_file():
                status(status_path, overall="PENDING", state="WAITING_FOR_TREATMENT_ENDPOINT")
                time.sleep(max(1, args.poll_seconds))
                continue
            endpoint_status = load(endpoint_status_path)
            if endpoint_status.get("overall") == "PENDING":
                status(status_path, overall="PENDING", state="WAITING_FOR_TREATMENT_ENDPOINT")
                time.sleep(max(1, args.poll_seconds))
                continue
            if endpoint_status.get("overall") != "PASS" or endpoint_status.get("state") != "ARM_ENDPOINT_FROZEN":
                raise ValueError("treatment endpoint terminal not PASS")
            treatment_checkpoint = Path(endpoint_status["checkpoint_path"])
            if not treatment_checkpoint.is_file() or sha256(treatment_checkpoint) != endpoint_status.get("checkpoint_sha256"):
                raise ValueError("treatment endpoint hash mismatch")

            complete = lambda path: mirror_complete(path, mirror_lock_sha, mirror_tool_sha)
            for arm, endpoint, output in (("control", control_checkpoint, control_output), ("treatment", treatment_checkpoint, treatment_output)):
                if not complete(output):
                    preserved = wait_or_preserve(output, complete, args.poll_seconds, args.stable_polls)
                    if preserved:
                        status(status_path, overall="RUNNING", state=f"PRESERVED_INTERRUPTED_{arm.upper()}_MIRROR", preserved=preserved)
                    run([
                        sys.executable, "-u", str(mirror_tool), "run-arm",
                        "--manifest", str(manifest), "--endpoint", str(endpoint), "--arm", arm, "--out", str(output),
                        "--device", "cpu", "--priority", "below-normal", "--torch-threads", "1", "--torch-interop-threads", "1",
                        "--measurement-lock", str(measurement_lock), "--expected-lock-sha256", mirror_lock_sha,
                    ], status_path, f"RUNNING_{arm.upper()}_MIRROR")
                    if not complete(output):
                        raise ValueError(f"{arm} mirror incomplete")
            if mirror_audit.exists():
                if load(mirror_audit).get("overall") != "PASS_IMMUTABLE_H6_MIRROR":
                    preserve(mirror_audit)
            if not mirror_audit.exists():
                run([
                    sys.executable, "-u", str(mirror_tool), "audit", "--manifest", str(manifest),
                    "--control", str(control_output), "--treatment", str(treatment_output), "--out", str(mirror_audit),
                    "--measurement-lock", str(measurement_lock), "--expected-lock-sha256", mirror_lock_sha,
                ], status_path, "RUNNING_MIRROR_AUDIT")
            if load(mirror_audit).get("overall") != "PASS_IMMUTABLE_H6_MIRROR":
                raise ValueError("mirror audit fail closed")
            if not mirror_judgment.exists():
                run([
                    sys.executable, "-u", str(mirror_tool), "judge", "--manifest", str(manifest),
                    "--control", str(control_output), "--treatment", str(treatment_output), "--audit", str(mirror_audit), "--out", str(mirror_judgment),
                    "--measurement-lock", str(measurement_lock), "--expected-lock-sha256", mirror_lock_sha,
                ], status_path, "RUNNING_MIRROR_JUDGMENT")
            if not h6_judgment.exists():
                run([
                    sys.executable, "-u", str(judge_tool), "--design-lock", str(design_path), "--expected-lock-sha256", sha256(design_path),
                    "--treatment-status", str(endpoint_status_path), "--protocol-status", str(protocol_status_path),
                    "--mirror-judgment", str(mirror_judgment), "--out", str(h6_judgment), "--device", "cuda",
                ], status_path, "RUNNING_H6_TERMINAL_JUDGMENT")
    except Exception as exc:
        status(status_path, overall="FAIL_CLOSED", state="COMPLETION_CHAIN_STOPPED", error=f"{type(exc).__name__}: {exc}", behavior_launch_authorized=False, official_hands_authorized=0)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
