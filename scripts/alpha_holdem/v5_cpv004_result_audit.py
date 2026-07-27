#!/usr/bin/env python3
"""Independent fail-closed audit of CPV004 terminal bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite CPV004 audit")
    result = json.loads(args.result.read_text(encoding="utf-8"))
    prereg_path = ROOT / "reports/v5_cpv004_preregistration_20260719.json"
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    checks["schema"] = result.get("schema_version") == "v5.cpv004.result.v1"
    checks["identity"] = result.get("design_id") == "CPV004_CORRECTED_FINAL_CLEANUP_OBSERVATION_GATE"
    checks["result_pass"] = result.get("overall") == "PASS" and result.get("classification") == "CPV004_PASS_CORRECTED_FINAL_CLEANUP_OBSERVATION"
    checks["prereg_hash"] = sha(prereg_path) == result.get("preregistration_sha256")
    checks["single_change"] = result.get("single_engineering_change") == prereg.get("single_engineering_change")
    tools = result.get("tool_hashes", {})
    checks["four_tools"] = len(tools) == 4
    for relative, expected in tools.items():
        checks[f"tool_{Path(relative).name}"] = sha(ROOT / relative) == expected
    cycles = result.get("cycles", [])
    checks["twenty_cycles"] = len(cycles) == prereg["fixture"]["stress_cycles"] == 20
    checks["cycle_indices"] = [cycle.get("cycle") for cycle in cycles] == list(range(20))
    checks["every_cycle_pass"] = len(cycles) == 20 and all(cycle.get("overall") == "PASS" and all(cycle.get("checks", {}).values()) for cycle in cycles)
    checks["ready_deadline"] = len(cycles) == 20 and max(cycle.get("ready_elapsed_seconds", 99) for cycle in cycles) <= prereg["gates"]["initial_ready_deadline_seconds"]
    checks["ready_before_scan"] = len(cycles) == 20 and all(cycle["checks"].get("ready_before_scan") for cycle in cycles)
    checks["five_roles_each"] = len(cycles) == 20 and all(set(cycle.get("role_results", {})) == set(prereg["fixture"]["roles"]) for cycle in cycles)
    checks["all_role_results"] = len(cycles) == 20 and all(all(value.get("overall") == "PASS" and value.get("trigger_provenance_complete") is True for value in cycle["role_results"].values()) for cycle in cycles)
    required_adversarial = set(prereg["gates"]["adversarial_tokens_required"])
    checks["adversarial_set"] = len(cycles) == 20 and all(set(cycle.get("adversarial", {})) == required_adversarial for cycle in cycles)
    checks["adversarial_fail_closed"] = len(cycles) == 20 and all(all(value.get("pass") and value["result"].get("overall") == "FAIL_CLOSED" and value["result"].get("trigger_provenance_complete") for value in cycle["adversarial"].values()) for cycle in cycles)
    checks["supervisor_live"] = len(cycles) == 20 and all(cycle.get("live_state") == "LIVE" for cycle in cycles)
    checks["supervisor_shutdown"] = len(cycles) == 20 and all(cycle.get("shutdown_state") == prereg["gates"]["supervisor_exit_classification"] for cycle in cycles)
    checks["pid_reuse_safe"] = len(cycles) == 20 and all(cycle.get("pid_reuse_state") == prereg["gates"]["supervisor_pid_reuse_classification"] for cycle in cycles)
    checks["cleanup_deadline"] = len(cycles) == 20 and all(cycle.get("shutdown", {}).get("cleanup_elapsed_seconds", 99) <= prereg["gates"]["cleanup_deadline_seconds"] for cycle in cycles)
    checks["final_zero_survivors"] = len(cycles) == 20 and all(not cycle.get("final_survivors") for cycle in cycles)
    checks["intermediate_diagnostic_only"] = len(cycles) == 20 and all(cycle.get("per_child_survivor_snapshots_interpretation") == "DIAGNOSTIC_ONLY_NOT_GATE" for cycle in cycles)
    checks["normal_exit_zero"] = len(cycles) == 20 and all(cycle["checks"].get("normal_exit_zero") for cycle in cycles)
    injected = result.get("injected_readiness_failure", {})
    checks["injected_nonzero"] = injected.get("ready_absent") is True and injected.get("nonzero") is True and injected.get("pass") is True and not injected.get("final_survivors")
    aggregate = result.get("aggregate", {})
    checks["aggregate"] = aggregate.get("cycles_required") == aggregate.get("cycles_passed") == 20 and aggregate.get("all_roles_pass") is True and aggregate.get("all_adversarial_pass") is True and aggregate.get("all_final_cleanup_pass") is True and aggregate.get("all_normal_exit_zero") is True and aggregate.get("all_pid_reuse_safe") is True and aggregate.get("injected_readiness_failure_pass") is True
    checks["no_failures"] = not result.get("deterministic_failures") and not result.get("fixture_errors")
    checks["no_forbidden_process"] = not result.get("initial_forbidden_processes") and not result.get("final_forbidden_processes")
    checks["no_trainer_gpu_official"] = result.get("trainer_launched") is False and result.get("gpu_used") is False and result.get("official_hands") == 0
    checks["terminal_effect"] = result.get("terminal_effect") == "PERMITS_SEPARATE_H15_PREREGISTRATION_ONLY"
    checks["no_strength"] = result.get("strength_claim") == "FORBIDDEN"
    failed = [name for name, passed in checks.items() if not passed]
    audit = {
        "schema_version": "v5.cpv004.result_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "result_sha256": sha(args.result),
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "terminal_effect": result.get("terminal_effect") if not failed else "REQUIRES_ROUTE_REVIEW_013_NO_BEHAVIOR_LAUNCH",
        "behavior_launch_authority": "NONE_H15_REQUIRES_SEPARATE_REGISTRATION",
        "official_hands": 0,
    }
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
