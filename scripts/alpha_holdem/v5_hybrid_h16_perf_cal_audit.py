#!/usr/bin/env python3
"""Independent fail-closed audit for H16 representative PERF-CAL."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v5_hybrid_h16_perf_cal import (  # noqa: E402
    MSE_STABILITY_RATIO_MIN,
    SCHEMA,
    SOURCE_HANDS,
    SOURCE_ITERATION,
    THROUGHPUT_RATIO_MIN,
    deterministic_transitions,
    transition_sha256,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def close(left: float, right: float, tolerance: float = 1e-10) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--tool", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    artifact = load(args.artifact)
    checks: dict[str, bool] = {}

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)

    source = Path(artifact.get("source", {}).get("path", ""))
    workload = artifact.get("workload", {})
    timing = artifact.get("timing", {})
    gates = artifact.get("gates", {})
    raw = timing.get("raw_seconds", {})
    mse_raw = raw.get("mse", [])
    smooth_raw = raw.get("smooth_l1", [])
    mse_repeat = [float(statistics.median([float(x) for x in values])) for values in mse_raw]
    smooth_repeat = [float(statistics.median([float(x) for x in values])) for values in smooth_raw]
    mse_median = float(statistics.median(mse_repeat)) if mse_repeat else -1.0
    smooth_median = float(statistics.median(smooth_repeat)) if smooth_repeat else -1.0
    ratio = mse_median / smooth_median if mse_median > 0 and smooth_median > 0 else -1.0
    stability = min(mse_repeat) / max(mse_repeat) if mse_repeat and max(mse_repeat) > 0 else -1.0

    check("schema", artifact.get("schema_version") == SCHEMA)
    check(
        "overall_pass",
        artifact.get("overall") == "PASS"
        and artifact.get("classification") == "H16_REPRESENTATIVE_PERF_CAL_PASS",
    )
    check("arm", artifact.get("arm") in {"control", "treatment", "offline-smoke"})
    check("source_exists", source.is_file())
    check("source_hash", source.is_file() and sha256(source) == artifact.get("source", {}).get("sha256"))
    check(
        "source_identity",
        artifact.get("source", {}).get("iteration") == SOURCE_ITERATION
        and artifact.get("source", {}).get("hands") == SOURCE_HANDS
        and artifact.get("source", {}).get("optimizer_loaded") is True,
    )
    check("tool_hash", args.tool.is_file() and sha256(args.tool) == artifact.get("tool_sha256"))
    check(
        "registered_dimensions",
        workload.get("rows") == 4096
        and workload.get("mini_batch_size") == 1024
        and workload.get("ppo_epochs") == 4
        and workload.get("target_kl") == 1e-12
        and workload.get("warmup_updates_per_mode") == 2
        and workload.get("timed_updates_per_repeat_per_mode") == 8
        and workload.get("repeats") == 5
        and workload.get("order") == "ALTERNATING_MSE_SMOOTHL1"
        and workload.get("device") == "cuda",
    )
    check(
        "full_update_shape",
        workload.get("full_trinal_clip_ppo_update") is True
        and workload.get("forced_kl_early_stop") is True
        and workload.get("value_head_catchup_epochs") == 3,
    )
    check(
        "sample_shape",
        len(mse_raw) == len(smooth_raw) == 5
        and all(len(values) == 8 for values in mse_raw + smooth_raw),
    )
    check(
        "positive_finite_samples",
        all(float(value) > 0 for values in mse_raw + smooth_raw for value in values),
    )
    recorded_repeat = timing.get("repeat_median_seconds", {})
    recorded_mode = timing.get("mode_median_seconds", {})
    check("mse_repeat_medians", len(mse_repeat) == 5 and all(close(a, b) for a, b in zip(mse_repeat, recorded_repeat.get("mse", []))))
    check("smooth_repeat_medians", len(smooth_repeat) == 5 and all(close(a, b) for a, b in zip(smooth_repeat, recorded_repeat.get("smooth_l1", []))))
    check("mode_medians", close(mse_median, recorded_mode.get("mse", -2)) and close(smooth_median, recorded_mode.get("smooth_l1", -2)))
    check("throughput_recomputed", close(ratio, timing.get("full_update_throughput_ratio", -2)))
    check("stability_recomputed", close(stability, timing.get("mse_repeat_stability_ratio", -2)))
    check(
        "throughput_gate",
        gates.get("full_update_throughput_ratio_min") == THROUGHPUT_RATIO_MIN
        and gates.get("full_update_throughput_ratio_pass") is True
        and ratio >= THROUGHPUT_RATIO_MIN,
    )
    check(
        "stability_gate",
        gates.get("mse_repeat_stability_ratio_min") == MSE_STABILITY_RATIO_MIN
        and gates.get("mse_repeat_stability_ratio_pass") is True
        and stability >= MSE_STABILITY_RATIO_MIN,
    )
    identity = artifact.get("identity", {})
    check(
        "identity_gate",
        gates.get("numerical_gradient_actor_scope_identity_pass") is True
        and identity.get("pass") is True
        and identity.get("actor_model_bitwise_equal") is True
        and identity.get("actor_optimizer_bitwise_equal") is True
        and identity.get("value_head_differs") is True
        and identity.get("all_reported_numerics_finite") is True
        and identity.get("forced_kl_and_three_catchup_epochs") is True,
    )
    check(
        "path1_unchanged",
        artifact.get("path1", {}).get("coordinator_pid") == 23720
        and artifact.get("path1", {}).get("worker_count") == 6
        and artifact.get("path1", {}).get("priority") == "BelowNormal"
        and artifact.get("path1", {}).get("changed") is False,
    )
    check("isolation", artifact.get("forbidden_processes") == [])
    check("no_behavior", artifact.get("behavior_change") is False and artifact.get("checkpoint_changed") is False and artifact.get("official_hands") == 0)

    transition_recomputed = False
    if source.is_file() and workload.get("device") == "cuda" and torch.cuda.is_available():
        checkpoint = torch.load(source, map_location="cpu", weights_only=False)
        transitions = deterministic_transitions(
            checkpoint, "cuda", int(workload.get("seed", -1)), int(workload.get("rows", -1))
        )
        transition_recomputed = transition_sha256(transitions) == workload.get("transition_sha256")
    check("transition_bundle_recomputed", transition_recomputed)

    failed = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema_version": "v5.hybrid.h16.representative_perf_cal_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "checks": checks,
        "failed": failed,
        "artifact_sha256": sha256(args.artifact),
        "tool_sha256": sha256(args.tool),
        "behavior_authority": "NONE_REPORTING_ONLY",
        "official_hands": 0,
        "strength_claim": "FORBIDDEN",
    }
    if args.out.exists():
        raise FileExistsError(args.out)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
