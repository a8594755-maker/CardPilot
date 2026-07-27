#!/usr/bin/env python3
"""Watch for a gated V5 Slumbot benchmark and launch it once ready.

This is the execution counterpart to v5_slumbot_benchmark_plan.py. It waits
until the planner returns READY, freezes the candidate checkpoint to an
immutable benchmark file, then launches Slumbot sessions. The default launch
path is direct Python child processes; the PowerShell wrapper is retained as a
rollback path.

Use this only for gated benchmark stages. quick5k is an API/loader smoke, not a
promotion or L5/L6 claim.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from v5_slumbot_benchmark_plan import evaluate as evaluate_plan
from v5_slumbot_benchmark_plan import write_markdown as write_plan_markdown
from v5_slumbot_artifact_audit import DEFAULT_RATE_FIELDS
from v5_slumbot_artifact_audit import audit as audit_slumbot_artifacts
from v5_slumbot_artifact_audit import write_markdown as write_artifact_audit_markdown
from v5_slumbot_hand_review import build_review as build_slumbot_hand_review
from v5_slumbot_hand_review import DEFAULT_BASELINE_BB100
from v5_slumbot_hand_review import write_markdown as write_hand_review_markdown
from v5_slumbot_pipeline_preflight import build_preflight
from v5_slumbot_pipeline_preflight import write_markdown as write_preflight_markdown


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fmt_rate(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{float(value):.3f}"
    return str(value)


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def load_checkpoint_summary(path: Path) -> dict[str, Any]:
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(ckpt, dict):
        raise TypeError(f"checkpoint is {type(ckpt).__name__}, not dict")
    return {
        "iteration": ckpt.get("iteration"),
        "total_hands": ckpt.get("total_hands"),
        "version": ckpt.get("version"),
        "env_version": ckpt.get("env_version"),
        "obs_version": ckpt.get("obs_version"),
        "action_space_version": ckpt.get("action_space_version"),
        "run_id": ckpt.get("run_id"),
    }


def plan_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        run_dir=args.run_dir,
        checkpoint=args.checkpoint,
        stage=args.stage,
        tag=args.tag,
        output_dir=args.output_dir,
        sessions=args.sessions,
        hands_per_session=args.hands_per_session,
        min_training_hands=args.min_training_hands,
        allow_early=args.allow_early,
        allow_existing_output=False,
        promotion_gate_json=args.promotion_gate_json,
        no_require_promotion20k=args.no_require_promotion20k,
        no_require_quality_gate=args.no_require_quality_gate,
        max_health_age_seconds=args.max_health_age_seconds,
        no_health_age_check=args.no_health_age_check,
        terminal_endpoint_status_json=args.terminal_endpoint_status_json,
        terminal_protocol_status_json=args.terminal_protocol_status_json,
        policy_mode=args.policy_mode,
        temperature=args.temperature,
        guarded_allin_max_spr=args.guarded_allin_max_spr,
        guarded_allin_min_prob=args.guarded_allin_min_prob,
        callguard_min_prob=args.callguard_min_prob,
        callguard_ratio=args.callguard_ratio,
        callguard_include_open=args.callguard_include_open,
    )


def refresh_plan(args: argparse.Namespace) -> dict[str, Any]:
    summary = evaluate_plan(plan_args(args))
    summary["launcher"] = {
        "launch_path": args.launch_path,
        "wrapper_command_is_preview": args.launch_path != "wrapper",
    }
    if args.plan_json:
        write_json(Path(args.plan_json), summary)
    if args.plan_md:
        out_md = Path(args.plan_md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        write_plan_markdown(out_md, summary)
    return summary


def collect_artifact_status(artifacts: dict[str, Any]) -> dict[str, Any]:
    artifact_status: dict[str, Any] = {}
    for name, value in artifacts.items():
        if isinstance(value, str) and any(ch in value for ch in "*?[]"):
            matches = sorted(glob.glob(value))
            artifact_status[name] = {"pattern": value, "match_count": len(matches), "matches_tail": matches[-5:]}
        else:
            artifact_status[name] = Path(str(value)).exists()
    return artifact_status


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def session_paths(output_dir: Path, tag: str, index: int) -> dict[str, Path]:
    prefix = output_dir / f"bench_v55_{tag}_part{index}"
    return {
        "result_json": prefix.with_suffix(".json"),
        "hands_jsonl": output_dir / f"bench_v55_{tag}_part{index}_hands.jsonl",
        "dump_jsonl": output_dir / f"bench_v55_{tag}_part{index}_dump.jsonl",
    }


def run_capture(cmd: list[str], out_txt: Path) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    out_txt.write_text(proc.stdout, encoding="utf-8", errors="replace")
    return {
        "returncode": proc.returncode,
        "elapsed_seconds": time.time() - started,
        "command": cmd,
        "out_txt": str(out_txt),
        "output_tail": proc.stdout[-4000:],
    }


def set_below_normal(pid: int) -> dict[str, Any]:
    if os.name != "nt":
        return {"status": "SKIPPED", "reason": "not_windows"}
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"$p=Get-Process -Id {int(pid)} -ErrorAction Stop; $p.PriorityClass='BelowNormal'; [string]$p.PriorityClass",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        return {
            "status": "PASS" if proc.returncode == 0 else "WARN",
            "returncode": proc.returncode,
            "output": proc.stdout.strip(),
        }
    except Exception as exc:
        return {"status": "WARN", "error": f"{type(exc).__name__}: {exc}"}


def direct_play_command(args: argparse.Namespace, frozen_checkpoint: Path, hands: int, paths: dict[str, Path]) -> list[str]:
    cmd = [
        sys.executable,
        "-X",
        "utf8",
        "-u",
        str(SCRIPT_DIR / "play_slumbot.py"),
        "--model",
        str(frozen_checkpoint),
        "--hands",
        str(hands),
        "--device",
        "cpu",
        "--policy-mode",
        args.policy_mode,
        "--temperature",
        str(args.temperature),
        "--guarded-allin-max-spr",
        str(args.guarded_allin_max_spr),
        "--guarded-allin-min-prob",
        str(args.guarded_allin_min_prob),
        "--callguard-min-prob",
        str(args.callguard_min_prob),
        "--callguard-ratio",
        str(args.callguard_ratio),
        "--result-json",
        str(paths["result_json"]),
        "--hand-results-jsonl",
        str(paths["hands_jsonl"]),
        "--dump-slumbot",
        str(paths["dump_jsonl"]),
    ]
    if args.callguard_include_open:
        cmd.append("--callguard-include-open")
    return cmd


def terminate_sessions(sessions: list[dict[str, Any]], *, timeout_seconds: float = 15.0) -> None:
    deadline = time.time() + timeout_seconds
    for session in sessions:
        proc = session.get("process")
        if proc is not None and proc.poll() is None:
            proc.terminate()
    for session in sessions:
        proc = session.get("process")
        if proc is None or proc.poll() is not None:
            continue
        remaining = max(0.0, deadline - time.time())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            proc.kill()


def write_direct_summary(summary_path: Path, tag: str, sessions: list[dict[str, Any]], ci: dict[str, Any] | None) -> None:
    lines = [
        f"Direct Slumbot benchmark summary for {tag}",
        f"checked_at={now_iso()}",
        "",
    ]
    if ci:
        lines.extend(
            [
                f"hands={int(ci.get('hands') or 0):,}",
                f"bb/100={float(ci.get('bb_per_100') or 0.0):+.2f}",
                (
                    "95% CI bb/100="
                    f"[{float(ci.get('lower_bound_bb_per_100') or 0.0):+.2f}, "
                    f"{float(ci.get('upper_bound_bb_per_100') or 0.0):+.2f}]"
                ),
                f"milestone_level={ci.get('milestone_level')}",
                "",
            ]
        )
    lines.append("sessions:")
    for session in sessions:
        paths = session["paths"]
        result = load_json(paths["result_json"]) or {}
        lines.append(
            "  "
            f"part{session['index']}: pid={session.get('pid')} exit={session.get('returncode')} "
            f"hands={result.get('successful_hands', 'n/a')} "
            f"bb/100={result.get('bb_per_100', 'n/a')} "
            f"hand_bytes={file_size(paths['hands_jsonl'])} "
            f"dump_bytes={file_size(paths['dump_jsonl'])}"
        )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def freeze_checkpoint(checkpoint_path: Path, frozen_path: Path, expected: dict[str, Any], *, retries: int = 3) -> dict[str, Any]:
    frozen_path.parent.mkdir(parents=True, exist_ok=True)
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            shutil.copy2(checkpoint_path, frozen_path)
            copied = load_checkpoint_summary(frozen_path)
            mismatches = []
            for key in ("iteration", "total_hands", "version", "env_version", "obs_version", "action_space_version"):
                if copied.get(key) != expected.get(key):
                    mismatches.append(f"{key}: copied={copied.get(key)!r} expected={expected.get(key)!r}")
            if mismatches:
                raise RuntimeError("; ".join(mismatches))
            return copied
        except Exception as exc:
            last_error = str(exc)
            time.sleep(min(5, attempt))
    raise RuntimeError(f"failed to freeze checkpoint after {retries} attempts: {last_error}")


def run_artifact_audit(plan: dict[str, Any]) -> dict[str, Any]:
    output_dir = Path(plan["output_dir"])
    tag = str(plan["tag"])
    expected_parts = int(plan.get("sessions") or 0) or None
    expected_hands = int(plan.get("planned_hands") or 0) or None
    out_json = output_dir / f"bench_v55_{tag}_artifact_audit.json"
    out_md = output_dir / f"bench_v55_{tag}_artifact_audit.md"
    audit_args = argparse.Namespace(
        tag=tag,
        output_dir=str(output_dir),
        min_parts=1,
        expected_parts=expected_parts,
        min_hands=1,
        expected_hands=expected_hands,
        require_rate_field=list(DEFAULT_RATE_FIELDS),
        out_json=str(out_json),
        out_md=str(out_md),
    )
    summary = audit_slumbot_artifacts(audit_args)
    write_json(out_json, summary)
    write_artifact_audit_markdown(summary, out_md)
    summary["out_json"] = str(out_json)
    summary["out_md"] = str(out_md)
    return summary


def run_hand_review(plan: dict[str, Any]) -> dict[str, Any]:
    output_dir = Path(plan["output_dir"])
    tag = str(plan["tag"])
    out_json = output_dir / f"bench_v55_{tag}_hand_review.json"
    out_md = output_dir / f"bench_v55_{tag}_hand_review.md"
    policy = plan.get("policy") if isinstance(plan.get("policy"), dict) else {}
    review_args = argparse.Namespace(
        run_dir=str(plan.get("run_dir") or ""),
        output_dir=str(output_dir),
        tag=tag,
        ci_json="",
        loss_report_json="",
        artifact_audit_json="",
        selection="official",
        policy_mode=str(policy.get("policy_mode") or "greedy"),
        baseline_bb100=DEFAULT_BASELINE_BB100,
        l6_target_bb100=11.1,
        out_json=str(out_json),
        out_md=str(out_md),
    )
    summary = build_slumbot_hand_review(review_args)
    write_json(out_json, summary)
    write_hand_review_markdown(summary, out_md)
    summary["out_json"] = str(out_json)
    summary["out_md"] = str(out_md)
    return summary


def run_benchmark_wrapper(args: argparse.Namespace, plan: dict[str, Any], frozen_checkpoint: Path) -> dict[str, Any]:
    output_dir = Path(plan["output_dir"])
    tag = str(plan["tag"])
    orchestrator_log = output_dir / f"bench_v55_{tag}_orchestrator.log"
    orchestrator_err = output_dir / f"bench_v55_{tag}_orchestrator_err.log"
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT_DIR / "bench_v55_slumbot.ps1"),
        "-ModelPath",
        str(frozen_checkpoint),
        "-Tag",
        tag,
        "-HandsPerSession",
        str(plan["hands_per_session"]),
        "-Sessions",
        str(plan["sessions"]),
        "-OutputDir",
        str(output_dir),
        "-RunDir",
        str(Path(plan["run_dir"])),
        "-PythonExe",
        sys.executable,
        "-PolicyMode",
        args.policy_mode,
        "-Temperature",
        str(args.temperature),
        "-GuardedAllinMaxSpr",
        str(args.guarded_allin_max_spr),
        "-GuardedAllinMinProb",
        str(args.guarded_allin_min_prob),
        "-CallguardMinProb",
        str(args.callguard_min_prob),
        "-CallguardRatio",
        str(args.callguard_ratio),
    ]
    if args.callguard_include_open:
        cmd.append("-CallguardIncludeOpen")

    started = time.time()
    with orchestrator_log.open("w", encoding="utf-8", errors="replace") as out, orchestrator_err.open("w", encoding="utf-8", errors="replace") as err:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=out,
            stderr=err,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    artifacts = plan.get("artifacts", {})
    artifact_status = collect_artifact_status(artifacts)

    promotion = load_json(Path(str(artifacts.get("promotion_json", "")))) if artifacts.get("promotion_json") else None
    ci = load_json(Path(str(artifacts.get("ci_json", "")))) if artifacts.get("ci_json") else None
    loss_report = load_json(Path(str(artifacts.get("loss_report_json", "")))) if artifacts.get("loss_report_json") else None
    artifact_audit = run_artifact_audit(plan)
    hand_review = run_hand_review(plan)
    hand_review_ok = hand_review.get("overall") not in {"MISSING_CI", "INCOMPLETE"}
    status = "PASS" if proc.returncode == 0 and artifact_audit.get("overall") == "PASS" and hand_review_ok else "FAIL"
    return {
        "status": status,
        "launch_path": "wrapper",
        "returncode": proc.returncode,
        "elapsed_seconds": time.time() - started,
        "command": cmd,
        "policy": benchmark_policy_summary(args),
        "orchestrator_log": str(orchestrator_log),
        "orchestrator_err": str(orchestrator_err),
        "artifact_status": artifact_status,
        "artifact_audit": artifact_audit,
        "hand_review": hand_review,
        "ci_summary": ci,
        "loss_report_summary": loss_report,
        "promotion_summary": promotion,
        "checked_at": now_iso(),
    }


def run_benchmark_direct(args: argparse.Namespace, plan: dict[str, Any], frozen_checkpoint: Path) -> dict[str, Any]:
    output_dir = Path(plan["output_dir"])
    tag = str(plan["tag"])
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = plan.get("artifacts", {})
    direct_log = output_dir / f"bench_v55_{tag}_direct_launcher.log"
    direct_err = output_dir / f"bench_v55_{tag}_direct_launcher_err.log"
    summary_txt = Path(str(artifacts.get("summary_txt") or output_dir / f"bench_v55_{tag}_summary.txt"))
    ci_json = Path(str(artifacts.get("ci_json") or output_dir / f"bench_v55_{tag}_ci_summary.json"))
    promotion_json = Path(str(artifacts.get("promotion_json") or output_dir / f"bench_v55_{tag}_promotion_gate.json"))
    promotion_md = Path(str(artifacts.get("promotion_md") or output_dir / f"bench_v55_{tag}_promotion_gate.md"))
    dump_analysis = Path(str(artifacts.get("dump_analysis") or output_dir / f"bench_v55_{tag}_dump_analysis.txt"))
    loss_report_json = Path(str(artifacts.get("loss_report_json") or output_dir / f"bench_v55_{tag}_loss_report.json"))
    loss_report_md = Path(str(artifacts.get("loss_report_md") or output_dir / f"bench_v55_{tag}_loss_report.md"))
    loss_report_txt = loss_report_json.with_suffix(".txt")

    def log_direct(message: str) -> None:
        line = f"{now_iso()} {message}"
        print(line, flush=True)
        direct_log.parent.mkdir(parents=True, exist_ok=True)
        with direct_log.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    started = time.time()
    sessions: list[dict[str, Any]] = []
    failures: list[str] = []
    commands: list[list[str]] = []
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    hands_per_session = int(plan["hands_per_session"])

    log_direct(
        f"direct launcher start tag={tag} sessions={plan['sessions']} "
        f"hands_per_session={hands_per_session} stdout=DEVNULL stderr=DEVNULL"
    )
    direct_err.write_text("", encoding="utf-8")

    for index in range(1, int(plan["sessions"]) + 1):
        paths = session_paths(output_dir, tag, index)
        cmd = direct_play_command(args, frozen_checkpoint, hands_per_session, paths)
        commands.append(cmd)
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(REPO_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except Exception as exc:
            failures.append(f"session {index} launch failed: {type(exc).__name__}: {exc}")
            continue
        priority = {"status": "SKIPPED", "reason": "disabled"}
        if not args.no_direct_low_priority:
            priority = set_below_normal(proc.pid)
        sessions.append(
            {
                "index": index,
                "pid": proc.pid,
                "process": proc,
                "paths": paths,
                "command": cmd,
                "priority": priority,
            }
        )
        log_direct(f"session {index} started pid={proc.pid} priority={priority.get('status')} result={paths['result_json']}")
        if not args.no_direct_low_priority and priority.get("status") != "PASS":
            failures.append(
                f"session {index} BelowNormal priority setup failed: {priority}"
            )
            break

    if failures:
        terminate_sessions(sessions)

    last_log = 0.0
    stall_reason = ""
    while sessions and not failures:
        alive = [session for session in sessions if session["process"].poll() is None]
        now = time.time()
        if now - last_log >= max(1.0, float(args.direct_poll_seconds)):
            last_log = now
            nonzero = 0
            for session in sessions:
                paths = session["paths"]
                if file_size(paths["hands_jsonl"]) + file_size(paths["dump_jsonl"]) > 0:
                    nonzero += 1
            log_direct(f"monitor alive={len(alive)}/{len(sessions)} nonzero_outputs={nonzero}/{len(sessions)} elapsed={now - started:.1f}s")

        if alive and float(args.direct_stall_timeout_seconds) > 0:
            zero_alive = []
            for session in alive:
                paths = session["paths"]
                if file_size(paths["hands_jsonl"]) + file_size(paths["dump_jsonl"]) == 0:
                    zero_alive.append(session)
            if zero_alive and now - started >= float(args.direct_stall_timeout_seconds):
                stall_reason = (
                    f"{len(zero_alive)} live session(s) still have zero hand/dump bytes "
                    f"after {float(args.direct_stall_timeout_seconds):.1f}s"
                )
                failures.append(stall_reason)
                log_direct(f"STALL: {stall_reason}")
                terminate_sessions(sessions)
                break

        if not alive:
            break
        time.sleep(max(1.0, float(args.direct_poll_seconds)))

    for session in sessions:
        proc = session["process"]
        if proc.poll() is None:
            terminate_sessions([session])
        session["returncode"] = proc.returncode
        paths = session["paths"]
        missing = [name for name in ("result_json", "hands_jsonl", "dump_jsonl") if not paths[name].exists()]
        if proc.returncode != 0:
            failures.append(f"session {session['index']} exit={proc.returncode}")
        if missing:
            failures.append(f"session {session['index']} missing {', '.join(missing)}")
        if file_size(paths["hands_jsonl"]) <= 0:
            failures.append(f"session {session['index']} hand jsonl is empty")
        if file_size(paths["dump_jsonl"]) <= 0:
            failures.append(f"session {session['index']} dump jsonl is empty")

    hand_files = [session["paths"]["hands_jsonl"] for session in sessions]
    dump_files = [session["paths"]["dump_jsonl"] for session in sessions]
    derived: dict[str, Any] = {}

    if not failures:
        ci_txt = ci_json.with_suffix(".txt")
        ci_cmd = [sys.executable, str(SCRIPT_DIR / "slumbot_ci_from_hands.py"), *[str(path) for path in hand_files], "--out-json", str(ci_json)]
        derived["ci"] = run_capture(ci_cmd, ci_txt)
        if derived["ci"]["returncode"] != 0 or not ci_json.exists():
            failures.append("CI summary failed or missing")

    ci = load_json(ci_json) if ci_json.exists() else None
    write_direct_summary(summary_txt, tag, sessions, ci)

    if not failures:
        promotion_txt = promotion_json.with_suffix(".txt")
        promotion_cmd = [
            sys.executable,
            str(SCRIPT_DIR / "v5_slumbot_promotion_gate.py"),
            "--checkpoint",
            str(frozen_checkpoint),
            "--ci-json",
            str(ci_json),
            "--out-json",
            str(promotion_json),
            "--out-md",
            str(promotion_md),
        ]
        run_dir = str(plan.get("run_dir") or args.run_dir or "")
        if run_dir:
            promotion_cmd.extend(["--run-dir", run_dir])
        if args.terminal_endpoint_status_json:
            promotion_cmd.extend(["--terminal-endpoint-status-json", args.terminal_endpoint_status_json])
        if args.terminal_protocol_status_json:
            promotion_cmd.extend(["--terminal-protocol-status-json", args.terminal_protocol_status_json])
        derived["promotion_gate"] = run_capture(promotion_cmd, promotion_txt)
        promotion_summary = load_json(promotion_json) if promotion_json.exists() else None
        accepted, acceptance_detail = promotion_gate_artifact_acceptable(
            str(plan.get("stage") or args.stage),
            derived["promotion_gate"]["returncode"],
            promotion_summary,
        )
        derived["promotion_gate"]["artifact_accepted"] = accepted
        derived["promotion_gate"]["acceptance_detail"] = acceptance_detail
        if not accepted or not promotion_json.exists() or not promotion_md.exists():
            failures.append("promotion gate failed or missing")

    if not failures:
        dump_cmd = [sys.executable, str(SCRIPT_DIR / "analyze_dump.py"), "--label", tag, "--dumps", *[str(path) for path in dump_files]]
        derived["dump_analysis"] = run_capture(dump_cmd, dump_analysis)
        if derived["dump_analysis"]["returncode"] != 0 or not dump_analysis.exists():
            failures.append("dump analysis failed or missing")

    if not failures:
        for stale_path in (loss_report_json, loss_report_md, loss_report_txt):
            try:
                stale_path.unlink(missing_ok=True)
            except OSError:
                pass
        loss_cmd = [
            sys.executable,
            str(SCRIPT_DIR / "v5_slumbot_loss_report.py"),
            "--label",
            tag,
            "--dumps",
            *[str(path) for path in dump_files],
            "--out-json",
            str(loss_report_json),
            "--out-md",
            str(loss_report_md),
        ]
        derived["loss_report"] = run_capture(loss_cmd, loss_report_txt)
        if derived["loss_report"]["returncode"] != 0 or not loss_report_json.exists() or not loss_report_md.exists():
            failures.append("loss report failed or missing")
        else:
            loss_loaded = load_json(loss_report_json) or {}
            rates = loss_loaded.get("rates") if isinstance(loss_loaded.get("rates"), dict) else {}
            if rates.get("sb_open_call_rate") is None or rates.get("sb_open_raise_rate") is None:
                failures.append("loss report missing SB open call/raise rates")

    artifact_status = collect_artifact_status(artifacts)
    promotion = load_json(promotion_json) if promotion_json.exists() else None
    ci = load_json(ci_json) if ci_json.exists() else None
    loss_report = load_json(loss_report_json) if loss_report_json.exists() else None
    artifact_audit = run_artifact_audit(plan) if not failures else {}
    hand_review = run_hand_review(plan) if not failures else {}
    hand_review_ok = hand_review.get("overall") not in {"MISSING_CI", "INCOMPLETE"} if hand_review else False
    status = "PASS" if not failures and artifact_audit.get("overall") == "PASS" and hand_review_ok else "FAIL"

    compact_sessions: list[dict[str, Any]] = []
    for session in sessions:
        paths = session["paths"]
        compact_sessions.append(
            {
                "index": session["index"],
                "pid": session["pid"],
                "returncode": session.get("returncode"),
                "priority": session.get("priority"),
                "result_json": str(paths["result_json"]),
                "hands_jsonl": str(paths["hands_jsonl"]),
                "dump_jsonl": str(paths["dump_jsonl"]),
                "hand_bytes": file_size(paths["hands_jsonl"]),
                "dump_bytes": file_size(paths["dump_jsonl"]),
            }
        )

    return {
        "status": status,
        "launch_path": "direct",
        "returncode": 0 if status == "PASS" else 1,
        "elapsed_seconds": time.time() - started,
        "command": commands,
        "policy": benchmark_policy_summary(args),
        "orchestrator_log": str(direct_log),
        "orchestrator_err": str(direct_err),
        "artifact_status": artifact_status,
        "artifact_audit": artifact_audit,
        "hand_review": hand_review,
        "ci_summary": ci,
        "loss_report_summary": loss_report,
        "promotion_summary": promotion,
        "direct_sessions": compact_sessions,
        "derived_commands": derived,
        "failures": failures,
        "stall_reason": stall_reason,
        "checked_at": now_iso(),
    }


def run_benchmark(args: argparse.Namespace, plan: dict[str, Any], frozen_checkpoint: Path) -> dict[str, Any]:
    if args.launch_path == "wrapper":
        return run_benchmark_wrapper(args, plan, frozen_checkpoint)
    return run_benchmark_direct(args, plan, frozen_checkpoint)


def promotion_gate_artifact_acceptable(
    stage: str,
    returncode: int,
    summary: dict[str, Any] | None,
) -> tuple[bool, str]:
    """Separate quick-screen artifact validity from a deliberately failed promotion gate."""
    if summary is None:
        return False, "promotion summary missing or unreadable"
    failed = {
        str(item.get("name"))
        for item in (summary.get("checks") or [])
        if item.get("status") == "FAIL"
    }
    if returncode == 0 and not failed:
        return True, "promotion audit PASS"
    if stage == "quick5k" and failed == {"promotion_hands"}:
        return True, "quick5k promotion_hands block is expected; metadata/artifacts PASS"
    return False, f"unexpected promotion audit failures={sorted(failed)} returncode={returncode}"


def benchmark_policy_summary(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "policy_mode": args.policy_mode,
        "temperature": float(args.temperature),
        "guarded_allin_max_spr": float(args.guarded_allin_max_spr),
        "guarded_allin_min_prob": float(args.guarded_allin_min_prob),
        "callguard_min_prob": float(args.callguard_min_prob),
        "callguard_ratio": float(args.callguard_ratio),
        "callguard_include_open": bool(args.callguard_include_open),
    }


def run_preflight(args: argparse.Namespace, plan: dict[str, Any], frozen_checkpoint: Path) -> dict[str, Any]:
    output_dir = Path(plan["output_dir"])
    tag = str(plan["tag"])
    preflight_dir = output_dir / f"bench_v55_{tag}_preflight"
    preflight_json = output_dir / f"bench_v55_{tag}_preflight.json"
    preflight_md = output_dir / f"bench_v55_{tag}_preflight.md"
    preflight_args = argparse.Namespace(
        run_dir=plan["run_dir"],
        checkpoint=str(frozen_checkpoint),
        device=args.preflight_device,
        out_dir=str(preflight_dir),
        out_json="",
        out_md="",
        terminal_endpoint_status_json=args.terminal_endpoint_status_json,
        terminal_protocol_status_json=args.terminal_protocol_status_json,
    )
    summary = build_preflight(preflight_args)
    write_json(preflight_json, summary)
    write_preflight_markdown(summary, preflight_md)
    summary["preflight_json"] = str(preflight_json)
    summary["preflight_md"] = str(preflight_md)
    return summary


def run_selector_replay(args: argparse.Namespace, plan: dict[str, Any], frozen_checkpoint: Path) -> dict[str, Any]:
    artifacts = plan.get("artifacts") or {}
    output_dir = Path(plan["output_dir"])
    tag = str(plan["tag"])
    replay_json = Path(str(artifacts.get("selector_replay_json") or output_dir / f"bench_v55_{tag}_selector_replay.json"))
    replay_md = Path(str(artifacts.get("selector_replay_md") or output_dir / f"bench_v55_{tag}_selector_replay.md"))
    dump_glob = str(artifacts.get("dump_glob") or output_dir / f"bench_v55_{tag}_part*_dump.jsonl")
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "v5_slumbot_selector_replay.py"),
        "--checkpoint",
        str(frozen_checkpoint),
        "--dump",
        dump_glob,
        "--device",
        args.selector_replay_device,
        "--policies",
        args.selector_replay_policies,
        "--temperature",
        str(args.temperature),
        "--guarded-allin-max-spr",
        str(args.guarded_allin_max_spr),
        "--guarded-allin-min-prob",
        str(args.guarded_allin_min_prob),
        "--callguard-min-prob",
        str(args.callguard_min_prob),
        "--callguard-ratio",
        str(args.callguard_ratio),
        "--out-json",
        str(replay_json),
        "--out-md",
        str(replay_md),
    ]
    if args.selector_replay_limit > 0:
        cmd.extend(["--limit", str(args.selector_replay_limit)])

    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    summary = load_json(replay_json) if replay_json.exists() else None
    return {
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "returncode": proc.returncode,
        "elapsed_seconds": time.time() - started,
        "command": cmd,
        "selector_replay_json": str(replay_json),
        "selector_replay_md": str(replay_md),
        "summary": summary,
        "output_tail": proc.stdout[-4000:],
        "checked_at": now_iso(),
    }


def rerun_promotion_gate_with_selector(
    args: argparse.Namespace,
    plan: dict[str, Any],
    frozen_checkpoint: Path,
    selector_replay: dict[str, Any],
) -> dict[str, Any]:
    artifacts = plan.get("artifacts") or {}
    ci_json_value = str(artifacts.get("ci_json") or "")
    promotion_json_value = str(artifacts.get("promotion_json") or "")
    promotion_md_value = str(artifacts.get("promotion_md") or "")
    selector_json_value = str(selector_replay.get("selector_replay_json") or "")
    ci_json = Path(ci_json_value) if ci_json_value else None
    promotion_json = Path(promotion_json_value) if promotion_json_value else None
    promotion_md = Path(promotion_md_value) if promotion_md_value else None
    selector_json = Path(selector_json_value) if selector_json_value else None
    if (
        ci_json is None
        or selector_json is None
        or promotion_json is None
        or promotion_md is None
        or not ci_json.exists()
        or not selector_json.exists()
    ):
        return {
            "status": "SKIPPED",
            "reason": "missing ci_json, selector_replay_json, or promotion_json path",
            "ci_json": str(ci_json) if ci_json else "",
            "selector_replay_json": str(selector_json) if selector_json else "",
            "promotion_json": str(promotion_json) if promotion_json else "",
            "checked_at": now_iso(),
        }

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "v5_slumbot_promotion_gate.py"),
        "--checkpoint",
        str(frozen_checkpoint),
        "--ci-json",
        str(ci_json),
        "--out-json",
        str(promotion_json),
        "--out-md",
        str(promotion_md),
        "--selector-replay-json",
        str(selector_json),
    ]
    run_dir = str(plan.get("run_dir") or args.run_dir or "")
    if run_dir:
        cmd.extend(["--run-dir", run_dir])
    if args.terminal_endpoint_status_json:
        cmd.extend(["--terminal-endpoint-status-json", args.terminal_endpoint_status_json])
    if args.terminal_protocol_status_json:
        cmd.extend(["--terminal-protocol-status-json", args.terminal_protocol_status_json])

    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    summary = load_json(promotion_json) if promotion_json.exists() else None
    accepted, acceptance_detail = promotion_gate_artifact_acceptable(
        str(plan.get("stage") or args.stage), proc.returncode, summary
    )
    return {
        "status": "PASS" if accepted else "FAIL",
        "promotion_gate_returncode": proc.returncode,
        "promotion_gate_overall": (summary or {}).get("overall"),
        "selector_replay_clean": ((summary or {}).get("decisions") or {}).get("selector_replay_clean"),
        "elapsed_seconds": time.time() - started,
        "command": cmd,
        "promotion_json": str(promotion_json),
        "promotion_md": str(promotion_md),
        "summary": summary,
        "acceptance_detail": acceptance_detail,
        "output_tail": proc.stdout[-4000:],
        "checked_at": now_iso(),
    }


def selector_replay_report_lines(selector_replay: dict[str, Any] | None) -> list[str]:
    if not selector_replay:
        return []
    lines = [
        f"- selector replay status: `{selector_replay.get('status')}`",
        f"- selector replay JSON: `{selector_replay.get('selector_replay_json')}`",
        f"- selector replay MD: `{selector_replay.get('selector_replay_md')}`",
    ]
    summary = selector_replay.get("summary") or {}
    policies = summary.get("policies") or {}
    greedy = policies.get("greedy") or {}
    callguard = policies.get("preflop-callguard") or {}
    greedy_pf = ((greedy.get("situations") or {}).get("preflop_facing_bet") or {}).get("rates") or {}
    callguard_pf = ((callguard.get("situations") or {}).get("preflop_facing_bet") or {}).get("rates") or {}
    changes = (summary.get("changes_vs_greedy") or {}).get("preflop-callguard") or {}
    if greedy_pf or callguard_pf:
        lines.append(
            "- selector replay preflop facing-bet call rate: "
            f"greedy `{float(greedy_pf.get('call', 0.0)):.3f}`, "
            f"preflop-callguard `{float(callguard_pf.get('call', 0.0)):.3f}`"
        )
    if changes:
        lines.append(
            "- selector replay callguard changes vs greedy: "
            f"`{changes.get('changed')}` decisions "
            f"(`{float(changes.get('changed_rate') or 0.0):.3f}`), "
            f"preflop facing-bet `{changes.get('changed_preflop_facing_bet')}`"
        )
    promotion_gate = selector_replay.get("promotion_gate") or {}
    if promotion_gate:
        lines.append(
            "- selector replay promotion gate rerun: "
            f"`{promotion_gate.get('status')}`, overall `{promotion_gate.get('promotion_gate_overall')}`, "
            f"selector clean `{promotion_gate.get('selector_replay_clean')}`"
        )
    return lines


def append_report(
    report_path: Path | None,
    plan: dict[str, Any],
    frozen: dict[str, Any],
    result: dict[str, Any],
    selector_replay: dict[str, Any] | None = None,
) -> None:
    if report_path is None:
        return
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "",
        f"## Slumbot {plan['stage']} Benchmark Watch",
        "",
        f"- checked at: `{result.get('checked_at')}`",
        f"- status: `{result.get('status')}`",
        f"- launch path: `{result.get('launch_path', 'wrapper')}`",
        f"- tag: `{plan.get('tag')}`",
        f"- planned hands: `{plan.get('planned_hands'):,}`",
        f"- policy mode: `{result.get('policy', {}).get('policy_mode', 'greedy')}`",
        f"- policy temperature: `{result.get('policy', {}).get('temperature', 1.0)}`",
        f"- frozen checkpoint iteration: `{frozen.get('iteration')}`",
        f"- frozen checkpoint hands: `{frozen.get('total_hands'):,}`",
        f"- orchestrator log: `{result.get('orchestrator_log')}`",
        f"- CI JSON: `{plan.get('artifacts', {}).get('ci_json')}`",
        f"- promotion JSON: `{plan.get('artifacts', {}).get('promotion_json')}`",
        f"- dump analysis: `{plan.get('artifacts', {}).get('dump_analysis')}`",
        f"- loss report JSON: `{plan.get('artifacts', {}).get('loss_report_json')}`",
        f"- loss report MD: `{plan.get('artifacts', {}).get('loss_report_md')}`",
    ]
    ci = result.get("ci_summary") or {}
    if ci:
        lines.extend(
            [
                f"- Slumbot hands: `{ci.get('hands'):,}`",
                f"- Slumbot bb/100: `{float(ci.get('bb_per_100') or 0.0):+.2f}`",
                f"- Slumbot 95% CI lower: `{float(ci.get('lower_bound_bb_per_100') or 0.0):+.2f}`",
                f"- milestone: `{ci.get('milestone_level')}`",
            ]
        )
    loss_report = result.get("loss_report_summary") or {}
    rates = loss_report.get("rates") if isinstance(loss_report.get("rates"), dict) else {}
    if rates:
        lines.extend(
            [
                "- loss report SB open fold / call / raise / all-in: "
                f"`{fmt_rate(rates.get('sb_open_fold_rate'))}` / `{fmt_rate(rates.get('sb_open_call_rate'))}` / "
                f"`{fmt_rate(rates.get('sb_open_raise_rate'))}` / `{fmt_rate(rates.get('sb_open_allin_rate'))}`",
                "- loss report BB vs open call / raise: "
                f"`{fmt_rate(rates.get('bb_vs_open_call_rate'))}` / `{fmt_rate(rates.get('bb_vs_open_raise_rate'))}`",
            ]
        )
    loss_warnings = loss_report.get("warnings") if isinstance(loss_report.get("warnings"), list) else []
    if loss_warnings:
        lines.append("- loss report warnings:")
        lines.extend(f"  - {warning}" for warning in loss_warnings[:8])
    audit_summary = result.get("artifact_audit") if isinstance(result.get("artifact_audit"), dict) else {}
    if audit_summary:
        lines.extend(
            [
                f"- artifact audit: `{audit_summary.get('overall')}`",
                f"- artifact audit JSON: `{audit_summary.get('out_json')}`",
                f"- artifact audit MD: `{audit_summary.get('out_md')}`",
            ]
        )
    hand_review = result.get("hand_review") if isinstance(result.get("hand_review"), dict) else {}
    if hand_review:
        lines.extend(
            [
                f"- hand review: `{hand_review.get('overall')}`",
                f"- hand review JSON: `{hand_review.get('out_json')}`",
                f"- hand review MD: `{hand_review.get('out_md')}`",
                f"- hand review evidence class: `{hand_review.get('evidence_class')}`",
                f"- hand review training adjustment: `{hand_review.get('training_adjustment')}`",
            ]
        )
        hypotheses = hand_review.get("loss_hypotheses") if isinstance(hand_review.get("loss_hypotheses"), list) else []
        if hypotheses:
            lines.append("- hand review top loss hypotheses:")
            for item in hypotheses[:5]:
                lines.append(
                    f"  - `{item.get('area')}`: {item.get('evidence')} -> {item.get('training_signal')}"
                )
    lines.append("- scope: quick5k is a smoke/API check only; L5/L6 requires formal 100k+ CI gate")
    lines.extend(selector_replay_report_lines(selector_replay))
    report_path.open("a", encoding="utf-8").write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch and launch a gated V5 Slumbot benchmark.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--checkpoint", default="")
    parser.add_argument("--stage", choices=["quick5k", "promotion20k", "formal100k"], default="quick5k")
    parser.add_argument("--tag", default="")
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--sessions", type=int, default=0)
    parser.add_argument("--hands-per-session", type=int, default=0)
    parser.add_argument("--min-training-hands", type=int, default=None)
    parser.add_argument("--allow-early", action="store_true")
    parser.add_argument("--promotion-gate-json", default="", help="For formal100k, explicit promotion20k promotion_gate.json prerequisite.")
    parser.add_argument("--no-require-promotion20k", action="store_true", help="Allow formal100k planning without a strong promotion20k gate.")
    parser.add_argument("--no-require-quality-gate", action="store_true", help="Allow promotion/formal planning even when scorecard quality gate is WARN/FAIL.")
    parser.add_argument("--max-health-age-seconds", type=int, default=600)
    parser.add_argument("--no-health-age-check", action="store_true")
    parser.add_argument("--terminal-endpoint-status-json", default="", help="Fail-closed frozen endpoint PASS evidence for a finished run.")
    parser.add_argument("--terminal-protocol-status-json", default="", help="Matching finished protocol PASS evidence for a finished run.")
    parser.add_argument("--sleep-seconds", type=float, default=300.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Do not launch even if READY.")
    parser.add_argument("--preflight-only", action="store_true", help="If READY, freeze the checkpoint and run local preflight, then exit without launching Slumbot.")
    parser.add_argument("--no-preflight", action="store_true", help="Skip local frozen-checkpoint preflight before launch.")
    parser.add_argument("--preflight-device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument(
        "--launch-path",
        choices=["direct", "wrapper"],
        default="direct",
        help="How to run Slumbot sessions. Direct bypasses bench_v55_slumbot.ps1; wrapper is retained for rollback.",
    )
    parser.add_argument("--direct-poll-seconds", type=float, default=30.0)
    parser.add_argument(
        "--direct-stall-timeout-seconds",
        type=float,
        default=600.0,
        help="Abort direct launch if any live session still has zero hand/dump bytes after this many seconds. Use 0 to disable.",
    )
    parser.add_argument("--no-direct-low-priority", action="store_true", help="Do not force direct child sessions to BelowNormal priority.")
    parser.add_argument(
        "--policy-mode",
        choices=["greedy", "greedy-guarded", "preflop-callguard", "sample", "guarded", "preflop-mixed"],
        default="greedy",
        help="Action selector for Slumbot sessions. Default keeps official cadence greedy.",
    )
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--guarded-allin-max-spr", type=float, default=2.0)
    parser.add_argument("--guarded-allin-min-prob", type=float, default=0.65)
    parser.add_argument("--callguard-min-prob", type=float, default=0.20)
    parser.add_argument("--callguard-ratio", type=float, default=0.65)
    parser.add_argument("--callguard-include-open", action="store_true")
    parser.add_argument("--no-selector-replay", action="store_true", help="Skip offline selector replay after a successful benchmark.")
    parser.add_argument("--selector-replay-device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument(
        "--selector-replay-policies",
        default="greedy,greedy-guarded,preflop-callguard,preflop-callguard-open",
    )
    parser.add_argument("--selector-replay-limit", type=int, default=0, help="Optional max hero decisions for selector replay.")
    parser.add_argument(
        "--selector-replay-max-planned-hands",
        type=int,
        default=25_000,
        help="Run selector replay automatically only when planned benchmark hands are at or below this threshold.",
    )
    parser.add_argument("--plan-json", default="")
    parser.add_argument("--plan-md", default="")
    parser.add_argument("--status-json", default="")
    parser.add_argument("--log", default="")
    parser.add_argument("--append-report", default="")
    args = parser.parse_args()
    if args.preflight_only and args.no_preflight:
        parser.error("--preflight-only requires preflight; remove --no-preflight")

    run_dir = Path(args.run_dir)
    status_path = Path(args.status_json) if args.status_json else run_dir / f"slumbot_{args.stage}_launch_status.json"
    log_path = Path(args.log) if args.log else run_dir / f"slumbot_{args.stage}_launch_watch.log"
    report_path = Path(args.append_report) if args.append_report else None

    def log(message: str) -> None:
        line = f"{now_iso()} {message}"
        print(line, flush=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.open("a", encoding="utf-8").write(line + "\n")

    log(
        "slumbot benchmark launcher started "
        f"run_dir={run_dir} stage={args.stage} dry_run={args.dry_run} launch_path={args.launch_path}"
    )
    while True:
        plan = refresh_plan(args)
        write_json(
            status_path,
            {
                "checked_at": now_iso(),
                "state": "WAITING" if plan["overall"] == "BLOCKED" else plan["overall"],
                "launch_path": args.launch_path,
                "plan": plan,
            },
        )
        log(
            f"plan overall={plan['overall']} checkpoint_iter={plan['checkpoint'].get('iteration')} "
            f"checkpoint_hands={plan['checkpoint'].get('total_hands')} tag={plan['tag']}"
        )

        launchable = plan["overall"] in {"READY", "READY_WITH_WARNINGS"}
        if plan["overall"] == "READY_WITH_WARNINGS":
            log("READY_WITH_WARNINGS has no failed required checks; launching with recorded warnings")
        if launchable:
            if args.dry_run and not args.preflight_only:
                write_json(status_path, {"checked_at": now_iso(), "state": "DRY_RUN_READY", "launch_path": args.launch_path, "plan": plan})
                log("dry-run ready; exiting without benchmark")
                return 0

            checkpoint_path = Path(plan["checkpoint_path"])
            frozen_path = Path(plan["output_dir"]) / f"bench_v55_{plan['tag']}_checkpoint.pt"
            write_json(status_path, {"checked_at": now_iso(), "state": "FREEZING", "launch_path": args.launch_path, "plan": plan, "frozen_checkpoint": str(frozen_path)})
            try:
                frozen_summary = freeze_checkpoint(checkpoint_path, frozen_path, plan["checkpoint"])
            except Exception as exc:
                retry_state = {
                    "checked_at": now_iso(),
                    "state": "FREEZE_RETRY",
                    "launch_path": args.launch_path,
                    "plan": plan,
                    "frozen_checkpoint": str(frozen_path),
                    "error": str(exc),
                }
                write_json(status_path, retry_state)
                log(f"freeze failed; will retry after next poll: {exc}")
                if args.once:
                    return 1
                time.sleep(args.sleep_seconds)
                continue
            log(f"frozen checkpoint={frozen_path} iter={frozen_summary.get('iteration')} hands={frozen_summary.get('total_hands')}")

            preflight_summary = None
            if not args.no_preflight:
                write_json(
                    status_path,
                    {
                        "checked_at": now_iso(),
                        "state": "PREFLIGHT",
                        "launch_path": args.launch_path,
                        "plan": plan,
                        "frozen_checkpoint": str(frozen_path),
                        "frozen_summary": frozen_summary,
                    },
                )
                preflight_summary = run_preflight(args, plan, frozen_path)
                log(
                    f"preflight status={preflight_summary.get('overall')} "
                    f"json={preflight_summary.get('preflight_json')}"
                )
                if preflight_summary.get("overall") != "PASS":
                    write_json(
                        status_path,
                        {
                            "checked_at": now_iso(),
                            "state": "FAIL",
                            "launch_path": args.launch_path,
                            "plan": plan,
                            "frozen_checkpoint": str(frozen_path),
                            "frozen_summary": frozen_summary,
                            "preflight": preflight_summary,
                        },
                    )
                    return 1

            if args.preflight_only:
                write_json(
                    status_path,
                    {
                        "checked_at": now_iso(),
                        "state": "PREFLIGHT_ONLY_PASS",
                        "launch_path": args.launch_path,
                        "plan": plan,
                        "frozen_checkpoint": str(frozen_path),
                        "frozen_summary": frozen_summary,
                        "preflight": preflight_summary,
                    },
                )
                log("preflight-only ready; exiting without benchmark")
                return 0

            write_json(
                status_path,
                {
                    "checked_at": now_iso(),
                    "state": "RUNNING",
                    "launch_path": args.launch_path,
                    "plan": plan,
                    "frozen_checkpoint": str(frozen_path),
                    "frozen_summary": frozen_summary,
                    "preflight": preflight_summary,
                },
            )
            result = run_benchmark(args, plan, frozen_path)
            selector_replay = None
            planned_hands = int(plan.get("planned_hands") or 0)
            if (
                result["status"] == "PASS"
                and not args.no_selector_replay
                and planned_hands <= int(args.selector_replay_max_planned_hands)
            ):
                write_json(
                    status_path,
                    {
                        "checked_at": now_iso(),
                        "state": "SELECTOR_REPLAY",
                        "launch_path": args.launch_path,
                        "plan": plan,
                        "frozen_checkpoint": str(frozen_path),
                        "frozen_summary": frozen_summary,
                        "preflight": preflight_summary,
                        "benchmark_result": result,
                    },
                )
                log(f"running selector replay for tag={plan['tag']} planned_hands={planned_hands}")
                selector_replay = run_selector_replay(args, plan, frozen_path)
                log(
                    f"selector replay status={selector_replay.get('status')} "
                    f"json={selector_replay.get('selector_replay_json')}"
                )
                if selector_replay.get("status") == "PASS":
                    log("rerunning promotion gate with selector replay")
                    selector_gate = rerun_promotion_gate_with_selector(args, plan, frozen_path, selector_replay)
                    selector_replay["promotion_gate"] = selector_gate
                    if selector_gate.get("summary") is not None:
                        result["promotion_summary"] = selector_gate.get("summary")
                    log(
                        "selector promotion gate "
                        f"status={selector_gate.get('status')} overall={selector_gate.get('promotion_gate_overall')} "
                        f"selector_clean={selector_gate.get('selector_replay_clean')}"
                    )
            elif result["status"] == "PASS" and not args.no_selector_replay:
                selector_replay = {
                    "status": "SKIPPED",
                    "reason": (
                        f"planned_hands {planned_hands:,} > "
                        f"selector_replay_max_planned_hands {int(args.selector_replay_max_planned_hands):,}"
                    ),
                    "checked_at": now_iso(),
                }
            write_json(
                status_path,
                {
                    "checked_at": now_iso(),
                    "state": result["status"],
                    "launch_path": args.launch_path,
                    "plan": plan,
                    "frozen_checkpoint": str(frozen_path),
                    "frozen_summary": frozen_summary,
                    "preflight": preflight_summary,
                    "benchmark_result": result,
                    "selector_replay": selector_replay,
                },
            )
            append_report(report_path, plan, frozen_summary, result, selector_replay)
            log(f"benchmark finished status={result['status']} elapsed={result['elapsed_seconds']:.1f}s")
            return 0 if result["status"] == "PASS" else 1

        if args.once:
            log("once mode complete")
            return 0 if plan["overall"] in {"READY", "READY_WITH_WARNINGS"} else 1
        time.sleep(args.sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
