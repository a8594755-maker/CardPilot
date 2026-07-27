#!/usr/bin/env python3
"""Independent audit of the terminal H6 first60 protocol abort."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def effective(values: list[dict]) -> float:
    sample = values[1:61]
    if len(sample) != 60:
        raise ValueError("not exactly60 accepted rows after warmup")
    elapsed = (datetime.fromisoformat(sample[-1]["recorded_at"]) - datetime.fromisoformat(sample[0]["recorded_at"])).total_seconds()
    if elapsed <= 0:
        raise ValueError("nonpositive elapsed time")
    return (int(sample[-1]["hands"]) - int(sample[0]["hands"])) / elapsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-design-lock-sha256", required=True)
    parser.add_argument("--judgment", type=Path, required=True)
    parser.add_argument("--protocol-status", type=Path, required=True)
    parser.add_argument("--control-metrics", type=Path, required=True)
    parser.add_argument("--treatment-metrics", type=Path, required=True)
    parser.add_argument("--partial-mirror", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    errors: list[str] = []
    try:
        design = load(args.design_lock)
        judgment = load(args.judgment)
        protocol = load(args.protocol_status)
        control_hps = effective(rows(args.control_metrics))
        treatment_hps = effective(rows(args.treatment_metrics))
        ratio = treatment_hps / control_hps
        if sha256(args.design_lock) != args.expected_design_lock_sha256.lower() or design.get("design_id") != "H6" or design.get("status") != "LOCKED":
            errors.append("design lock identity")
        if judgment.get("overall") != "FAIL" or judgment.get("classification") != "H6_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT" or judgment.get("route_review_required") is not True:
            errors.append("judgment identity/classification")
        first60 = protocol.get("first60", {})
        if protocol.get("overall") != "FAIL" or protocol.get("state") != "H6_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT" or protocol.get("stop_action") != "TERMINATED":
            errors.append("protocol identity/termination")
        if first60.get("rows_used") != [2, 61] or float(first60.get("minimum", -1)) != 0.85:
            errors.append("registered rows/threshold")
        if ratio >= 0.85 or abs(float(first60.get("ratio", -1)) - ratio) > 1e-12:
            errors.append("independent ratio")
        if not args.partial_mirror.is_file():
            errors.append("partial mirror missing")
        result = {
            "schema_version": "v5.hybrid.h6.protocol_abort_audit.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "PASS_IMMUTABLE_H6_PROTOCOL_ABORT" if not errors else "FAIL_CLOSED",
            "errors": errors,
            "independent_control_effective_hps": control_hps,
            "independent_treatment_effective_hps": treatment_hps,
            "independent_ratio": ratio,
            "threshold": 0.85,
            "source_sha256": {
                "design_lock": sha256(args.design_lock),
                "judgment": sha256(args.judgment),
                "protocol_status": sha256(args.protocol_status),
                "control_metrics": sha256(args.control_metrics),
                "treatment_metrics": sha256(args.treatment_metrics),
                "partial_control_mirror": sha256(args.partial_mirror),
            },
            "partial_control_mirror_rows": sum(1 for line in args.partial_mirror.open("rb") if line.strip()),
            "partial_control_mirror_classification": "POST_PROTOCOL_ABORT_EXPLORATORY_ONLY_NOT_JUDGMENT_EVIDENCE",
            "endpoint_mse_status": "NOT_RUN_PROTOCOL_ABORT",
            "full_window_status": "NOT_RUN_PROTOCOL_ABORT",
            "mirror_judgment_status": "NOT_RUN_PROTOCOL_ABORT",
            "official_hands": 0,
            "strength_claim": "FORBIDDEN",
        }
        return_code = 0 if not errors else 2
    except Exception as exc:
        result = {"schema_version": "v5.hybrid.h6.protocol_abort_audit.v1", "checked_at": datetime.now(timezone.utc).isoformat(), "overall": "FAIL_CLOSED", "errors": errors + [f"{type(exc).__name__}: {exc}"], "official_hands": 0, "strength_claim": "FORBIDDEN"}
        return_code = 2
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
