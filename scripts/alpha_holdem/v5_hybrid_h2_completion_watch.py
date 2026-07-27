#!/usr/bin/env python3
"""Duplicate-safe H2 post-treatment mirror/judgment/route-review supervisor.

The watcher launches no trainer and no Slumbot evaluation.  It waits for exact
frozen endpoint/protocol artifacts, completes the immutable CPU mirror bundle,
runs the locked H2 judgment, and conditionally runs HYBRID-ROUTE-REVIEW-001.
Interrupted mirror rows are preserved under an ``.interrupted-*`` name before an
exact same-sample restart; they never enter the audited bundle.
"""

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


MIRROR_LOCK_SHA = "800c0b75e70ab5dedb54c853956d27333598f1e9ddcf6fa85162ad59e0921618"
JUDGMENT_LOCK_SHA = "f776d11bb01ed44a8d386ba31cce335be66b742f83e8c6a6de07451ca3003d9a"
ROUTE_REGISTRATION_SHA = "3ea1762520c61dccf8e272c63a168a895738175ecccd63e7593bffdb76a5e1df"
EXPECTED_MIRROR_TOOL_SHA = "0e1dc76bfc8e23f0493435e520fdffa78bc9f840417067646338cdea77bf1231"
EXPECTED_JUDGE_TOOL_SHA = "000f7273ca8673377c11de16b7ed50f940f679ffb5acead9adffe89b758643b6"
EXPECTED_ROUTE_TOOL_SHA = "46794b148dbbe717604d55e9dc70240539eb25f5466620a27a561940a67e1579"
PAIRS = 40_000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_status(path: Path, **payload: object) -> None:
    value = {
        "schema_version": "v5.hybrid.h2.completion_watch_status.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def exact_endpoint(path: Path, arm: str) -> dict | None:
    if not path.is_file():
        return None
    status = load(path)
    if status.get("overall") == "PENDING":
        return None
    if (
        status.get("overall") != "PASS"
        or status.get("state") != "ARM_ENDPOINT_FROZEN"
        or status.get("arm") != arm
    ):
        raise ValueError(f"{arm}_endpoint_terminal_not_pass")
    checkpoint = Path(status["checkpoint_path"])
    if not checkpoint.is_file() or sha256(checkpoint) != status.get("checkpoint_sha256"):
        raise ValueError(f"{arm}_endpoint_checkpoint_identity")
    return status


def exact_protocol(path: Path, arm: str) -> dict | None:
    if not path.is_file():
        return None
    status = load(path)
    if status.get("overall") == "PENDING":
        return None
    expected = "PASS_CONTROL_BASELINE_FROZEN" if arm == "control" else "PASS"
    if status.get("overall") != "PASS" or status.get("first60", {}).get("status") != expected:
        raise ValueError(f"{arm}_protocol_terminal_not_pass")
    return status


def count_nonblank(path: Path) -> int:
    with path.open("rb") as stream:
        return sum(1 for line in stream if line.strip())


def mirror_complete(output: Path) -> bool:
    summary_path = output.with_suffix(".summary.json")
    if not output.is_file() or not summary_path.is_file():
        return False
    summary = load(summary_path)
    return (
        summary.get("pairs") == PAIRS
        and summary.get("rows_sha256") == sha256(output)
        and count_nonblank(output) == PAIRS
        and summary.get("measurement_lock_sha256") == MIRROR_LOCK_SHA
        and summary.get("tool_sha256") == EXPECTED_MIRROR_TOOL_SHA
    )


def preserve_invalid(path: Path) -> list[str]:
    preserved: list[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for candidate in (path, path.with_suffix(".summary.json")):
        if candidate.exists():
            destination = candidate.with_name(candidate.name + f".interrupted-{stamp}")
            candidate.replace(destination)
            preserved.append(str(destination.resolve()))
    return preserved


def run_checked(command: list[str], status_path: Path, stage: str) -> None:
    atomic_status(status_path, overall="RUNNING", state=stage, command=command)
    process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[2])
    atomic_status(status_path, overall="RUNNING", state=stage, child_pid=process.pid, command=command)
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"{stage}_exit_{return_code}")


def wait_for_existing_mirror(output: Path, poll_seconds: int, stable_polls: int) -> bool:
    """Return True if complete; False if a partial output has stopped changing."""
    last_size = -1
    stable = 0
    while output.exists() and not mirror_complete(output):
        size = output.stat().st_size
        if size == last_size:
            stable += 1
        else:
            stable = 0
            last_size = size
        if stable >= stable_polls:
            return False
        time.sleep(poll_seconds)
    return mirror_complete(output)


