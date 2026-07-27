#!/usr/bin/env python3
"""Fail-closed independent audit for the CAL-EXT-002 design lock."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "reports/v5_cal_ext_002_design_lock_20260716.json"
OUT = ROOT / "reports/v5_cal_ext_002_design_lock_audit_20260716.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def processes() -> list[dict]:
    script = "Get-CimInstance Win32_Process | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    cp = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, encoding="utf-8")
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr)
    raw = cp.stdout.strip()
    if not raw:
        return []
    data = json.loads(raw)
    return data if isinstance(data, list) else [data]


def main() -> int:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    c: dict[str, bool] = {}
    c["schema"] = lock.get("schema_version") == "v5.external_calibration.design_lock.v1"
    c["identity"] = lock.get("measurement_id") == "CAL-EXT-002_H11_CONTROL_GREEDY_QUICK5K"
    c["locked_pending_audit"] = lock.get("state") == "LOCKED_PENDING_INDEPENDENT_AUDIT"
    a = lock["authority"]
    refs = {
        "prereg": (ROOT / "reports/v5_cal_ext_002_preregistration_20260716.json", a["preregistration_sha256"]),
        "prereg_audit": (ROOT / "reports/v5_cal_ext_002_preregistration_audit_20260716.json", a["preregistration_audit_sha256"]),
        "h12_judgment": (ROOT / "reports/v5_hybrid_h12_judgment_20260716.json", a["h12_terminal_judgment_sha256"]),
        "h12_audit": (ROOT / "reports/v5_hybrid_h12_terminal_audit_20260716.json", a["h12_terminal_audit_sha256"]),
    }
    for key, (path, expected) in refs.items():
        c[f"authority_{key}"] = path.is_file() and sha(path) == expected
    prereg_audit = json.loads(refs["prereg_audit"][0].read_text(encoding="utf-8"))
    c["prereg_audit_pass"] = prereg_audit.get("overall") == "PASS" and prereg_audit.get("checks_passed") == prereg_audit.get("checks_total") == 44
    cp = lock["checkpoint"]
    source, frozen = Path(cp["source_path"]), Path(cp["frozen_path"])
    c["source_hash"] = source.is_file() and sha(source) == cp["source_and_frozen_sha256"]
    c["frozen_hash"] = frozen.is_file() and sha(frozen) == cp["source_and_frozen_sha256"]
    c["checkpoint_size"] = source.is_file() and frozen.is_file() and source.stat().st_size == frozen.stat().st_size == cp["bytes"]
    run = ROOT / "models/alpha_holdem_v5_hybrid/v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715"
    t = lock["terminal_evidence"]
    c["manifest_hash"] = sha(run / "run_manifest.json") == t["run_manifest_sha256"]
    c["endpoint_hash"] = sha(run / "h11_control_endpoint_status.json") == t["endpoint_status_sha256"]
    c["protocol_hash"] = sha(run / "h11_control_protocol_status.json") == t["protocol_status_sha256"]
    pf = lock["preflight"]
    preflight_refs = {
        "static_plan": ROOT / "reports/v5_cal_ext_002_launch_plan_20260716.json",
        "watch_plan": ROOT / "reports/v5_cal_ext_002_watch_plan_20260716.json",
        "pipeline_preflight": ROOT / "reports/v5_cal_ext_002_pipeline_preflight_20260716.json",
        "watch_preflight_status": ROOT / "reports/v5_cal_ext_002_preflight_status_20260716.json",
        "frozen_checkpoint_preflight": ROOT / "models/bench_v55_cal_ext_002_h11_control_greedy_quick5k_20260716_preflight.json",
    }
    for key, path in preflight_refs.items():
        c[f"preflight_{key}_hash"] = path.is_file() and sha(path) == pf[f"{key}_sha256"]
    pipeline = json.loads(preflight_refs["pipeline_preflight"].read_text(encoding="utf-8"))
    watch_status = json.loads(preflight_refs["watch_preflight_status"].read_text(encoding="utf-8"))
    c["pipeline_pass"] = pipeline.get("overall") == "PASS" and len(pipeline.get("inference_cases", [])) == 6
    c["watch_preflight_pass"] = watch_status.get("state") == "PREFLIGHT_ONLY_PASS"
    l = lock["launch"]
    c["greedy_direct"] = l.get("policy_mode") == "greedy" and l.get("evidence_policy_label") == "greedy-direct" and l.get("launch_path") == "direct"
    c["fixed_5000"] = l.get("sessions") == 4 and l.get("hands_per_session") == 1250 and l.get("planned_hands") == 5000
    c["cpu_below_normal"] = l.get("device") == "cpu" and l.get("child_priority") == "BelowNormal_FAIL_CLOSED"
    c["no_adaptation"] = l.get("adaptive_extension") is False and l.get("checkpoint_change") is False
    c["selector_replay"] = l.get("selector_replay") == "REQUIRED_CPU"
    tag = l["tag"]
    part_outputs = list((ROOT / "models").glob(f"bench_v55_{tag}_part*"))
    c["no_output_collision"] = not part_outputs
    for rel, expected in lock["tool_lock"].items():
        path = ROOT / rel
        c[f"tool_{Path(rel).name}"] = path.is_file() and sha(path) == expected
    sentinel = json.loads((ROOT / "reports/v5_active_window.json").read_text(encoding="utf-8"))
    c["terminal_sentinel"] = sentinel.get("active") is False and sentinel.get("terminal") is True and sentinel.get("state") == "H12_TERMINAL_INCONCLUSIVE"
    ps = processes()
    commands = [str(x.get("CommandLine") or "").lower() for x in ps]
    c["no_trainer"] = not any("train_v5" in x for x in commands)
    c["no_mirror"] = not any("mirror_eval" in x or "v5_hybrid_mirror" in x for x in commands)
    c["no_slumbot"] = not any("play_slumbot.py" in x or "v5_slumbot_benchmark_watch.py" in x for x in commands)
    path1 = [x for x in ps if int(x.get("ProcessId") or -1) == 37656]
    c["path1_coordinator"] = len(path1) == 1
    rc = lock["result_contract"]
    c["result_contract"] = rc.get("exact_hands") == 5000 and rc.get("quick5k_promotion_fail_set_exact") == ["promotion_hands"] and rc.get("any_other_failure") == "FAIL_CLOSED"
    c["no_strength_claim"] = rc.get("official_calibration_only") is True and rc.get("strength_claim") == "FORBIDDEN"
    c["route_review_009_next"] = rc.get("next_transition") == "POST_CAL_ROUTE_REVIEW_009_REGISTRATION"
    failed = sorted(k for k, ok in c.items() if not ok)
    out = {
        "schema_version": "v5.external_calibration.design_lock_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "design_lock_sha256": sha(LOCK),
        "checks": c,
        "checks_passed": sum(c.values()),
        "checks_total": len(c),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "launch_authority": "EXACT_LOCKED_DIRECT_WATCH_LAUNCH" if not failed else "NONE",
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
