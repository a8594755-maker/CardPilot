#!/usr/bin/env python3
"""Trainerless PCV007 numerical-envelope and CUDA-event timing audit."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

from v5_hybrid_h17_perf_cal import (
    active_forbidden_processes,
    build_model_and_optimizer,
    deterministic_transitions,
    one_full_update,
    path1_identity,
    sha256,
    transition_sha256,
    update_kwargs,
)
from v5_pcv006_run import optimizer_diffs, tensor_diff
from alpha_holdem.train_mp3_hybrid_h1 import trinal_clip_ppo_update


PREREG_SHA = "71b6962793b26db3ea852ff4bff7424c7688dd800a3c6f70306aef2310a20c7d"
SOURCE_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
TRANSITION_SEED = 2026071980
UPDATE_SEED = 2026971980
MODEL_TOLERANCE = 1e-6
OPTIMIZER_TOLERANCE = 1e-8


def state_differences(
    left: dict[str, torch.Tensor], right: dict[str, torch.Tensor], parameter_names: set[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in sorted(left):
        if name.startswith("value_head."):
            continue
        diff = tensor_diff(left[name], right[name])
        if diff:
            rows.append({"name": name, "role": "parameter" if name in parameter_names else "buffer", **diff})
    return rows


def maximum(rows: list[dict[str, Any]]) -> float:
    return max((float(row.get("max_abs", 0.0)) for row in rows), default=0.0)


def gpu_event_update(
    checkpoint: dict[str, Any], transitions: list[tuple], mode: str, seed: int
) -> tuple[float, dict[str, Any]]:
    model, optimizer = build_model_and_optimizer(checkpoint, "cuda")
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.cuda.synchronize()
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    stats = trinal_clip_ppo_update(
        model,
        optimizer,
        transitions,
        "cuda",
        **update_kwargs(mode, 1024, 4, 1e-12),
    )
    end.record()
    torch.cuda.synchronize()
    elapsed_ms = float(start.elapsed_time(end))
    del optimizer, model, start, end
    torch.cuda.empty_cache()
    return elapsed_ms, stats


def forced_shape(stats: dict[str, Any]) -> bool:
    return (
        stats.get("kl_early_stop_triggered") is True
        and int(stats.get("ppo_epochs_completed", -1)) == 1
        and int(stats.get("value_head_catchup_epochs", -1)) == 3
        and stats.get("value_head_catchup_actor_state_unchanged") is True
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--device", choices=["cuda"], default="cuda")
    parser.add_argument("--path1-pid", type=int, required=True)
    parser.add_argument("--path1-workers", type=int, choices=[6], default=6)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite immutable PCV007 result")
    if sha256(args.preregistration) != PREREG_SHA or sha256(args.source) != SOURCE_SHA:
        raise SystemExit("PCV007 preregistration/source identity mismatch")
    forbidden = active_forbidden_processes()
    if forbidden:
        raise SystemExit("PCV007 forbidden trainer/evaluator process")
    path1 = path1_identity(args.path1_pid, args.path1_workers)
    checkpoint = torch.load(args.source, map_location="cpu", weights_only=False)
    transitions = deterministic_transitions(checkpoint, args.device, TRANSITION_SEED, 4096)
    model, optimizer = build_model_and_optimizer(checkpoint, "cpu")
    parameter_names = {name for name, _ in model.named_parameters()}
    del optimizer, model

    replicas: dict[str, list[dict[str, Any]]] = {"mse": [], "smooth_l1": []}
    all_stats: list[dict[str, Any]] = []
    for mode in ("mse", "smooth_l1"):
        for replica in range(4):
            _, stats, state, opt_state = one_full_update(
                checkpoint, transitions, args.device, mode, UPDATE_SEED, 1024, 4, 1e-12
            )
            replicas[mode].append({"state": state, "optimizer": opt_state, "stats": stats})
            all_stats.append(stats)

    same_mode: dict[str, Any] = {}
    for mode in ("mse", "smooth_l1"):
        model_rows: list[dict[str, Any]] = []
        optimizer_rows: list[dict[str, Any]] = []
        for left_index in range(4):
            for right_index in range(left_index + 1, 4):
                pair_model = state_differences(
                    replicas[mode][left_index]["state"], replicas[mode][right_index]["state"], parameter_names
                )
                pair_optimizer = [
                    row for row in optimizer_diffs(
                        replicas[mode][left_index]["optimizer"], replicas[mode][right_index]["optimizer"]
                    ) if not row["name"].startswith("value_head.")
                ]
                model_rows.extend({"pair": [left_index, right_index], **row} for row in pair_model)
                optimizer_rows.extend({"pair": [left_index, right_index], **row} for row in pair_optimizer)
        same_mode[mode] = {
            "model_differences": model_rows,
            "optimizer_differences": optimizer_rows,
            "model_max_abs": maximum(model_rows),
            "optimizer_max_abs": maximum(optimizer_rows),
        }

    cross_model = state_differences(
        replicas["mse"][0]["state"], replicas["smooth_l1"][0]["state"], parameter_names
    )
    cross_optimizer = [
        row for row in optimizer_diffs(
            replicas["mse"][0]["optimizer"], replicas["smooth_l1"][0]["optimizer"]
        ) if not row["name"].startswith("value_head.")
    ]
    cross_model_max = maximum(cross_model)
    cross_optimizer_max = maximum(cross_optimizer)

    for warmup in range(4):
        modes = ("mse", "smooth_l1") if warmup % 2 == 0 else ("smooth_l1", "mse")
        for mode in modes:
            _, stats = gpu_event_update(checkpoint, transitions, mode, UPDATE_SEED + 100000 + warmup)
            all_stats.append(stats)
    raw_ms: dict[str, list[list[float]]] = {"mse": [], "smooth_l1": []}
    for repeat in range(7):
        modes = ("mse", "smooth_l1") if repeat % 2 == 0 else ("smooth_l1", "mse")
        for mode in modes:
            values: list[float] = []
            for update in range(16):
                elapsed, stats = gpu_event_update(
                    checkpoint, transitions, mode, UPDATE_SEED + 200000 + repeat * 100 + update
                )
                values.append(elapsed)
                all_stats.append(stats)
            raw_ms[mode].append(values)
    repeat_medians = {
        mode: [float(statistics.median(values)) for values in raw_ms[mode]]
        for mode in ("mse", "smooth_l1")
    }
    mode_medians = {
        mode: float(statistics.median(repeat_medians[mode]))
        for mode in ("mse", "smooth_l1")
    }
    throughput_ratio = mode_medians["mse"] / mode_medians["smooth_l1"]
    mse_stability = min(repeat_medians["mse"]) / max(repeat_medians["mse"])
    finite = all(
        math.isfinite(value) and value > 0
        for mode in raw_ms.values() for repeat in mode for value in repeat
    ) and all(
        row.get("finite") is True
        for row in cross_model + cross_optimizer
        + same_mode["mse"]["model_differences"] + same_mode["mse"]["optimizer_differences"]
        + same_mode["smooth_l1"]["model_differences"] + same_mode["smooth_l1"]["optimizer_differences"]
    )
    gates = {
        "forced_trigger_shape_pass": all(forced_shape(stats) for stats in all_stats),
        "cross_mode_non_value_model_within_tolerance": cross_model_max <= MODEL_TOLERANCE,
        "cross_mode_non_value_optimizer_within_tolerance": cross_optimizer_max <= OPTIMIZER_TOLERANCE,
        "same_mode_envelope_complete": True,
        "all_numerics_finite": finite,
        "gpu_event_throughput_ratio": throughput_ratio,
        "gpu_event_throughput_ratio_min": 0.85,
        "gpu_event_throughput_ratio_pass": throughput_ratio >= 0.85,
        "gpu_event_mse_stability_ratio": mse_stability,
        "gpu_event_mse_stability_ratio_min": 0.95,
        "gpu_event_mse_stability_ratio_pass": mse_stability >= 0.95,
    }
    passed = all(value for key, value in gates.items() if key.endswith("_pass") or key in {
        "forced_trigger_shape_pass", "cross_mode_non_value_model_within_tolerance",
        "cross_mode_non_value_optimizer_within_tolerance", "same_mode_envelope_complete",
        "all_numerics_finite",
    })
    result = {
        "schema_version": "v5.pcv007.result.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if passed else "FAIL_CLOSED",
        "classification": "PCV007_PASS_NUMERICAL_ENVELOPE_AND_GPU_EVENT_TIMING" if passed else "PCV007_FAIL",
        "preregistration_sha256": PREREG_SHA,
        "source": {"path": str(args.source.resolve()), "sha256": SOURCE_SHA, "iteration": 35051, "hands": 576021901},
        "workload": {
            "rows": 4096, "mini_batch_size": 1024, "ppo_epochs": 4, "target_kl": 1e-12,
            "old_log_prob_offset": 10.0, "transition_seed": TRANSITION_SEED,
            "identity_update_seed": UPDATE_SEED, "same_mode_replicas_each": 4,
            "timer": "torch.cuda.Event_with_synchronize", "warmup_updates_per_mode": 4,
            "timed_updates_per_repeat_per_mode": 16, "repeats": 7,
            "transition_sha256": transition_sha256(transitions),
        },
        "numerical_envelope": {
            "same_mode": same_mode,
            "cross_mode_model_differences": cross_model,
            "cross_mode_optimizer_differences": cross_optimizer,
            "cross_mode_model_max_abs": cross_model_max,
            "cross_mode_optimizer_max_abs": cross_optimizer_max,
            "model_tolerance": MODEL_TOLERANCE,
            "optimizer_tolerance": OPTIMIZER_TOLERANCE,
        },
        "timing": {
            "raw_milliseconds": raw_ms,
            "repeat_median_milliseconds": repeat_medians,
            "mode_median_milliseconds": mode_medians,
        },
        "gates": gates,
        "path1": path1,
        "forbidden_processes": forbidden,
        "trainer_started": False,
        "checkpoint_written": False,
        "official_hands": 0,
        "behavior_or_method_inference": "FORBIDDEN",
        "next_authority": "ROUTE_REVIEW018_ONLY",
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": result["overall"], "classification": result["classification"], "gates": gates}, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
