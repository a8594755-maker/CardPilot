#!/usr/bin/env python3
"""Plan V5 throughput sweep experiments without starting training.

The active L6 run should not be hot-edited. This helper reads a source V5
checkpoint and emits guarded short-run commands for worker / hands-per-iter
variants, plus compare commands for each candidate run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch


EXPECTED_METADATA = {
    "version": "v5.zero",
    "env_version": "v55",
    "obs_version": "v55",
    "action_space_version": "9slot_v5",
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"_load_error": str(exc)}


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


def parse_int_list(value: str) -> list[int]:
    result: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        result.append(int(part))
    if not result:
        raise argparse.ArgumentTypeError("list must contain at least one integer")
    return result


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def ps_command(parts: list[str]) -> str:
    return " ".join(ps_quote(p) if any(ch.isspace() for ch in p) else p for p in parts)


def action_prior_target_text(config: dict[str, Any], prefix: str, default: str) -> str:
    raw = config.get(f"{prefix}_action_prior_target")
    if raw:
        return str(raw)
    values = config.get(f"{prefix}_action_prior_target_values")
    if isinstance(values, (list, tuple)) and len(values) == 4:
        return ",".join(str(float(value)) for value in values)
    return default


def config_value(config: dict[str, Any], key: str, default: Any) -> Any:
    """Return a saved config value without replacing valid false/zero values."""
    value = config.get(key)
    return default if value is None else value


def inherited_execution_config(config: dict[str, Any]) -> dict[str, Any]:
    """Execution flags that a throughput-only continuation must preserve."""
    return {
        "rollout_mode": str(config_value(config, "rollout_mode", "single")),
        "rollout_envs_per_worker": int(config_value(config, "rollout_envs_per_worker", 1)),
        "inference_min_batch_slots": int(config_value(config, "inference_min_batch_slots", 0)),
        "inference_batch_deadline_us": float(
            config_value(config, "inference_batch_deadline_us", 700.0)
        ),
        "mirror_self_play_deals": bool(config_value(config, "mirror_self_play_deals", False)),
        "allin_runout_ev": bool(config_value(config, "allin_runout_ev", False)),
        "allin_runout_ev_max_runouts": int(
            config_value(config, "allin_runout_ev_max_runouts", 200)
        ),
    }


def resolve_hands_per_iter_values(
    config: dict[str, Any],
    requested: str,
    allow_change: bool,
) -> tuple[int, list[int], list[int]]:
    """Keep PPO cadence fixed unless a changed HPI sweep is explicitly authorized."""
    source_hpi = int(config_value(config, "hands_per_iter", 16_384))
    requested_values = parse_int_list(requested) if requested.strip() else [source_hpi]
    changed_values = [value for value in requested_values if value != source_hpi]
    if changed_values and not allow_change:
        # Do not emit changed-cadence variants when the explicit opt-in is absent.
        return source_hpi, [source_hpi], changed_values
    return source_hpi, requested_values, []


def is_process_alive(pid: Any) -> bool | None:
    try:
        pid_int = int(pid)
    except Exception:
        return None
    if pid_int <= 0:
        return None
    command = (
        f"if (Get-Process -Id {pid_int} -ErrorAction SilentlyContinue) "
        "{ 'true' } else { 'false' }"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    text = completed.stdout.strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None


def add_check(checks: list[dict[str, str]], name: str, status: str, detail: str) -> None:
    checks.append({"name": name, "status": status, "detail": detail})


def checkpoint_lineage(checkpoint: dict[str, Any]) -> bool:
    if "fresh_from_zero_lineage" in checkpoint:
        return bool(checkpoint.get("fresh_from_zero_lineage"))
    return checkpoint.get("version") == "v5.zero" and checkpoint.get("resume") is None


def build_train_command(
    args: argparse.Namespace,
    checkpoint_path: Path,
    config: dict[str, Any],
    run_id: str,
    run_dir: Path,
    workers: int,
    hands_per_iter: int,
) -> str:
    postflop_prior_coef = float(config.get("postflop_action_prior_coef") or 0.0)
    postflop_prior_target = action_prior_target_text(
        config,
        "postflop",
        "0.15,0.30,0.52,0.03",
    )
    preflop_prior_coef = float(config.get("preflop_action_prior_coef") or 0.0)
    preflop_prior_target = action_prior_target_text(
        config,
        "preflop",
        "0.30,0.25,0.43,0.02",
    )
    execution = inherited_execution_config(config)
    parts = [
        args.python,
        "-X",
        "utf8",
        "-u",
        "scripts\\alpha_holdem\\train_v5.py",
        "--device",
        args.device,
        "--workers",
        str(workers),
        "--hands-per-iter",
        str(hands_per_iter),
        "--total-hands",
        str(int(config.get("total_hands") or args.total_hands)),
        "--starting-stack",
        str(config.get("starting_stack") or 200.0),
        "--env-version",
        str(config.get("env_version") or "v55"),
        "--lr",
        str(config.get("lr") or 3e-4),
        "--gamma",
        str(config.get("gamma") or 0.999),
        "--delta1",
        str(config.get("delta1") or 3.0),
        "--entropy-coef",
        str(config.get("entropy_coef") or 0.05),
        "--entropy-floor",
        str(config.get("entropy_floor") or 0.3),
        "--postflop-action-prior-coef",
        str(postflop_prior_coef),
        "--postflop-action-prior-target",
        postflop_prior_target,
        "--preflop-action-prior-coef",
        str(preflop_prior_coef),
        "--preflop-action-prior-target",
        preflop_prior_target,
        "--k-best",
        str(int(config.get("k_best") or 5)),
        "--pool-strategy",
        str(config.get("pool_strategy") or "loss-kbest"),
        "--pool-history-limit",
        str(int(config.get("pool_history_limit") or 200)),
        "--self-play-fraction",
        str(config.get("self_play_fraction") or 0.2),
        "--opponent-assignment",
        str(config.get("opponent_assignment") or "per-iteration"),
        "--rollout-mode",
        str(execution["rollout_mode"]),
        "--rollout-envs-per-worker",
        str(execution["rollout_envs_per_worker"]),
        "--inference-min-batch-slots",
        str(execution["inference_min_batch_slots"]),
        "--inference-batch-deadline-us",
        str(execution["inference_batch_deadline_us"]),
        "--allin-runout-ev-max-runouts",
        str(execution["allin_runout_ev_max_runouts"]),
        "--snapshot-every",
        str(int(config.get("snapshot_every") or 200)),
        "--save-interval",
        str(int(config.get("save_interval") or 100)),
        "--resume",
        str(checkpoint_path),
        "--allow-resume",
        "--no-reset-optimizer",
        "--run-id",
        run_id,
        "--run-dir",
        str(run_dir),
        "--max-runtime-seconds",
        str(args.max_runtime_seconds),
    ]
    if execution["mirror_self_play_deals"]:
        parts.append("--mirror-self-play-deals")
    if execution["allin_runout_ev"]:
        parts.append("--allin-runout-ev")
    return ps_command(parts)


def build_compare_command(
    args: argparse.Namespace,
    source_run_dir: Path,
    run_dir: Path,
    variant_tag: str,
) -> str:
    json_path = run_dir / f"throughput_compare_{variant_tag}.json"
    md_path = run_dir / f"throughput_compare_{variant_tag}.md"
    parts = [
        args.python,
        "scripts\\alpha_holdem\\v5_throughput_compare.py",
        "--baseline-run-dir",
        str(source_run_dir),
        "--candidate-run-dir",
        str(run_dir),
        "--tail",
        str(args.compare_tail),
        "--min-baseline-rows",
        str(args.min_baseline_rows),
        "--min-candidate-rows",
        str(args.min_candidate_rows),
        "--min-hps-ratio",
        str(args.min_hps_ratio),
        "--min-inf-bs-ratio",
        str(args.min_inf_bs_ratio),
        "--min-candidate-inf-bs",
        str(args.min_candidate_inf_bs),
        "--out-json",
        str(json_path),
        "--out-md",
        str(md_path),
    ]
    return ps_command(parts)


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    source_run_dir = Path(args.source_run_dir)
    checkpoint_path = Path(args.checkpoint) if args.checkpoint else source_run_dir / "latest.pt"
    output_root = Path(args.output_root)
    manifest = load_json(source_run_dir / "run_manifest.json")
    checkpoint = load_checkpoint(checkpoint_path)
    checkpoint_ready = not checkpoint.get("_missing") and not checkpoint.get("_load_error")
    config = checkpoint.get("config") if isinstance(checkpoint.get("config"), dict) else {}
    effective_config = dict(config)
    overrides: dict[str, Any] = {}
    for key in (
        "postflop_action_prior_coef",
        "postflop_action_prior_target",
        "preflop_action_prior_coef",
        "preflop_action_prior_target",
    ):
        value = getattr(args, key, None)
        if value is not None and value != "":
            effective_config[key] = value
            overrides[key] = value
    action_prior_config = {
        "postflop_action_prior_coef": float(effective_config.get("postflop_action_prior_coef") or 0.0),
        "postflop_action_prior_target": action_prior_target_text(
            effective_config,
            "postflop",
            "0.15,0.30,0.52,0.03",
        ),
        "preflop_action_prior_coef": float(effective_config.get("preflop_action_prior_coef") or 0.0),
        "preflop_action_prior_target": action_prior_target_text(
            effective_config,
            "preflop",
            "0.30,0.25,0.43,0.02",
        ),
    }
    execution_config = inherited_execution_config(effective_config)

    checks: list[dict[str, str]] = []
    if source_run_dir.exists():
        add_check(checks, "source_run_dir", "PASS", f"exists: {source_run_dir}")
    else:
        add_check(checks, "source_run_dir", "FAIL", f"missing: {source_run_dir}")

    if checkpoint.get("_missing"):
        add_check(checks, "checkpoint_load", "FAIL", f"missing: {checkpoint_path}")
    elif checkpoint.get("_load_error"):
        add_check(checks, "checkpoint_load", "FAIL", str(checkpoint["_load_error"]))
    else:
        add_check(checks, "checkpoint_load", "PASS", f"loaded {checkpoint_path}")

    for key, expected in EXPECTED_METADATA.items():
        actual = checkpoint.get(key)
        if not checkpoint_ready:
            add_check(checks, key, "FAIL", "checkpoint unavailable")
        elif actual == expected:
            add_check(checks, key, "PASS", f"{key}={actual}")
        else:
            add_check(checks, key, "FAIL", f"{key}={actual!r}, expected {expected!r}")

    if not checkpoint_ready:
        add_check(checks, "actual_hand_accounting", "FAIL", "checkpoint unavailable")
        add_check(checks, "fresh_from_zero_lineage", "FAIL", "checkpoint unavailable")
    else:
        status = "PASS" if checkpoint.get("actual_hand_accounting") is True else "FAIL"
        add_check(checks, "actual_hand_accounting", status, f"actual_hand_accounting={checkpoint.get('actual_hand_accounting')!r}")
        lineage = checkpoint_lineage(checkpoint)
        add_check(checks, "fresh_from_zero_lineage", "PASS" if lineage else "FAIL", f"fresh_from_zero_lineage={lineage}")

    live_pid = manifest.get("process_id")
    active_source = is_process_alive(live_pid)
    if active_source is True:
        add_check(
            checks,
            "active_source_trainer",
            "WARN",
            f"source manifest process_id {live_pid} is still alive; do not execute sweep concurrently",
        )
    elif active_source is False:
        add_check(checks, "active_source_trainer", "PASS", f"source manifest process_id {live_pid} is not alive")
    else:
        add_check(checks, "active_source_trainer", "WARN", "could not verify source trainer process state")

    worker_values = parse_int_list(args.workers)
    source_hpi, hpi_values, unauthorized_hpi_values = resolve_hands_per_iter_values(
        effective_config,
        str(getattr(args, "hands_per_iter", "") or ""),
        bool(getattr(args, "allow_hands_per_iter_change", False)),
    )
    if unauthorized_hpi_values:
        add_check(
            checks,
            "hands_per_iter_change_authorization",
            "FAIL",
            (
                f"requested hands_per_iter values {unauthorized_hpi_values} differ from source "
                f"{source_hpi}; pass --allow-hands-per-iter-change to opt into changed PPO cadence. "
                "Changed-cadence variants were not emitted."
            ),
        )
    elif any(value != source_hpi for value in hpi_values):
        add_check(
            checks,
            "hands_per_iter_change_authorization",
            "PASS",
            f"explicit opt-in accepted: source={source_hpi}, requested={hpi_values}",
        )
    else:
        add_check(
            checks,
            "hands_per_iter_change_authorization",
            "PASS",
            f"PPO cadence preserved at source hands_per_iter={source_hpi}",
        )
    stamp = now.strftime("%Y%m%d_%H%M%S")
    source_leaf = source_run_dir.name
    variants = []
    seen_dirs: set[str] = set()
    capacity_failures: list[str] = []
    for workers in worker_values:
        for hpi in hpi_values:
            variant_tag = f"w{workers}_hpi{hpi}"
            run_id = f"{source_leaf}_sweep_{variant_tag}_{stamp}"
            run_dir = output_root / run_id
            collision = run_dir.exists() or str(run_dir) in seen_dirs
            seen_dirs.add(str(run_dir))
            inference_capacity_slots = workers * int(execution_config["rollout_envs_per_worker"])
            min_batch_capacity_ok = (
                int(execution_config["inference_min_batch_slots"]) <= inference_capacity_slots
            )
            if not min_batch_capacity_ok:
                capacity_failures.append(
                    f"{variant_tag}: min_batch_slots={execution_config['inference_min_batch_slots']} "
                    f"> capacity={inference_capacity_slots}"
                )
            train_command = None
            compare_command = None
            if min_batch_capacity_ok:
                train_command = build_train_command(
                    args=args,
                    checkpoint_path=checkpoint_path,
                    config=effective_config,
                    run_id=run_id,
                    run_dir=run_dir,
                    workers=workers,
                    hands_per_iter=hpi,
                )
                compare_command = build_compare_command(
                    args=args,
                    source_run_dir=source_run_dir,
                    run_dir=run_dir,
                    variant_tag=variant_tag,
                )
            variants.append(
                {
                    "variant": variant_tag,
                    "workers": workers,
                    "hands_per_iter": hpi,
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "output_collision": collision,
                    "inference_capacity_slots": inference_capacity_slots,
                    "inference_min_batch_slots": execution_config["inference_min_batch_slots"],
                    "min_batch_capacity_ok": min_batch_capacity_ok,
                    "train_command": train_command,
                    "compare_command": compare_command,
                }
            )
    if any(v["output_collision"] for v in variants):
        add_check(checks, "output_collision", "FAIL", "one or more planned run dirs already exist")
    else:
        add_check(checks, "output_collision", "PASS", "no planned run dir collisions")
    if capacity_failures:
        add_check(
            checks,
            "variant_min_batch_capacity",
            "FAIL",
            "; ".join(capacity_failures),
        )
    else:
        add_check(
            checks,
            "variant_min_batch_capacity",
            "PASS",
            "every variant can satisfy inherited inference_min_batch_slots",
        )

    statuses = {check["status"] for check in checks}
    if "FAIL" in statuses:
        overall = "BLOCKED"
    elif "WARN" in statuses:
        overall = "READY_WITH_WARNINGS"
    else:
        overall = "READY"

    return {
        "checked_at": now.isoformat(),
        "overall": overall,
        "source_run_dir": str(source_run_dir),
        "checkpoint_path": str(checkpoint_path),
        "output_root": str(output_root),
        "active_source_trainer": active_source,
        "max_runtime_seconds": args.max_runtime_seconds,
        "checks": checks,
        "checkpoint": {
            "iteration": checkpoint.get("iteration") if checkpoint_ready else None,
            "total_hands": checkpoint.get("total_hands") if checkpoint_ready else None,
            "run_id": checkpoint.get("run_id") if checkpoint_ready else None,
            "version": checkpoint.get("version") if checkpoint_ready else None,
            "env_version": checkpoint.get("env_version") if checkpoint_ready else None,
            "fresh_from_zero_lineage": checkpoint_lineage(checkpoint) if checkpoint_ready else None,
            "workers": config.get("workers"),
            "hands_per_iter": config.get("hands_per_iter"),
            "execution": execution_config,
            "overrides": overrides,
            "action_prior": action_prior_config,
        },
        "variants": variants,
        "notes": [
            "This planner does not start trainers.",
            "Do not execute a CUDA sweep while the long L6 trainer is running unless intentionally accepting contention.",
            "Each candidate should be compared with v5_throughput_compare.py before any guarded cutover.",
            "EXP-002/003 execution flags are inherited from the frozen source checkpoint.",
            "Changing hands_per_iter changes PPO update cadence and requires --allow-hands-per-iter-change.",
            "Throughput PASS is engineering evidence only and cannot support Slumbot, L5, or L6 claims.",
        ],
    }


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# V5 Throughput Sweep Plan",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Overall: **{summary['overall']}**",
        f"- Source run: `{summary['source_run_dir']}`",
        f"- Checkpoint: `{summary['checkpoint_path']}`",
        f"- Output root: `{summary['output_root']}`",
        f"- Max runtime per candidate: `{summary['max_runtime_seconds']}` seconds",
        f"- Postflop action prior: coef `{summary['checkpoint']['action_prior']['postflop_action_prior_coef']}` "
        f"target `{summary['checkpoint']['action_prior']['postflop_action_prior_target']}`",
        f"- Preflop action prior: coef `{summary['checkpoint']['action_prior']['preflop_action_prior_coef']}` "
        f"target `{summary['checkpoint']['action_prior']['preflop_action_prior_target']}`",
        f"- Inherited execution config: `{summary['checkpoint']['execution']}`",
        f"- Overrides: `{summary['checkpoint']['overrides']}`",
        "",
        "Checks:",
        "",
    ]
    for check in summary["checks"]:
        lines.append(f"- {check['status']}: `{check['name']}` - {check['detail']}")
    lines.extend(["", "Variants:", ""])
    for variant in summary["variants"]:
        lines.extend(
            [
                f"## {variant['variant']}",
                "",
                f"- workers: `{variant['workers']}`",
                f"- hands_per_iter: `{variant['hands_per_iter']}`",
                f"- inference capacity/min slots: `{variant['inference_capacity_slots']}` / "
                f"`{variant['inference_min_batch_slots']}`",
                f"- min-batch capacity gate: `{'PASS' if variant['min_batch_capacity_ok'] else 'FAIL'}`",
                f"- run dir: `{variant['run_dir']}`",
                "",
                "Train command:" if variant["train_command"] else "Train command: `NOT EMITTED (min-batch capacity gate failed)`",
                "",
                *(["```powershell", variant["train_command"], "```"] if variant["train_command"] else []),
                "",
                "Compare command:" if variant["compare_command"] else "Compare command: `NOT EMITTED`",
                "",
                *(["```powershell", variant["compare_command"], "```"] if variant["compare_command"] else []),
                "",
            ]
        )
    lines.extend(["Notes:", ""])
    for note in summary["notes"]:
        lines.append(f"- {note}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run-dir", required=True)
    parser.add_argument("--checkpoint", default="", help="Defaults to <source-run-dir>/latest.pt.")
    parser.add_argument("--output-root", default="tmp/v5_throughput_sweeps")
    parser.add_argument("--workers", default="28,32,36")
    parser.add_argument(
        "--hands-per-iter",
        default="",
        help="Comma-separated HPI values. Defaults to the source checkpoint value only.",
    )
    parser.add_argument(
        "--allow-hands-per-iter-change",
        action="store_true",
        help="Explicitly opt into HPI values that change PPO update cadence.",
    )
    parser.add_argument("--max-runtime-seconds", type=float, default=900.0)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--python", default="python")
    parser.add_argument("--total-hands", type=int, default=2_700_000_000)
    parser.add_argument("--postflop-action-prior-coef", type=float)
    parser.add_argument("--postflop-action-prior-target", default="")
    parser.add_argument("--preflop-action-prior-coef", type=float)
    parser.add_argument("--preflop-action-prior-target", default="")
    parser.add_argument("--compare-tail", type=int, default=20)
    parser.add_argument("--min-baseline-rows", type=int, default=20)
    parser.add_argument("--min-candidate-rows", type=int, default=20)
    parser.add_argument("--min-hps-ratio", type=float, default=1.05)
    parser.add_argument("--min-inf-bs-ratio", type=float, default=1.0)
    parser.add_argument("--min-candidate-inf-bs", type=float, default=12.0)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = evaluate(args)
    print(f"overall={summary['overall']}")
    print(f"variants={len(summary['variants'])}")
    print(f"active_source_trainer={summary['active_source_trainer']}")
    for variant in summary["variants"]:
        print(f"- {variant['variant']}: workers={variant['workers']} hpi={variant['hands_per_iter']}")

    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print(f"wrote={out_json}")
    if args.out_md:
        write_markdown(Path(args.out_md), summary)
        print(f"wrote={args.out_md}")

    return 0 if summary["overall"] in {"READY", "READY_WITH_WARNINGS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
