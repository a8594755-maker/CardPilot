#!/usr/bin/env python3
"""Independent fail-closed terminal audit for CAL-EXT-002."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPLETION = ROOT / "reports/v5_cal_ext_002_completion_20260716.json"
OUT = ROOT / "reports/v5_cal_ext_002_completion_audit_20260716.json"
TAG = "cal_ext_002_h11_control_greedy_quick5k_20260716"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rows(path: Path) -> int:
    with path.open("r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def main() -> int:
    d = json.loads(COMPLETION.read_text(encoding="utf-8"))
    c: dict[str, bool] = {}
    c["schema"] = d.get("schema_version") == "v5.external_calibration.completion.v1"
    c["identity"] = d.get("measurement_id") == "CAL-EXT-002_H11_CONTROL_GREEDY_QUICK5K"
    c["terminal_fail_closed"] = d.get("terminal") is True and d.get("verdict") == "FAIL_CLOSED" and d.get("classification") == "CAL_EXT_002_FAIL_CLOSED_UNEXPECTED_SELECTOR_PROMOTION_FAILURES"
    refs = {
        "preregistration": ROOT / "reports/v5_cal_ext_002_preregistration_20260716.json",
        "preregistration_audit": ROOT / "reports/v5_cal_ext_002_preregistration_audit_20260716.json",
        "design_lock": ROOT / "reports/v5_cal_ext_002_design_lock_20260716.json",
        "design_lock_audit": ROOT / "reports/v5_cal_ext_002_design_lock_audit_20260716.json",
    }
    for key, path in refs.items():
        c[f"authority_{key}"] = sha(path) == d["authority"][f"{key}_sha256"]
    source = ROOT / "models/alpha_holdem_v5_hybrid/v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715/h11_control_endpoint.pt"
    frozen = ROOT / f"models/bench_v55_{TAG}_checkpoint.pt"
    expected_cp = d["checkpoint"]["source_and_frozen_sha256"]
    c["source_checkpoint"] = sha(source) == expected_cp
    c["frozen_checkpoint"] = sha(frozen) == expected_cp
    bundle_paths = {
        "launch_status": ROOT / "reports/v5_cal_ext_002_launch_status_20260716.json",
        "runtime_plan": ROOT / "reports/v5_cal_ext_002_runtime_plan_20260716.json",
        "ci_summary": ROOT / f"models/bench_v55_{TAG}_ci_summary.json",
        "promotion_gate": ROOT / f"models/bench_v55_{TAG}_promotion_gate.json",
        "artifact_audit": ROOT / f"models/bench_v55_{TAG}_artifact_audit.json",
        "artifact_audit_md": ROOT / f"models/bench_v55_{TAG}_artifact_audit.md",
        "hand_review": ROOT / f"models/bench_v55_{TAG}_hand_review.json",
        "hand_review_md": ROOT / f"models/bench_v55_{TAG}_hand_review.md",
        "selector_replay": ROOT / f"models/bench_v55_{TAG}_selector_replay.json",
        "selector_replay_md": ROOT / f"models/bench_v55_{TAG}_selector_replay.md",
        "loss_report": ROOT / f"models/bench_v55_{TAG}_loss_report.json",
        "loss_report_md": ROOT / f"models/bench_v55_{TAG}_loss_report.md",
        "dump_analysis": ROOT / f"models/bench_v55_{TAG}_dump_analysis.txt",
        "summary": ROOT / f"models/bench_v55_{TAG}_summary.txt",
    }
    for key, path in bundle_paths.items():
        c[f"bundle_{key}"] = path.is_file() and sha(path) == d["bundle"][f"{key}_sha256"]
    part_expected = d["part_sha256"]
    total_hands = 0
    total_dump = 0
    for i in range(1, 5):
        paths = {
            "result": ROOT / f"models/bench_v55_{TAG}_part{i}.json",
            "hands": ROOT / f"models/bench_v55_{TAG}_part{i}_hands.jsonl",
            "dump": ROOT / f"models/bench_v55_{TAG}_part{i}_dump.jsonl",
        }
        for role, path in paths.items():
            c[f"part{i}_{role}_hash"] = path.is_file() and sha(path) == part_expected[f"part{i}_{role}"]
        n = rows(paths["hands"])
        c[f"part{i}_hands_1250"] = n == 1250
        total_hands += n
        total_dump += rows(paths["dump"])
    c["exact_total_hands"] = total_hands == 5000 == d["measurement"]["hands"]
    c["decision_rows"] = total_dump == 29878 == d["measurement"]["decision_rows"]
    ci = json.loads(bundle_paths["ci_summary"].read_text(encoding="utf-8"))
    c["ci_identity"] = ci.get("hands") == 5000 and ci.get("bb_per_100") == d["measurement"]["bb_per_100"] and ci.get("lower_bound_bb_per_100") == d["measurement"]["ci95_lower_bb_per_100"] and ci.get("upper_bound_bb_per_100") == d["measurement"]["ci95_upper_bb_per_100"]
    c["l0"] = ci.get("milestone_level") == "L0" and d["measurement"].get("l5_claim") is False
    audit = json.loads(bundle_paths["artifact_audit"].read_text(encoding="utf-8"))
    review = json.loads(bundle_paths["hand_review"].read_text(encoding="utf-8"))
    c["artifact_audit_pass"] = audit.get("overall") == "PASS" and audit.get("fail_count") == 0 and audit.get("total_hands") == 5000
    c["hand_review_pass"] = review.get("overall") == "PASS" and review.get("ci", {}).get("hands") == 5000
    promotion = json.loads(bundle_paths["promotion_gate"].read_text(encoding="utf-8"))
    fail_set = [x["name"] for x in promotion.get("checks", []) if x.get("status") == "FAIL"]
    observed = d["registered_gate"]["observed_promotion_fail_set"]
    c["observed_fail_set"] = fail_set == observed
    c["accepted_fail_set_mismatch"] = fail_set != d["registered_gate"]["accepted_promotion_fail_set_exact"]
    c["unexpected_selector_failures"] = d["registered_gate"]["unexpected_failures"] == ["selector_replay_played_postflop_aggression", "selector_replay_greedy_postflop_aggression"]
    c["registered_fail_closed"] = d["registered_gate"].get("registered_fail_closed_triggered") is True
    c["no_promotion"] = d["interpretation"].get("promotion_authorized") is False and d["interpretation"].get("formal100k_authorized") is False
    c["no_strength_claim"] = d["interpretation"].get("l5_l6_claim") == "FORBIDDEN"
    c["route_review_009"] = d["interpretation"].get("next_transition") == "REGISTER_AND_EXECUTE_ROUTE_REVIEW_009"
    failed = sorted(k for k, ok in c.items() if not ok)
    out = {
        "schema_version": "v5.external_calibration.completion_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "completion_sha256": sha(COMPLETION),
        "checks": c,
        "checks_passed": sum(c.values()),
        "checks_total": len(c),
        "failed": failed,
        "overall": "PASS_COMPLETE_CAL_EXT_002_TERMINAL_FAIL_CLOSED" if not failed else "FAIL_CLOSED_AUDIT",
        "official_hands": 5000,
        "latest_official_level": "L0",
        "strength_claim": "FORBIDDEN",
        "next_transition": "ROUTE_REVIEW_009" if not failed else "NONE",
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
