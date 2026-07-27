#!/usr/bin/env python3
"""Independent consistency audit for the H2 protocol-abort terminal artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def independent_hps(values: list[dict]) -> float:
    sample = values[1:61]
    if len(sample) != 60:
        raise ValueError("not exactly 60 rows after warmup")
    elapsed = (datetime.fromisoformat(sample[-1]["recorded_at"]) - datetime.fromisoformat(sample[0]["recorded_at"])).total_seconds()
    return (int(sample[-1]["hands"]) - int(sample[0]["hands"])) / elapsed


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--judgment", required=True)
    p.add_argument("--expected-judgment-sha256", required=True)
    p.add_argument("--control-metrics", required=True)
    p.add_argument("--treatment-metrics", required=True)
    p.add_argument("--protocol-status", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    out = Path(a.out).resolve()
    errors: list[str] = []
    try:
        judgment_path = Path(a.judgment).resolve()
        if sha(judgment_path) != a.expected_judgment_sha256.lower():
            errors.append("judgment SHA mismatch")
        judgment = load(judgment_path)
        protocol_path = Path(a.protocol_status).resolve()
        protocol = load(protocol_path)
        control_path, treatment_path = Path(a.control_metrics).resolve(), Path(a.treatment_metrics).resolve()
        control_hps, treatment_hps = independent_hps(rows(control_path)), independent_hps(rows(treatment_path))
        ratio = treatment_hps / control_hps
        if judgment.get("overall") != "FAIL" or judgment.get("classification") != "H2_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT":
            errors.append("terminal classification mismatch")
        if judgment.get("route_review_required") is not True or judgment.get("protocol_abort") is not True:
            errors.append("terminal route/protocol flags mismatch")
        if ratio >= 0.85:
            errors.append("independent ratio does not fail")
        if abs(float(judgment.get("registered_gate", {}).get("ratio", -1)) - ratio) > 1e-12:
            errors.append("judgment ratio mismatch")
        if protocol.get("state") != "H2_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT" or protocol.get("stop_action") != "TERMINATED":
            errors.append("protocol status mismatch")
        sources = judgment.get("source_sha256", {})
        for key, path in (("control_metrics", control_path), ("treatment_metrics", treatment_path), ("protocol_status", protocol_path)):
            if sources.get(key) != sha(path):
                errors.append(f"source hash mismatch: {key}")
        payload = {
            "schema_version": "v5.hybrid.h2.protocol_abort_judgment_audit.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "PASS_IMMUTABLE_H2_PROTOCOL_ABORT_JUDGMENT" if not errors else "FAIL_CLOSED",
            "errors": errors,
            "independent_control_effective_hps": control_hps,
            "independent_treatment_effective_hps": treatment_hps,
            "independent_ratio": ratio,
            "judgment_sha256": sha(judgment_path),
            "official_hands": 0,
            "strength_claim": "FORBIDDEN",
        }
        rc = 0 if not errors else 2
    except Exception as exc:
        payload = {
            "schema_version": "v5.hybrid.h2.protocol_abort_judgment_audit.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "FAIL_CLOSED",
            "errors": errors + [f"{type(exc).__name__}: {exc}"],
            "official_hands": 0,
            "strength_claim": "FORBIDDEN",
        }
        rc = 2
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
