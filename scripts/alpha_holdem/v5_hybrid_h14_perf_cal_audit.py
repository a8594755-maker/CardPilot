#!/usr/bin/env python3
"""Independent fail-closed audit for H14 PERF-CAL artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v5_hybrid_h14_perf_cal import (
    COMMON_BASELINE_RATIO_MIN,
    LOSS_RATIO_MIN,
    deterministic_batch,
    tensor_sha256,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def close(left: float, right: float, tolerance: float = 1e-12) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--tool", type=Path, required=True)
    parser.add_argument("--control-baseline", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    artifact = load(args.artifact)
    checks: dict[str, bool] = {}

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)

    source = Path(artifact.get("source", {}).get("path", ""))
    batch = artifact.get("batch", {})
    timing = artifact.get("timing", {})
    gates = artifact.get("gates", {})
    mse = [float(value) for value in timing.get("mse_seconds_per_step_samples", [])]
    smooth = [float(value) for value in timing.get("smooth_l1_seconds_per_step_samples", [])]
    mse_median = float(statistics.median(mse)) if mse else -1.0
    smooth_median = float(statistics.median(smooth)) if smooth else -1.0
    loss_ratio = mse_median / smooth_median if mse_median > 0 and smooth_median > 0 else -1.0

    check("schema", artifact.get("schema_version") == "v5.hybrid.h14.perf_cal.v1")
    check("overall_pass", artifact.get("overall") == "PASS" and artifact.get("classification") == "H14_PERF_CAL_PASS")
    check("source_exists", source.is_file())
    check("source_hash", source.is_file() and sha256(source) == artifact.get("source", {}).get("sha256"))
    check("source_identity", artifact.get("source", {}).get("iteration") == 35051 and artifact.get("source", {}).get("hands") == 576021901)
    check("tool_hash", args.tool.is_file() and sha256(args.tool) == artifact.get("tool_sha256"))
    check("batch_hash", tensor_sha256(deterministic_batch(int(batch.get("seed", -1)), int(batch.get("size", -1)))) == batch.get("sha256"))
    check("sample_counts", len(mse) == int(artifact.get("benchmark", {}).get("repeats", -1)) and len(smooth) == len(mse) and len(mse) > 0)
    check("positive_samples", all(value > 0 for value in mse + smooth))
    check("mse_median", close(mse_median, timing.get("mse_seconds_per_step_median", -2)))
    check("smooth_median", close(smooth_median, timing.get("smooth_l1_seconds_per_step_median", -2)))
    check("loss_ratio", close(loss_ratio, timing.get("smooth_l1_over_mse_throughput_ratio", -2)))
    check("loss_gate", gates.get("loss_throughput_ratio_min") == LOSS_RATIO_MIN and gates.get("loss_throughput_ratio_pass") is True and loss_ratio >= LOSS_RATIO_MIN)
    common_ratio = float(timing.get("common_mse_baseline_match_ratio", -1))
    check("common_gate", gates.get("common_mse_baseline_ratio_min") == COMMON_BASELINE_RATIO_MIN and gates.get("common_mse_baseline_ratio_pass") is True and common_ratio >= COMMON_BASELINE_RATIO_MIN)
    check("optimizer_and_value_only", artifact.get("benchmark", {}).get("optimizer_state_loaded") is True and artifact.get("benchmark", {}).get("value_head_only") is True)
    check("path1_unchanged", artifact.get("path1", {}).get("coordinator_pid") == 23720 and artifact.get("path1", {}).get("worker_count") == 6 and artifact.get("path1", {}).get("priority") == "BelowNormal" and artifact.get("path1", {}).get("changed") is False)
    check("isolation", artifact.get("forbidden_processes") == [])
    check("no_behavior", artifact.get("behavior_change") is False and artifact.get("checkpoint_changed") is False and artifact.get("official_hands") == 0)
    if artifact.get("arm") == "treatment":
        check("control_baseline_required", args.control_baseline is not None and args.control_baseline.is_file())
        if args.control_baseline is not None and args.control_baseline.is_file():
            control = load(args.control_baseline)
            recorded = artifact.get("control_baseline") or {}
            control_mse = float(control.get("timing", {}).get("mse_seconds_per_step_median", -1))
            recomputed_common = min(control_mse, mse_median) / max(control_mse, mse_median)
            check("control_baseline_hash", recorded.get("sha256") == sha256(args.control_baseline))
            check("control_baseline_identity", control.get("arm") == "control" and control.get("overall") == "PASS" and control.get("batch", {}).get("sha256") == batch.get("sha256"))
            check("common_ratio_recomputed", close(recomputed_common, common_ratio))
    else:
        check("no_control_baseline_needed", artifact.get("control_baseline") is None and close(common_ratio, 1.0))

    failed = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema_version": "v5.hybrid.h14.perf_cal_audit.v1",
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
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
