"""Audit matched-training accounting and common-deck evaluation evidence."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import torch


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stats(values) -> dict:
    values = np.asarray(list(values), dtype=np.float64)
    mean = float(values.mean())
    half = 1.96 * float(values.std(ddof=1)) / math.sqrt(len(values))
    return {
        "pairs": len(values),
        "bb100": mean * 100.0,
        "ci95_low_bb100": (mean - half) * 100.0,
        "ci95_high_bb100": (mean + half) * 100.0,
    }


def close(a: float, b: float) -> bool:
    return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-12)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    base = args.base_dir.resolve()
    arm_dirs = {"control": base / "control", "treatment": base / "treatment_recovery2"}
    arm_rows = {}
    gates = {}
    for name, directory in arm_dirs.items():
        manifest = json.loads((directory / "run_manifest.json").read_text())
        checkpoint = torch.load(directory / "latest.pt", map_location="cpu", weights_only=False)
        env = checkpoint["environment_hand_accounting"]
        public = checkpoint["public_opponent_accounting"]
        workers = env["session_worker_counts"]
        public_workers = public["session_worker_counts"]
        arm_rows[name] = {
            "manifest_status": manifest["status"],
            "iteration": int(checkpoint["iteration"]),
            "transition_hands": int(checkpoint["total_hands"]),
            "environment_hands": int(env["completed_hands"]),
            "environment_prefix_complete": bool(env["prefix_complete"]),
            "environment_worker_count": len(workers),
            "environment_workers_nonzero": sum(row["completed_hands"] > 0 for row in workers),
            "public_hands": int(public["hands"]),
            "public_decisions": int(public["decisions"]),
            "public_inference_bypasses": int(public["inference_bypasses"]),
            "public_workers_nonzero": sum(row["hands"] > 0 for row in public_workers),
            "checkpoint_sha256": sha256_path(directory / "latest.pt"),
            "manifest_sha256": sha256_path(directory / "run_manifest.json"),
            "metrics_sha256": sha256_path(directory / "h1_training_metrics.jsonl"),
            "metrics_lines": sum(1 for _ in (directory / "h1_training_metrics.jsonl").open()),
        }
        gates[f"{name}_finished"] = manifest["status"] == "finished"
        gates[f"{name}_two_iterations"] = int(checkpoint["iteration"]) == 2
        gates[f"{name}_environment_prefix_complete"] = bool(env["prefix_complete"])
        gates[f"{name}_all_12_environment_workers_nonzero"] = (
            len(workers) == 12 and all(row["completed_hands"] > 0 for row in workers)
        )
    treatment_public = arm_rows["treatment"]
    gates["treatment_public_accounting_consistent"] = (
        treatment_public["public_hands"] > 0
        and treatment_public["public_decisions"]
        == treatment_public["public_inference_bypasses"]
        and treatment_public["public_workers_nonzero"] == 12
    )
    gates["control_public_hands_zero"] = arm_rows["control"]["public_hands"] == 0

    summary_path = base / "evaluation" / "summary.json"
    raw_path = base / "evaluation" / "common_deck_pairs.jsonl.gz"
    summary = json.loads(summary_path.read_text())
    rows = []
    with gzip.open(raw_path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    counts = Counter(row["anchor"] for row in rows)
    pooled = stats(row["treatment_minus_control_pair_mean_bb"] for row in rows)
    gates["raw_hash_matches_summary"] = sha256_path(raw_path) == summary["raw_pairs_sha256"]
    gates["raw_row_count_8192"] = len(rows) == 8192
    gates["four_anchors_2048_pairs_each"] = len(counts) == 4 and set(counts.values()) == {2048}
    gates["raw_decks_are_permutations"] = all(
        len(row["deck"]) == 52 and len(set(row["deck"])) == 52 for row in rows
    )
    gates["pooled_statistics_recompute"] = (
        close(pooled["bb100"], summary["pooled_treatment_minus_control_bb100"])
        and close(
            (pooled["ci95_high_bb100"] - pooled["ci95_low_bb100"]) / 2.0,
            summary["pooled_treatment_minus_control_ci95_bb100"],
        )
    )
    gates["frozen_control_hash_matches_eval"] = (
        arm_rows["control"]["checkpoint_sha256"] == summary["input_sha256"]["control"]
    )
    gates["frozen_treatment_hash_matches_eval"] = (
        arm_rows["treatment"]["checkpoint_sha256"] == summary["input_sha256"]["treatment"]
    )
    output = {
        "schema": "cardpilot.public_opponent_matched_audit.v1",
        "arms": arm_rows,
        "evaluation": {
            "summary_sha256": sha256_path(summary_path),
            "raw_sha256": sha256_path(raw_path),
            "anchor_pair_counts": dict(counts),
            "recomputed_pooled": pooled,
        },
        "gates": gates,
        "passed": all(gates.values()),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, sort_keys=True))
    if not output["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
