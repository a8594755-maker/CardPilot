#!/usr/bin/env python3
"""Audit both sessions plus the release-scaling contract."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import torch

HERE = Path(__file__).resolve().parent
REFERENCE = (
    HERE.parent
    / "v6-legacy-risk-weighted-source-margin-smoke-20260901"
    / "audit_smoke.py"
)
spec = importlib.util.spec_from_file_location("matched_smoke_auditor", REFERENCE)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load auditor: {REFERENCE}")
auditor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auditor)
auditor.HERE = HERE


def rows(label: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (HERE / label / "h1_training_metrics.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]


def main() -> None:
    arms = {
        "control": auditor.audit_arm("control", 4.0),
        "treatment": auditor.audit_arm("treatment", 4.0),
    }
    control_checkpoint = torch.load(
        HERE / "control/latest.pt", map_location="cpu", weights_only=False
    )
    treatment_checkpoint = torch.load(
        HERE / "treatment/latest.pt", map_location="cpu", weights_only=False
    )
    control_rows = rows("control")
    treatment_rows = rows("treatment")
    release = {
        "control": sum(
            int(row["source_greedy_margin_released_rows"])
            for row in control_rows
        ),
        "treatment": sum(
            int(row["source_greedy_margin_released_rows"])
            for row in treatment_rows
        ),
    }
    checks = {
        "arms": all(row["status"] == "PASS" for row in arms.values()),
        "control_flag_off": not bool(
            control_checkpoint["config"]["source_greedy_risk_scale_release"]
        ),
        "treatment_flag_on": bool(
            treatment_checkpoint["config"]["source_greedy_risk_scale_release"]
        ),
        "treatment_release_nonzero": release["treatment"] > 0,
        "treatment_release_reduced": (
            release["treatment"] < release["control"]
        ),
    }
    result = {
        "schema": "cardpilot.risk_scaled_release_smoke_audit.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "released_rows_sum": release,
        "arms": arms,
    }
    (HERE / "session_audit.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
