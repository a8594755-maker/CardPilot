#!/usr/bin/env python3
"""Independent post-window auditor for the registered CT003 Stage-A endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import torch


TOKEN = "7296402ab1ddaadd86ebde1795d0f2ad"
SOURCE_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
SOURCE_HANDS = 576_021_901
TARGET_HANDS = 581_021_901
POOL_IDS = [109, 115, 120, 129, 103]
TARGET_MODE = "full_trajectory_discounted_mc_gamma_0.999"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite_tree(value) -> bool:
    if torch.is_tensor(value):
        return bool(torch.isfinite(value).all())
    if isinstance(value, dict):
        return all(finite_tree(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(finite_tree(item) for item in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run_dir = Path(args.run_dir).resolve()
    out = Path(args.out).resolve()
    checkpoint_path = run_dir / "latest.pt"
    metrics_path = run_dir / "h1_training_metrics.jsonl"
    provenance_path = run_dir / "opponent_assignment_provenance.jsonl"
    manifest_path = run_dir / "run_manifest.json"
    checks: dict[str, bool] = {}

    checks["checkpoint_exists"] = checkpoint_path.is_file()
    checks["metrics_exists"] = metrics_path.is_file()
    checks["provenance_exists"] = provenance_path.is_file()
    checks["manifest_exists"] = manifest_path.is_file()
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    metrics = [
        json.loads(line) for line in metrics_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    provenance = [
        json.loads(line) for line in provenance_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    hands = int(checkpoint.get("total_hands", -1))
    iteration = int(checkpoint.get("iteration", -1))
    new_hands = hands - SOURCE_HANDS
    checks["bounded_hands"] = 5_000_000 <= new_hands <= 5_050_000
    checks["endpoint_at_least_target"] = hands >= TARGET_HANDS
    checks["metrics_nonempty"] = bool(metrics)
    checks["metrics_count_matches_iterations"] = len(metrics) == iteration - 35_051
    checks["target_mode_all_rows"] = all(
        row.get("ct003_target_mode") == TARGET_MODE for row in metrics
    )
    checks["target_fraction_exact_one_all_rows"] = all(
        float(row.get("ct003_mc_target_fraction", -1.0)) == 1.0 for row in metrics
    )
    checks["target_rows_positive_all_rows"] = all(
        int(row.get("ct003_mc_target_rows", 0)) > 0 for row in metrics
    )
    checks["metrics_finite"] = finite_tree(metrics)
    checks["model_finite"] = finite_tree(checkpoint.get("model"))
    checks["optimizer_finite"] = finite_tree(checkpoint.get("optimizer"))
    contract = checkpoint.get("lg003") or {}
    checks["source_hash_bound"] = (
        contract.get("source_checkpoint_sha256") == SOURCE_SHA256
    )
    checks["ct003_identity_bound"] = (
        contract.get("ct003_registration_token") == TOKEN
        and contract.get("ct003_preregistration_sha256")
        == "7702ff2d7323bcb053443a7b1e540e4624f43e3d932bfd2c3ecbb7afb0bb11fe"
        and contract.get("ct003_target_mode") == TARGET_MODE
    )
    snapshots = checkpoint.get("pool_snapshots") or []
    checks["pool_exact"] = [int(row.get("id", -1)) for row in snapshots] == POOL_IDS
    checks["provenance_count"] = len(provenance) == len(metrics)
    checks["provenance_iterations_contiguous"] = [
        int(row.get("applies_to_iteration", -1)) for row in provenance
    ] == list(range(35_052, iteration + 1))
    checks["provenance_uniform"] = all(
        row.get("conditional_weights") == {
            "103": 0.2, "109": 0.2, "115": 0.2, "120": 0.2, "129": 0.2
        }
        for row in provenance
    )
    previous = None
    chain_ok = True
    for row in provenance:
        payload = dict(row)
        record_hash = payload.pop("record_sha256", None)
        if payload.get("previous_record_sha256") != previous:
            chain_ok = False
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if hashlib.sha256(encoded).hexdigest() != record_hash:
            chain_ok = False
        previous = record_hash
    checks["provenance_hash_chain"] = chain_ok
    hps = sorted(float(row["hands_per_second"]) for row in metrics)
    median_hps = hps[len(hps) // 2]
    control_metrics = Path(
        "models/alpha_holdem_v5_hybrid/"
        "v5_lg003c1_8bf8cedf78b6e8c8fe153802908ed893_20260723/"
        "control_uniform_stagea/h1_training_metrics.jsonl"
    ).resolve()
    control_rows = [
        json.loads(line) for line in control_metrics.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    control_hps = sorted(float(row["hands_per_second"]) for row in control_rows)
    control_median_hps = control_hps[len(control_hps) // 2]
    checks["throughput_ratio_at_least_0_85"] = median_hps / control_median_hps >= 0.85
    checks["manifest_finished"] = manifest.get("status") == "finished"
    checks["checkpoint_hash_stable"] = sha256_path(checkpoint_path) == sha256_path(checkpoint_path)

    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": "v5.ct003.stage_a.window_audit.v1",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "failed_checks": failed,
        "measurements": {
            "iteration": iteration,
            "total_hands": hands,
            "new_hands": new_hands,
            "metric_rows": len(metrics),
            "provenance_rows": len(provenance),
            "median_hps": median_hps,
            "control_median_hps": control_median_hps,
            "throughput_ratio": median_hps / control_median_hps,
        },
        "artifacts": {
            str(checkpoint_path): {
                "sha256": sha256_path(checkpoint_path),
                "bytes": checkpoint_path.stat().st_size,
            },
            str(metrics_path): {
                "sha256": sha256_path(metrics_path),
                "bytes": metrics_path.stat().st_size,
            },
            str(provenance_path): {
                "sha256": sha256_path(provenance_path),
                "bytes": provenance_path.stat().st_size,
            },
            str(manifest_path): {
                "sha256": sha256_path(manifest_path),
                "bytes": manifest_path.stat().st_size,
            },
        },
    }
    if out.exists():
        raise RuntimeError(f"refusing to overwrite audit: {out}")
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
