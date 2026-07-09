#!/usr/bin/env python3
"""Read-only throughput audit for a live V5 run.

This script diagnoses whether the current run is collection-bound, PPO-bound,
or likely under-batched. It does not start, stop, or modify training.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_monitor import parse_log


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def round_or_none(value: Any, digits: int = 3) -> float | None:
    number = finite(value)
    if number is None:
        return None
    return round(number, digits)


def nvidia_smi_snapshot() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw",
        "--format=csv,noheader,nounits",
    ]
    try:
        proc = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    if proc.returncode != 0:
        return {"available": False, "error": proc.stderr.strip() or proc.stdout.strip()}
    line = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 6:
        return {"available": False, "raw": line}
    return {
        "available": True,
        "name": parts[0],
        "gpu_utilization_percent": round_or_none(parts[1], 1),
        "memory_utilization_percent": round_or_none(parts[2], 1),
        "memory_used_mb": round_or_none(parts[3], 1),
        "memory_total_mb": round_or_none(parts[4], 1),
        "power_draw_w": round_or_none(parts[5], 1),
        "raw": line,
    }


def with_effective_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    previous_hands: int | None = None
    for row in rows:
        item = dict(row)
        hands = int(row.get("hands") or 0)
        if previous_hands is not None:
            iter_hands = max(0, hands - previous_hands)
        else:
            iter_hands = None
        previous_hands = hands

        collect = finite(row.get("collect_seconds")) or 0.0
        ppo = finite(row.get("ppo_seconds")) or 0.0
        total_seconds = collect + ppo
        item["iteration_hands"] = iter_hands
        item["iteration_total_seconds"] = total_seconds
        item["ppo_share"] = ppo / total_seconds if total_seconds > 0 else None
        item["collect_share"] = collect / total_seconds if total_seconds > 0 else None
        item["effective_hands_per_second"] = (
            iter_hands / total_seconds if iter_hands is not None and total_seconds > 0 else None
        )
        item["reported_collect_hands_per_second"] = row.get("hands_per_second")
        enriched.append(item)
    return enriched


def summarize_window(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    values = {
        "reported_collect_hps": [float(r["reported_collect_hands_per_second"]) for r in rows if finite(r.get("reported_collect_hands_per_second")) is not None],
        "effective_hps": [float(r["effective_hands_per_second"]) for r in rows if finite(r.get("effective_hands_per_second")) is not None],
        "tdecps": [float(r["trainable_decisions_per_second"]) for r in rows if finite(r.get("trainable_decisions_per_second")) is not None],
        "inf_bs": [float(r["inference_batch_size"]) for r in rows if finite(r.get("inference_batch_size")) is not None],
        "collect_seconds": [float(r["collect_seconds"]) for r in rows if finite(r.get("collect_seconds")) is not None],
        "ppo_seconds": [float(r["ppo_seconds"]) for r in rows if finite(r.get("ppo_seconds")) is not None],
        "ppo_share": [float(r["ppo_share"]) for r in rows if finite(r.get("ppo_share")) is not None],
        "iteration_total_seconds": [float(r["iteration_total_seconds"]) for r in rows if finite(r.get("iteration_total_seconds")) is not None],
    }
    return {
        "label": label,
        "rows": len(rows),
        "first_iteration": rows[0].get("iteration") if rows else None,
        "latest_iteration": rows[-1].get("iteration") if rows else None,
        "first_hands": rows[0].get("hands") if rows else None,
        "latest_hands": rows[-1].get("hands") if rows else None,
        "reported_collect_hps_mean": round_or_none(mean(values["reported_collect_hps"]), 1),
        "reported_collect_hps_p50": round_or_none(percentile(values["reported_collect_hps"], 0.50), 1),
        "reported_collect_hps_p90": round_or_none(percentile(values["reported_collect_hps"], 0.90), 1),
        "effective_hps_mean": round_or_none(mean(values["effective_hps"]), 1),
        "effective_hps_p50": round_or_none(percentile(values["effective_hps"], 0.50), 1),
        "effective_hps_p90": round_or_none(percentile(values["effective_hps"], 0.90), 1),
        "trainable_decisions_per_second_mean": round_or_none(mean(values["tdecps"]), 1),
        "inference_batch_size_mean": round_or_none(mean(values["inf_bs"]), 2),
        "inference_batch_size_p50": round_or_none(percentile(values["inf_bs"], 0.50), 2),
        "collect_seconds_mean": round_or_none(mean(values["collect_seconds"]), 2),
        "ppo_seconds_mean": round_or_none(mean(values["ppo_seconds"]), 2),
        "ppo_share_mean": round_or_none(mean(values["ppo_share"]), 3),
        "iteration_total_seconds_mean": round_or_none(mean(values["iteration_total_seconds"]), 2),
    }


def summarize_buckets(rows: list[dict[str, Any]], fast_inf_bs: float) -> dict[str, Any]:
    fast = [row for row in rows if float(row.get("inference_batch_size") or 0.0) >= fast_inf_bs]
    slow = [row for row in rows if float(row.get("inference_batch_size") or 0.0) < fast_inf_bs]
    return {
        "threshold_fast_inference_batch_size": fast_inf_bs,
        "fast_rows": summarize_window(fast, "fast_batch") if fast else None,
        "slow_rows": summarize_window(slow, "slow_batch") if slow else None,
        "fast_fraction": round_or_none(len(fast) / len(rows), 3) if rows else None,
    }


def add_check(checks: list[dict[str, str]], name: str, status: str, detail: str) -> None:
    checks.append({"name": name, "status": status, "detail": detail})


def classify(summary: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    latest = summary.get("latest_window") or {}
    gpu = summary.get("gpu") or {}
    config = summary.get("config") or {}

    rows = int(latest.get("rows") or 0)
    if rows >= args.min_rows:
        add_check(checks, "sample_rows", "PASS", f"latest window rows {rows} >= {args.min_rows}")
    else:
        add_check(checks, "sample_rows", "PENDING", f"latest window rows {rows} < {args.min_rows}")

    effective = finite(latest.get("effective_hps_mean"))
    if effective is None:
        add_check(checks, "effective_hps", "PENDING", "cannot compute effective h/s")
    elif effective >= args.target_effective_hps:
        add_check(checks, "effective_hps", "PASS", f"effective h/s {effective:.1f} >= {args.target_effective_hps:.1f}")
    elif effective >= args.warn_effective_hps:
        add_check(checks, "effective_hps", "WARN", f"effective h/s {effective:.1f} below target {args.target_effective_hps:.1f}")
    else:
        add_check(checks, "effective_hps", "WARN", f"effective h/s {effective:.1f} below warn {args.warn_effective_hps:.1f}")

    ppo_share = finite(latest.get("ppo_share_mean"))
    if ppo_share is None:
        add_check(checks, "ppo_share", "PENDING", "cannot compute PPO share")
    elif ppo_share > args.ppo_share_warn:
        add_check(checks, "ppo_share", "WARN", f"PPO takes {ppo_share:.1%} of collect+PPO time")
    else:
        add_check(checks, "ppo_share", "PASS", f"PPO takes {ppo_share:.1%} of collect+PPO time")

    inf_bs = finite(latest.get("inference_batch_size_mean"))
    workers = int(config.get("workers") or 0)
    if inf_bs is None:
        add_check(checks, "inference_batching", "PENDING", "cannot compute inference batch size")
    elif workers > 0 and inf_bs < args.min_inf_bs_ratio_of_workers * workers:
        add_check(
            checks,
            "inference_batching",
            "WARN",
            f"mean inf_bs {inf_bs:.2f} is low for {workers} workers",
        )
    else:
        add_check(checks, "inference_batching", "PASS", f"mean inf_bs {inf_bs:.2f}")

    if gpu.get("available"):
        util = finite(gpu.get("gpu_utilization_percent"))
        if util is not None and util < args.gpu_util_warn:
            add_check(checks, "gpu_utilization", "WARN", f"GPU utilization {util:.1f}% < {args.gpu_util_warn:.1f}%")
        else:
            add_check(checks, "gpu_utilization", "PASS", f"GPU utilization {util:.1f}%" if util is not None else "GPU available")
    else:
        add_check(checks, "gpu_utilization", "WARN", f"nvidia-smi unavailable: {gpu.get('error') or gpu.get('raw')}")

    statuses = {check["status"] for check in checks}
    if "PENDING" in statuses:
        overall = "PENDING"
    elif "WARN" in statuses:
        overall = "WARN"
    else:
        overall = "PASS"

    recommendations: list[str] = []
    if inf_bs is not None and workers > 0 and inf_bs < args.min_inf_bs_ratio_of_workers * workers:
        recommendations.append(
            "Mean inference batch size is low relative to workers; a guarded sweep with more workers or larger hands_per_iter may improve throughput."
        )
    if ppo_share is not None and ppo_share > args.ppo_share_warn:
        recommendations.append(
            "PPO time is a meaningful share of wall clock; test larger hands_per_iter or larger mini_batch_size in a separate short sweep before changing the live run."
        )
    if gpu.get("available") and finite(gpu.get("gpu_utilization_percent")) is not None and float(gpu["gpu_utilization_percent"]) < args.gpu_util_warn:
        recommendations.append(
            "GPU is not saturated; collection/inference scheduling is probably the bottleneck."
        )
    if not recommendations:
        recommendations.append(
            "Current run is throughput-healthy. Do not hot-edit the live trainer; use the existing guarded sweep plan for any worker/hands_per_iter change."
        )

    return {"overall": overall, "checks": checks, "recommendations": recommendations}


def speed_decision(summary: dict[str, Any]) -> str:
    classification = summary.get("classification") or {}
    overall = classification.get("overall")
    checks = {check.get("name"): check for check in classification.get("checks") or []}

    if overall == "PENDING":
        return "WAIT_FOR_MORE_THROUGHPUT_ROWS"
    if overall == "PASS":
        return "CONTINUE_CURRENT_RUN"

    effective_hps = (checks.get("effective_hps") or {}).get("status")
    gpu_utilization = (checks.get("gpu_utilization") or {}).get("status")
    inference_batching = (checks.get("inference_batching") or {}).get("status")
    ppo_share = (checks.get("ppo_share") or {}).get("status")

    if (
        overall == "WARN"
        and effective_hps == "WARN"
        and (gpu_utilization == "WARN" or inference_batching == "WARN")
        and ppo_share != "WARN"
    ):
        return "PREPARE_SWEEP_CONTROLLED_RESTART_ONLY"
    if overall == "WARN":
        return "CONTINUE_WITH_THROUGHPUT_WARN"
    return "INSPECT_THROUGHPUT_AUDIT"


def add_top_level_aliases(summary: dict[str, Any]) -> None:
    classification = summary.get("classification") or {}
    latest = summary.get("latest_window") or {}
    long_window = summary.get("long_window") or {}
    buckets = summary.get("batch_buckets") or {}
    fast = buckets.get("fast_rows") or {}
    slow = buckets.get("slow_rows") or {}
    gpu = summary.get("gpu") or {}

    summary["overall"] = classification.get("overall")
    summary["decision"] = speed_decision(summary)
    summary["recommendation_summary"] = (
        (classification.get("recommendations") or [None])[0]
    )
    summary["effective_hps_latest"] = latest.get("effective_hps_mean")
    summary["effective_hps_long"] = long_window.get("effective_hps_mean")
    summary["reported_collect_hps_latest"] = latest.get("reported_collect_hps_mean")
    summary["inference_batch_size_mean"] = latest.get("inference_batch_size_mean")
    summary["ppo_share_mean"] = latest.get("ppo_share_mean")
    summary["fast_fraction"] = buckets.get("fast_fraction")
    summary["fast_effective_hps_mean"] = fast.get("effective_hps_mean")
    summary["slow_effective_hps_mean"] = slow.get("effective_hps_mean")
    summary["gpu_utilization_percent"] = gpu.get("gpu_utilization_percent")
    summary["gpu_memory_used_mb"] = gpu.get("memory_used_mb")
    summary["gpu_memory_total_mb"] = gpu.get("memory_total_mb")


def build_summary(run_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    raw_rows = parse_log(run_dir / "latest_train.log")
    rows = with_effective_metrics(raw_rows)
    manifest = load_json(run_dir / "run_manifest.json")
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    latest_rows = rows[-args.tail:] if args.tail > 0 else rows
    longer_rows = rows[-args.long_tail:] if args.long_tail > 0 else rows

    latest_window = summarize_window(latest_rows, f"tail_{args.tail}")
    long_window = summarize_window(longer_rows, f"tail_{args.long_tail}")
    buckets = summarize_buckets(latest_rows, args.fast_inf_bs)
    gpu = nvidia_smi_snapshot() if not args.no_gpu_snapshot else {"available": False, "skipped": True}

    summary: dict[str, Any] = {
        "checked_at": now_iso(),
        "run_dir": str(run_dir),
        "run_id": manifest.get("run_id") or run_dir.name,
        "config": {
            "device": config.get("device"),
            "workers": config.get("workers"),
            "hands_per_iter": config.get("hands_per_iter"),
            "mini_batch_size": config.get("mini_batch_size"),
            "ppo_epochs": config.get("ppo_epochs"),
            "opponent_assignment": config.get("opponent_assignment"),
            "self_play_fraction": config.get("self_play_fraction"),
        },
        "parsed_rows": len(rows),
        "latest_row": rows[-1] if rows else None,
        "latest_window": latest_window,
        "long_window": long_window,
        "batch_buckets": buckets,
        "gpu": gpu,
        "notes": [
            "reported_collect_hps is the trainer log h/s and excludes PPO time.",
            "effective_hps uses iteration_hands / (collect_seconds + ppo_seconds), so it is closer to wall-clock throughput.",
            "This is an engineering throughput audit only; it does not prove model strength, Slumbot progress, L5, or L6.",
        ],
    }
    summary["classification"] = classify(summary, args)
    add_top_level_aliases(summary)
    return summary


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    latest = summary.get("latest_window") or {}
    long_window = summary.get("long_window") or {}
    buckets = summary.get("batch_buckets") or {}
    fast = buckets.get("fast_rows") or {}
    slow = buckets.get("slow_rows") or {}
    gpu = summary.get("gpu") or {}
    classification = summary.get("classification") or {}
    config = summary.get("config") or {}

    lines = [
        "# V5 Throughput Audit",
        "",
        f"- Checked at: `{summary.get('checked_at')}`",
        f"- Run: `{summary.get('run_id')}`",
        f"- Overall: **{classification.get('overall')}**",
        f"- Decision: **{summary.get('decision')}**",
        f"- Workers / hands_per_iter / minibatch: `{config.get('workers')}` / `{config.get('hands_per_iter')}` / `{config.get('mini_batch_size')}`",
        f"- Device: `{config.get('device')}`",
        "",
        "## Latest Window",
        "",
        f"- Rows: `{latest.get('rows')}` iterations `{latest.get('first_iteration')}` to `{latest.get('latest_iteration')}`",
        f"- Reported collect h/s mean: `{latest.get('reported_collect_hps_mean')}`",
        f"- Effective h/s mean: `{latest.get('effective_hps_mean')}`",
        f"- Effective h/s p50 / p90: `{latest.get('effective_hps_p50')}` / `{latest.get('effective_hps_p90')}`",
        f"- Trainable decisions/sec mean: `{latest.get('trainable_decisions_per_second_mean')}`",
        f"- Inference batch size mean / p50: `{latest.get('inference_batch_size_mean')}` / `{latest.get('inference_batch_size_p50')}`",
        f"- Collect seconds mean: `{latest.get('collect_seconds_mean')}`",
        f"- PPO seconds mean: `{latest.get('ppo_seconds_mean')}`",
        f"- PPO share mean: `{latest.get('ppo_share_mean')}`",
        "",
        "## Longer Window",
        "",
        f"- Rows: `{long_window.get('rows')}` iterations `{long_window.get('first_iteration')}` to `{long_window.get('latest_iteration')}`",
        f"- Effective h/s mean: `{long_window.get('effective_hps_mean')}`",
        f"- Inference batch size mean: `{long_window.get('inference_batch_size_mean')}`",
        "",
        "## Batch Buckets",
        "",
        f"- Fast bucket threshold inf_bs: `{buckets.get('threshold_fast_inference_batch_size')}`",
        f"- Fast fraction: `{buckets.get('fast_fraction')}`",
        f"- Fast effective h/s mean: `{fast.get('effective_hps_mean')}` over `{fast.get('rows')}` rows",
        f"- Slow effective h/s mean: `{slow.get('effective_hps_mean')}` over `{slow.get('rows')}` rows",
        "",
        "## GPU Snapshot",
        "",
    ]
    if gpu.get("available"):
        lines.extend(
            [
                f"- GPU: `{gpu.get('name')}`",
                f"- Utilization: `{gpu.get('gpu_utilization_percent')}%`",
                f"- Memory: `{gpu.get('memory_used_mb')}/{gpu.get('memory_total_mb')} MB`",
                f"- Power: `{gpu.get('power_draw_w')} W`",
            ]
        )
    else:
        lines.append(f"- GPU snapshot unavailable: `{gpu.get('error') or gpu.get('raw') or gpu.get('skipped')}`")

    lines.extend(["", "## Checks", ""])
    for check in classification.get("checks") or []:
        lines.append(f"- {check.get('status')}: `{check.get('name')}` - {check.get('detail')}")

    lines.extend(["", "## Recommendations", ""])
    for item in classification.get("recommendations") or []:
        lines.append(f"- {item}")

    lines.extend(["", "## Notes", ""])
    for note in summary.get("notes") or []:
        lines.append(f"- {note}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a live V5 throughput audit.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--tail", type=int, default=60)
    parser.add_argument("--long-tail", type=int, default=240)
    parser.add_argument("--min-rows", type=int, default=20)
    parser.add_argument("--target-effective-hps", type=float, default=800.0)
    parser.add_argument("--warn-effective-hps", type=float, default=650.0)
    parser.add_argument("--ppo-share-warn", type=float, default=0.28)
    parser.add_argument("--min-inf-bs-ratio-of-workers", type=float, default=0.45)
    parser.add_argument("--gpu-util-warn", type=float, default=70.0)
    parser.add_argument("--fast-inf-bs", type=float, default=18.0)
    parser.add_argument("--no-gpu-snapshot", action="store_true")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_summary(Path(args.run_dir), args)
    text = json.dumps(summary, indent=2, sort_keys=True)
    print(text)
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(text + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(summary, Path(args.out_md))

    overall = (summary.get("classification") or {}).get("overall")
    return 0 if overall in {"PASS", "WARN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
