#!/usr/bin/env python3
"""Independent terminal audit of the invalid VR002C1 Stage-A process exit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import psutil
import torch


REPO = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "8d3cb2f1a897d1b9228b14ee7043db49"
IDENTITY = TOKEN + "6c7a319c4af7318aae4e0103ac534a4d"
SOURCE_HANDS = 576_021_901
SOURCE_ITERATION = 35_051
MIN_NEW_HANDS = 5_000_000
EXPECTED_FILES = {
    "latest.pt": (359_350_313, "e6aa5c972ab4b0864ba5159d1a740edd8e8f82a71f4f90639597ef2cc427cadc"),
    "opponent_assignment_provenance.jsonl": (
        127_739,
        "30a905479822c5ae1025fe23f7d0fbad3095a4f3c161fa9d3b8dcb6446201c17",
    ),
    "vr002_metrics.jsonl": (
        374_852,
        "549c807b2b63f4b25b91ebd6908f9c31f8ccdd286ef95e7ea2468b4c540f6171",
    ),
    "vr002_trace_manifest.jsonl": (
        39_744_647,
        "736682cf9337878edc5d329d12392a4cbdd7167dc696fcfc4faff2464a3d343b",
    ),
}
AUTHORITIES = {
    "reports/v5_vr002c1_cpu_default_generator_correction_preregistration_"
    f"{TOKEN}_20260723.json":
        "a0a9ff27017257a27cad92bacf2a69f64a1442b218495a3d6d6a76ea7244948e",
    "reports/v5_vr002c1_cpu_default_generator_correction_preregistration_audit_"
    f"{TOKEN}_20260723.json":
        "cfa2a0836deb6345fea46680077278ae7db98a36e6b76d762b7493858b73bf19",
    f"scripts/alpha_holdem/v5_vr002c1_qboost_core_{TOKEN}.py":
        "7d16d0545260e83e016e99065fd3f714d2bf2d8dc4c435944ad82ce5eed2f34d",
    f"scripts/alpha_holdem/v5_vr002c1_train_{TOKEN}.py":
        "e190b9992b3050c70d793cf2b3de7abcf74c8dab75f3fe7013705fadbce3de5d",
    f"scripts/alpha_holdem/v5_vr002c1_launcher_{TOKEN}.ps1":
        "542e2d207f7a2d330d5c9ba41d2497c77d84d15dc8054ea5851146d41501ffc9",
    f"scripts/alpha_holdem/v5_vr002c1_implementation_audit_{TOKEN}.py":
        "cf8168fe5b255e254ca9ed7167570cdb336f71ce6a74140e493f42b58d8b388a",
    f"scripts/alpha_holdem/v5_vr002c1_window_audit_{TOKEN}.py":
        "57572d4bb7dd7a9d2fa02470f7f014f906dbba7b5cb03f16b53ef31c88c25480",
    f"reports/v5_vr002c1_implementation_audit_{TOKEN}_20260723.json":
        "7f96daffbf06fa339785c491bd36bf14d981b4769e236b3146a20ef4a7a21069",
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(row: dict[str, Any]) -> str:
    payload = dict(row)
    payload.pop("record_sha256", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def load_jsonl_exact(path: Path) -> tuple[list[dict[str, Any]], bool]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    lines = text.splitlines()
    rows = [json.loads(line) for line in lines]
    exact_layout = raw.endswith(b"\n") and bool(lines) and all(line.strip() for line in lines)
    return rows, exact_layout


def finite_tree(value: Any) -> bool:
    if torch.is_tensor(value):
        return bool(torch.isfinite(value).all())
    if isinstance(value, dict):
        return all(finite_tree(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return all(finite_tree(child) for child in value)
    return not isinstance(value, float) or math.isfinite(value)


def valid_chain(rows: list[dict[str, Any]]) -> bool:
    previous = "0" * 64
    for row in rows:
        if row.get("previous_record_sha256") != previous:
            return False
        if row.get("record_sha256") != canonical_hash(row):
            return False
        previous = row["record_sha256"]
    return True


def process_is_quiescent() -> bool:
    current = os.getpid()
    for proc in psutil.process_iter(["pid", "ppid", "cmdline"]):
        try:
            if proc.info["pid"] == current:
                continue
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if (
                proc.info["pid"] in (40408, 6748)
                or proc.info.get("ppid") == 6748
                or TOKEN in cmdline
                or "parent_pid=6748" in cmdline
            ):
                return False
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run_dir = Path(args.run_dir).resolve()
    report_path = Path(args.report).resolve()
    out = Path(args.out).resolve()
    if out.exists():
        raise RuntimeError(f"refusing to overwrite audit output: {out}")

    checks: dict[str, bool] = {}
    checks["all_frozen_authority_hashes_exact"] = all(
        (REPO / relative).is_file()
        and sha256_path(REPO / relative) == expected
        for relative, expected in AUTHORITIES.items()
    )

    direct_entries = list(run_dir.iterdir())
    checks["exact_four_file_inventory"] = (
        {item.name for item in direct_entries} == set(EXPECTED_FILES)
        and all(item.is_file() for item in direct_entries)
    )
    checks["no_nested_directories"] = not any(item.is_dir() for item in run_dir.rglob("*"))
    checks["no_reparse_points"] = not any(item.is_symlink() for item in run_dir.rglob("*"))
    checks["no_temporary_files"] = not any(
        item.name.endswith(".tmp") or ".tmp." in item.name for item in run_dir.rglob("*")
    )
    checks["run_manifest_absent"] = not (run_dir / "run_manifest.json").exists()
    checks["exact_file_bytes_and_hashes"] = all(
        (run_dir / name).stat().st_size == expected_bytes
        and sha256_path(run_dir / name) == expected_hash
        for name, (expected_bytes, expected_hash) in EXPECTED_FILES.items()
    )
    checks["attempt_processes_quiescent"] = process_is_quiescent()

    metrics, metrics_layout = load_jsonl_exact(run_dir / "vr002_metrics.jsonl")
    traces, traces_layout = load_jsonl_exact(run_dir / "vr002_trace_manifest.jsonl")
    provenance, provenance_layout = load_jsonl_exact(
        run_dir / "opponent_assignment_provenance.jsonl"
    )
    checks["jsonl_exact_layout"] = metrics_layout and traces_layout and provenance_layout
    checks["jsonl_rows_finite"] = finite_tree(metrics) and finite_tree(traces) and finite_tree(provenance)
    checks["exact_row_counts_161_161_162"] = (
        len(metrics) == 161 and len(traces) == 161 and len(provenance) == 162
    )
    checks["metric_record_hashes"] = all(
        row.get("record_sha256") == canonical_hash(row) for row in metrics
    )
    checks["trace_hash_chain"] = valid_chain(traces)
    checks["provenance_hash_chain"] = valid_chain(provenance)

    expected_iterations = list(range(SOURCE_ITERATION + 1, SOURCE_ITERATION + 1 + len(metrics)))
    checks["metric_trace_iterations_contiguous"] = (
        [int(row.get("iteration", -1)) for row in metrics] == expected_iterations
        and [int(row.get("iteration", -1)) for row in traces] == expected_iterations
    )
    checks["provenance_sequence_exact"] = all(
        int(row.get("applies_to_iteration", -1)) == SOURCE_ITERATION + index + 1
        and int(row.get("assignment_version", -1)) == index + 1
        and int(row.get("generation", -1)) == SOURCE_ITERATION + index
        for index, row in enumerate(provenance)
    )
    checks["provenance_total_sources_exact"] = all(
        int(row.get("total_hands", -1))
        == (SOURCE_HANDS if index == 0 else int(metrics[index - 1]["total_hands"]))
        for index, row in enumerate(provenance)
    )
    checks["final_provenance_is_unused_next_assignment"] = (
        int(provenance[-1]["applies_to_iteration"]) == int(metrics[-1]["iteration"]) + 1
        and int(provenance[-1]["total_hands"]) == int(metrics[-1]["total_hands"])
    )

    checks["metric_trace_pairing_exact"] = all(
        int(metric["rollout_complete_hands"]) == int(trace["complete_hands"])
        and int(metric["rollout_admitted_hands"]) == int(trace["admitted_hands"])
        and int(metric["rollout_mixed_or_stale_hands"]) == int(trace["mixed_or_stale_hands"])
        and int(metric["rollout_stale_assignment_hands"]) == int(trace["stale_assignment_hands"])
        and int(metric["assignment_version"]) == int(trace["assignment_version_collected"])
        and metric["trace_hand_chain_sha256"] == trace["cumulative_hand_sha256"]
        and metric["exp003_metrics"] == trace["exp003_metrics"]
        and metric["identity"] == IDENTITY
        and trace["identity"] == IDENTITY
        for metric, trace in zip(metrics, traces, strict=True)
    )
    checks["cumulative_counts_exact"] = (
        sum(int(row["complete_hands"]) for row in traces) == int(metrics[-1]["complete_hands"])
        and sum(int(row["admitted_hands"]) for row in traces) == int(metrics[-1]["admitted_hands"])
        and sum(int(row["mixed_or_stale_hands"]) for row in traces)
        == int(metrics[-1]["mixed_or_stale_hands"])
        and sum(int(row["stale_assignment_hands"]) for row in traces)
        == int(metrics[-1]["stale_assignment_hands"])
    )
    checks["per_metric_hand_identities_exact"] = all(
        int(row["new_hands"]) == int(row["total_hands"]) - SOURCE_HANDS
        and int(row["complete_hands"]) == int(row["new_hands"])
        and int(row["admitted_hands"]) + int(row["mixed_or_stale_hands"])
        == int(row["complete_hands"])
        for row in metrics
    )
    checks["invalid_endpoint_below_first_crossing"] = (
        int(metrics[-1]["total_hands"]) == 579_086_001
        and int(metrics[-1]["new_hands"]) == 3_064_100
        and int(metrics[-1]["new_hands"]) < MIN_NEW_HANDS
        and all(int(row["new_hands"]) < MIN_NEW_HANDS for row in metrics)
    )

    checkpoint = torch.load(run_dir / "latest.pt", map_location="cpu", weights_only=False)
    contract = checkpoint.get("vr002") or {}
    checks["checkpoint_matches_last_durable_metric"] = (
        int(checkpoint.get("iteration", -1)) == int(metrics[-1]["iteration"])
        and int(checkpoint.get("total_hands", -1)) == int(metrics[-1]["total_hands"])
        and int(contract.get("complete_hands", -1)) == int(metrics[-1]["complete_hands"])
        and int(contract.get("admitted_hands", -1)) == int(metrics[-1]["admitted_hands"])
        and int(contract.get("mixed_or_stale_hands", -1))
        == int(metrics[-1]["mixed_or_stale_hands"])
        and int(contract.get("stale_assignment_hands", -1))
        == int(metrics[-1]["stale_assignment_hands"])
    )
    checks["checkpoint_identity_and_config_exact"] = (
        contract.get("identity") == IDENTITY
        and contract.get("identity_sha256") == IDENTITY
        and contract.get("token") == TOKEN
        and contract.get("preregistration_sha256") == AUTHORITIES[
            "reports/v5_vr002c1_cpu_default_generator_correction_preregistration_"
            f"{TOKEN}_20260723.json"
        ]
        and contract.get("core_sha256") == AUTHORITIES[
            f"scripts/alpha_holdem/v5_vr002c1_qboost_core_{TOKEN}.py"
        ]
        and contract.get("trainer_sha256") == AUTHORITIES[
            f"scripts/alpha_holdem/v5_vr002c1_train_{TOKEN}.py"
        ]
        and int(contract.get("central_serialized_floats", -1)) == 895
        and int(contract.get("legal_sidecar_floats", -1)) == 9
        and float(contract.get("gamma", -1)) == 0.999
        and float(contract.get("lambda", -1)) == 0.95
        and int(contract.get("q_epochs", -1)) == 4
        and int(contract.get("q_physical_rows_per_minibatch", -1)) == 512
        and contract.get("actor_before_critic") is True
        and contract.get("historical_replay") is False
    )
    checks["checkpoint_required_structures_present"] = all(
        key in checkpoint
        for key in (
            "model",
            "optimizer",
            "vr002_q_model",
            "vr002_q_optimizer",
            "vr002_q_minibatch_generator_state",
        )
    )
    checks["checkpoint_tensors_finite"] = all(
        finite_tree(checkpoint[key])
        for key in (
            "model",
            "optimizer",
            "vr002_q_model",
            "vr002_q_optimizer",
            "vr002_q_minibatch_generator_state",
        )
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    checks["terminal_report_identity_and_status_exact"] = (
        report.get("identity_sha256") == IDENTITY
        and report.get("status")
        == "VR002C1_STAGEA_PROCESS_EXIT_CAUSE_UNPROVEN_INVALID_ENDPOINT_FREEZE_NO_QUICK5K_NO_RERUN"
        and report.get("invocation", {}).get("launcher_exit_code_preserved") is False
        and report.get("invocation", {}).get("launcher_stderr_preserved") is False
        and report.get("invocation", {}).get("resource_guard_trigger_proven") is False
        and report.get("invocation", {}).get("process_exit_cause") == "UNPROVEN"
    )
    checks["terminal_report_governance_exact"] = (
        report.get("judgment", {}).get("registered_valid_endpoint") is False
        and report.get("judgment", {}).get("window_auditor_eligible") is False
        and report.get("judgment", {}).get("mechanism_result") == "UNJUDGED"
        and report.get("judgment", {}).get("external_effect") == "UNJUDGED"
        and report.get("judgment", {}).get("quick5k_trigger") is False
        and report.get("judgment", {}).get("checkpoint_status")
        == "PERMANENTLY_PROVISIONAL_AND_INELIGIBLE"
        and report.get("judgment", {}).get(
            "never_repair_mutate_resume_rerun_extend_select_or_screen"
        ) is True
    )
    checks["terminal_report_raw_hashes_exact"] = all(
        report["frozen_output"]["files"][name]["bytes"] == expected_bytes
        and report["frozen_output"]["files"][name]["sha256"] == expected_hash
        for name, (expected_bytes, expected_hash) in EXPECTED_FILES.items()
    )

    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": "v5.vr002c1.stagea_invalid_endpoint_audit.v1",
        "audited_at": "2026-07-23T20:55:00-04:00",
        "status": (
            "VR002C1_STAGEA_INVALID_ENDPOINT_INDEPENDENT_AUDIT_PASS"
            if not failed
            else "VR002C1_STAGEA_INVALID_ENDPOINT_INDEPENDENT_AUDIT_FAIL"
        ),
        "identity_sha256": IDENTITY,
        "terminal_report_sha256": sha256_path(report_path),
        "frozen_output_sha256": {
            name: sha256_path(run_dir / name) for name in sorted(EXPECTED_FILES)
        },
        "independent_recomputation": checks,
        "judgment": {
            "taxonomy": "INVALID_BEHAVIOR_WINDOW_ENDPOINT_WITH_UNPROVEN_PROCESS_EXIT_CAUSE",
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
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "passed": result["passed"],
                      "total": result["total"], "failed_checks": failed}, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