def ensure_mirror_arm(
    *,
    arm: str,
    endpoint: Path,
    output: Path,
    mirror_tool: Path,
    manifest: Path,
    measurement_lock: Path,
    status_path: Path,
    poll_seconds: int,
    stable_polls: int,
) -> None:
    if mirror_complete(output):
        return
    preserved: list[str] = []
    if output.exists() or output.with_suffix(".summary.json").exists():
        if output.exists() and wait_for_existing_mirror(output, poll_seconds, stable_polls):
            return
        preserved = preserve_invalid(output)
    command = [
        sys.executable,
        "-u",
        str(mirror_tool),
        "run-arm",
        "--manifest",
        str(manifest),
        "--endpoint",
        str(endpoint),
        "--arm",
        arm,
        "--out",
        str(output),
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
        MIRROR_LOCK_SHA,
    ]
    if preserved:
        atomic_status(
            status_path,
            overall="RUNNING",
            state=f"PRESERVED_INTERRUPTED_{arm.upper()}_MIRROR",
            preserved=preserved,
        )
    run_checked(command, status_path, f"RUNNING_{arm.upper()}_MIRROR")
    if not mirror_complete(output):
        raise ValueError(f"{arm}_mirror_postrun_incomplete")


def remove_invalid_result(path: Path, predicate) -> None:
    if not path.exists():
        return
    try:
        if predicate(load(path)):
            return
    except Exception:
        pass
    preserve_invalid(path)


