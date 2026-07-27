#!/usr/bin/env python3
"""Fail-closed terminal H18 judgment using fixed contemporaneous arms and source anchor."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from v5_h1_calibration import endpoint_predictions

REPS = 10000
MSE_SEED = 2026071907
PREREG_SHA = "8f1f3df1c7fee8c4f8990d5354313330d497f75b1d81de6ceb1f7aa9b4225481"
ANCHOR_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
TOOL = Path(__file__).resolve()


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def rows(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def effective(values: list[dict], first60: bool = False) -> float | None:
    sample = values[1:61] if first60 else values[1:]
    if len(sample) < 2:
        return None
    elapsed = (
        datetime.fromisoformat(sample[-1]["recorded_at"])
        - datetime.fromisoformat(sample[0]["recorded_at"])
    ).total_seconds()
    return (int(sample[-1]["hands"]) - int(sample[0]["hands"])) / elapsed if elapsed > 0 else None


def endpoint(status_path: Path, arm: str):
    status = load(status_path)
    if status.get("overall") != "PASS" or status.get("state") != "ARM_ENDPOINT_FROZEN" or status.get("arm") != arm:
        raise ValueError(f"{arm} endpoint status")
    checkpoint = Path(status["checkpoint_path"])
    if not checkpoint.is_file() or sha(checkpoint) != status.get("checkpoint_sha256"):
        raise ValueError(f"{arm} endpoint hash")
    return status, checkpoint


def mse(control: Path, treatment: Path, anchor: Path, holdout: Path, device: str) -> dict:
    decisions = rows(holdout / "decisions.jsonl")
    control_errors = endpoint_predictions(control, decisions, device)
    treatment_errors = endpoint_predictions(treatment, decisions, device)
    anchor_errors = endpoint_predictions(anchor, decisions, device)
    deals = sorted(set(control_errors) & set(treatment_errors) & set(anchor_errors))
    if len(deals) != 10000:
        raise ValueError("MSE holdout deal coverage")
    control_array = np.asarray([control_errors[deal] for deal in deals])
    treatment_array = np.asarray([treatment_errors[deal] for deal in deals])
    anchor_array = np.asarray([anchor_errors[deal] for deal in deals])
    primary_point = float(1.0 - treatment_array.mean() / control_array.mean())
    anchor_point = float(treatment_array.mean() / anchor_array.mean() - 1.0)
    rng = np.random.default_rng(MSE_SEED)
    primary_samples = np.empty(REPS)
    anchor_samples = np.empty(REPS)
    for index in range(REPS):
        sample = rng.integers(0, len(deals), len(deals))
        treatment_mean = treatment_array[sample].mean()
        primary_samples[index] = float(1.0 - treatment_mean / control_array[sample].mean())
        anchor_samples[index] = float(treatment_mean / anchor_array[sample].mean() - 1.0)
    primary_lower, primary_upper = map(float, np.quantile(primary_samples, [0.025, 0.975]))
    anchor_lower, anchor_upper = map(float, np.quantile(anchor_samples, [0.025, 0.975]))
    return {
        "deal_clusters": len(deals),
        "control_normalized_mse": float(control_array.mean()),
        "treatment_normalized_mse": float(treatment_array.mean()),
        "source_anchor_normalized_mse": float(anchor_array.mean()),
        "primary_reduction": {
            "point": primary_point,
            "ci95_lower": primary_lower,
            "ci95_upper": primary_upper,
            "point_min": 0.075,
            "ci95_lower_min": 0.0,
        },
        "anchor_relative_degradation": {
            "point": anchor_point,
            "ci95_lower": anchor_lower,
            "ci95_upper": anchor_upper,
            "point_max": 0.05,
            "ci95_upper_max": 0.10,
        },
        "bootstrap_repetitions": REPS,
        "bootstrap_seed": MSE_SEED,
    }


def verify_lock(path: Path, expected: str) -> dict:
    if sha(path) != expected.lower():
        raise ValueError("design lock SHA")
    lock = load(path)
    if lock.get("design_id") != "H18" or lock.get("status") != "LOCKED" or lock.get("preregistration", {}).get("sha256") != PREREG_SHA:
        raise ValueError("design lock identity")
    if lock.get("tools", {}).get("scripts/alpha_holdem/v5_hybrid_h18_judge.py") != sha(TOOL):
        raise ValueError("judge tool binding")
    for item in lock.get("frozen_files", []):
        frozen = Path(item["path"])
        if not frozen.is_file() or sha(frozen) != item["sha256"]:
            raise ValueError("frozen artifact " + str(frozen))
    return lock


def catchup_accounting(control_rows: list[dict], treatment_rows: list[dict]) -> dict:
    control_ok = all(
        bool(row.get("value_head_catchup_enabled"))
        and row.get("value_head_catchup_loss_mode") == "mse"
        and float(row.get("value_head_catchup_smooth_l1_beta", -1)) == 1.0
        and bool(row.get("value_head_catchup_actor_state_unchanged"))
        for row in control_rows
    )
    treatment_enabled = all(
        bool(row.get("value_head_catchup_enabled"))
        and row.get("value_head_catchup_loss_mode") == "smooth_l1"
        and float(row.get("value_head_catchup_smooth_l1_beta", -1)) == 1.0
        for row in treatment_rows
    )
    treatment_actor_unchanged = all(
        bool(row.get("value_head_catchup_actor_state_unchanged")) for row in treatment_rows
    )
    exact = True
    for row in control_rows + treatment_rows:
        completed = int(row.get("ppo_epochs_completed", 0))
        triggered = bool(row.get("kl_early_stop_triggered"))
        catchup_epochs = int(row.get("value_head_catchup_epochs", 0))
        catchup_minibatches = int(row.get("value_head_catchup_minibatches", 0))
        expected = 4 - completed if triggered and completed < 4 else 0
        if catchup_epochs != expected or (expected > 0 and catchup_minibatches <= 0) or (expected == 0 and catchup_minibatches != 0):
            exact = False
    triggered_rows = sum(bool(row.get("kl_early_stop_triggered")) for row in treatment_rows)
    catchup_rows = sum(int(row.get("value_head_catchup_epochs", 0)) > 0 for row in treatment_rows)
    return {
        "control_mse_identity_exact": control_ok,
        "treatment_enabled_all_rows": treatment_enabled,
        "treatment_actor_state_unchanged_all_rows": treatment_actor_unchanged,
        "remaining_epoch_accounting_exact": exact,
        "treatment_rows": len(treatment_rows),
        "triggered_rows": triggered_rows,
        "catchup_rows": catchup_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--control-status", type=Path, required=True)
    parser.add_argument("--treatment-status", type=Path, required=True)
    parser.add_argument("--control-protocol", type=Path, required=True)
    parser.add_argument("--treatment-protocol", type=Path, required=True)
    parser.add_argument("--mirror-judgment", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    args = parser.parse_args()
    try:
        lock = verify_lock(args.design_lock, args.expected_lock_sha256)
        control_protocol = load(args.control_protocol) if args.control_protocol.is_file() else {}
        treatment_protocol = load(args.treatment_protocol) if args.treatment_protocol.is_file() else {}
        terminal = next(
            (value for value in (control_protocol, treatment_protocol) if value.get("overall") == "FAIL"),
            None,
        )
        if terminal:
            state = str(terminal.get("state", ""))
            if "RESOURCE_ISOLATION" in state:
                verdict = "INCONCLUSIVE"
                classification = "H18_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION"
            elif state.startswith("H18_FAIL_PROTOCOL_ABORT_"):
                verdict = "FAIL"
                classification = state
            else:
                raise ValueError("unrecognized protocol terminal")
            result = {
                "schema_version": "v5.hybrid.h18.judgment.v1",
                "design_id": "H18",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "overall": verdict,
                "classification": classification,
                "protocol_terminal": terminal,
                "design_lock_sha256": sha(args.design_lock),
                "official_hands": 0,
                "strength_claim": "FORBIDDEN",
                "route_review_required": True,
            }
            return_code = 0
        else:
            if (
                control_protocol.get("overall") != "PASS"
                or control_protocol.get("first60", {}).get("status") != "PASS_CONTROL_BASELINE_FROZEN"
                or treatment_protocol.get("overall") != "PASS"
                or treatment_protocol.get("first60", {}).get("status") != "PASS"
            ):
                raise ValueError("protocol statuses not terminal PASS")
            control_status, control_checkpoint = endpoint(args.control_status, "control")
            treatment_status, treatment_checkpoint = endpoint(args.treatment_status, "treatment")
            anchor = Path(lock["measurement"]["source_anchor_path"])
            if not anchor.is_file() or sha(anchor) != ANCHOR_SHA:
                raise ValueError("H18 source anchor identity")
            mirror = load(args.mirror_judgment)
            if mirror.get("schema_version") != "v5.hybrid.h18.mirror_judgment.v1":
                raise ValueError("mirror identity")
            calibration = mse(
                control_checkpoint,
                treatment_checkpoint,
                anchor,
                Path(lock["measurement"]["holdout_dir"]),
                args.device,
            )
            control_rows = rows(Path(lock["arms"]["control"]["metrics_path"]))
            treatment_rows = rows(Path(lock["arms"]["treatment"]["metrics_path"]))
            control_first60 = effective(control_rows, True)
            treatment_first60 = effective(treatment_rows, True)
            control_full = effective(control_rows)
            treatment_full = effective(treatment_rows)
            first60_ratio = treatment_first60 / control_first60 if control_first60 and treatment_first60 else None
            full_ratio = treatment_full / control_full if control_full and treatment_full else None
            control_entropy = statistics.median(float(row["entropy"]) for row in control_rows[-200:])
            treatment_entropy = statistics.median(float(row["entropy"]) for row in treatment_rows[-200:])
            treatment_kl = np.asarray([float(row["approx_kl"]) for row in treatment_rows])
            treatment_fraction = float((treatment_kl > 0.03).mean())
            triggers = sum(bool(row.get("kl_early_stop_triggered")) for row in treatment_rows)
            trigger_fraction = triggers / len(treatment_rows)
            kl = {
                "treatment_rows": len(treatment_kl),
                "treatment_p95": float(np.quantile(treatment_kl, 0.95)),
                "treatment_fraction_above_0_03": treatment_fraction,
                "registered_treatment_fraction_max": 0.06044407894736842,
                "early_stop_triggers": triggers,
                "early_stop_trigger_fraction": trigger_fraction,
            }
            catchup = catchup_accounting(control_rows, treatment_rows)
            primary = calibration["primary_reduction"]
            anchor_guard = calibration["anchor_relative_degradation"]
            mirror_control = mirror.get("comparisons", {}).get("treatment_vs_control", {})
            mirror_anchor = mirror.get("comparisons", {}).get("treatment_vs_source_anchor", {})
            checks = {
                "catchup_control_mse_identity": catchup["control_mse_identity_exact"],
                "catchup_treatment_enabled": catchup["treatment_enabled_all_rows"],
                "catchup_actor_state_unchanged": catchup["treatment_actor_state_unchanged_all_rows"],
                "catchup_epoch_accounting": catchup["remaining_epoch_accounting_exact"],
                "endpoint_mse_primary_point": primary["point"] >= 0.075,
                "endpoint_mse_primary_ci_lower": primary["ci95_lower"] >= 0.0,
                "endpoint_mse_anchor_point": anchor_guard["point"] <= 0.05,
                "endpoint_mse_anchor_ci_upper": anchor_guard["ci95_upper"] <= 0.10,
                "kl_p95": kl["treatment_p95"] <= 0.03,
                "kl_excursion_fraction": treatment_fraction <= 0.06044407894736842,
                "early_stop_trigger_fraction": trigger_fraction >= 0.05,
                "mirror_treatment_control": mirror_control.get("status") == "PASS",
                "mirror_treatment_anchor": mirror_anchor.get("status") == "PASS",
                "throughput_first60": first60_ratio is not None and first60_ratio >= 0.85,
                "throughput_full": full_ratio is not None and full_ratio >= 0.85,
                "entropy_floor": treatment_entropy >= 0.3,
                "entropy_noninferior": treatment_entropy >= control_entropy - 0.10,
                "resource_isolation": control_protocol.get("resource_isolation_violations") == [] and treatment_protocol.get("resource_isolation_violations") == [],
            }
            deterministic_names = {
                "catchup_control_mse_identity",
                "catchup_treatment_enabled",
                "catchup_actor_state_unchanged",
                "catchup_epoch_accounting",
                "kl_p95",
                "kl_excursion_fraction",
                "early_stop_trigger_fraction",
                "throughput_first60",
                "throughput_full",
                "entropy_floor",
                "entropy_noninferior",
                "resource_isolation",
            }
            deterministic_failure = any(not checks[name] for name in deterministic_names)
            clearly_adverse = (
                primary["ci95_upper"] < 0.0
                or anchor_guard["ci95_lower"] > 0.10
                or mirror_control.get("status") == "FAIL"
                or mirror_anchor.get("status") == "FAIL"
            )
            if deterministic_failure or clearly_adverse:
                verdict = "FAIL"
                classification = "H18_FAIL_REGISTERED_GATE"
            elif all(checks.values()):
                verdict = "PASS"
                classification = "H18_PASS_ALL_REGISTERED_GATES"
            else:
                verdict = "INCONCLUSIVE"
                classification = "H18_INCONCLUSIVE_FIXED_SAMPLE"
            result = {
                "schema_version": "v5.hybrid.h18.judgment.v1",
                "design_id": "H18",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "overall": verdict,
                "classification": classification,
                "checks": checks,
                "catchup_accounting": catchup,
                "kl_stability": kl,
                "endpoint_mse": calibration,
                "mirror": mirror,
                "control_effective_hps_first60": control_first60,
                "treatment_effective_hps_first60": treatment_first60,
                "throughput_ratio_first60": first60_ratio,
                "control_effective_hps_full": control_full,
                "treatment_effective_hps_full": treatment_full,
                "throughput_ratio_full": full_ratio,
                "control_entropy_median_last200": control_entropy,
                "treatment_entropy_median_last200": treatment_entropy,
                "control_endpoint": control_status,
                "treatment_endpoint": treatment_status,
                "design_lock_sha256": sha(args.design_lock),
                "official_hands": 0,
                "strength_claim": "FORBIDDEN",
                "route_review_required": verdict in {"FAIL", "INCONCLUSIVE"},
            }
            return_code = 0
    except Exception as exc:
        result = {
            "schema_version": "v5.hybrid.h18.judgment.v1",
            "design_id": "H18",
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
