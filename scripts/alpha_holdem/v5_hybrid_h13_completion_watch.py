#!/usr/bin/env python3
"""Duplicate-safe H13 post-arm evaluation and terminal judgment supervisor."""
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

import psutil

PAIRS = 40000


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def status(path: Path, **payload) -> None:
    value = {
        "schema_version": "v5.hybrid.h13.completion_watch_status.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def count_rows(path: Path) -> int:
    with path.open("rb") as stream:
        return sum(1 for line in stream if line.strip())


def complete(path: Path, lock_sha: str, tool_sha: str) -> bool:
    summary_path = path.with_suffix(".summary.json")
    if not path.is_file() or not summary_path.is_file():
        return False
    summary = load(summary_path)
    return (
        summary.get("pairs") == PAIRS
        and summary.get("rows_sha256") == sha(path)
        and count_rows(path) == PAIRS
        and summary.get("measurement_lock_sha256") == lock_sha
        and summary.get("tool_sha256") == tool_sha
    )


def preserve(path: Path) -> list[str]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = []
    for item in (path, path.with_suffix(".summary.json")):
        if item.exists():
            destination = item.with_name(item.name + f".interrupted-{stamp}")
            item.replace(destination)
            result.append(str(destination.resolve()))
    return result


def run(command: list[str], status_path: Path, stage: str) -> None:
    status(status_path, overall="RUNNING", state=stage, command=command)
    process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[2])
    status(status_path, overall="RUNNING", state=stage, child_pid=process.pid, command=command)
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"{stage}_exit_{return_code}")


def endpoint(path: Path, arm: str) -> dict | None:
    if not path.is_file():
        return None
    value = load(path)
    if value.get("overall") == "PENDING":
        return None
    if value.get("overall") != "PASS" or value.get("state") != "ARM_ENDPOINT_FROZEN" or value.get("arm") != arm:
        raise ValueError(f"{arm} endpoint terminal")
    checkpoint = Path(value["checkpoint_path"])
    if not checkpoint.is_file() or sha(checkpoint) != value.get("checkpoint_sha256"):
        raise ValueError(f"{arm} checkpoint identity")
    return value


