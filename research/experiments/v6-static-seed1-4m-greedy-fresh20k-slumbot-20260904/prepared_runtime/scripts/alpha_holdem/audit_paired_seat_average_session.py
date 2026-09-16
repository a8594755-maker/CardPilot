#!/usr/bin/env python3
"""Audit paired-seat actor-reward evidence from a completed train_v5 session."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


MIRROR_RE = re.compile(r"mirror=(\d+)/(\d+)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--expected-iterations", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    manifest_path = args.run_dir / "run_manifest.json"
    metrics_path = args.run_dir / "h1_training_metrics.jsonl"
    train_log_path = args.run_dir / "latest_train.log"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metric_rows = [
        json.loads(line)
        for line in metrics_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    mirror_rows = [
        tuple(map(int, match.groups()))
        for match in MIRROR_RE.finditer(train_log_path.read_text(encoding="utf-8"))
    ]
    ratios = [float(row["actor_terminal_reward_variance_ratio"]) for row in metric_rows]
    override_rows = [int(row["actor_reward_override_rows"]) for row in metric_rows]
    checks = {
        "manifest_finished": manifest.get("status") == "finished",
        "paired_mode_enabled": bool((manifest.get("config") or {}).get("paired_seat_average_returns")),
        "iteration_count": len(metric_rows) == args.expected_iterations,
        "mirror_log_count": len(mirror_rows) == args.expected_iterations,
        "every_mirror_count_positive": all(source > 0 for source, _ in mirror_rows),
        "every_mirror_count_balanced": all(source == replay for source, replay in mirror_rows),
        "every_override_count_positive": all(value > 0 for value in override_rows),
        "every_override_terminal_only": all(
            bool(row["actor_reward_override_terminal_only"]) for row in metric_rows
        ),
        "every_variance_ratio_below_one": all(0.0 <= value < 1.0 for value in ratios),
    }
    report = {
        "schema": "cardpilot.paired-seat-average-session-audit.v2",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "run_id": manifest.get("run_id"),
        "legacy_training_marker_hands": int(manifest.get("total_hands", 0)),
        "emitted_paired_physical_hands_lower_bound": 2 * sum(source for source, _ in mirror_rows),
        "physical_total_exact": False,
        "physical_accounting_note": "Legacy logs cover emitted paired batches, not all completed or discarded worker tails.",
        "metric_rows": len(metric_rows),
        "mirror_rows": len(mirror_rows),
        "matched_pairs": sum(source for source, _ in mirror_rows),
        "actor_reward_override_rows": sum(override_rows),
        "variance_ratio_min": min(ratios),
        "variance_ratio_mean": sum(ratios) / len(ratios),
        "variance_ratio_max": max(ratios),
        "checks": checks,
        "source_artifacts": {
            str(manifest_path): sha256(manifest_path),
            str(metrics_path): sha256(metrics_path),
            str(train_log_path): sha256(train_log_path),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
