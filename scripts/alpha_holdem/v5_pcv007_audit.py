#!/usr/bin/env python3
"""Independent fail-closed audit for the immutable PCV007 result."""
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


PREREG_SHA = "71b6962793b26db3ea852ff4bff7424c7688dd800a3c6f70306aef2310a20c7d"
SOURCE_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
EXPECTED_PAIRS = {(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)


def pair_coverage(rows: list[dict[str, Any]]) -> set[tuple[int, int]]:
    return {tuple(int(value) for value in row["pair"]) for row in rows}


def maximum(rows: list[dict[str, Any]]) -> float:
    return max((float(row["max_abs"]) for row in rows), default=0.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--path1-pid", type=int, required=True)
    parser.add_argument("--path1-workers", type=int, choices=[6], default=6)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite immutable PCV007 audit")

    result = json.loads(args.result.read_text(encoding="utf-8"))
    numerical = result["numerical_envelope"]
    timing = result["timing"]
    raw = timing["raw_milliseconds"]
    repeat_medians = {
        mode: [float(statistics.median(repeat)) for repeat in raw[mode]]
        for mode in ("mse", "smooth_l1")
    }
    mode_medians = {
        mode: float(statistics.median(repeat_medians[mode]))
        for mode in ("mse", "smooth_l1")
    }
    throughput_ratio = mode_medians["mse"] / mode_medians["smooth_l1"]
    mse_stability = min(repeat_medians["mse"]) / max(repeat_medians["mse"])
    all_numeric_rows = (
        numerical["cross_mode_model_differences"]
        + numerical["cross_mode_optimizer_differences"]
        + numerical["same_mode"]["mse"]["model_differences"]
        + numerical["same_mode"]["mse"]["optimizer_differences"]
        + numerical["same_mode"]["smooth_l1"]["model_differences"]
        + numerical["same_mode"]["smooth_l1"]["optimizer_differences"]
    )
    path1 = path1_identity(args.path1_pid, args.path1_workers)
    forbidden = active_forbidden_processes()

    checks = {
        "preregistration_binding": sha256(args.preregistration) == PREREG_SHA
        and result["preregistration_sha256"] == PREREG_SHA,
        "source_identity": sha256(args.source) == SOURCE_SHA
        and result["source"] == {
            "path": str(args.source.resolve()), "sha256": SOURCE_SHA,
            "iteration": 35051, "hands": 576021901,
        },
        "runner_binding": sha256(args.runner) == result["tool_sha256"],
        "workload_identity": result["workload"] | {} == result["workload"]
        and all([
            result["workload"]["rows"] == 4096,
            result["workload"]["mini_batch_size"] == 1024,
            result["workload"]["ppo_epochs"] == 4,
            close(result["workload"]["target_kl"], 1e-12),
            close(result["workload"]["old_log_prob_offset"], 10.0),
            result["workload"]["transition_seed"] == 2026071980,
            result["workload"]["identity_update_seed"] == 2026971980,
            result["workload"]["same_mode_replicas_each"] == 4,
            result["workload"]["timer"] == "torch.cuda.Event_with_synchronize",
            result["workload"]["warmup_updates_per_mode"] == 4,
            result["workload"]["timed_updates_per_repeat_per_mode"] == 16,
            result["workload"]["repeats"] == 7,
        ]),
        "timing_dimensions": all(
            len(raw[mode]) == 7 and all(len(repeat) == 16 for repeat in raw[mode])
            for mode in ("mse", "smooth_l1")
        ),
        "timing_values_finite_positive": all(
            math.isfinite(float(value)) and float(value) > 0
            for mode in ("mse", "smooth_l1") for repeat in raw[mode] for value in repeat
        ),
        "timing_medians_recomputed": all(
            close(repeat_medians[mode][index], timing["repeat_median_milliseconds"][mode][index])
            for mode in ("mse", "smooth_l1") for index in range(7)
        ) and all(
            close(mode_medians[mode], timing["mode_median_milliseconds"][mode])
            for mode in ("mse", "smooth_l1")
        ),
        "throughput_ratio_recomputed": close(throughput_ratio, result["gates"]["gpu_event_throughput_ratio"])
        and throughput_ratio >= 0.85,
        "mse_stability_recomputed": close(mse_stability, result["gates"]["gpu_event_mse_stability_ratio"])
        and mse_stability >= 0.95,
        "same_mode_pair_coverage": all(
            pair_coverage(numerical["same_mode"][mode][kind]) == EXPECTED_PAIRS
            for mode in ("mse", "smooth_l1")
            for kind in ("model_differences", "optimizer_differences")
        ),
        "same_mode_maxima_recomputed": all(
            close(
                maximum(numerical["same_mode"][mode][kind + "_differences"]),
                numerical["same_mode"][mode][kind + "_max_abs"],
            )
            for mode in ("mse", "smooth_l1") for kind in ("model", "optimizer")
        ),
        "cross_mode_maxima_recomputed": close(
            maximum(numerical["cross_mode_model_differences"]), numerical["cross_mode_model_max_abs"]
        ) and close(
            maximum(numerical["cross_mode_optimizer_differences"]), numerical["cross_mode_optimizer_max_abs"]
        ),
        "cross_mode_tolerances_pass": numerical["cross_mode_model_max_abs"] <= 1e-6
        and numerical["cross_mode_optimizer_max_abs"] <= 1e-8,
        "all_reported_differences_finite": all(row.get("finite") is True for row in all_numeric_rows),
        "registered_gates_exact": all([
            result["gates"]["forced_trigger_shape_pass"] is True,
            result["gates"]["cross_mode_non_value_model_within_tolerance"] is True,
            result["gates"]["cross_mode_non_value_optimizer_within_tolerance"] is True,
            result["gates"]["same_mode_envelope_complete"] is True,
            result["gates"]["all_numerics_finite"] is True,
            result["gates"]["gpu_event_throughput_ratio_pass"] is True,
            result["gates"]["gpu_event_mse_stability_ratio_pass"] is True,
        ]),
        "classification_exact": result["overall"] == "PASS"
        and result["classification"] == "PCV007_PASS_NUMERICAL_ENVELOPE_AND_GPU_EVENT_TIMING",
        "trainerless_no_checkpoint": result["trainer_started"] is False
        and result["checkpoint_written"] is False and forbidden == [],
        "path1_unchanged": result["path1"] == path1 and path1["changed"] is False
        and path1["gpu_use"] is False and path1["priority"] == "BelowNormal",
        "no_official_or_method_inference": result["official_hands"] == 0
        and result["behavior_or_method_inference"] == "FORBIDDEN"
        and result["next_authority"] == "ROUTE_REVIEW018_ONLY",
    }
    failed = [name for name, passed in checks.items() if not passed]
    audit = {
        "schema_version": "v5.pcv007.result_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "artifact_sha256": sha256(args.result),
        "runner_sha256": sha256(args.runner),
        "checks": checks,
        "checks_passed": len(checks) - len(failed),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "classification": result["classification"] if not failed else "PCV007_AUDIT_FAIL_CLOSED",
        "recomputed": {
            "throughput_ratio": throughput_ratio,
            "mse_stability_ratio": mse_stability,
            "cross_mode_model_max_abs": maximum(numerical["cross_mode_model_differences"]),
            "cross_mode_optimizer_max_abs": maximum(numerical["cross_mode_optimizer_differences"]),
        },
        "official_hands": 0,
        "behavior_launch_authority": "NONE_ROUTE_REVIEW018_ONLY",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": audit["overall"], "passed": audit["checks_passed"], "total": audit["checks_total"], "failed": failed}, indent=2))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