def active_h13_trainers() -> list[int]:
    active = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
            if "train_v5.py" in command and "v5_hybrid_h13_" in command:
                active.append(process.pid)
        except Exception:
            pass
    return active


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--status-json", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    os.chdir(repo)
    status_path = args.status_json.resolve()
    lock_path = args.design_lock.resolve()
    try:
        if not lock_path.is_file() or sha(lock_path) != args.expected_lock_sha256.lower():
            raise ValueError("design lock SHA")
        lock = load(lock_path)
        if lock.get("design_id") != "H13" or lock.get("status") != "LOCKED":
            raise ValueError("design lock identity")
        tools = lock["tools"]
        mirror_tool = repo / "scripts/alpha_holdem/v5_hybrid_h13_mirror.py"
        judge_tool = repo / "scripts/alpha_holdem/v5_hybrid_h13_judge.py"
        active_window_tool = repo / "scripts/alpha_holdem/v5_hybrid_h13_active_window.py"
        if (
            sha(mirror_tool) != tools["scripts/alpha_holdem/v5_hybrid_h13_mirror.py"]
            or sha(judge_tool) != tools["scripts/alpha_holdem/v5_hybrid_h13_judge.py"]
            or sha(active_window_tool) != tools["scripts/alpha_holdem/v5_hybrid_h13_active_window.py"]
        ):
            raise ValueError("child tool hash")
        mirror_dir = Path(lock["measurement"]["mirror_dir"])
        manifest = mirror_dir / "manifest.json"
        measurement_lock = mirror_dir / "measurement_lock.json"
        measurement_lock_sha = lock["measurement"]["mirror_lock_sha256"]
        mirror_tool_sha = tools["scripts/alpha_holdem/v5_hybrid_h13_mirror.py"]
        if (
            sha(manifest) != lock["measurement"]["mirror_manifest_sha256"]
            or sha(measurement_lock) != measurement_lock_sha
        ):
            raise ValueError("mirror artifacts")
        if args.validate_only:
            status(status_path, overall="PASS", state="VALIDATE_ONLY_STATIC_CONTRACT_PASS")
            return 0
        directories = {
            arm: Path(lock["arms"][arm]["run_dir"])
            for arm in ("control", "treatment")
        }
        endpoint_status = {
            arm: directories[arm] / f"h13_{arm}_endpoint_status.json"
            for arm in directories
        }
        protocol = {
            arm: directories[arm] / f"h13_{arm}_protocol_status.json"
            for arm in directories
        }
        outputs = {
            "control": mirror_dir / "control_pairs.jsonl",
            "treatment": mirror_dir / "treatment_pairs.jsonl",
            "anchor": mirror_dir / "anchor_pairs.jsonl",
        }
        audit = mirror_dir / "audit.json"
        mirror_judgment = mirror_dir / "judgment.json"
        judgment = repo / "reports/v5_hybrid_h13_judgment_20260716.json"
        active_window_sentinel = repo / "reports/v5_active_window.json"
        while True:
            if judgment.is_file():
                existing = load(judgment)
                if (
                    existing.get("design_lock_sha256") == sha(lock_path)
                    and existing.get("overall") in {"PASS", "FAIL", "INCONCLUSIVE"}
                ):
                    transition = subprocess.run(
                        [
                            sys.executable,
                            str(active_window_tool),
                            "terminal",
                            "--sentinel",
                            str(active_window_sentinel),
                            "--design-lock",
                            str(lock_path),
                            "--expected-lock-sha256",
                            sha(lock_path),
                            "--verdict",
                            existing["overall"],
                            "--judgment",
                            str(judgment),
                        ],
                        cwd=repo,
                        text=True,
                        capture_output=True,
                    )
                    if transition.returncode != 0:
                        raise RuntimeError(f"active_window_terminal_exit_{transition.returncode}: {transition.stderr}")
                    status(
                        status_path,
                        overall="PASS",
                        state="TERMINAL_RESULT_READY_HANDOFF_UPDATE_REQUIRED",
                        verdict=existing["overall"],
                        h13_judgment=str(judgment.resolve()),
                    )
                    return 0
            terminal = None
            for arm in ("control", "treatment"):
                if protocol[arm].is_file() and load(protocol[arm]).get("overall") == "FAIL":
                    terminal = arm
                    break
            if terminal:
                run(
                    [
                        sys.executable,
                        "-u",
                        str(judge_tool),
                        "--design-lock",
                        str(lock_path),
                        "--expected-lock-sha256",
                        sha(lock_path),
                        "--control-status",
                        str(endpoint_status["control"]),
                        "--treatment-status",
                        str(endpoint_status["treatment"]),
                        "--control-protocol",
                        str(protocol["control"]),
                        "--treatment-protocol",
                        str(protocol["treatment"]),
                        "--mirror-judgment",
                        str(mirror_judgment),
                        "--out",
                        str(judgment),
                        "--device",
                        "cuda",
                    ],
                    status_path,
                    "RUNNING_H13_PROTOCOL_TERMINAL_JUDGMENT",
                )
                continue
            endpoints = {
                arm: endpoint(endpoint_status[arm], arm)
                for arm in ("control", "treatment")
            }
            if not all(endpoints.values()):
                status(
                    status_path,
                    overall="PENDING",
                    state="WAITING_FOR_BOTH_FROZEN_ENDPOINTS",
                    control_endpoint=bool(endpoints["control"]),
                    treatment_endpoint=bool(endpoints["treatment"]),
                )
                time.sleep(max(1, args.poll_seconds))
                continue
            active = active_h13_trainers()
            if active:
                status(
                    status_path,
                    overall="PENDING",
                    state="WAITING_FOR_ALL_H13_TRAINERS_TO_EXIT",
                    active_h13_trainers=active,
                )
                time.sleep(max(1, args.poll_seconds))
                continue
            endpoint_paths = {
                "control": endpoints["control"]["checkpoint_path"],
                "treatment": endpoints["treatment"]["checkpoint_path"],
                "anchor": lock["measurement"]["source_anchor_path"],
            }
            for arm in ("control", "treatment", "anchor"):
                if not complete(outputs[arm], measurement_lock_sha, mirror_tool_sha):
                    if outputs[arm].exists() or outputs[arm].with_suffix(".summary.json").exists():
                        preserve(outputs[arm])
                    run(
                        [
                            sys.executable,
                            "-u",
                            str(mirror_tool),
                            "run-arm",
                            "--manifest",
                            str(manifest),
                            "--endpoint",
                            str(endpoint_paths[arm]),
                            "--arm",
                            arm,
                            "--out",
                            str(outputs[arm]),
                            "--device",
                            "cpu",
                            "--priority",
                            "below-normal",
                            "--torch-threads",
                            "1",
                            "--torch-interop-threads",
                            "1",
                            "--measurement-lock",
                            str(measurement_lock),
                            "--expected-lock-sha256",
                            measurement_lock_sha,
                        ],
                        status_path,
                        f"RUNNING_{arm.upper()}_MIRROR",
                    )
                    if not complete(outputs[arm], measurement_lock_sha, mirror_tool_sha):
                        raise ValueError(f"{arm} mirror incomplete")
            if not audit.exists():
                run(
                    [
                        sys.executable,
                        "-u",
                        str(mirror_tool),
                        "audit",
                        "--manifest",
                        str(manifest),
                        "--control",
                        str(outputs["control"]),
                        "--treatment",
                        str(outputs["treatment"]),
                        "--anchor",
                        str(outputs["anchor"]),
                        "--out",
                        str(audit),
                        "--measurement-lock",
                        str(measurement_lock),
                        "--expected-lock-sha256",
                        measurement_lock_sha,
                    ],
                    status_path,
                    "RUNNING_MIRROR_AUDIT",
                )
            if load(audit).get("overall") != "PASS_IMMUTABLE_H13_MIRROR":
                raise ValueError("mirror audit")
            if not mirror_judgment.exists():
                run(
                    [
                        sys.executable,
                        "-u",
                        str(mirror_tool),
                        "judge",
                        "--manifest",
                        str(manifest),
                        "--control",
                        str(outputs["control"]),
                        "--treatment",
                        str(outputs["treatment"]),
                        "--anchor",
                        str(outputs["anchor"]),
                        "--audit",
                        str(audit),
                        "--out",
                        str(mirror_judgment),
                        "--measurement-lock",
                        str(measurement_lock),
                        "--expected-lock-sha256",
                        measurement_lock_sha,
                    ],
                    status_path,
                    "RUNNING_MIRROR_JUDGMENT",
                )
            if not judgment.exists():
                run(
                    [
                        sys.executable,
                        "-u",
                        str(judge_tool),
                        "--design-lock",
                        str(lock_path),
                        "--expected-lock-sha256",
                        sha(lock_path),
                        "--control-status",
                        str(endpoint_status["control"]),
                        "--treatment-status",
                        str(endpoint_status["treatment"]),
                        "--control-protocol",
                        str(protocol["control"]),
                        "--treatment-protocol",
                        str(protocol["treatment"]),
                        "--mirror-judgment",
                        str(mirror_judgment),
                        "--out",
                        str(judgment),
                        "--device",
                        "cuda",
                    ],
                    status_path,
                    "RUNNING_H13_TERMINAL_JUDGMENT",
                )
    except Exception as exc:
        status(
            status_path,
            overall="FAIL_CLOSED",
            state="COMPLETION_CHAIN_STOPPED",
            error=f"{type(exc).__name__}: {exc}",
            behavior_launch_authorized=False,
            official_hands_authorized=0,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
