#!/usr/bin/env python3
"""Fail-closed terminal H6 judgment. Reporting only; launches nothing."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from v5_h1_calibration import endpoint_predictions
from v5_h6_ppo_stability_readiness import parse_rows


REPS = 10_000
MSE_SEED = 2026071602
PREREG_SHA = "6b8ba0e4b396d74e1daf15bc9cb93a1018b671ec064f2ad591957c897ea46225"
CONTROL_SHA = "f35558536365006afee9b1311352d465144dfed715a1028362def333147d3d3b"
TOOL_PATH = Path(__file__).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def effective(rows: list[dict], first60: bool = False) -> float | None:
    sample = rows[1:61] if first60 else rows[1:]
    if len(sample) < 2:
        return None
    elapsed = (datetime.fromisoformat(sample[-1]["recorded_at"]) - datetime.fromisoformat(sample[0]["recorded_at"])).total_seconds()
    return (int(sample[-1]["hands"]) - int(sample[0]["hands"])) / elapsed if elapsed > 0 else None


def mse_comparison(control: Path, treatment: Path, holdout: Path, device: str) -> dict[str, Any]:
    rows = jsonl(holdout / "decisions.jsonl")
    control_values = endpoint_predictions(control, rows, device)
    treatment_values = endpoint_predictions(treatment, rows, device)
    deals = sorted(set(control_values) & set(treatment_values))
    if len(deals) != 10_000:
        raise ValueError("MSE holdout deal coverage mismatch")
    control_mse = np.array([control_values[deal] for deal in deals])
    treatment_mse = np.array([treatment_values[deal] for deal in deals])
    point = float(treatment_mse.mean() / control_mse.mean() - 1)
    rng = np.random.default_rng(MSE_SEED)
    samples = np.empty(REPS)
    for index in range(REPS):
        selected = rng.integers(0, len(deals), len(deals))
        samples[index] = float(treatment_mse[selected].mean() / control_mse[selected].mean() - 1)
    lower, upper = map(float, np.quantile(samples, [0.025, 0.975]))
    return {
        "deal_clusters": len(deals),
        "control_normalized_mse": float(control_mse.mean()),
        "treatment_normalized_mse": float(treatment_mse.mean()),
        "relative_degradation": point,
        "ci95_lower": lower,
        "ci95_upper": upper,
        "bootstrap_repetitions": REPS,
        "bootstrap_seed": MSE_SEED,
    }


def verify_lock(path: Path, expected: str) -> dict:
    if sha256(path) != expected.lower():
        raise ValueError("design lock SHA mismatch")
    lock = load(path)
    if lock.get("design_id") != "H6" or lock.get("status") != "LOCKED":
        raise ValueError("design lock identity/status")
    if lock.get("preregistration", {}).get("sha256") != PREREG_SHA:
        raise ValueError("preregistration binding")
    if lock.get("tools", {}).get("scripts/alpha_holdem/v5_hybrid_h6_judge.py") != sha256(TOOL_PATH):
        raise ValueError("judge tool binding")
    for item in lock.get("frozen_files", []):
        artifact = Path(item["path"])
        if not artifact.is_file() or sha256(artifact) != item["sha256"]:
            raise ValueError("frozen file mismatch " + str(artifact))
    return lock


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--treatment-status", type=Path, required=True)
    parser.add_argument("--protocol-status", type=Path, required=True)
    parser.add_argument("--mirror-judgment", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    args = parser.parse_args()
    try:
        lock = verify_lock(args.design_lock, args.expected_lock_sha256)
        protocol = load(args.protocol_status)
        if protocol.get("overall") == "FAIL" and str(protocol.get("state", "")).startswith("H6_FAIL_PROTOCOL_ABORT_"):
            result = {
                "schema_version": "v5.hybrid.h6.judgment.v1",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "overall": "FAIL",
                "classification": protocol["state"],
                "protocol": protocol,
                "design_lock_sha256": sha256(args.design_lock),
                "official_hands": 0,
                "strength_claim": "FORBIDDEN",
                "route_review_required": True,
            }
            return_code = 0
        else:
            if protocol.get("overall") != "PASS" or protocol.get("first60", {}).get("status") != "PASS":
                raise ValueError("treatment protocol is not terminal PASS")
            treatment_status = load(args.treatment_status)
            if treatment_status.get("overall") != "PASS" or treatment_status.get("state") != "ARM_ENDPOINT_FROZEN":
                raise ValueError("treatment endpoint status invalid")
            treatment = Path(treatment_status["checkpoint_path"])
            if not treatment.is_file() or sha256(treatment) != treatment_status.get("checkpoint_sha256"):
                raise ValueError("treatment endpoint identity")
            control = Path(lock["arms"]["control"]["checkpoint_path"])
            if not control.is_file() or sha256(control) != CONTROL_SHA:
                raise ValueError("control endpoint identity")
            mirror = load(args.mirror_judgment)
            if mirror.get("schema_version") != "v5.hybrid.h6.mirror_judgment.v1":
                raise ValueError("mirror judgment identity")
            mse = mse_comparison(control, treatment, Path(lock["measurement"]["holdout_dir"]), args.device)

            control_metrics = jsonl(Path(lock["arms"]["control"]["metrics_path"]))
            treatment_metrics = jsonl(Path(lock["arms"]["treatment"]["metrics_path"]))
            control_first = effective(control_metrics, True)
            treatment_first = effective(treatment_metrics, True)
            control_full = effective(control_metrics)
            treatment_full = effective(treatment_metrics)
            ratio_first = treatment_first / control_first if treatment_first and control_first else None
            ratio_full = treatment_full / control_full if treatment_full and control_full else None
            control_entropy = statistics.median(float(row["entropy"]) for row in control_metrics[-200:])
            treatment_entropy = statistics.median(float(row["entropy"]) for row in treatment_metrics[-200:])

            control_kl_rows = parse_rows(Path(lock["arms"]["control"]["train_log_path"]).read_text(encoding="utf-8-sig", errors="replace"))
            treatment_kl_rows = parse_rows(Path(lock["arms"]["treatment"]["train_log_path"]).read_text(encoding="utf-8-sig", errors="replace"))
            if len(control_kl_rows) != 1216 or len(treatment_kl_rows) != len(treatment_metrics):
                raise ValueError("KL row coverage mismatch")
            treatment_kl = np.asarray([float(row["approx_kl"]) for row in treatment_kl_rows])
            triggers = sum(bool(row.get("kl_early_stop_triggered")) for row in treatment_metrics)
            kl = {
                "rows": len(treatment_kl_rows),
                "p95": float(np.quantile(treatment_kl, 0.95)),
                "rows_above_0_03": int((treatment_kl > 0.03).sum()),
                "fraction_above_0_03": float((treatment_kl > 0.03).mean()),
                "early_stop_triggers": triggers,
                "early_stop_trigger_fraction": triggers / len(treatment_metrics),
            }
            checks = {
                "kl_p95": kl["p95"] <= 0.03,
                "kl_excursion_fraction": kl["fraction_above_0_03"] <= 0.06044407894736842,
                "early_stop_trigger_fraction": kl["early_stop_trigger_fraction"] >= 0.05,
                "endpoint_mse_point": mse["relative_degradation"] <= 0.05,
                "endpoint_mse_ci_upper": mse["ci95_upper"] <= 0.10,
                "mirror_noninferiority": mirror.get("status") == "PASS",
                "throughput_first60": ratio_first is not None and ratio_first >= 0.85,
                "throughput_full": ratio_full is not None and ratio_full >= 0.85,
                "entropy_floor": treatment_entropy >= 0.3,
                "entropy_noninferior": treatment_entropy >= control_entropy - 0.10,
            }
            if any(not checks[name] for name in ("endpoint_mse_point", "endpoint_mse_ci_upper", "throughput_first60", "throughput_full", "entropy_floor", "entropy_noninferior")) or mirror.get("status") == "FAIL" or any(not checks[name] for name in ("kl_p95", "kl_excursion_fraction", "early_stop_trigger_fraction")):
                verdict, classification = "FAIL", "H6_FAIL_REGISTERED_GATE"
            elif all(checks.values()) and mirror.get("status") == "PASS":
                verdict, classification = "PASS", "H6_PASS_ALL_REGISTERED_GATES"
            else:
                verdict, classification = "INCONCLUSIVE", "H6_INCONCLUSIVE_FIXED_SAMPLE"
            result = {
                "schema_version": "v5.hybrid.h6.judgment.v1",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "overall": verdict,
                "classification": classification,
                "checks": checks,
                "kl_stability": kl,
                "endpoint_mse": mse,
                "mirror": mirror,
                "control_effective_hps_first60": control_first,
                "treatment_effective_hps_first60": treatment_first,
                "throughput_ratio_first60": ratio_first,
                "control_effective_hps_full": control_full,
                "treatment_effective_hps_full": treatment_full,
                "throughput_ratio_full": ratio_full,
                "control_entropy_median_last200": control_entropy,
                "treatment_entropy_median_last200": treatment_entropy,
                "control_checkpoint_sha256": CONTROL_SHA,
                "treatment_endpoint": treatment_status,
                "design_lock_sha256": sha256(args.design_lock),
                "official_hands": 0,
                "strength_claim": "FORBIDDEN",
                "route_review_required": verdict in {"FAIL", "INCONCLUSIVE"},
            }
            return_code = 0
    except Exception as exc:
        result = {
            "schema_version": "v5.hybrid.h6.judgment.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "INCONCLUSIVE",
            "classification": "FAIL_CLOSED_MISSING_OR_INVALID_EVIDENCE",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "official_hands": 0,
            "strength_claim": "FORBIDDEN",
        }
        return_code = 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
