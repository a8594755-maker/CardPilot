#!/usr/bin/env python3
"""Fresh correction for the VR002C1 terminal auditor's self-ancestor census defect."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import psutil


REPO = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "8d3cb2f1a897d1b9228b14ee7043db49"
IDENTITY = TOKEN + "6c7a319c4af7318aae4e0103ac534a4d"
PARENT_AUDIT = REPO / (
    "reports/v5_vr002c1_stagea_process_exit_audit_"
    f"{TOKEN}_20260723.json"
)
PARENT_AUDIT_SHA256 = "539e8428a1ee077404d11fe47851549ac1431b28afe1348284be8e4d83284fc5"
REPORT = REPO / (
    "reports/v5_vr002c1_stagea_process_exit_cause_unproven_"
    f"{TOKEN}_20260723.json"
)
REPORT_SHA256 = "2bf92991406a39159c08d0b2ebb785e54b0951058a9a053d25647c9acad5add2"
RUN_DIR = REPO / (
    "models/alpha_holdem_v5_hybrid/"
    f"v5_vr002c1_{TOKEN}_20260723/vrpo_stagea"
)
RAW_HASHES = {
    "latest.pt": "e6aa5c972ab4b0864ba5159d1a740edd8e8f82a71f4f90639597ef2cc427cadc",
    "opponent_assignment_provenance.jsonl":
        "30a905479822c5ae1025fe23f7d0fbad3095a4f3c161fa9d3b8dcb6446201c17",
    "vr002_metrics.jsonl":
        "549c807b2b63f4b25b91ebd6908f9c31f8ccdd286ef95e7ea2468b4c540f6171",
    "vr002_trace_manifest.jsonl":
        "736682cf9337878edc5d329d12392a4cbdd7167dc696fcfc4faff2464a3d343b",
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def own_ancestry() -> set[int]:
    excluded: set[int] = set()
    pid = os.getpid()
    while pid and pid not in excluded:
        excluded.add(pid)
        try:
            pid = psutil.Process(pid).ppid()
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            break
    return excluded


def independent_target_census() -> list[dict[str, object]]:
    excluded = own_ancestry()
    matches: list[dict[str, object]] = []
    for proc in psutil.process_iter(["pid", "ppid", "name", "cmdline"]):
        try:
            pid = int(proc.info["pid"])
            if pid in excluded:
                continue
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if (
                pid in (40408, 6748)
                or int(proc.info.get("ppid") or -1) == 6748
                or TOKEN in cmdline
                or "parent_pid=6748" in cmdline
            ):
                matches.append(
                    {
                        "pid": pid,
                        "ppid": proc.info.get("ppid"),
                        "name": proc.info.get("name"),
                    }
                )
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
    return matches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    if out.exists():
        raise RuntimeError(f"refusing to overwrite corrected audit: {out}")

    parent = json.loads(PARENT_AUDIT.read_text(encoding="utf-8"))
    parent_checks = parent.get("independent_recomputation") or {}
    matches = independent_target_census()
    checks = {
        "parent_failed_audit_identity_exact":
            sha256_path(PARENT_AUDIT) == PARENT_AUDIT_SHA256,
        "parent_failed_only_self_ancestor_sensitive_census":
            parent.get("passed") == 28
            and parent.get("total") == 29
            and parent.get("failed_checks") == ["attempt_processes_quiescent"]
            and parent_checks.get("attempt_processes_quiescent") is False
            and all(
                value is True
                for name, value in parent_checks.items()
                if name != "attempt_processes_quiescent"
            ),
        "terminal_report_identity_exact": sha256_path(REPORT) == REPORT_SHA256,
        "frozen_raw_hashes_still_exact": all(
            sha256_path(RUN_DIR / name) == expected
            for name, expected in RAW_HASHES.items()
        ),
        "corrected_census_excludes_only_own_ancestry": len(matches) == 0,
        "registered_manifest_still_absent": not (RUN_DIR / "run_manifest.json").exists(),
    }
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": "v5.vr002c1.stagea_invalid_endpoint_audit_c1.v1",
        "audited_at": "2026-07-23T21:02:00-04:00",
        "status": (
            "VR002C1_STAGEA_INVALID_ENDPOINT_C1_INDEPENDENT_AUDIT_PASS"
            if not failed
            else "VR002C1_STAGEA_INVALID_ENDPOINT_C1_INDEPENDENT_AUDIT_FAIL"
        ),
        "identity_sha256": IDENTITY,
        "fresh_correction": {
            "parent_audit_sha256": PARENT_AUDIT_SHA256,
            "parent_terminal_defect":
                "process census matched the auditor's own PowerShell ancestor because its command line contained the frozen token",
            "sole_correction":
                "exclude the current auditor's process ancestry before applying the identical PID, parent-PID and token match predicates",
            "scientific_design_changed": False,
        },
        "corrected_process_census": {
            "excluded_own_ancestry": True,
            "target_match_count": len(matches),
            "matches": matches,
        },
        "independent_recomputation": checks,
        "judgment": {
            "taxonomy":
                "INVALID_BEHAVIOR_WINDOW_ENDPOINT_WITH_UNPROVEN_PROCESS_EXIT_CAUSE",
            "registered_endpoint_reached": False,
            "process_exit_cause": "UNPROVEN",
            "mechanism_result": "UNJUDGED",
            "external_effect": "UNJUDGED",
            "quick5k_trigger": False,
            "checkpoint_eligible": False,
            "exact_terminal_status":
                "VR002C1_STAGEA_PROCESS_EXIT_CAUSE_UNPROVEN_INVALID_ENDPOINT_FREEZE_NO_QUICK5K_NO_RERUN",
        },
        "passed": sum(checks.values()),
        "total": len(checks),
        "failed_checks": failed,
    }
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(
        {
            "status": result["status"],
            "passed": result["passed"],
            "total": result["total"],
            "failed_checks": failed,
            "target_match_count": len(matches),
        },
        sort_keys=True,
    ))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
