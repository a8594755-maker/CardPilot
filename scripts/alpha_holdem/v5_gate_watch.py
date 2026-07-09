#!/usr/bin/env python3
"""Watch or verify AlphaHoldem V5 checkpoint gates.

This tool is read-only with respect to training. It checks that the live log,
latest checkpoint, pool snapshots, and fixed-env metadata have reached a
specific gate such as iteration 600 / pool_snapshots 3.

Exit codes:
  0: gate passed
  1: gate reached but failed checks, or checkpoint could not be loaded after grace
  2: gate is still pending
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

from v5_monitor import parse_log


def refresh_health_status(run_dir: Path, python: str) -> dict[str, Any]:
    proc = subprocess.run(
        [
            python,
            "scripts/alpha_holdem/v5_monitor.py",
            "--run-dir",
            str(run_dir),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "exit_code": proc.returncode,
        "output": proc.stdout.strip().splitlines()[-3:],
    }


def file_age_seconds(path: Path, now: datetime) -> float | None:
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None
    return max(0.0, (now - modified).total_seconds())


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_load_error": str(exc)}


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True}
    try:
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    except Exception as exc:
        return {"_load_error": str(exc)}
    if not isinstance(checkpoint, dict):
        return {"_load_error": f"checkpoint is {type(checkpoint).__name__}, not dict"}
    return checkpoint


def pool_snapshots(checkpoint: dict[str, Any]) -> list[Any]:
    pool = checkpoint.get("pool_snapshots")
    if pool is None:
        pool = checkpoint.get("opponent_pool")
    if isinstance(pool, list):
        return pool
    return []


def pool_hands(pool: list[Any]) -> list[int | None]:
    values: list[int | None] = []
    for item in pool:
        if isinstance(item, dict):
            hands = item.get("hands", item.get("total_hands"))
            values.append(int(hands) if hands is not None else None)
        else:
            values.append(None)
    return values


def approx_equal(a: Any, b: float, tolerance: float = 1e-6) -> bool:
    try:
        return abs(float(a) - b) <= tolerance
    except Exception:
        return False


def fresh_from_zero_lineage(checkpoint: dict[str, Any]) -> bool:
    """Return whether a checkpoint belongs to the V5 random-init lineage.

    Older fresh V5 checkpoints did not persist this field, so the fallback is:
    v5.zero with no recorded resume source.
    """
    if "fresh_from_zero_lineage" in checkpoint:
        return bool(checkpoint.get("fresh_from_zero_lineage"))
    return checkpoint.get("version") == "v5.zero" and checkpoint.get("resume") is None


def config_int(config: dict[str, Any], key: str) -> int | None:
    try:
        value = int(config.get(key) or 0)
    except Exception:
        return None
    return value if value > 0 else None


def next_multiple_after(value: int, interval: int | None) -> int | None:
    if not interval:
        return None
    return ((value // interval) + 1) * interval


def expected_stored_pool_snapshots(target_iteration: int | None, snapshot_interval: int | None, k_best: int | None) -> int | None:
    if not target_iteration or not snapshot_interval:
        return None
    expected = target_iteration // snapshot_interval
    if k_best and k_best > 0:
        expected = min(expected, k_best)
    return expected


def evaluate_gate(
    run_dir: Path,
    target_iteration: int,
    expected_pool_snapshots: int,
    expected_env_version: str,
    expected_obs_version: str,
    expected_action_space_version: str,
    expected_stack_bb: float,
    expected_opponent_assignment: str,
    expected_pool_strategy: str,
    checkpoint_load_grace_seconds: float,
    require_current_pool_snapshot: bool,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    manifest = load_json(run_dir / "run_manifest.json")
    health = load_json(run_dir / "health_status.json")
    rows = parse_log(run_dir / "latest_train.log")
    latest = rows[-1] if rows else None
    checkpoint_path = run_dir / "latest.pt"
    checkpoint = load_checkpoint(checkpoint_path)
    pool = pool_snapshots(checkpoint)
    checkpoint_ready = not checkpoint.get("_missing") and not checkpoint.get("_load_error")
    checkpoint_age = file_age_seconds(checkpoint_path, now)
    live_reached = latest is not None and int(latest["iteration"]) >= target_iteration

    checks: list[dict[str, str]] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    if latest is None:
        add("training_log", "PENDING", "No parsed latest_train.log rows")
    elif int(latest["iteration"]) >= target_iteration:
        add("live_iteration", "PASS", f"latest log iteration {latest['iteration']} >= {target_iteration}")
    else:
        add("live_iteration", "PENDING", f"latest log iteration {latest['iteration']} < {target_iteration}")

    if checkpoint.get("_missing"):
        status = "FAIL" if live_reached else "PENDING"
        add("checkpoint_load", status, "latest.pt is missing")
    elif checkpoint.get("_load_error"):
        load_error = str(checkpoint["_load_error"])
        in_grace = checkpoint_age is not None and checkpoint_age <= checkpoint_load_grace_seconds
        if live_reached and in_grace:
            add(
                "checkpoint_load",
                "PENDING",
                f"{load_error}; latest.pt age {checkpoint_age:.1f}s <= grace {checkpoint_load_grace_seconds:.1f}s",
            )
        else:
            add("checkpoint_load", "FAIL", load_error)
    else:
        add("checkpoint_load", "PASS", "latest.pt loaded")

    ckpt_iteration = checkpoint.get("iteration")
    if not checkpoint_ready:
        add("checkpoint_iteration", "PENDING", "checkpoint unavailable")
    elif ckpt_iteration is None:
        add("checkpoint_iteration", "PENDING", "checkpoint iteration missing")
    elif int(ckpt_iteration) >= target_iteration:
        add("checkpoint_iteration", "PASS", f"checkpoint iteration {ckpt_iteration} >= {target_iteration}")
    else:
        add("checkpoint_iteration", "PENDING", f"checkpoint iteration {ckpt_iteration} < {target_iteration}")

    pool_hand_values = pool_hands(pool)

    if not checkpoint_ready:
        add("pool_snapshots", "PENDING", "checkpoint unavailable")
    elif len(pool) >= expected_pool_snapshots:
        add("pool_snapshots", "PASS", f"pool snapshots {len(pool)} >= {expected_pool_snapshots}")
    else:
        add("pool_snapshots", "PENDING", f"pool snapshots {len(pool)} < {expected_pool_snapshots}")

    if require_current_pool_snapshot:
        total_hands = checkpoint.get("total_hands")
        if not checkpoint_ready:
            add("pool_current_snapshot", "PENDING", "checkpoint unavailable")
        elif ckpt_iteration is None or int(ckpt_iteration) < target_iteration:
            add("pool_current_snapshot", "PENDING", "target checkpoint not reached")
        elif total_hands is None:
            add("pool_current_snapshot", "FAIL", "checkpoint total_hands missing")
        elif not pool_hand_values:
            add("pool_current_snapshot", "FAIL", "pool hand counts missing")
        elif int(total_hands) in pool_hand_values:
            add("pool_current_snapshot", "PASS", f"pool contains current checkpoint hands {total_hands}; pool_hands={pool_hand_values}")
        else:
            add(
                "pool_current_snapshot",
                "FAIL",
                f"pool does not contain checkpoint hands {total_hands}; pool_hands={pool_hand_values}",
            )

    expected_metadata = {
        "version": "v5.zero",
        "env_version": expected_env_version,
        "obs_version": expected_obs_version,
        "action_space_version": expected_action_space_version,
    }
    for key, expected in expected_metadata.items():
        actual = checkpoint.get(key)
        if not checkpoint_ready:
            add(key, "PENDING", "checkpoint unavailable")
        elif actual == expected:
            add(key, "PASS", f"{key}={actual}")
        else:
            add(key, "FAIL", f"{key}={actual!r}, expected {expected!r}")

    if not checkpoint_ready:
        add("starting_stack_bb", "PENDING", "checkpoint unavailable")
    elif approx_equal(checkpoint.get("starting_stack_bb"), expected_stack_bb):
        add("starting_stack_bb", "PASS", f"starting_stack_bb={checkpoint.get('starting_stack_bb')}")
    else:
        add(
            "starting_stack_bb",
            "FAIL",
            f"starting_stack_bb={checkpoint.get('starting_stack_bb')!r}, expected {expected_stack_bb}",
        )

    if not checkpoint_ready:
        add("actual_hand_accounting", "PENDING", "checkpoint unavailable")
    elif checkpoint.get("actual_hand_accounting") is True:
        add("actual_hand_accounting", "PASS", "actual_hand_accounting=True")
    else:
        add(
            "actual_hand_accounting",
            "FAIL",
            f"actual_hand_accounting={checkpoint.get('actual_hand_accounting')!r}, expected True",
        )

    checkpoint_config = checkpoint.get("config") if isinstance(checkpoint.get("config"), dict) else {}
    if expected_opponent_assignment:
        actual_assignment = checkpoint_config.get("opponent_assignment")
        if not checkpoint_ready:
            add("opponent_assignment", "PENDING", "checkpoint unavailable")
        elif actual_assignment == expected_opponent_assignment:
            add("opponent_assignment", "PASS", f"opponent_assignment={actual_assignment}")
        else:
            add(
                "opponent_assignment",
                "FAIL",
                f"opponent_assignment={actual_assignment!r}, expected {expected_opponent_assignment!r}",
            )

    if expected_pool_strategy:
        actual_pool_strategy = checkpoint.get("pool_strategy") or checkpoint_config.get("pool_strategy")
        if not checkpoint_ready:
            add("pool_strategy", "PENDING", "checkpoint unavailable")
        elif actual_pool_strategy == expected_pool_strategy:
            add("pool_strategy", "PASS", f"pool_strategy={actual_pool_strategy}")
        else:
            add(
                "pool_strategy",
                "FAIL",
                f"pool_strategy={actual_pool_strategy!r}, expected {expected_pool_strategy!r}",
            )

    if not checkpoint_ready:
        add("fresh_from_zero_lineage", "PENDING", "checkpoint unavailable")
    elif fresh_from_zero_lineage(checkpoint):
        add(
            "fresh_from_zero_lineage",
            "PASS",
            f"fresh_from_zero_lineage=True; resume={checkpoint.get('resume')!r}",
        )
    else:
        add(
            "fresh_from_zero_lineage",
            "FAIL",
            f"fresh_from_zero_lineage={checkpoint.get('fresh_from_zero_lineage')!r}; "
            f"resume={checkpoint.get('resume')!r}",
        )

    health_overall = health.get("overall")
    if health_overall == "PASS":
        add("health_status", "PASS", "latest health_status.json is PASS")
    elif health_overall:
        add("health_status", "FAIL" if health_overall == "FAIL" else "WARN", f"health overall {health_overall}")
    else:
        add("health_status", "PENDING", "health_status.json missing or unreadable")

    if any(c["status"] == "FAIL" for c in checks):
        overall = "FAIL"
    elif any(c["status"] == "PENDING" for c in checks):
        overall = "PENDING"
    elif any(c["status"] == "WARN" for c in checks):
        overall = "WARN"
    else:
        overall = "PASS"

    latest_iteration = latest.get("iteration") if isinstance(latest, dict) else None
    latest_hands = latest.get("hands") if isinstance(latest, dict) else None
    checkpoint_hands = checkpoint.get("total_hands")
    live_reached_target = latest_iteration is not None and int(latest_iteration) >= int(target_iteration)
    checkpoint_reached_target = ckpt_iteration is not None and int(ckpt_iteration) >= int(target_iteration)

    return {
        "run_dir": str(run_dir),
        "run_id": manifest.get("run_id") or checkpoint.get("run_id"),
        "checked_at": now.isoformat(),
        "config": manifest.get("config") if isinstance(manifest.get("config"), dict) else {},
        "target_iteration": target_iteration,
        "expected_pool_snapshots": expected_pool_snapshots,
        "overall": overall,
        "live_iteration": latest_iteration,
        "live_hands": latest_hands,
        "checkpoint_iteration": ckpt_iteration,
        "checkpoint_hands": checkpoint_hands,
        "live_reached_target": live_reached_target,
        "checkpoint_reached_target": checkpoint_reached_target,
        "remaining_live_iterations": (
            max(0, int(target_iteration) - int(latest_iteration)) if latest_iteration is not None else None
        ),
        "remaining_checkpoint_iterations": (
            max(0, int(target_iteration) - int(ckpt_iteration)) if ckpt_iteration is not None else None
        ),
        "latest": latest,
        "checkpoint": {
            "iteration": ckpt_iteration,
            "total_hands": checkpoint_hands,
            "version": checkpoint.get("version"),
            "env_version": checkpoint.get("env_version"),
            "obs_version": checkpoint.get("obs_version"),
            "action_space_version": checkpoint.get("action_space_version"),
            "starting_stack_bb": checkpoint.get("starting_stack_bb"),
            "actual_hand_accounting": checkpoint.get("actual_hand_accounting"),
            "resume": checkpoint.get("resume"),
            "fresh_from_zero_lineage": fresh_from_zero_lineage(checkpoint) if checkpoint_ready else None,
            "lineage_root_run_id": checkpoint.get("lineage_root_run_id"),
            "lineage_parent_checkpoint": checkpoint.get("lineage_parent_checkpoint"),
            "opponent_assignment": checkpoint_config.get("opponent_assignment"),
            "pool_strategy": checkpoint.get("pool_strategy") or checkpoint_config.get("pool_strategy"),
            "pool_snapshots": len(pool),
            "pool_hands": pool_hand_values,
            "load_age_seconds": checkpoint_age,
        },
        "health_overall": health_overall,
        "checks": checks,
    }


def write_outputs(run_dir: Path, target_iteration: int, summary: dict[str, Any]) -> None:
    json_path = run_dir / f"gate_{target_iteration}_status.json"
    md_path = run_dir / f"gate_{target_iteration}_status.md"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    latest = summary.get("latest") or {}
    checkpoint = summary.get("checkpoint") or {}
    lines = [
        f"# V5 Gate {target_iteration} Status",
        "",
        f"- Run id: `{summary.get('run_id')}`",
        f"- Checked at: `{summary.get('checked_at')}`",
        f"- Overall: **{summary.get('overall')}**",
        f"- Target iteration: `{target_iteration}`",
        f"- Expected pool snapshots: `{summary.get('expected_pool_snapshots')}`",
        "",
        "Live log:",
        "",
        f"- Iteration: `{latest.get('iteration')}`",
        f"- Hands: `{latest.get('hands')}`",
        f"- Pool size: `{latest.get('pool_size')}`",
        f"- Entropy: `{latest.get('entropy')}`",
        f"- Value loss: `{latest.get('value_loss')}`",
        "",
        "Checkpoint:",
        "",
        f"- Iteration: `{checkpoint.get('iteration')}`",
        f"- Hands: `{checkpoint.get('total_hands')}`",
        f"- Version: `{checkpoint.get('version')}`",
        f"- Env / obs: `{checkpoint.get('env_version')}` / `{checkpoint.get('obs_version')}`",
        f"- Action space: `{checkpoint.get('action_space_version')}`",
        f"- Starting stack bb: `{checkpoint.get('starting_stack_bb')}`",
        f"- Actual hand accounting: `{checkpoint.get('actual_hand_accounting')}`",
        f"- Resume: `{checkpoint.get('resume')}`",
        f"- Fresh-from-zero lineage: `{checkpoint.get('fresh_from_zero_lineage')}`",
        f"- Lineage root run id: `{checkpoint.get('lineage_root_run_id')}`",
        f"- Lineage parent checkpoint: `{checkpoint.get('lineage_parent_checkpoint')}`",
        f"- Opponent assignment: `{checkpoint.get('opponent_assignment')}`",
        f"- Pool strategy: `{checkpoint.get('pool_strategy')}`",
        f"- Pool snapshots: `{checkpoint.get('pool_snapshots')}`",
        f"- Pool hands: `{checkpoint.get('pool_hands')}`",
        "",
        "Checks:",
        "",
    ]
    for check in summary.get("checks", []):
        lines.append(f"- {check['status']}: `{check['name']}` - {check['detail']}")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


def append_report_if_pass(report_path: Path, target_iteration: int, summary: dict[str, Any]) -> bool:
    if summary.get("overall") != "PASS":
        return False
    if not report_path.exists():
        return False

    title = f"## Gate {target_iteration} Verification"
    report = report_path.read_text(encoding="utf-8", errors="replace")
    if title in report:
        return False

    checked_local = datetime.fromisoformat(str(summary["checked_at"])).astimezone()
    latest = summary.get("latest") or {}
    checkpoint = summary.get("checkpoint") or {}

    config = summary.get("config") if isinstance(summary.get("config"), dict) else {}
    save_interval = config_int(config, "save_interval")
    snapshot_interval = config_int(config, "snapshot_every")
    k_best = config_int(config, "k_best")
    next_checkpoint = next_multiple_after(target_iteration, save_interval) or (target_iteration + 100)
    next_snapshot = next_multiple_after(target_iteration, snapshot_interval) or (target_iteration + 200)
    next_snapshot_expected_pool = expected_stored_pool_snapshots(next_snapshot, snapshot_interval, k_best)
    next_snapshot_detail = f"- iteration {next_snapshot}: next opponent-pool snapshot"
    if next_snapshot_expected_pool is not None:
        next_snapshot_detail += f" (expected stored snapshots: {next_snapshot_expected_pool})"
    lines = [
        title,
        "",
        f"Automatically appended by `scripts/alpha_holdem/v5_gate_watch.py` at {checked_local:%Y-%m-%d %H:%M %Z}:",
        "",
        "- overall: PASS",
        f"- live iteration: {latest.get('iteration')}",
        f"- live hands: {latest.get('hands')}",
        f"- checkpoint iteration: {checkpoint.get('iteration')}",
        f"- checkpoint hands: {checkpoint.get('total_hands')}",
        f"- checkpoint version: `{checkpoint.get('version')}`",
        f"- checkpoint env version: `{checkpoint.get('env_version')}`",
        f"- checkpoint obs version: `{checkpoint.get('obs_version')}`",
        f"- checkpoint action space version: `{checkpoint.get('action_space_version')}`",
        f"- checkpoint starting stack: {checkpoint.get('starting_stack_bb')}bb",
        f"- checkpoint actual hand accounting: `{checkpoint.get('actual_hand_accounting')}`",
        f"- checkpoint resume source: `{checkpoint.get('resume')}`",
        f"- checkpoint fresh-from-zero lineage: `{checkpoint.get('fresh_from_zero_lineage')}`",
        f"- checkpoint lineage root run id: `{checkpoint.get('lineage_root_run_id')}`",
        f"- checkpoint lineage parent checkpoint: `{checkpoint.get('lineage_parent_checkpoint')}`",
        f"- checkpoint opponent assignment: `{checkpoint.get('opponent_assignment')}`",
        f"- checkpoint pool strategy: `{checkpoint.get('pool_strategy')}`",
        f"- checkpoint pool snapshots: {checkpoint.get('pool_snapshots')}",
        f"- pool snapshot hand counts: `{checkpoint.get('pool_hands')}`",
        f"- health status: {summary.get('health_overall')}",
        "",
        "Next gates:",
        "",
        f"- iteration {next_checkpoint}: checkpoint stability save",
        next_snapshot_detail,
        "- no Slumbot success or L6 claim is allowed from this gate alone",
        "",
    ]
    report_path.write_text(report.rstrip() + "\n\n" + "\n".join(lines), encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--target-iteration", type=int, required=True)
    parser.add_argument("--expected-pool-snapshots", type=int, required=True)
    parser.add_argument("--expected-env-version", default="v55")
    parser.add_argument("--expected-obs-version", default="v55")
    parser.add_argument("--expected-action-space-version", default="9slot_v5")
    parser.add_argument("--expected-stack-bb", type=float, default=200.0)
    parser.add_argument(
        "--expected-opponent-assignment",
        default="",
        help="Optional checkpoint config opponent_assignment value to require, e.g. per-iteration.",
    )
    parser.add_argument(
        "--expected-pool-strategy",
        default="",
        help="Optional checkpoint pool_strategy value to require, e.g. loss-kbest.",
    )
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--timeout-seconds", type=float, default=0.0)
    parser.add_argument(
        "--checkpoint-load-grace-seconds",
        type=float,
        default=300.0,
        help="Treat transient latest.pt load failures as pending while the file was modified within this window.",
    )
    parser.add_argument(
        "--require-current-pool-snapshot",
        action="store_true",
        help="Require the latest stored pool snapshot hand count to equal the checkpoint total_hands.",
    )
    parser.add_argument(
        "--append-report",
        default="",
        help="Optional markdown report to append when the gate reaches PASS.",
    )
    parser.add_argument(
        "--refresh-health",
        action="store_true",
        help="Run v5_monitor.py before each gate check so health_status.json is fresh.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used for --refresh-health.",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    start = time.monotonic()
    summary: dict[str, Any] | None = None

    while True:
        health_refresh = None
        if args.refresh_health:
            health_refresh = refresh_health_status(run_dir, args.python)
        summary = evaluate_gate(
            run_dir=run_dir,
            target_iteration=args.target_iteration,
            expected_pool_snapshots=args.expected_pool_snapshots,
            expected_env_version=args.expected_env_version,
            expected_obs_version=args.expected_obs_version,
            expected_action_space_version=args.expected_action_space_version,
            expected_stack_bb=args.expected_stack_bb,
            expected_opponent_assignment=args.expected_opponent_assignment,
            expected_pool_strategy=args.expected_pool_strategy,
            checkpoint_load_grace_seconds=args.checkpoint_load_grace_seconds,
            require_current_pool_snapshot=args.require_current_pool_snapshot,
        )
        if health_refresh is not None:
            summary["health_refresh"] = health_refresh
            if health_refresh.get("exit_code") != 0:
                summary["checks"].append(
                    {
                        "name": "health_refresh",
                        "status": "WARN",
                        "detail": f"v5_monitor.py exited {health_refresh.get('exit_code')}",
                    }
                )
                if summary["overall"] == "PASS":
                    summary["overall"] = "WARN"
        write_outputs(run_dir, args.target_iteration, summary)
        overall = str(summary["overall"])
        latest = summary.get("latest") or {}
        checkpoint = summary.get("checkpoint") or {}
        print(
            f"{overall}: gate={args.target_iteration} "
            f"live_iter={latest.get('iteration')} "
            f"ckpt_iter={checkpoint.get('iteration')} "
            f"pool_snapshots={checkpoint.get('pool_snapshots')}",
            flush=True,
        )
        if overall in {"PASS", "FAIL", "WARN"}:
            if overall == "PASS" and args.append_report:
                appended = append_report_if_pass(Path(args.append_report), args.target_iteration, summary)
                print(f"report_appended={appended}", flush=True)
            break
        if args.timeout_seconds <= 0:
            break
        elapsed = time.monotonic() - start
        if elapsed >= args.timeout_seconds:
            break
        sleep_for = min(args.poll_seconds, args.timeout_seconds - elapsed)
        if sleep_for > 0:
            time.sleep(sleep_for)

    if summary is None:
        return 1
    if summary["overall"] == "PASS":
        return 0
    if summary["overall"] in {"FAIL", "WARN"}:
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
