#!/usr/bin/env python3
"""Publish the preregistered H2 first60 protocol-abort terminal branch.

This is reporting-only.  It exists because the original completion supervisor
only accepted two full endpoints, while the immutable H2 contract requires the
treatment to stop before an endpoint when first60 throughput is below 0.85.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def metric_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def first60_effective_hps(rows: list[dict]) -> float:
    used = rows[1:61]
    if len(used) != 60:
        raise ValueError(f"first60 requires 61 accepted rows, found {len(rows)}")
    elapsed = (
        datetime.fromisoformat(used[-1]["recorded_at"])
        - datetime.fromisoformat(used[0]["recorded_at"])
    ).total_seconds()
    if elapsed <= 0:
        raise ValueError("non-positive first60 elapsed time")
    return (int(used[-1]["hands"]) - int(used[0]["hands"])) / elapsed


def classify(control_hps: float, treatment_hps: float, minimum: float) -> tuple[str, str]:
    ratio = treatment_hps / control_hps
    if ratio < minimum:
        return "FAIL", "H2_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT"
    raise ValueError("protocol-abort judgment invoked without registered throughput failure")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--preregistration", required=True)
    p.add_argument("--expected-preregistration-sha256", required=True)
    p.add_argument("--design-lock", required=True)
    p.add_argument("--expected-design-lock-sha256", required=True)
    p.add_argument("--judgment-lock", required=True)
    p.add_argument("--expected-judgment-lock-sha256", required=True)
    p.add_argument("--control-metrics", required=True)
    p.add_argument("--treatment-metrics", required=True)
    p.add_argument("--protocol-status", required=True)
    p.add_argument("--control-endpoint-status", required=True)
    p.add_argument("--treatment-manifest", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    out_path = Path(args.out).resolve()
    try:
        paths = {
            "preregistration": Path(args.preregistration).resolve(),
            "design_lock": Path(args.design_lock).resolve(),
            "judgment_lock": Path(args.judgment_lock).resolve(),
            "control_metrics": Path(args.control_metrics).resolve(),
            "treatment_metrics": Path(args.treatment_metrics).resolve(),
            "protocol_status": Path(args.protocol_status).resolve(),
            "control_endpoint_status": Path(args.control_endpoint_status).resolve(),
            "treatment_manifest": Path(args.treatment_manifest).resolve(),
        }
        expected = {
            "preregistration": args.expected_preregistration_sha256.lower(),
            "design_lock": args.expected_design_lock_sha256.lower(),
            "judgment_lock": args.expected_judgment_lock_sha256.lower(),
        }
        for key, value in expected.items():
            if sha256(paths[key]) != value:
                raise ValueError(f"{key} SHA256 mismatch")

        prereg = load(paths["preregistration"])
        design = load(paths["design_lock"])
        judgment_lock = load(paths["judgment_lock"])
        protocol = load(paths["protocol_status"])
        control_endpoint = load(paths["control_endpoint_status"])
        manifest = load(paths["treatment_manifest"])
        if prereg.get("experiment_id") != "H2" or prereg.get("status") != "REGISTERED_NO_LAUNCH":
            raise ValueError("H2 preregistration identity")
        if design.get("design_id") != "H2" or design.get("status") != "LOCKED":
            raise ValueError("H2 design-lock identity")
        if judgment_lock.get("design_id") != "H2-JUDGMENT-001" or judgment_lock.get("status") != "LOCKED":
            raise ValueError("H2 judgment-lock identity")
        minimum = float(judgment_lock["gates"]["throughput_first60_ratio_min"])
        if minimum != 0.85 or int(judgment_lock["gates"]["throughput_first_rows"]) != 60:
            raise ValueError("registered first60 gate identity")
        if protocol.get("overall") != "FAIL" or protocol.get("state") != "H2_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT":
            raise ValueError("protocol-abort status identity")
        if protocol.get("stop_action") != "TERMINATED" or protocol.get("first60", {}).get("status") != "FAIL":
            raise ValueError("protocol-abort termination evidence")
        if control_endpoint.get("overall") != "PASS" or control_endpoint.get("state") != "ARM_ENDPOINT_FROZEN":
            raise ValueError("control endpoint identity")
        config = manifest.get("config", {})
        if (
            manifest.get("run_id") != design["arms"]["treatment"]["run_id"]
            or config.get("h2_window_arm") != "treatment"
            or config.get("showdown_ev_value_targets") is not True
            or int(config.get("showdown_ev_value_target_max_runouts", -1)) != 200
            or config.get("h2_preregistration_sha256") != expected["preregistration"]
            or config.get("h2_design_lock_sha256") != expected["design_lock"]
        ):
            raise ValueError("treatment manifest/config identity")

        control_rows = metric_rows(paths["control_metrics"])
        treatment_rows = metric_rows(paths["treatment_metrics"])
        control_hps = first60_effective_hps(control_rows)
        treatment_hps = first60_effective_hps(treatment_rows)
        ratio = treatment_hps / control_hps
        recorded = protocol["first60"]
        for actual, observed, label in (
            (control_hps, float(recorded["control_effective_hps"]), "control h/s"),
            (treatment_hps, float(recorded["treatment_effective_hps"]), "treatment h/s"),
            (ratio, float(recorded["ratio"]), "ratio"),
        ):
            if abs(actual - observed) > 1e-9 * max(1.0, abs(actual)):
                raise ValueError(f"protocol {label} mismatch")
        overall, classification = classify(control_hps, treatment_hps, minimum)
        output = {
            "schema_version": "v5.hybrid.h2.protocol_abort_judgment.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": overall,
            "classification": classification,
            "judgment_mode": "REGISTERED_PROTOCOL_ABORT_SHORT_CIRCUIT",
            "protocol_abort": True,
            "route_review_required": True,
            "registered_gate": {
                "minimum_ratio": minimum,
                "warmup_rows_excluded": 1,
                "rows": 60,
                "control_effective_hps": control_hps,
                "treatment_effective_hps": treatment_hps,
                "ratio": ratio,
                "pass": False,
            },
            "control_endpoint": control_endpoint,
            "treatment_terminal_iteration": int(manifest.get("iteration", -1)),
            "treatment_terminal_hands": int(manifest.get("total_hands", -1)),
            "registered_measurements_not_run_due_protocol_abort": [
                "treatment_full_endpoint",
                "endpoint_mse",
                "treatment_fixed40k_mirror",
                "full_window_throughput",
                "terminal_entropy_noninferiority",
            ],
            "source_sha256": {key: sha256(value) for key, value in paths.items()},
            "judgment_lock_sha256": expected["judgment_lock"],
            "official_hands": 0,
            "strength_claim": "FORBIDDEN",
        }
        rc = 0
    except Exception as exc:
        output = {
            "schema_version": "v5.hybrid.h2.protocol_abort_judgment.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "INCONCLUSIVE",
            "classification": "FAIL_CLOSED_MISSING_OR_INVALID_EVIDENCE",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "route_review_required": False,
            "official_hands": 0,
            "strength_claim": "FORBIDDEN",
        }
        rc = 2
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
