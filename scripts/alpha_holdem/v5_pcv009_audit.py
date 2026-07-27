#!/usr/bin/env python3
"""Independent audit for immutable PCV009 phase-aware identity result."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


PREREG_SHA = "a90b9566b76a7679070dcde2a664ac2e41335154ff7ee932d655af930771dc86"
COMMAND_SHA = "efaf227352c6620b4f12dd5f06ac67d98d834feb11384b167170618dc1cf9e99"
CREATE_TIME = 1784302339.7041352
EXPECTED_HASHES = {
    "preregistration": PREREG_SHA,
    "coordinator_code": "71c60ea468d530b26a24673607c141a8f5ca80c5e1e2acdd61a06e2cac2cf986",
    "old_checker": "8191f46a08b37d4a6d4ba9223fea9ecd7477e869c6cef64d8aa305b8b8060d07",
    "live_lock": "83b3a99870116b939c7ede0b51283f1b5c0849dd1ccdb50024e9e0fa3a71fdc6",
    "status_correction": "cc36efb723b506d35212939ffa653fa10f79082d4852ad9972195f61fd9ca583",
    "status_correction_audit": "b980222260b4161e60e22458d9eb28de171fc56d00c52d158adaa303baff8073",
    "progress": "d153cf5684cef59bb2aca0b62ffdb37d7a74cbf36bd54efa1f4aa111922aa2ed",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recompute_counts(row: dict[str, Any]) -> dict[str, int]:
    roles = row["roles"]
    return {
        "solve_worker": sum(item["role"] == "SOLVE_WORKER" for item in roles),
        "qa_200bb_board": sum(item["role"] == "QA_200BB_BOARD" for item in roles),
        "conhost_ignored": sum(item["role"] == "CONHOST_IGNORED" for item in roles),
        "unknown": sum(item["role"] == "UNKNOWN" for item in roles),
        "active_work": sum(item["role"] in ("SOLVE_WORKER", "QA_200BB_BOARD") for item in roles),
        "transient_exits": int(row["role_counts"]["transient_exits"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--coordinator-code", type=Path, required=True)
    parser.add_argument("--old-checker", type=Path, required=True)
    parser.add_argument("--live-lock", type=Path, required=True)
    parser.add_argument("--status-correction", type=Path, required=True)
    parser.add_argument("--status-correction-audit", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--path1-pid", type=int, choices=[23720], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite immutable PCV009 audit")
    result = json.loads(args.result.read_text(encoding="utf-8"))
    actual_hashes = {
        "preregistration": sha256(args.preregistration),
        "coordinator_code": sha256(args.coordinator_code),
        "old_checker": sha256(args.old_checker),
        "live_lock": sha256(args.live_lock),
        "status_correction": sha256(args.status_correction),
        "status_correction_audit": sha256(args.status_correction_audit),
        "progress": sha256(args.progress),
    }
    observations = result["observations"]
    counts = [recompute_counts(row) for row in observations]
    coordinator = psutil.Process(args.path1_pid)
    live_command_sha = hashlib.sha256(" ".join(coordinator.cmdline()).encode("utf-8")).hexdigest()
    summary = result["summary"]
    recomputed_summary = {
        "solve_worker_count_range": [min(row["solve_worker"] for row in counts), max(row["solve_worker"] for row in counts)],
        "qa_child_count_range": [min(row["qa_200bb_board"] for row in counts), max(row["qa_200bb_board"] for row in counts)],
        "active_work_count_range": [min(row["active_work"] for row in counts), max(row["active_work"] for row in counts)],
        "unknown_role_count": sum(row["unknown"] for row in counts),
        "transient_exit_count": sum(row["transient_exits"] for row in counts),
        "qa_role_observed": any(row["qa_200bb_board"] > 0 for row in counts),
        "gpu_pid_match_count": sum(len(row["descendant_gpu_pid_intersection"]) for row in observations),
    }
    checks = {
        "preregistration_binding": actual_hashes["preregistration"] == PREREG_SHA and result["preregistration_sha256"] == PREREG_SHA,
        "all_frozen_hashes": actual_hashes == EXPECTED_HASHES and result["frozen_hashes"] == EXPECTED_HASHES,
        "runner_binding": sha256(args.runner) == result["tool_sha256"],
        "schema_and_classification": result["schema_version"] == "v5.pcv009.result.v1" and result["overall"] == "PASS" and result["classification"] == "PCV009_PASS_PHASE_AWARE_PATH1_IDENTITY_CONTRACT",
        "observation_dimensions": len(observations) == 20 and [row["index"] for row in observations] == list(range(20)),
        "observation_contract": result["observation_contract"] == {"snapshots": 20, "interval_seconds": 1.0, "active_work_min": 1, "active_work_max": 6},
        "stored_role_counts_recomputed": all(row["role_counts"] == count for row, count in zip(observations, counts)),
        "only_allowlisted_roles": all(item["role"] in ("SOLVE_WORKER", "QA_200BB_BOARD", "CONHOST_IGNORED") for row in observations for item in row["roles"]),
        "work_role_bounds": all(1 <= row["active_work"] <= 6 for row in counts),
        "coordinator_identity_in_window": all(row["coordinator_pid"] == 23720 and math.isclose(row["coordinator_create_time"], CREATE_TIME, rel_tol=0.0, abs_tol=1e-6) and row["coordinator_command_sha256"] == COMMAND_SHA and row["coordinator_priority"] == psutil.BELOW_NORMAL_PRIORITY_CLASS for row in observations),
        "node_priorities_in_window": all(row["node_child_priorities_below_normal"] is True for row in observations),
        "no_gpu_pid_match_in_window": all(row["descendant_gpu_pid_intersection"] == [] for row in observations),
        "static_mechanism_complete": all(result["static_mechanism"].values()),
        "summary_recomputed": summary == recomputed_summary,
        "registered_gates_exact": all(result["gates"].values()),
        "live_coordinator_identity": coordinator.pid == 23720 and math.isclose(coordinator.create_time(), CREATE_TIME, rel_tol=0.0, abs_tol=1e-6) and live_command_sha == COMMAND_SHA and coordinator.nice() == psutil.BELOW_NORMAL_PRIORITY_CLASS,
        "path1_mutation_false": result["path1_mutation"] is False,
        "trainerless_no_checkpoint": result["trainer_started"] is False and result["checkpoint_written"] is False,
        "pcv008_closure": result["pcv008_reconstruction_or_reclassification"] == "FORBIDDEN",
        "no_official_or_inference": result["official_hands"] == 0 and result["behavior_method_or_strength_inference"] == "FORBIDDEN" and result["next_authority"] == "ROUTE_REVIEW021_ONLY",
    }
    failed = [name for name, passed in checks.items() if not passed]
    audit = {
        "schema_version": "v5.pcv009.result_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "artifact_sha256": sha256(args.result),
        "runner_sha256": sha256(args.runner),
        "checks": checks,
        "checks_passed": len(checks) - len(failed),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "classification": result["classification"] if not failed else "PCV009_AUDIT_FAIL_CLOSED",
        "recomputed_summary": recomputed_summary,
        "official_hands": 0,
        "behavior_launch_authority": "NONE_ROUTE_REVIEW021_ONLY",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": audit["overall"], "passed": audit["checks_passed"], "total": audit["checks_total"], "failed": failed, "summary": recomputed_summary}, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
