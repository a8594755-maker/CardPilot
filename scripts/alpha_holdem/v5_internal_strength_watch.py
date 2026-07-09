#!/usr/bin/env python3
"""Run V5 internal strength probes at checkpoint/pool-snapshot gates.

This watcher is intentionally lightweight and read-only with respect to
training. It waits for specified checkpoint iterations, verifies health and
metadata, then launches v5_internal_strength_probe.py and records artifacts.
It never calls Slumbot and must not be used as an L5/L6 promotion gate.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch


SCRIPT_DIR = Path(__file__).resolve().parent
PROBE_SCRIPT = SCRIPT_DIR / "v5_internal_strength_probe.py"
EXPECTED_METADATA = {
    "version": "v5.zero",
    "env_version": "v55",
    "obs_version": "v55",
    "action_space_version": "9slot_v5",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"_load_error": str(exc)}


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def set_below_normal(pid: int) -> dict[str, Any]:
    if sys.platform != "win32":
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
            cwd=str(Path.cwd()),
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


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True}
    try:
        obj = torch.load(path, map_location="cpu", weights_only=False)
    except Exception as exc:
        return {"_load_error": str(exc)}
    if not isinstance(obj, dict):
        return {"_load_error": f"checkpoint is {type(obj).__name__}, not dict"}
    return obj


def pool_hands(checkpoint: dict[str, Any]) -> list[int | None]:
    pool = checkpoint.get("pool_snapshots") or []
    if not isinstance(pool, list):
        return []
    values: list[int | None] = []
    for item in pool:
        if isinstance(item, dict):
            hands = item.get("hands", item.get("total_hands"))
            values.append(int(hands) if hands is not None else None)
        else:
            values.append(None)
    return values


def check_ready(
    run_dir: Path,
    target_iteration: int,
    *,
    require_health_pass: bool,
    require_current_pool_snapshot: bool,
) -> tuple[str, dict[str, Any]]:
    checkpoint_path = run_dir / "latest.pt"
    health = load_json(run_dir / "health_status.json")
    checkpoint = load_checkpoint(checkpoint_path)
    checks: list[dict[str, str]] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    if checkpoint.get("_missing"):
        add("checkpoint_load", "PENDING", f"missing: {checkpoint_path}")
    elif checkpoint.get("_load_error"):
        add("checkpoint_load", "PENDING", str(checkpoint["_load_error"]))
    else:
        add("checkpoint_load", "PASS", f"loaded: {checkpoint_path}")

    checkpoint_ready = not checkpoint.get("_missing") and not checkpoint.get("_load_error")
    ckpt_iter = checkpoint.get("iteration") if checkpoint_ready else None
    total_hands = checkpoint.get("total_hands") if checkpoint_ready else None
    checkpoint_config = checkpoint.get("config") if isinstance(checkpoint.get("config"), dict) else {}
    pool_strategy = checkpoint.get("pool_strategy") or checkpoint_config.get("pool_strategy")

    if not checkpoint_ready:
        add("checkpoint_iteration", "PENDING", "checkpoint unavailable")
    elif ckpt_iter is None:
        add("checkpoint_iteration", "PENDING", "iteration missing")
    elif int(ckpt_iter) >= target_iteration:
        add("checkpoint_iteration", "PASS", f"checkpoint iteration {ckpt_iter} >= {target_iteration}")
    else:
        add("checkpoint_iteration", "PENDING", f"checkpoint iteration {ckpt_iter} < {target_iteration}")

    for key, expected in EXPECTED_METADATA.items():
        if not checkpoint_ready:
            add(key, "PENDING", "checkpoint unavailable")
            continue
        actual = checkpoint.get(key)
        if actual == expected:
            add(key, "PASS", f"{key}={actual}")
        else:
            add(key, "FAIL", f"{key}={actual!r}, expected {expected!r}")

    if require_health_pass:
        health_overall = health.get("overall")
        if health_overall == "PASS":
            add("health", "PASS", "health_status overall PASS")
        elif health.get("_missing"):
            add("health", "PENDING", "health_status.json missing")
        else:
            add("health", "PENDING", f"health_status overall {health_overall!r}")

    hands = pool_hands(checkpoint) if checkpoint_ready else []
    if require_current_pool_snapshot:
        if str(pool_strategy or "").lower() == "loss-kbest":
            add(
                "pool_current_snapshot",
                "PASS",
                "not required for loss-kbest; active pool keeps best historical snapshots and may prune the current checkpoint",
            )
        elif not checkpoint_ready:
            add("pool_current_snapshot", "PENDING", "checkpoint unavailable")
        elif ckpt_iter is None or int(ckpt_iter) < target_iteration:
            add("pool_current_snapshot", "PENDING", "target checkpoint not reached")
        elif not hands:
            add("pool_current_snapshot", "PENDING", "pool hand counts missing")
        elif total_hands is None:
            add("pool_current_snapshot", "FAIL", "checkpoint total_hands missing")
        elif int(total_hands) in hands:
            add("pool_current_snapshot", "PASS", f"pool contains current checkpoint hands {total_hands}; pool_hands={hands}")
        else:
            add("pool_current_snapshot", "PENDING", f"pool does not contain checkpoint hands {total_hands}; pool_hands={hands}")

    fail = [item for item in checks if item["status"] == "FAIL"]
    pending = [item for item in checks if item["status"] == "PENDING"]
    overall = "FAIL" if fail else "PENDING" if pending else "READY"
    return overall, {
        "checked_at": now_iso(),
        "target_iteration": target_iteration,
        "overall": overall,
        "checks": checks,
        "checkpoint": {
            "path": str(checkpoint_path),
            "iteration": ckpt_iter,
            "total_hands": total_hands,
            "pool_hands": hands,
        },
        "health_overall": health.get("overall"),
    }


def run_probe(args: argparse.Namespace, target_iteration: int) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    out_prefix = run_dir / f"internal_strength_probe_iter{target_iteration}_{args.hands}h"
    out_json = Path(str(out_prefix) + ".json")
    out_md = Path(str(out_prefix) + ".md")
    if out_json.exists() and out_md.exists() and not args.force:
        return {
            "status": "SKIPPED_EXISTS",
            "target_iteration": target_iteration,
            "out_json": str(out_json),
            "out_md": str(out_md),
            "checked_at": now_iso(),
        }

    cmd = [
        args.python,
        str(PROBE_SCRIPT),
        "--checkpoint",
        str(run_dir / "latest.pt"),
        "--hands",
        str(args.hands),
        "--max-pool-snapshots",
        str(args.max_pool_snapshots),
        "--device",
        args.device,
        "--starting-stack",
        str(args.starting_stack),
        "--seed",
        str(args.seed + target_iteration),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    ]
    if args.opponents:
        cmd.extend(["--opponents", *args.opponents])

    started = time.time()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        cmd,
        cwd=str(Path.cwd()),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    priority = {"status": "SKIPPED", "reason": "disabled"}
    if not args.no_low_priority:
        priority = set_below_normal(proc.pid)
    stdout, _ = proc.communicate()
    stdout = stdout or ""
    return {
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "target_iteration": target_iteration,
        "pid": proc.pid,
        "priority": priority,
        "returncode": proc.returncode,
        "elapsed_seconds": time.time() - started,
        "out_json": str(out_json),
        "out_md": str(out_md),
        "command": cmd,
        "output_tail": stdout[-4000:],
        "checked_at": now_iso(),
    }


def append_launch_report(report_path: Path, probe_result: dict[str, Any], summary: dict[str, Any] | None) -> None:
    if not report_path:
        return
    report_path.parent.mkdir(parents=True, exist_ok=True)
    target = probe_result.get("target_iteration")
    status = probe_result.get("status")
    lines = [
        "",
        f"## Internal Strength Watch Gate {target}",
        "",
        f"- checked at: `{probe_result.get('checked_at')}`",
        f"- status: `{status}`",
        f"- json: `{probe_result.get('out_json')}`",
        f"- markdown: `{probe_result.get('out_md')}`",
        "- scope: internal fixed-opponent probe only; not Slumbot and not an L5/L6 claim",
    ]
    if summary:
        trends = summary.get("trends", {})
        lines.append(f"- checkpoint iteration: `{summary.get('checkpoint', {}).get('iteration')}`")
        lines.append(f"- checkpoint hands: `{summary.get('checkpoint', {}).get('total_hands'):,}`")
        for opponent, trend in trends.items():
            lines.append(
                f"- `{opponent}` trend: latest_is_best=`{trend.get('latest_is_best')}`, "
                f"strictly_increasing=`{trend.get('strictly_increasing')}`, "
                f"positive_steps=`{trend.get('positive_adjacent_steps')}/{trend.get('total_adjacent_steps')}`"
            )
    report_path.open("a", encoding="utf-8").write("\n".join(lines) + "\n")


def load_probe_summary(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        return json.loads(candidate.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def target_iterations(start: int, max_iteration: int, step: int) -> list[int]:
    if step <= 0:
        raise ValueError("--step must be positive")
    if max_iteration < start:
        return []
    return list(range(start, max_iteration + 1, step))


def build_status_payload(
    *,
    run_dir: Path,
    targets: list[int],
    completed: list[int],
    history: list[dict[str, Any]],
    latest_readiness: dict[str, Any] | None = None,
    latest_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    next_target = next((target for target in targets if target not in completed), None)
    readiness = latest_readiness or {}
    checkpoint = readiness.get("checkpoint") if isinstance(readiness.get("checkpoint"), dict) else {}
    payload: dict[str, Any] = {
        "checked_at": now_iso(),
        "run_dir": str(run_dir),
        "targets": targets,
        "completed": completed,
        "next_target": next_target,
        "next_status": readiness.get("overall") if readiness.get("target_iteration") == next_target else None,
        "current_checkpoint_iteration": checkpoint.get("iteration"),
        "current_checkpoint_hands": checkpoint.get("total_hands"),
        "latest_readiness": latest_readiness,
        "latest_probe": latest_probe,
        "history_tail": history[-20:],
    }
    payload["overall"] = (
        "COMPLETE"
        if next_target is None
        else payload["next_status"]
        or (latest_probe or {}).get("status")
        or "PENDING"
    )
    if completed:
        payload["latest_completed_target"] = max(completed)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch V5 gates and run internal strength probes.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--start-iteration", type=int, required=True)
    parser.add_argument("--max-iteration", type=int, required=True)
    parser.add_argument("--step", type=int, default=200)
    parser.add_argument("--hands", type=int, default=200)
    parser.add_argument("--opponents", nargs="+", default=["call-station", "aggressive"])
    parser.add_argument("--max-pool-snapshots", type=int, default=5)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--starting-stack", type=float, default=200.0)
    parser.add_argument("--seed", type=int, default=20260704)
    parser.add_argument("--sleep-seconds", type=float, default=60.0)
    parser.add_argument("--require-health-pass", action="store_true")
    parser.add_argument("--no-require-current-pool-snapshot", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--once", action="store_true", help="Check targets once and exit without waiting.")
    parser.add_argument("--no-low-priority", action="store_true", help="Do not force probe child processes to BelowNormal priority.")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--status-json", default=None)
    parser.add_argument("--log", default=None)
    parser.add_argument("--append-report", default=None)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    status_path = Path(args.status_json) if args.status_json else run_dir / "internal_strength_watch_status.json"
    log_path = Path(args.log) if args.log else run_dir / "internal_strength_watch.log"
    report_path = Path(args.append_report) if args.append_report else None
    targets = target_iterations(args.start_iteration, args.max_iteration, args.step)
    completed: list[int] = []
    history: list[dict[str, Any]] = []

    def log(message: str) -> None:
        line = f"{now_iso()} {message}"
        print(line, flush=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.open("a", encoding="utf-8").write(line + "\n")

    log(
        f"internal strength watcher started run_dir={run_dir} "
        f"targets={targets} hands={args.hands} opponents={args.opponents}"
    )

    while True:
        made_progress = False
        for target in targets:
            if target in completed:
                continue
            overall, readiness = check_ready(
                run_dir,
                target,
                require_health_pass=args.require_health_pass,
                require_current_pool_snapshot=not args.no_require_current_pool_snapshot,
            )
            history.append({"target": target, "readiness": readiness})
            write_json(
                status_path,
                build_status_payload(
                    run_dir=run_dir,
                    targets=targets,
                    completed=completed,
                    history=history,
                    latest_readiness=readiness,
                ),
            )
            log(
                f"target={target} readiness={overall} "
                f"ckpt_iter={readiness['checkpoint'].get('iteration')} "
                f"hands={readiness['checkpoint'].get('total_hands')}"
            )
            if overall == "FAIL":
                log(f"target={target} fail; waiting for operator review")
                if args.once:
                    return
                time.sleep(args.sleep_seconds)
                break
            if overall != "READY":
                if args.once:
                    continue
                time.sleep(args.sleep_seconds)
                break

            probe_result = run_probe(args, target)
            history.append({"target": target, "probe": probe_result})
            if probe_result.get("status") in ("PASS", "SKIPPED_EXISTS"):
                completed.append(target)
                made_progress = True
                summary = load_probe_summary(probe_result.get("out_json"))
                if probe_result.get("status") == "PASS":
                    append_launch_report(report_path, probe_result, summary)
                log(
                    f"target={target} probe={probe_result.get('status')} "
                    f"elapsed={probe_result.get('elapsed_seconds', 0):.1f}s"
                )
            else:
                log(f"target={target} probe failed returncode={probe_result.get('returncode')}")
                write_json(
                    status_path,
                    build_status_payload(
                        run_dir=run_dir,
                        targets=targets,
                        completed=completed,
                        history=history,
                        latest_probe=probe_result,
                    ),
                )
                return

            write_json(
                status_path,
                build_status_payload(
                    run_dir=run_dir,
                    targets=targets,
                    completed=completed,
                    history=history,
                    latest_probe=probe_result,
                ),
            )

        if all(target in completed for target in targets):
            log("all targets complete")
            return
        if args.once:
            log("once mode complete")
            return
        if not made_progress:
            time.sleep(args.sleep_seconds)


if __name__ == "__main__":
    main()
