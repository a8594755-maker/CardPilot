#!/usr/bin/env python3
"""Independent pre-registration audit for the H2 implementation candidate."""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[1]
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v5_h1_calibration import SOURCE_SHA, unpack_obs
from v5_mirror_eval import init_model, sha256_file, utc_now


CONTROL_DIR = REPO_ROOT / "tmp" / "h2_gpu_control_stability"
TREATMENT_DIR = REPO_ROOT / "tmp" / "h2_gpu_treatment_stability_v3"
PANEL_DIR = REPO_ROOT / "reports" / "h2_var_001_20260713"
SOURCE = REPO_ROOT / "models" / "alpha_holdem_v5_from_zero" / "v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709" / "v5_exp005_cutover_gate31400_checkpoint.pt"
METRIC_RE = re.compile(r"^\[\s*(\d+)\].*?hands=([\d,]+).*?ent=([-+\d.]+).*?h/s=(\d+)")


def metric_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = METRIC_RE.search(line)
        if match:
            rows.append({
                "iteration": int(match.group(1)),
                "hands": int(match.group(2).replace(",", "")),
                "entropy": float(match.group(3)),
                "hps": float(match.group(4)),
            })
    return rows


def effective_hps(rows: list[dict], skip: int = 1) -> float:
    selected = rows[skip:]
    if not selected:
        raise ValueError("no metric rows after warmup exclusion")
    durations = []
    hand_counts = []
    previous_hands = rows[skip - 1]["hands"] if skip else 0
    for row in selected:
        count = row["hands"] - previous_hands
        if count <= 0 or row["hps"] <= 0:
            raise ValueError("invalid metric row")
        hand_counts.append(count)
        durations.append(count / row["hps"])
        previous_hands = row["hands"]
    return float(sum(hand_counts) / sum(durations))


def scrub_config(config: dict) -> dict:
    ignored = {"run_id", "run_dir", "out", "opponent_assignment_provenance_file", "showdown_ev_value_targets"}
    return {key: value for key, value in config.items() if key not in ignored}


def actor_logits_identity() -> dict:
    if sha256_file(SOURCE) != SOURCE_SHA:
        raise ValueError("source checkpoint SHA mismatch")
    checkpoint = torch.load(SOURCE, map_location="cpu", weights_only=False)
    first = init_model(checkpoint, "cpu")
    second = init_model(checkpoint, "cpu")
    rows = []
    decisions = PANEL_DIR.parent / "h1_cal_001_attempt2_20260712" / "decisions.jsonl"
    with decisions.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
            if len(rows) == 128:
                break
    decoded = [unpack_obs(row["packed_obs_zlib_b64"], row["obs_sha256"]) for row in rows]
    cards = torch.tensor(np.stack([item[0] for item in decoded]))
    actions = torch.tensor(np.stack([item[1] for item in decoded]))
    extras = torch.tensor(np.stack([item[2] for item in decoded]))
    masks = torch.tensor(np.stack([item[3] for item in decoded]))
    with torch.no_grad():
        logits_first = first(cards, actions, extras, masks)[0]
        logits_second = second(cards, actions, extras, masks)[0]
    delta = float(torch.max(torch.abs(logits_first - logits_second)).item())
    return {"rows": len(rows), "max_abs_actor_logits_delta": delta, "pass": delta == 0.0}


