#!/usr/bin/env python3
"""Trainerless PCV006 localization of H17 real-model actor-state differences."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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
)


PREREG_SHA = "255b38d28b3115db543f70c29549c4cc2e54ae7955da97fa7150dfe7db2a0b9f"
SOURCE_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
TRANSITION_SEED = 2026071980
UPDATE_SEED = 2026971980


def tensor_diff(left: torch.Tensor, right: torch.Tensor) -> dict[str, Any] | None:
    if torch.equal(left, right):
        return None
    delta = (left.detach().cpu().to(torch.float64) - right.detach().cpu().to(torch.float64)).abs()
    return {
        "dtype": str(left.dtype),
        "shape": list(left.shape),
        "max_abs": float(delta.max()) if delta.numel() else 0.0,
        "nonzero": int(torch.count_nonzero(delta)),
        "finite": bool(torch.isfinite(delta).all()),
    }


def optimizer_diffs(left: dict[str, dict[str, Any]], right: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in sorted(set(left) | set(right)):
        lstate, rstate = left.get(name, {}), right.get(name, {})
        for field in sorted(set(lstate) | set(rstate)):
            lv, rv = lstate.get(field), rstate.get(field)
            if torch.is_tensor(lv) and torch.is_tensor(rv):
                diff = tensor_diff(lv, rv)
                if diff:
                    rows.append({"name": name, "field": field, **diff})
            elif lv != rv:
                rows.append({
                    "name": name,
                    "field": field,
                    "dtype": type(lv).__name__,
                    "shape": [],
                    "left": lv,
                    "right": rv,
                    "finite": not isinstance(lv, float) or (math.isfinite(lv) and math.isfinite(rv)),
                })
    return rows


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
        raise SystemExit("refusing to overwrite immutable PCV006 result")
    if sha256(args.preregistration) != PREREG_SHA or sha256(args.source) != SOURCE_SHA:
        raise SystemExit("PCV006 preregistration/source identity mismatch")
    if active_forbidden_processes():
        raise SystemExit("PCV006 forbidden trainer/evaluator process")
    path1 = path1_identity(args.path1_pid, args.path1_workers)
    checkpoint = torch.load(args.source, map_location="cpu", weights_only=False)
    transitions = deterministic_transitions(checkpoint, args.device, TRANSITION_SEED, 4096)
    _, mse_stats, mse_state, mse_optimizer = one_full_update(
        checkpoint, transitions, args.device, "mse", UPDATE_SEED, 1024, 4, 1e-12
    )
    _, smooth_stats, smooth_state, smooth_optimizer = one_full_update(
        checkpoint, transitions, args.device, "smooth_l1", UPDATE_SEED, 1024, 4, 1e-12
    )
    model, optimizer = build_model_and_optimizer(checkpoint, "cpu")
    parameter_names = {name for name, _ in model.named_parameters()}
    buffer_names = {name for name, _ in model.named_buffers()}
    del optimizer, model

    model_differences: list[dict[str, Any]] = []
    for name in sorted(mse_state):
        diff = tensor_diff(mse_state[name], smooth_state[name])
        if diff:
            role = "value_head" if name.startswith("value_head.") else (
                "parameter" if name in parameter_names else "buffer" if name in buffer_names else "other_state"
            )
            model_differences.append({"name": name, "role": role, **diff})
    optimizer_differences = optimizer_diffs(mse_optimizer, smooth_optimizer)
    non_value_model = [row for row in model_differences if row["role"] != "value_head"]
    non_value_optimizer = [row for row in optimizer_differences if not row["name"].startswith("value_head.")]
    value_model = [row for row in model_differences if row["role"] == "value_head"]
    forced_shape = all(
        stats.get("kl_early_stop_triggered") is True
        and int(stats.get("ppo_epochs_completed", -1)) == 1
        and int(stats.get("value_head_catchup_epochs", -1)) == 3
        and stats.get("value_head_catchup_actor_state_unchanged") is True
        for stats in (mse_stats, smooth_stats)
    )
    finite = all(row.get("finite") is True for row in model_differences + optimizer_differences)
    identity_failure_reproduced = bool(non_value_model or non_value_optimizer)
    result = {
        "schema_version": "v5.pcv006.result.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS_LOCALIZATION_COMPLETE" if identity_failure_reproduced and finite and forced_shape else "FAIL_CLOSED",
        "classification": "PCV006_PASS_REAL_MODEL_ACTOR_STATE_DIFFERENCE_LOCALIZED" if identity_failure_reproduced and finite and forced_shape else "PCV006_FAIL",
        "preregistration_sha256": PREREG_SHA,
        "source": {"path": str(args.source.resolve()), "sha256": SOURCE_SHA, "iteration": 35051, "hands": 576021901},
        "workload": {
            "rows": 4096, "mini_batch_size": 1024, "ppo_epochs": 4, "target_kl": 1e-12,
            "old_log_prob_offset": 10.0, "transition_seed": TRANSITION_SEED,
            "identity_update_seed": UPDATE_SEED, "device": args.device,
            "transition_sha256": transition_sha256(transitions),
        },
        "h17_identity_failure_reproduced": identity_failure_reproduced,
        "forced_trigger_shape_pass": forced_shape,
        "all_numerics_finite": finite,
        "model_differences": model_differences,
        "optimizer_differences": optimizer_differences,
        "non_value_model_differences": non_value_model,
        "non_value_optimizer_differences": non_value_optimizer,
        "value_head_model_differences": value_model,
        "counts": {
            "model_total": len(model_differences),
            "model_non_value": len(non_value_model),
            "optimizer_total": len(optimizer_differences),
            "optimizer_non_value": len(non_value_optimizer),
            "value_head_model": len(value_model),
        },
        "stats": {"mse": mse_stats, "smooth_l1": smooth_stats},
        "path1": path1,
        "trainer_started": False,
        "checkpoint_written": False,
        "official_hands": 0,
        "behavior_or_method_inference": "FORBIDDEN",
        "next_authority": "ROUTE_REVIEW017_ONLY",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "overall": result["overall"], "classification": result["classification"],
        "counts": result["counts"], "non_value_model_names": [row["name"] for row in non_value_model],
        "non_value_optimizer_names": sorted({row["name"] for row in non_value_optimizer}),
    }, indent=2, sort_keys=True))
    return 0 if result["overall"] == "PASS_LOCALIZATION_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
