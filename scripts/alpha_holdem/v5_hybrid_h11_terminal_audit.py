#!/usr/bin/env python3
"""Independent fail-closed terminal audit for the H11 protocol-abort path."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def metric_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def effective_hps(rows: list[dict]) -> float:
    sample = rows[1:61]
    if len(sample) != 60:
        raise ValueError("first60 requires exact metric rows 2..61")
    start = datetime.fromisoformat(sample[0]["recorded_at"])
    end = datetime.fromisoformat(sample[-1]["recorded_at"])
    elapsed = (end - start).total_seconds()
    if elapsed <= 0:
        raise ValueError("non-positive first60 elapsed time")
    return (int(sample[-1]["hands"]) - int(sample[0]["hands"])) / elapsed


def close(left: float | None, right: float | None, tolerance: float = 1e-9) -> bool:
    return left is not None and right is not None and abs(float(left) - float(right)) <= tolerance


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--judgment", type=Path, required=True)
    parser.add_argument("--sentinel", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    lock_path = args.design_lock.resolve()
    judgment_path = args.judgment.resolve()
    sentinel_path = args.sentinel.resolve()
    lock = load(lock_path)
    judgment = load(judgment_path)
    sentinel = load(sentinel_path)
    control_dir = Path(lock["arms"]["control"]["run_dir"])
    treatment_dir = Path(lock["arms"]["treatment"]["run_dir"])
    control_protocol_path = control_dir / "h11_control_protocol_status.json"
    control_endpoint_path = control_dir / "h11_control_endpoint_status.json"
    treatment_protocol_path = treatment_dir / "h11_treatment_protocol_status.json"
    treatment_endpoint_path = treatment_dir / "h11_treatment_endpoint_status.json"
    completion_path = treatment_dir / "h11_completion_watch_status.json"
    control_manifest_path = control_dir / "run_manifest.json"
    treatment_manifest_path = treatment_dir / "run_manifest.json"
    control_metrics_path = control_dir / "h1_training_metrics.jsonl"
    treatment_metrics_path = treatment_dir / "h1_training_metrics.jsonl"

    control_protocol = load(control_protocol_path)
    control_endpoint = load(control_endpoint_path)
    treatment_protocol = load(treatment_protocol_path)
    treatment_endpoint = load(treatment_endpoint_path)
    completion = load(completion_path)
    control_manifest = load(control_manifest_path)
    treatment_manifest = load(treatment_manifest_path)
    control_rows = metric_rows(control_metrics_path)
    treatment_rows = metric_rows(treatment_metrics_path)
    control_hps = effective_hps(control_rows)
    treatment_hps = effective_hps(treatment_rows)
    ratio = treatment_hps / control_hps
    threshold = float(lock["gates"]["first60_hps_ratio_min"])
    mirror_dir = Path(lock["measurement"]["mirror_dir"])
    mirror_outputs = [mirror_dir / name for name in (
        "control_pairs.jsonl", "treatment_pairs.jsonl", "anchor_pairs.jsonl", "audit.json", "judgment.json"
    )]

    checks: dict[str, bool] = {}

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)

    check("design_lock_sha", sha(lock_path) == args.expected_lock_sha256.lower())
    check("design_identity", lock.get("design_id") == "H11" and lock.get("status") == "LOCKED")
    check("judgment_identity", judgment.get("schema_version") == "v5.hybrid.h11.judgment.v1" and judgment.get("design_id") == "H11")
    check("judgment_terminal_fail", judgment.get("overall") == "FAIL" and judgment.get("classification") == "H11_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT")
    check("judgment_lock_bound", judgment.get("design_lock_sha256") == sha(lock_path))
    check("judgment_no_official_hands", judgment.get("official_hands") == 0 and judgment.get("strength_claim") == "FORBIDDEN")
    check("route_review_required", judgment.get("route_review_required") is True)
    check("control_manifest_identity", control_manifest.get("run_id") == lock["arms"]["control"]["run_id"] and control_manifest.get("status") == "finished")
    check("control_endpoint_frozen", control_endpoint.get("overall") == "PASS" and control_endpoint.get("state") == "ARM_ENDPOINT_FROZEN")
    check("control_checkpoint_exact", control_endpoint.get("checkpoint_sha256") == sha(Path(control_endpoint["checkpoint_path"])))
    check("control_protocol_pass", control_protocol.get("overall") == "PASS" and control_protocol.get("state") == "ARM_FINISHED_GUARDS_PASS")
    check("control_first60_frozen", control_protocol.get("first60", {}).get("status") == "PASS_CONTROL_BASELINE_FROZEN")
    check("control_first60_recomputed", close(control_hps, control_protocol.get("first60", {}).get("effective_hps")))
    check("treatment_manifest_identity", treatment_manifest.get("run_id") == lock["arms"]["treatment"]["run_id"])
    check("treatment_source_and_variable", treatment_manifest.get("config", {}).get("h11_window_arm") == "treatment" and treatment_manifest.get("config", {}).get("h11_catchup_loss") == "smooth_l1" and treatment_manifest.get("config", {}).get("h11_catchup_smooth_l1_beta") == 1.0)
    check("treatment_partial_exact_rows", len(treatment_rows) == 61)
    check("treatment_stopped_before_target", int(treatment_manifest.get("total_hands", 0)) < int(treatment_manifest.get("config", {}).get("total_hands", 0)))
    check("treatment_protocol_fail", treatment_protocol.get("overall") == "FAIL" and treatment_protocol.get("state") == "H11_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT")
    check("treatment_first60_fail", treatment_protocol.get("first60", {}).get("status") == "FAIL")
    check("treatment_first60_recomputed", close(treatment_hps, treatment_protocol.get("first60", {}).get("treatment_effective_hps")))
    check("ratio_recomputed", close(ratio, treatment_protocol.get("first60", {}).get("ratio")))
    check("threshold_exact", close(threshold, treatment_protocol.get("first60", {}).get("minimum")) and ratio < threshold)
    check("watcher_terminated_treatment", treatment_protocol.get("stop_action") == "TERMINATED")
    check("no_resource_isolation_violation", treatment_protocol.get("resource_isolation_violations") == [])
    check("treatment_endpoint_not_frozen", treatment_endpoint.get("overall") == "FAIL" and treatment_endpoint.get("state") != "ARM_ENDPOINT_FROZEN")
    check("completion_terminal_handoff", completion.get("overall") == "PASS" and completion.get("state") == "TERMINAL_RESULT_READY_HANDOFF_UPDATE_REQUIRED" and completion.get("verdict") == "FAIL")
    check("sentinel_terminal", sentinel.get("terminal") is True and sentinel.get("state") == "H11_TERMINAL_FAIL" and sentinel.get("verdict") == "FAIL")
    check("sentinel_judgment_bound", sentinel.get("judgment_sha256") == sha(judgment_path))
    check("mirror_forbidden_and_absent", all(not path.exists() for path in mirror_outputs))
    check("official_hands_zero_everywhere", all(value == 0 for value in (judgment.get("official_hands"), control_protocol.get("official_hands"), sentinel.get("official_hands_authorized"))))

    failed = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema_version": "v5.hybrid.h11.terminal_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS_COMPLETE_H11_TERMINAL_FAIL_PROTOCOL_ABORT" if not failed else "FAIL_CLOSED",
        "classification": judgment.get("classification"),
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "checks": checks,
        "failed": failed,
        "evidence": {
            "design_lock_sha256": sha(lock_path),
            "judgment_sha256": sha(judgment_path),
            "sentinel_sha256": sha(sentinel_path),
            "control_protocol_sha256": sha(control_protocol_path),
            "control_endpoint_sha256": sha(control_endpoint_path),
            "treatment_protocol_sha256": sha(treatment_protocol_path),
            "treatment_endpoint_sha256": sha(treatment_endpoint_path),
            "completion_sha256": sha(completion_path),
            "control_manifest_sha256": sha(control_manifest_path),
            "treatment_manifest_sha256": sha(treatment_manifest_path),
            "control_metrics_sha256": sha(control_metrics_path),
            "treatment_metrics_sha256": sha(treatment_metrics_path),
        },
        "first60": {
            "control_effective_hps": control_hps,
            "treatment_effective_hps": treatment_hps,
            "ratio": ratio,
            "minimum": threshold,
            "rows_used": [2, 61],
        },
        "method_verdict": "FAIL_PROTOCOL_NO_METHOD_EFFECT_JUDGMENT",
        "model_candidacy": "NONE_TREATMENT_ENDPOINT_NOT_FROZEN",
        "official_hands": 0,
        "strength_claim": "FORBIDDEN",
        "route_review_required": True,
    }
    args.out.resolve().write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
