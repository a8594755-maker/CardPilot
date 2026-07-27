#!/usr/bin/env python3
"""Independent fail-closed audit of one immutable H18 representative calibration."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from v5_hybrid_h17_perf_cal import active_forbidden_processes, path1_identity


SOURCE_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
THROUGHPUT_RATIO_MIN = 0.85
MSE_STABILITY_RATIO_MIN = 0.95
MODEL_TOLERANCE = 1e-6
OPTIMIZER_TOLERANCE = 1e-8


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)


def maximum(rows: list[dict[str, Any]]) -> float:
    return max((float(row["max_abs"]) for row in rows), default=0.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--tool", type=Path, required=True)
    parser.add_argument("--path1-pid", type=int, required=True)
    parser.add_argument("--path1-workers", type=int, choices=[6], default=6)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite immutable H18 calibration audit")
    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    raw = artifact.get("timing", {}).get("raw_milliseconds", {})
    repeat_medians = {
        mode: [float(statistics.median(repeat)) for repeat in raw.get(mode, [])]
        for mode in ("mse", "smooth_l1")
    }
    mode_medians = {
        mode: float(statistics.median(repeat_medians[mode])) if repeat_medians[mode] else -1.0
        for mode in ("mse", "smooth_l1")
    }
    ratio = mode_medians["mse"] / mode_medians["smooth_l1"] if mode_medians["smooth_l1"] > 0 else -1.0
    stability = min(repeat_medians["mse"]) / max(repeat_medians["mse"]) if repeat_medians["mse"] and max(repeat_medians["mse"]) > 0 else -1.0
    equivalence = artifact.get("equivalence", {})
    model_rows = equivalence.get("non_value_model_differences", [])
    optimizer_rows = equivalence.get("non_value_optimizer_differences", [])
    path1 = path1_identity(args.path1_pid, args.path1_workers)
    forbidden = active_forbidden_processes()
    checks = {
        "schema_and_classification": artifact.get("schema_version") == "v5.hybrid.h18.representative_perf_cal.v1"
        and artifact.get("overall") == "PASS" and artifact.get("classification") == "H18_REPRESENTATIVE_PERF_CAL_PASS",
        "arm_authority": artifact.get("arm") in {"control", "treatment", "offline-readiness"}
        and artifact.get("authority") == ("READINESS_ONLY" if artifact.get("arm") == "offline-readiness" else "IMMEDIATE_PER_ARM_GATE"),
        "source_identity": artifact.get("source", {}).get("sha256") == SOURCE_SHA
        and artifact.get("source", {}).get("iteration") == 35051
        and artifact.get("source", {}).get("hands") == 576021901
        and artifact.get("source", {}).get("optimizer_loaded") is True,
        "tool_binding": artifact.get("tool_sha256") == sha256(args.tool),
        "workload_identity": all([
            artifact.get("workload", {}).get("rows") == 4096,
            artifact.get("workload", {}).get("mini_batch_size") == 1024,
            artifact.get("workload", {}).get("ppo_epochs") == 4,
            close(artifact.get("workload", {}).get("target_kl", -1), 1e-12),
            close(artifact.get("workload", {}).get("forced_old_log_prob_offset", -1), 10.0),
            artifact.get("workload", {}).get("timer") == "torch.cuda.Event_with_synchronize",
            artifact.get("workload", {}).get("warmup_updates_per_mode") == 4,
            artifact.get("workload", {}).get("timed_updates_per_repeat_per_mode") == 16,
            artifact.get("workload", {}).get("repeats") == 7,
            artifact.get("workload", {}).get("order") == "ALTERNATING_MSE_SMOOTHL1",
            artifact.get("workload", {}).get("device") == "cuda",
            artifact.get("workload", {}).get("full_trinal_clip_ppo_update") is True,
            artifact.get("workload", {}).get("value_head_catchup_epochs") == 3,
        ]),
        "timing_dimensions": all(
            len(raw.get(mode, [])) == 7 and all(len(repeat) == 16 for repeat in raw.get(mode, []))
            for mode in ("mse", "smooth_l1")
        ),
        "timing_finite_positive": all(
            math.isfinite(float(value)) and float(value) > 0
            for mode in ("mse", "smooth_l1") for repeat in raw.get(mode, []) for value in repeat
        ),
        "timing_medians_recomputed": all(
            close(repeat_medians[mode][index], artifact["timing"]["repeat_median_milliseconds"][mode][index])
            for mode in ("mse", "smooth_l1") for index in range(7)
        ) and all(close(mode_medians[mode], artifact["timing"]["mode_median_milliseconds"][mode]) for mode in ("mse", "smooth_l1")),
        "throughput_recomputed_and_pass": close(ratio, artifact["timing"]["full_update_throughput_ratio"])
        and ratio >= THROUGHPUT_RATIO_MIN and artifact["gates"]["full_update_throughput_ratio_pass"] is True,
        "stability_recomputed_and_pass": close(stability, artifact["timing"]["mse_repeat_stability_ratio"])
        and stability >= MSE_STABILITY_RATIO_MIN and artifact["gates"]["mse_repeat_stability_ratio_pass"] is True,
        "model_maximum_recomputed": close(maximum(model_rows), equivalence.get("non_value_model_max_abs", -1)),
        "optimizer_maximum_recomputed": close(maximum(optimizer_rows), equivalence.get("non_value_optimizer_max_abs", -1)),
        "model_tolerance_gate": equivalence.get("non_value_model_max_abs_tolerance") == MODEL_TOLERANCE
        and maximum(model_rows) <= MODEL_TOLERANCE and artifact["gates"]["non_value_model_tolerance_pass"] is True,
        "optimizer_tolerance_gate": equivalence.get("non_value_optimizer_max_abs_tolerance") == OPTIMIZER_TOLERANCE
        and maximum(optimizer_rows) <= OPTIMIZER_TOLERANCE and artifact["gates"]["non_value_optimizer_tolerance_pass"] is True,
        "bitwise_gate_forbidden": equivalence.get("bitwise_identity_used_as_gate") is False,
        "value_head_differs": equivalence.get("value_head_differs") is True and artifact["gates"]["value_head_differs_pass"] is True,
        "all_numerics_finite": equivalence.get("all_reported_numerics_finite") is True
        and all(row.get("finite") is True for row in model_rows + optimizer_rows)
        and artifact["gates"]["all_numerics_finite_pass"] is True,
        "forced_shape": equivalence.get("forced_kl_and_three_catchup_epochs") is True
        and artifact["gates"]["forced_shape_pass"] is True,
        "trainerless_no_checkpoint": artifact.get("trainer_started") is False
        and artifact.get("checkpoint_changed") is False and forbidden == [],
        "path1_unchanged": artifact.get("path1") == path1 and path1.get("changed") is False
        and path1.get("gpu_use") is False and path1.get("priority") == "BelowNormal",
        "no_behavior_or_official": artifact.get("behavior_change") is False
        and artifact.get("official_hands") == 0 and artifact.get("strength_claim") == "FORBIDDEN",
    }
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": "v5.hybrid.h18.representative_perf_cal_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "artifact_sha256": sha256(args.artifact),
        "tool_sha256": sha256(args.tool),
        "checks": checks,
        "checks_passed": len(checks) - len(failed),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "recomputed": {"throughput_ratio": ratio, "mse_stability_ratio": stability, "model_max_abs": maximum(model_rows), "optimizer_max_abs": maximum(optimizer_rows)},
        "behavior_launch_authority": "NONE_AUDIT_ONLY",
        "official_hands": 0,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": result["overall"], "passed": result["checks_passed"], "total": result["checks_total"], "failed": failed}, indent=2))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
