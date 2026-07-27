#!/usr/bin/env python3
"""Fail-closed conditional HYBRID route review after H1 plus H2."""
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


def h2_trigger(judgment: dict) -> tuple[str, str]:
    overall = judgment.get("overall")
    classification = str(judgment.get("classification", ""))
    if overall == "PASS":
        return "NOT_TRIGGERED", "H2_PASS_CONTINUE_DEFAULT_H3_ROUTE"
    terminal_no_progress = (
        overall in {"FAIL", "INCONCLUSIVE"}
        and classification != "FAIL_CLOSED_MISSING_OR_INVALID_EVIDENCE"
        and judgment.get("route_review_required") is True
    )
    if terminal_no_progress:
        return "TRIGGERED", "H1_AND_H2_CONSECUTIVE_FAIL_OR_NO_PROGRESS"
    return "WAITING_FAIL_CLOSED", "H2_TERMINAL_IDENTITY_OR_EVIDENCE_NOT_VALID"


def select_next(h3_readiness: dict | None) -> tuple[str, bool]:
    ready = bool(
        h3_readiness
        and h3_readiness.get("overall") == "PASS_H3_ACTOR_POLICY_BRIDGE_READY"
        and int(h3_readiness.get("qa_complete_boards", 0)) >= 600
        and h3_readiness.get("exact_v55_roundtrip") is True
        and h3_readiness.get("legal_9_action_mass_mapping") is True
    )
    if ready:
        return "H3_ACTOR_ONLY_CFR_DISTILLATION_PREREGISTRATION", True
    return "H3_ENGINEERING_PREREQUISITES_ONLY_NO_BEHAVIOR_LAUNCH", False


def verify_registration(path: Path, expected: str) -> dict:
    if sha256(path) != expected.lower():
        raise ValueError("route-review preregistration SHA mismatch")
    registration = load(path)
    if registration.get("design_id") != "HYBRID-ROUTE-REVIEW-001":
        raise ValueError("route-review design identity")
    if registration.get("status") != "LOCKED_CONDITIONAL":
        raise ValueError("route-review status")
    if registration.get("tool_sha256") != sha256(Path(__file__).resolve()):
        raise ValueError("route-review tool binding")
    for item in registration.get("frozen_files", []):
        item_path = Path(item["path"])
        if not item_path.is_file() or sha256(item_path) != item["sha256"]:
            raise ValueError(f"frozen file mismatch: {item_path}")
    return registration


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--registration", required=True)
    p.add_argument("--expected-registration-sha256", required=True)
    p.add_argument("--h2-judgment", required=True)
    p.add_argument("--h3-readiness")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    out_path = Path(args.out)
    try:
        registration = verify_registration(Path(args.registration), args.expected_registration_sha256)
        h1 = load(Path(registration["h1_completion_audit"]))
        if h1.get("overall") != "PASS_COMPLETE_H1_TERMINAL_FAIL":
            raise ValueError("H1 terminal FAIL identity is not exact")
        judgment = load(Path(args.h2_judgment))
        if judgment.get("judgment_lock_sha256") != registration["h2_judgment_lock_sha256"]:
            raise ValueError("H2 judgment lock identity mismatch")
        trigger, trigger_reason = h2_trigger(judgment)
        if trigger == "WAITING_FAIL_CLOSED":
            raise ValueError(trigger_reason)
        readiness = load(Path(args.h3_readiness)) if args.h3_readiness and Path(args.h3_readiness).is_file() else None
        selected, prereg_authorized = select_next(readiness)
        output = {
            "schema_version": "v5.hybrid.route_review_001.result.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "PASS_ROUTE_REVIEW" if trigger == "TRIGGERED" else "PASS_NOT_TRIGGERED_H2_PASS",
            "trigger": trigger,
            "trigger_reason": trigger_reason,
            "selected_next": selected,
            "h3_behavior_preregistration_authorized": prereg_authorized,
            "behavior_launch_authorized": False,
            "route_exhausted": False,
            "candidate_permissions": registration["candidate_permissions"],
            "h2_judgment": judgment,
            "h3_readiness": readiness,
            "registration_sha256": sha256(Path(args.registration)),
            "official_hands": 0,
            "strength_claim": "FORBIDDEN",
        }
        rc = 0
    except Exception as exc:
        output = {
            "schema_version": "v5.hybrid.route_review_001.result.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "INCONCLUSIVE_FAIL_CLOSED",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "behavior_launch_authorized": False,
            "route_exhausted": False,
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
