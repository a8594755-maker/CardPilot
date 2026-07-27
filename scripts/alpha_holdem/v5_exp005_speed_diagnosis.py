#!/usr/bin/env python3
"""Reporting-only EXP-005 fixed-window throughput diagnosis."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_monitor import parse_log  # noqa: E402


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"rows": 0}
    iteration_hands = [int(row.get("iteration_hands") or 16_384) for row in rows]
    elapsed = [float(row["collect_seconds"]) + float(row["ppo_seconds"]) for row in rows]
    effective = [hands / seconds for hands, seconds in zip(iteration_hands, elapsed)]
    return {
        "rows": len(rows),
        "first_iteration": rows[0]["iteration"],
        "latest_iteration": rows[-1]["iteration"],
        "first_hands": rows[0]["hands"],
        "latest_hands": rows[-1]["hands"],
        "actual_hands_covered": rows[-1]["hands"] - rows[0]["hands"],
        "effective_hps_mean": statistics.fmean(effective),
        "effective_hps_weighted": sum(iteration_hands) / sum(elapsed),
        "collect_hps_mean": statistics.fmean(float(row["hands_per_second"]) for row in rows),
        "inference_batch_size_mean": statistics.fmean(float(row["inference_batch_size"]) for row in rows),
        "collect_seconds_mean": statistics.fmean(float(row["collect_seconds"]) for row in rows),
        "ppo_seconds_mean": statistics.fmean(float(row["ppo_seconds"]) for row in rows),
    }


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def diagnose(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    *,
    success_ratio: float,
    abort_ratio: float,
    min_candidate_rows: int,
) -> dict[str, Any]:
    baseline = summarize(baseline_rows)
    candidate = summarize(candidate_rows)
    weighted_ratio = ratio(candidate.get("effective_hps_weighted"), baseline.get("effective_hps_weighted"))
    mean_ratio = ratio(candidate.get("effective_hps_mean"), baseline.get("effective_hps_mean"))
    collect_ratio = ratio(candidate.get("collect_hps_mean"), baseline.get("collect_hps_mean"))
    inf_bs_ratio = ratio(candidate.get("inference_batch_size_mean"), baseline.get("inference_batch_size_mean"))
    if candidate.get("rows", 0) < min_candidate_rows or weighted_ratio is None:
        decision = "PENDING_MIN_ROWS"
    elif weighted_ratio < abort_ratio:
        decision = "ABORT_THRESHOLD_CONFIRMED_ROLLBACK_AT_EXACT_GATE"
    elif weighted_ratio >= success_ratio:
        decision = "CONTINUE_SPEED_GATE_CURRENTLY_PASS"
    else:
        decision = "CONTINUE_SPEED_WARN_ABOVE_ABORT"
    return {
        "baseline": baseline,
        "candidate": candidate,
        "ratios": {
            "effective_hps_weighted": weighted_ratio,
            "effective_hps_mean": mean_ratio,
            "collect_hps_mean": collect_ratio,
            "inference_batch_size_mean": inf_bs_ratio,
        },
        "thresholds": {
            "success_ratio": success_ratio,
            "abort_ratio": abort_ratio,
            "min_candidate_rows": min_candidate_rows,
        },
        "decision": decision,
        "terminal_method_judgment": False,
        "claim_scope": "engineering throughput only; no poker strength inference",
    }


def markdown(payload: dict[str, Any]) -> str:
    baseline = payload["baseline"]
    candidate = payload["candidate"]
    ratios = payload["ratios"]
    return "\n".join(
        [
            "# EXP-005 Speed Diagnosis",
            "",
            f"- Decision: `{payload['decision']}`",
            f"- Checked at: `{payload['checked_at']}`",
            f"- Cutover hands: `{payload['cutover_hands']:,}`",
            f"- Baseline exact actual-hand window: `{payload['baseline_lower_hands']:,}..{payload['cutover_hands']:,}`",
            f"- Baseline rows/effective h/s weighted: `{baseline['rows']}` / `{baseline['effective_hps_weighted']:.3f}`",
            f"- Candidate tail rows/effective h/s weighted: `{candidate['rows']}` / `{candidate['effective_hps_weighted']:.3f}`",
            f"- Effective weighted ratio: `{ratios['effective_hps_weighted']:.4f}` (success `>= {payload['thresholds']['success_ratio']:.2f}`, abort `< {payload['thresholds']['abort_ratio']:.2f}`)",
            f"- Collect h/s ratio: `{ratios['collect_hps_mean']:.4f}`",
            f"- Inference batch ratio: `{ratios['inference_batch_size_mean']:.4f}`",
            "",
            "The lower inference batch size is real, but PPO time is also lower; the registered gate uses effective wall-clock throughput. This is a provisional operational diagnosis, not the terminal 20M method judgment and not strength evidence.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-run-dir", required=True)
    parser.add_argument("--candidate-run-dir", required=True)
    parser.add_argument("--cutover-hands", type=int, required=True)
    parser.add_argument("--baseline-actual-hands", type=int, default=20_000_000)
    parser.add_argument("--candidate-tail", type=int, default=60)
    parser.add_argument("--min-candidate-rows", type=int, default=60)
    parser.add_argument("--success-ratio", type=float, default=0.90)
    parser.add_argument("--abort-ratio", type=float, default=0.85)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()

    baseline_all = parse_log(Path(args.baseline_run_dir) / "latest_train.log")
    candidate_all = parse_log(Path(args.candidate_run_dir) / "latest_train.log")
    lower = args.cutover_hands - args.baseline_actual_hands
    baseline_rows = [row for row in baseline_all if lower <= int(row["hands"]) <= args.cutover_hands]
    candidate_rows = [row for row in candidate_all if int(row["hands"]) > args.cutover_hands]
    if args.candidate_tail > 0:
        candidate_rows = candidate_rows[-args.candidate_tail :]
    payload = diagnose(
        baseline_rows,
        candidate_rows,
        success_ratio=args.success_ratio,
        abort_ratio=args.abort_ratio,
        min_candidate_rows=args.min_candidate_rows,
    )
    payload.update(
        {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "baseline_run_dir": args.baseline_run_dir,
            "candidate_run_dir": args.candidate_run_dir,
            "cutover_hands": args.cutover_hands,
            "baseline_lower_hands": lower,
        }
    )
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_md.write_text(markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
