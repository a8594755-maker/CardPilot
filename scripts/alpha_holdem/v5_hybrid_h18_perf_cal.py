#!/usr/bin/env python3
"""Registered trainerless representative full-PPO pre-arm calibration for H18."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

from v5_hybrid_h17_perf_cal import (
    active_forbidden_processes,
    atomic_json,
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


SCHEMA = "v5.hybrid.h18.representative_perf_cal.v1"
SOURCE_ITERATION = 35051
SOURCE_HANDS = 576021901
SOURCE_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
THROUGHPUT_RATIO_MIN = 0.85
MSE_STABILITY_RATIO_MIN = 0.95
MODEL_TOLERANCE = 1e-6
OPTIMIZER_TOLERANCE = 1e-8
FORCED_OLD_LOG_PROB_OFFSET = 10.0


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


def forced_shape(stats: dict[str, Any]) -> bool:
    return (
        stats.get("kl_early_stop_triggered") is True
        and int(stats.get("ppo_epochs_completed", -1)) == 1
        and int(stats.get("value_head_catchup_epochs", -1)) == 3
        and stats.get("value_head_catchup_actor_state_unchanged") is True
    )


def tolerance_pair(
    checkpoint: dict[str, Any], transitions: list[tuple], device: str, seed: int,
    mini_batch_size: int, epochs: int, target_kl: float,
) -> dict[str, Any]:
    _, mse_stats, mse_state, mse_opt = one_full_update(
        checkpoint, transitions, device, "mse", seed, mini_batch_size, epochs, target_kl
    )
    _, smooth_stats, smooth_state, smooth_opt = one_full_update(
        checkpoint, transitions, device, "smooth_l1", seed, mini_batch_size, epochs, target_kl
    )
    model, _ = build_model_and_optimizer(checkpoint, "cpu")
    parameter_names = {name for name, _ in model.named_parameters()}
    del model
    model_rows = state_differences(mse_state, smooth_state, parameter_names)
    optimizer_rows = [
        row for row in optimizer_diffs(mse_opt, smooth_opt)
        if not row["name"].startswith("value_head.")
    ]
    model_max = maximum(model_rows)
    optimizer_max = maximum(optimizer_rows)
    value_head_differs = any(
        not torch.equal(value, smooth_state[name])
        for name, value in mse_state.items() if name.startswith("value_head.")
    )
    finite = all(
        math.isfinite(float(stats[key]))
        for stats in (mse_stats, smooth_stats)
        for key in ("policy_loss", "value_loss", "entropy", "approx_kl", "value_head_catchup_loss")
    ) and all(row.get("finite") is True for row in model_rows + optimizer_rows)
    shape = forced_shape(mse_stats) and forced_shape(smooth_stats)
    passed = (
        model_max <= MODEL_TOLERANCE
        and optimizer_max <= OPTIMIZER_TOLERANCE
        and value_head_differs and finite and shape
    )
    return {
        "pass": passed,
        "non_value_model_differences": model_rows,
        "non_value_optimizer_differences": optimizer_rows,
        "non_value_model_max_abs": model_max,
        "non_value_optimizer_max_abs": optimizer_max,
        "non_value_model_max_abs_tolerance": MODEL_TOLERANCE,
        "non_value_optimizer_max_abs_tolerance": OPTIMIZER_TOLERANCE,
        "non_value_model_within_tolerance": model_max <= MODEL_TOLERANCE,
        "non_value_optimizer_within_tolerance": optimizer_max <= OPTIMIZER_TOLERANCE,
        "value_head_differs": value_head_differs,
        "all_reported_numerics_finite": finite,
        "forced_kl_and_three_catchup_epochs": shape,
        "bitwise_identity_used_as_gate": False,
        "mse_stats": {key: mse_stats[key] for key in (
            "ppo_epochs_completed", "kl_early_stop_triggered", "value_head_catchup_epochs",
            "value_head_catchup_minibatches", "value_head_catchup_actor_state_unchanged",
        )},
        "smooth_l1_stats": {key: smooth_stats[key] for key in (
            "ppo_epochs_completed", "kl_early_stop_triggered", "value_head_catchup_epochs",
            "value_head_catchup_minibatches", "value_head_catchup_actor_state_unchanged",
        )},
    }


def gpu_event_update(
    checkpoint: dict[str, Any], transitions: list[tuple], mode: str, seed: int,
    mini_batch_size: int, epochs: int, target_kl: float,
) -> tuple[float, dict[str, Any]]:
    model, optimizer = build_model_and_optimizer(checkpoint, "cuda")
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.cuda.synchronize()
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    stats = trinal_clip_ppo_update(
        model, optimizer, transitions, "cuda",
        **update_kwargs(mode, mini_batch_size, epochs, target_kl),
    )
    end.record()
    torch.cuda.synchronize()
    elapsed_ms = float(start.elapsed_time(end))
    del optimizer, model, start, end
    torch.cuda.empty_cache()
    return elapsed_ms, stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--arm", choices=("control", "treatment", "offline-readiness"), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--rows", type=int, default=4096)
    parser.add_argument("--mini-batch-size", type=int, default=1024)
    parser.add_argument("--ppo-epochs", type=int, default=4)
    parser.add_argument("--target-kl", type=float, default=1e-12)
    parser.add_argument("--warmup-updates", type=int, default=4)
    parser.add_argument("--timed-updates", type=int, default=16)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--device", choices=("cuda",), default="cuda")
    parser.add_argument("--path1-pid", type=int, default=23720)
    parser.add_argument("--path1-workers", type=int, default=6)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    out = args.out.resolve()
    try:
        if out.exists():
            raise FileExistsError(out)
        if not source.is_file() or sha256(source) != args.source_sha256.lower() or args.source_sha256.lower() != SOURCE_SHA:
            raise ValueError("source checkpoint identity mismatch")
        if not torch.cuda.is_available():
            raise ValueError("CUDA unavailable")
        if (args.rows, args.mini_batch_size, args.ppo_epochs, args.target_kl,
                args.warmup_updates, args.timed_updates, args.repeats) != (
                4096, 1024, 4, 1e-12, 4, 16, 7):
            raise ValueError("registered H18 representative calibration dimensions mismatch")
        forbidden = active_forbidden_processes()
        if forbidden:
            raise ValueError(f"forbidden active process(es): {forbidden}")
        path1 = path1_identity(args.path1_pid, args.path1_workers)
        checkpoint = torch.load(source, map_location="cpu", weights_only=False)
        if int(checkpoint.get("iteration", -1)) != SOURCE_ITERATION or int(checkpoint.get("total_hands", -1)) != SOURCE_HANDS:
            raise ValueError("source iteration/hands mismatch")
        transitions = deterministic_transitions(checkpoint, args.device, args.seed, args.rows)
        transition_hash = transition_sha256(transitions)
        equivalence = tolerance_pair(
            checkpoint, transitions, args.device, args.seed + 900000,
            args.mini_batch_size, args.ppo_epochs, args.target_kl,
        )
        all_stats: list[dict[str, Any]] = []
        order = ("mse", "smooth_l1")
        for warmup_index in range(args.warmup_updates):
            modes = order if warmup_index % 2 == 0 else tuple(reversed(order))
            for mode in modes:
                _, stats = gpu_event_update(
                    checkpoint, transitions, mode, args.seed + 100000 + warmup_index,
                    args.mini_batch_size, args.ppo_epochs, args.target_kl,
                )
                all_stats.append(stats)
        samples: dict[str, list[list[float]]] = {"mse": [], "smooth_l1": []}
        for repeat in range(args.repeats):
            modes = order if repeat % 2 == 0 else tuple(reversed(order))
            for mode in modes:
                values: list[float] = []
                for update_index in range(args.timed_updates):
                    elapsed_ms, stats = gpu_event_update(
                        checkpoint, transitions, mode, args.seed + 200000 + repeat * 100 + update_index,
                        args.mini_batch_size, args.ppo_epochs, args.target_kl,
                    )
                    if not forced_shape(stats):
                        raise RuntimeError("timed update violated registered forced-KL/catch-up shape")
                    values.append(elapsed_ms)
                    all_stats.append(stats)
                samples[mode].append(values)
        repeat_medians = {
            mode: [float(statistics.median(values)) for values in repeats]
            for mode, repeats in samples.items()
        }
        mode_medians = {
            mode: float(statistics.median(values)) for mode, values in repeat_medians.items()
        }
        throughput_ratio = mode_medians["mse"] / mode_medians["smooth_l1"]
        mse_stability = min(repeat_medians["mse"]) / max(repeat_medians["mse"])
        timing_finite = all(
            math.isfinite(value) and value > 0
            for repeats in samples.values() for values in repeats for value in values
        )
        passed = (
            throughput_ratio >= THROUGHPUT_RATIO_MIN
            and mse_stability >= MSE_STABILITY_RATIO_MIN
            and equivalence["pass"] and timing_finite
            and all(forced_shape(stats) for stats in all_stats)
        )
        payload = {
            "schema_version": SCHEMA,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "PASS" if passed else "FAIL_CLOSED",
            "classification": "H18_REPRESENTATIVE_PERF_CAL_PASS" if passed else "H18_REPRESENTATIVE_PERF_CAL_FAIL",
            "arm": args.arm,
            "authority": "READINESS_ONLY" if args.arm == "offline-readiness" else "IMMEDIATE_PER_ARM_GATE",
            "source": {"path": str(source), "sha256": sha256(source), "iteration": SOURCE_ITERATION, "hands": SOURCE_HANDS, "optimizer_loaded": True},
            "workload": {
                "seed": args.seed, "transition_sha256": transition_hash,
                "rows": args.rows, "mini_batch_size": args.mini_batch_size,
                "ppo_epochs": args.ppo_epochs, "target_kl": args.target_kl,
                "forced_old_log_prob_offset": FORCED_OLD_LOG_PROB_OFFSET,
                "timer": "torch.cuda.Event_with_synchronize",
                "warmup_updates_per_mode": args.warmup_updates,
                "timed_updates_per_repeat_per_mode": args.timed_updates,
                "repeats": args.repeats, "order": "ALTERNATING_MSE_SMOOTHL1",
                "device": "cuda", "device_name": torch.cuda.get_device_name(0),
                "full_trinal_clip_ppo_update": True,
                "forced_kl_early_stop": True, "value_head_catchup_epochs": 3,
            },
            "timing": {
                "raw_milliseconds": samples,
                "repeat_median_milliseconds": repeat_medians,
                "mode_median_milliseconds": mode_medians,
                "full_update_throughput_ratio": throughput_ratio,
                "mse_repeat_stability_ratio": mse_stability,
                "all_values_finite_positive": timing_finite,
            },
            "equivalence": equivalence,
            "gates": {
                "full_update_throughput_ratio_min": THROUGHPUT_RATIO_MIN,
                "full_update_throughput_ratio_pass": throughput_ratio >= THROUGHPUT_RATIO_MIN,
                "mse_repeat_stability_ratio_min": MSE_STABILITY_RATIO_MIN,
                "mse_repeat_stability_ratio_pass": mse_stability >= MSE_STABILITY_RATIO_MIN,
                "non_value_model_tolerance_pass": equivalence["non_value_model_within_tolerance"],
                "non_value_optimizer_tolerance_pass": equivalence["non_value_optimizer_within_tolerance"],
                "value_head_differs_pass": equivalence["value_head_differs"],
                "all_numerics_finite_pass": equivalence["all_reported_numerics_finite"] and timing_finite,
                "forced_shape_pass": equivalence["forced_kl_and_three_catchup_epochs"] and all(forced_shape(stats) for stats in all_stats),
            },
            "path1": path1,
            "forbidden_processes": forbidden,
            "behavior_change": False,
            "checkpoint_changed": False,
            "trainer_started": False,
            "official_hands": 0,
            "strength_claim": "FORBIDDEN",
            "tool_sha256": sha256(Path(__file__).resolve()),
        }
        atomic_json(out, payload, exclusive=True)
        print(json.dumps({"overall": payload["overall"], "classification": payload["classification"], "gates": payload["gates"]}, indent=2, sort_keys=True))
        return 0 if passed else 2
    except Exception as exc:
        failure = {
            "schema_version": SCHEMA,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "FAIL_CLOSED",
            "classification": "H18_REPRESENTATIVE_PERF_CAL_EXECUTION_FAILURE",
            "arm": args.arm,
            "error": f"{type(exc).__name__}: {exc}",
            "trainer_started": False,
            "behavior_change": False,
            "official_hands": 0,
            "strength_claim": "FORBIDDEN",
        }
        if not out.exists():
            atomic_json(out, failure, exclusive=True)
        print(json.dumps(failure, indent=2, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