def validate_tool(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or sha256(path) != expected:
        raise ValueError(f"{label}_tool_sha256")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--treatment-dir", type=Path, required=True)
    parser.add_argument("--status-json", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--stable-polls", type=int, default=10)
    args = parser.parse_args()
    repo = args.repo.resolve()
    os.chdir(repo)
    status_path = args.status_json.resolve()
    control_dir = args.control_dir.resolve()
    treatment_dir = args.treatment_dir.resolve()
    mirror_dir = repo / "reports" / "h2_mirror_001_20260713"
    mirror_tool = repo / "scripts" / "alpha_holdem" / "v5_hybrid_h2_mirror.py"
    judge_tool = repo / "scripts" / "alpha_holdem" / "v5_hybrid_h2_judge.py"
    route_tool = repo / "scripts" / "alpha_holdem" / "v5_hybrid_route_review_001.py"
    manifest = mirror_dir / "manifest.json"
    measurement_lock = mirror_dir / "measurement_lock_v2.json"
    judgment_lock = repo / "reports" / "v5_hybrid_h2_judgment_lock_v3_20260713.json"
    route_registration = repo / "reports" / "v5_hybrid_route_review_001_preregistration_20260713.json"
    control_output = mirror_dir / "control_pairs.jsonl"
    treatment_output = mirror_dir / "treatment_pairs.jsonl"
    mirror_audit = mirror_dir / "audit.json"
    mirror_judgment = mirror_dir / "judgment.json"
    h2_judgment = repo / "reports" / "v5_hybrid_h2_judgment_20260713.json"
    route_result = repo / "reports" / "v5_hybrid_route_review_001_result_20260713.json"

    try:
        validate_tool(mirror_tool, EXPECTED_MIRROR_TOOL_SHA, "mirror")
        validate_tool(judge_tool, EXPECTED_JUDGE_TOOL_SHA, "judge")
        validate_tool(route_tool, EXPECTED_ROUTE_TOOL_SHA, "route")
        if sha256(measurement_lock) != MIRROR_LOCK_SHA:
            raise ValueError("mirror_lock_sha256")
        if sha256(judgment_lock) != JUDGMENT_LOCK_SHA:
            raise ValueError("judgment_lock_sha256")
        if sha256(route_registration) != ROUTE_REGISTRATION_SHA:
            raise ValueError("route_registration_sha256")

        while True:
            if h2_judgment.is_file():
                existing = load(h2_judgment)
                if existing.get("judgment_lock_sha256") == JUDGMENT_LOCK_SHA and existing.get("overall") in {"PASS", "FAIL", "INCONCLUSIVE"}:
                    if existing.get("route_review_required") is True and (
                        not route_result.is_file()
                        or load(route_result).get("overall") != "PASS_ROUTE_REVIEW"
                    ):
                        pass
                    else:
                        atomic_status(
                            status_path,
                            overall="PASS",
                            state="TERMINAL_RESULT_READY_HANDOFF_UPDATE_REQUIRED",
                            h2_judgment=str(h2_judgment),
                            route_result=str(route_result) if route_result.is_file() else None,
                            verdict=existing.get("overall"),
                        )
                        return 0
            control_endpoint = exact_endpoint(control_dir / "h2_control_endpoint_status.json", "control")
            if not treatment_dir.is_dir():
                atomic_status(status_path, overall="PENDING", state="WAITING_TREATMENT_DIR")
                time.sleep(args.poll_seconds)
                continue
            treatment_endpoint = exact_endpoint(treatment_dir / "h2_treatment_endpoint_status.json", "treatment")
            treatment_protocol = exact_protocol(treatment_dir / "h2_treatment_protocol_status.json", "treatment")
            if control_endpoint is None or treatment_endpoint is None or treatment_protocol is None:
                atomic_status(
                    status_path,
                    overall="PENDING",
                    state="WAITING_TREATMENT_ENDPOINT_AND_PROTOCOL",
                    control_endpoint=bool(control_endpoint),
                    treatment_endpoint=bool(treatment_endpoint),
                    treatment_protocol=bool(treatment_protocol),
                )
                time.sleep(args.poll_seconds)
                continue

            ensure_mirror_arm(
                arm="control",
                endpoint=Path(control_endpoint["checkpoint_path"]),
                output=control_output,
                mirror_tool=mirror_tool,
                manifest=manifest,
                measurement_lock=measurement_lock,
                status_path=status_path,
                poll_seconds=args.poll_seconds,
                stable_polls=args.stable_polls,
            )
            ensure_mirror_arm(
                arm="treatment",
                endpoint=Path(treatment_endpoint["checkpoint_path"]),
                output=treatment_output,
                mirror_tool=mirror_tool,
                manifest=manifest,
                measurement_lock=measurement_lock,
                status_path=status_path,
                poll_seconds=args.poll_seconds,
                stable_polls=args.stable_polls,
            )

            remove_invalid_result(mirror_audit, lambda value: value.get("overall") == "PASS_IMMUTABLE_H2_MIRROR")
            if not mirror_audit.exists():
                run_checked(
                    [sys.executable, "-u", str(mirror_tool), "audit", "--manifest", str(manifest), "--control", str(control_output), "--treatment", str(treatment_output), "--out", str(mirror_audit), "--measurement-lock", str(measurement_lock), "--expected-lock-sha256", MIRROR_LOCK_SHA],
                    status_path,
                    "RUNNING_MIRROR_AUDIT",
                )
            if load(mirror_audit).get("overall") != "PASS_IMMUTABLE_H2_MIRROR":
                raise ValueError("mirror_audit_fail_closed")

            remove_invalid_result(mirror_judgment, lambda value: value.get("schema_version") == "v5.hybrid.h2.mirror_judgment.v1")
            if not mirror_judgment.exists():
                run_checked(
                    [sys.executable, "-u", str(mirror_tool), "judge", "--manifest", str(manifest), "--control", str(control_output), "--treatment", str(treatment_output), "--audit", str(mirror_audit), "--out", str(mirror_judgment), "--measurement-lock", str(measurement_lock), "--expected-lock-sha256", MIRROR_LOCK_SHA],
                    status_path,
                    "RUNNING_MIRROR_JUDGMENT",
                )

            remove_invalid_result(h2_judgment, lambda value: value.get("judgment_lock_sha256") == JUDGMENT_LOCK_SHA)
            if not h2_judgment.exists():
                run_checked(
                    [sys.executable, "-u", str(judge_tool), "--judgment-lock", str(judgment_lock), "--expected-lock-sha256", JUDGMENT_LOCK_SHA, "--control-status", str(control_dir / "h2_control_endpoint_status.json"), "--treatment-status", str(treatment_dir / "h2_treatment_endpoint_status.json"), "--mirror-judgment", str(mirror_judgment), "--out", str(h2_judgment), "--device", "cuda"],
                    status_path,
                    "RUNNING_H2_TERMINAL_JUDGMENT",
                )
            judgment = load(h2_judgment)
            if judgment.get("classification") == "FAIL_CLOSED_MISSING_OR_INVALID_EVIDENCE":
                raise ValueError("h2_judgment_fail_closed")

            if judgment.get("route_review_required") is True:
                remove_invalid_result(route_result, lambda value: value.get("overall") == "PASS_ROUTE_REVIEW")
                if not route_result.exists():
                    run_checked(
                        [sys.executable, "-u", str(route_tool), "--registration", str(route_registration), "--expected-registration-sha256", ROUTE_REGISTRATION_SHA, "--h2-judgment", str(h2_judgment), "--out", str(route_result)],
                        status_path,
                        "RUNNING_HYBRID_ROUTE_REVIEW_001",
                    )
                if load(route_result).get("overall") != "PASS_ROUTE_REVIEW":
                    raise ValueError("route_review_fail_closed")

            atomic_status(
                status_path,
                overall="PASS",
                state="TERMINAL_RESULT_READY_HANDOFF_UPDATE_REQUIRED",
                h2_judgment=str(h2_judgment),
                route_result=str(route_result) if route_result.exists() else None,
                verdict=judgment.get("overall"),
            )
            return 0
    except Exception as exc:
        atomic_status(
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
