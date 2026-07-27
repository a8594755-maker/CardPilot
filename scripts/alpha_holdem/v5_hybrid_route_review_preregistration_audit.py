#!/usr/bin/env python3
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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--registration", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    path = Path(args.registration).resolve()
    x = json.loads(path.read_text(encoding="utf-8-sig"))
    checks: dict[str, bool] = {}
    errors: list[str] = []

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)
        if not condition:
            errors.append(name)

    check("identity", x.get("design_id") == "HYBRID-ROUTE-REVIEW-001" and x.get("status") == "LOCKED_CONDITIONAL")
    tool = Path(x.get("tool_path", ""))
    check("tool_binding", tool.is_file() and sha256(tool) == x.get("tool_sha256"))
    files = x.get("frozen_files", [])
    check("frozen_files", len(files) >= 6 and all(Path(i["path"]).is_file() and sha256(Path(i["path"])) == i["sha256"] for i in files))
    trigger = x.get("trigger", {})
    check("trigger", trigger.get("h1") == "TERMINAL_FAIL" and trigger.get("h2_overall") == ["FAIL", "INCONCLUSIVE"] and trigger.get("exclude_classification") == "FAIL_CLOSED_MISSING_OR_INVALID_EVIDENCE")
    permissions = x.get("candidate_permissions", {})
    check("h3_gate", permissions.get("H3", {}).get("requires_qa_complete_boards") == 600 and permissions.get("H3", {}).get("actor_only") is True)
    check("h4_gate", permissions.get("H4", {}).get("requires_complete_common_deal_crossplay_matrix") is True)
    check("h5_gate", permissions.get("H5", {}).get("requires_resolver_legality_latency_blueprint_proof") is True)
    check("route_exhaustion", x.get("route_exhaustion_rule") == "only_terminal_failures_of_all_viable_in_family_candidates_may_escalate")
    check("no_launch", x.get("behavior_launch_authorized") is False and x.get("official_hands_authorized") == 0)
    output = {
        "schema_version": "v5.hybrid.route_review_001.preregistration_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS_IMMUTABLE_ROUTE_REVIEW_REGISTRATION" if not errors else "FAIL_CLOSED",
        "checks": checks,
        "errors": errors,
        "registration_sha256": sha256(path),
        "behavior_launch_authorized": False,
        "official_hands": 0,
    }
    Path(args.out).write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