def build() -> dict:
    commands = [
        [sys.executable, "-m", "py_compile", "scripts/alpha_holdem/v5_hybrid_h2_targets.py", "scripts/alpha_holdem/train_mp3_hybrid_h1.py", "scripts/alpha_holdem/train_v5.py", "scripts/alpha_holdem/v5_h2_variance_panel.py"],
        [sys.executable, "scripts/alpha_holdem/test_v5_hybrid_h2_targets.py", "-q"],
    ]
    command_results = []
    for command in commands:
        completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True)
        command_results.append({"command": command, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr})
    control_manifest = json.loads((CONTROL_DIR / "run_manifest.json").read_text(encoding="utf-8"))
    treatment_manifest = json.loads((TREATMENT_DIR / "run_manifest.json").read_text(encoding="utf-8"))
    control_rows = metric_rows(CONTROL_DIR / "latest_train.log")
    treatment_rows = metric_rows(TREATMENT_DIR / "latest_train.log")
    control_hps = effective_hps(control_rows)
    treatment_hps = effective_hps(treatment_rows)
    panel_audit = json.loads((PANEL_DIR / "audit.json").read_text(encoding="utf-8"))
    panel_summary = json.loads((PANEL_DIR / "summary.json").read_text(encoding="utf-8"))
    actor = actor_logits_identity()
    checks = {
        "compile_and_unit_tests": all(row["returncode"] == 0 for row in command_results),
        "micro_configs_equal_except_treatment_identity": scrub_config(control_manifest["config"]) == scrub_config(treatment_manifest["config"]),
        "micro_treatment_flag_only": not bool(control_manifest["config"]["showdown_ev_value_targets"]) and bool(treatment_manifest["config"]["showdown_ev_value_targets"]),
        "micro_rows_complete": len(control_rows) == 10 and len(treatment_rows) == 10,
        "micro_throughput_ratio_ge_0_85": treatment_hps / control_hps >= 0.85,
        "micro_entropy_floor": min(row["entropy"] for row in control_rows + treatment_rows) >= 0.3,
        "pretraining_actor_logits_delta_zero": actor["pass"],
        "h2_var_audit_pass": panel_audit.get("status") == "PASS_IMMUTABLE_H2_VAR_001" and not panel_audit.get("errors"),
        "h2_var_gates_pass": panel_summary.get("status") == "PASS_H2_VAR_001" and all(panel_summary.get("gates", {}).values()),
    }
    return {
        "schema_version": "v5.hybrid.h2.implementation_audit.v1",
        "checked_at": utc_now(),
        "overall": "PASS_IMPLEMENTATION_PREREG_READY" if all(checks.values()) else "FAIL_CLOSED",
        "checks": checks,
        "commands": command_results,
        "actor_identity": actor,
        "micro_window": {
            "classification": "ENGINEERING_ONLY_NOT_METHOD_JUDGMENT",
            "warmup_rows_excluded": 1,
            "control_rows": len(control_rows),
            "treatment_rows": len(treatment_rows),
            "control_effective_hps": control_hps,
            "treatment_effective_hps": treatment_hps,
            "hps_ratio": treatment_hps / control_hps,
            "minimum_entropy": min(row["entropy"] for row in control_rows + treatment_rows),
            "control_log_sha256": sha256_file(CONTROL_DIR / "latest_train.log"),
            "treatment_log_sha256": sha256_file(TREATMENT_DIR / "latest_train.log"),
            "control_manifest_sha256": sha256_file(CONTROL_DIR / "run_manifest.json"),
            "treatment_manifest_sha256": sha256_file(TREATMENT_DIR / "run_manifest.json"),
        },
        "h2_var": {
            "audit_sha256": sha256_file(PANEL_DIR / "audit.json"),
            "summary_sha256": sha256_file(PANEL_DIR / "summary.json"),
            "variance_reduction_point": panel_summary["variance_reduction_point"],
            "variance_reduction_ci95_lower": panel_summary["variance_reduction_ci95_lower"],
            "mean_bias_abs_point": panel_summary["mean_bias_abs_point"],
            "mean_bias_abs_ci95_upper": panel_summary["mean_bias_abs_ci95_upper"],
        },
        "source_checkpoint_sha256": SOURCE_SHA,
        "candidate_code": {
            "train_v5.py": sha256_file(REPO_ROOT / "scripts/alpha_holdem/train_v5.py"),
            "train_mp3_hybrid_h1.py": sha256_file(REPO_ROOT / "scripts/alpha_holdem/train_mp3_hybrid_h1.py"),
            "v5_hybrid_h2_targets.py": sha256_file(REPO_ROOT / "scripts/alpha_holdem/v5_hybrid_h2_targets.py"),
            "v5_h2_variance_panel.py": sha256_file(REPO_ROOT / "scripts/alpha_holdem/v5_h2_variance_panel.py"),
        },
        "launch_authority": "NONE_PREREGISTRATION_REQUIRED",
        "official_hands_authorized": 0,
        "strength_claim": "FORBIDDEN",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = build()
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["overall"].startswith("PASS_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
