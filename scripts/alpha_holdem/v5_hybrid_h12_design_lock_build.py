#!/usr/bin/env python3
"""Build the one-shot immutable H12 design lock after all offline gates pass."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "reports/v5_hybrid_h12_preregistration_v3_20260716.json"
PREREG_AUDIT = ROOT / "reports/v5_hybrid_h12_preregistration_audit_v5_20260716.json"
IMPLEMENTATION = ROOT / "reports/v5_hybrid_h12_implementation_audit_v4_20260716.json"
ROUTE_RESULT = ROOT / "reports/v5_hybrid_route_review_008_result_20260716.json"
ROUTE_AUDIT = ROOT / "reports/v5_hybrid_route_review_008_audit_20260716.json"
SOURCE = ROOT / "models/alpha_holdem_v5_hybrid/v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715/h11_control_endpoint.pt"
MIRROR_DIR = ROOT / "reports/h12_mirror_001_v3_20260716"
HOLDOUT = ROOT / "reports/h1_cal_001_attempt2_20260712"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def absolute(relative: str) -> str:
    return str((ROOT / relative).resolve())


def frozen(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite immutable H12 design lock")
    prereg = load(PREREG)
    prereg_audit = load(PREREG_AUDIT)
    implementation = load(IMPLEMENTATION)
    route_audit = load(ROUTE_AUDIT)
    if sha(PREREG) != "7ecd7a4342f75a92f4d4f12493bcd5fda9e3e92e7f43f023f8779becbdb48e57":
        raise SystemExit("preregistration hash")
    if prereg_audit.get("overall") != "PASS" or implementation.get("overall") != "PASS_H12_IMPLEMENTATION" or route_audit.get("overall") != "PASS":
        raise SystemExit("offline authority missing")
    source_sha = sha(SOURCE)
    if source_sha != prereg["source"]["checkpoint_sha256"]:
        raise SystemExit("source hash")
    tools = [
        "scripts/alpha_holdem/train_v5.py",
        "scripts/alpha_holdem/train_mp3_hybrid_h1.py",
        "scripts/alpha_holdem/environment_v55.py",
        "scripts/alpha_holdem/v5_assignment_provenance_audit.py",
        "scripts/alpha_holdem/v5_h1_calibration.py",
        "scripts/alpha_holdem/v5_mirror_eval.py",
        "scripts/alpha_holdem/v5_monitor.py",
        "scripts/alpha_holdem/v5_slumbot_benchmark_plan.py",
        "scripts/alpha_holdem/v5_hybrid_h12_implementation_audit.py",
        "scripts/alpha_holdem/v5_hybrid_h12_perf_cal.py",
        "scripts/alpha_holdem/v5_hybrid_h12_perf_cal_audit.py",
        "scripts/alpha_holdem/v5_hybrid_h12_health_watch.py",
        "scripts/alpha_holdem/v5_hybrid_h12_ordered_rearm.py",
        "scripts/alpha_holdem/v5_hybrid_h12_endpoint_watch.py",
        "scripts/alpha_holdem/v5_hybrid_h12_protocol_watch.py",
        "scripts/alpha_holdem/v5_hybrid_h12_treatment_launch_watch.py",
        "scripts/alpha_holdem/v5_hybrid_h12_active_window.py",
        "scripts/alpha_holdem/v5_hybrid_h12_mirror.py",
        "scripts/alpha_holdem/v5_hybrid_h12_judge.py",
        "scripts/alpha_holdem/v5_hybrid_h12_completion_watch.py",
        "scripts/alpha_holdem/v5_hybrid_h12_preflight.py",
        "scripts/alpha_holdem/v5_hybrid_h12_design_lock_audit.py",
        "scripts/alpha_holdem/v5_hybrid_h12_launch_control.ps1",
        "scripts/alpha_holdem/v5_hybrid_h12_launch_treatment.ps1",
        "scripts/alpha_holdem/v5_rearm_watchers.ps1",
        "scripts/alpha_holdem/test_v5_hybrid_h12_implementation.py",
        "scripts/alpha_holdem/test_v5_hybrid_h12_control_plane.py",
        "scripts/alpha_holdem/test_v5_hybrid_h12_rearm_contract.py",
        "scripts/alpha_holdem/test_v5_hybrid_h12_judge_contract.py",
        "scripts/alpha_holdem/test_v5_hybrid_h12_perf_cal.py",
        "scripts/alpha_holdem/test_v5_hybrid_h12_perf_cal_audit.py",
        "scripts/alpha_holdem/test_v5_hybrid_h12_health_watch.py",
        "scripts/alpha_holdem/test_v5_hybrid_h12_ordered_rearm.py",
        "scripts/alpha_holdem/v5_hybrid_h12_preregistration_audit.py",
        "scripts/alpha_holdem/v5_hybrid_h12_design_lock_build.py",
    ]
    tool_hashes = {relative: sha(ROOT / relative) for relative in tools}
    control_id = prereg["arms"]["control_run_id"]
    treatment_id = prereg["arms"]["treatment_run_id"]
    arm_values = {}
    for arm, run_id, loss in (
        ("control", control_id, "mse"),
        ("treatment", treatment_id, "smooth_l1"),
    ):
        run_dir = ROOT / "models/alpha_holdem_v5_hybrid" / run_id
        arm_values[arm] = {
            "run_id": run_id,
            "run_dir": str(run_dir.resolve()),
            "metrics_path": str((run_dir / "h1_training_metrics.jsonl").resolve()),
            "train_log_path": str((run_dir / "latest_train.log").resolve()),
            "provenance_path": str((run_dir / "opponent_assignment_provenance.jsonl").resolve()),
            "ppo_target_kl": 0.03,
            "value_head_catchup": True,
            "catchup_value_loss": loss,
            "catchup_smooth_l1_beta": 1.0,
        }
    common_config = {
        "device": "cuda", "workers": 22, "hands_per_iter": 16384,
        "rollout_mode": "multi", "rollout_envs_per_worker": 16,
        "inference_min_batch_slots": 256, "inference_batch_deadline_us": 1000.0,
        "ppo_epochs": 4, "mini_batch_size": 1024, "lr": 0.0003,
        "gamma": 0.999, "entropy_coef": 0.05, "entropy_floor": 0.3,
        "seed": 20260703, "worker_seed_base": 73000,
        "fixed_training_deal_stream": True, "opponent_assignment": "per-iteration",
        "opponent_groups": 5, "pool_strategy": "loss-kbest", "k_best": 5,
        "self_play_fraction": 0.2, "mirror_self_play_deals": True,
        "allin_runout_ev": True, "allin_runout_ev_max_runouts": 200,
        "preflop_action_prior_coef": 0.01, "postflop_action_prior_coef": 0.02,
        "preflop_sb_open_action_prior_coef": 0.0,
        "preflop_bb_vs_open_action_prior_coef": 0.0,
        "critic_contract": "critic_v1", "value_coef": 0.5,
        "reset_optimizer": False, "save_interval": 1, "snapshot_every": 200,
        "showdown_ev_value_targets": False,
    }
    mirror_manifest = MIRROR_DIR / "manifest.json"
    mirror_lock = MIRROR_DIR / "measurement_lock.json"
    fixed_files = [
        PREREG, PREREG_AUDIT, IMPLEMENTATION, ROUTE_RESULT, ROUTE_AUDIT,
        ROOT / "reports/v5_hybrid_h11_judgment_20260715.json",
        ROOT / "reports/v5_hybrid_h11_terminal_audit_20260716.json",
        ROOT / "reports/v5_hybrid_h11_throughput_diagnosis_20260716.json",
        ROOT / "reports/v5_hybrid_h12_perf_cal_offline_smoke_20260716.json",
        ROOT / "reports/v5_hybrid_h12_perf_cal_offline_smoke_audit_v2_20260716.json",
        ROOT / "reports/v5_cal_ext_001_completion_20260715.json",
        ROOT / "reports/v5_cal_ext_001_completion_audit_20260715.json",
        mirror_manifest, mirror_lock,
        HOLDOUT / "manifest.json", HOLDOUT / "audit.json",
        HOLDOUT / "decisions.jsonl", HOLDOUT / "hands.jsonl",
        ROOT / "models/alpha_holdem_v5_hybrid/v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715/h11_control_endpoint_status.json",
    ]
    lock = {
        "schema_version": "v5.hybrid.h12.design_lock.v2",
        "design_id": "H12",
        "status": "LOCKED",
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "supersedes": {
            "path": str((ROOT / "reports/v5_hybrid_h12_design_lock_20260716.json").resolve()),
            "sha256": "bbca7ea42aeb23acaf9ded88699c696ec8992ada4f1bf925bfb2f98ab2b524c4",
            "reason": "prelaunch control-plane schema correction: ordered_rearm_stages is now explicit",
            "launches_under_v1": 0,
        },
        "preregistration": frozen(PREREG),
        "preregistration_audit": frozen(PREREG_AUDIT),
        "implementation_audit": {**frozen(IMPLEMENTATION), "overall": implementation["overall"], "checks": "21/21 PASS; focused suite 23/23 PASS"},
        "route_review": {"result": frozen(ROUTE_RESULT), "audit": frozen(ROUTE_AUDIT), "route_exhausted": False},
        "single_variable": {"name": "catchup_value_loss", "control": "mse", "treatment": "smooth_l1_beta_1.0", "common_value_head_catchup": True, "common_ppo_target_kl": 0.03},
        "source": {"path": str(SOURCE.resolve()), "sha256": source_sha, "iteration": 35051, "hands": 576021901, "run_id": prereg["source"]["run_id"], "role": prereg["source"]["role"]},
        "preregistration_source": {"checkpoint_path": str(SOURCE.resolve()), "checkpoint_sha256": source_sha},
        "source_anchor": {"path": str(SOURCE.resolve()), "sha256": source_sha, "iteration": 35051, "hands": 576021901, "run_id": prereg["source"]["run_id"]},
        "forbidden_sources": [{**item, "path": absolute(item["path"])} for item in prereg["forbidden_sources"]],
        "arm_budget": {"actual_hands_each": 20000000, "minimum_endpoint_hands": 596021901, "maximum_overshoot_hands": 50000, "order": ["control", "treatment"]},
        "arms": arm_values,
        "common_config": common_config,
        "performance_calibration": prereg["performance_calibration"],
        "control_plane": {
            **prereg["control_plane"],
            "ordered_rearm_stages": {
                "control": prereg["control_plane"]["control_stage_order"],
                "treatment": prereg["control_plane"]["treatment_stage_order"],
            },
        },
        "resource_isolation": {
            "evaluation_during_arm": "FORBIDDEN",
            "slumbot_during_arm": "FORBIDDEN",
            "additional_cpu_or_gpu_jobs": "FORBIDDEN_DURING_ARMS_EXCEPT_EXISTING_PATH1",
            "path1_existing_job": "MAY_CONTINUE_EXISTING_BELOWNORMAL_NO_RESTART_EXPANSION_OR_NEW_WORKERS",
            "evaluation_start": "AFTER_BOTH_ENDPOINTS_FROZEN_PASS_AND_NO_TRAINER_ACTIVE",
            "active_window_sentinel": str((ROOT / "reports/v5_active_window.json").resolve()),
            "parent_or_delegated_observer_commands": "FORBIDDEN_WHILE_EITHER_ARM_ACTIVE_INCLUDING_FILE_READ_HASH_PROCESS_LIST",
            "allowed_project_processes": "EXACT_LOCKED_H12_LIFECYCLE_PLUS_EXISTING_PATH1_ONLY",
            "full_trigger_provenance": ["pid", "parent_pid", "creation_time", "executable", "command_line", "command_line_sha256"],
            "abort_terminalization": "MUST_SUPPORT_CONTROL_OR_TREATMENT_PROTOCOL_ABORT",
            "generic_planner_command_emission": "FAIL_CLOSED_WHILE_ACTIVE",
            "violation_classification": "H12_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION",
        },
        "measurement": {
            "holdout_dir": str(HOLDOUT.resolve()),
            "mse_bootstrap_repetitions": 10000, "mse_bootstrap_seed": 2026071902,
            "source_anchor_path": str(SOURCE.resolve()), "source_anchor_sha256": source_sha,
            "mirror_dir": str(MIRROR_DIR.resolve()),
            "mirror_manifest_sha256": sha(mirror_manifest),
            "mirror_lock_sha256": sha(mirror_lock),
            "mirror_pairs": 40000, "mirror_seed": 2026071901,
            "mirror_bootstrap_seed": 2026071901,
            "start_condition": "BOTH_H12_ENDPOINTS_FROZEN_PASS_AND_NO_TRAINER_ACTIVE",
        },
        "gates": {
            "endpoint_mse_primary_reduction_point_min": 0.075,
            "endpoint_mse_primary_ci95_lower_min": 0.0,
            "source_anchor_degradation_point_max": 0.05,
            "source_anchor_degradation_ci95_upper_max": 0.10,
            "kl_p95_max": 0.03,
            "kl_fraction_above_0_03_max": 0.06044407894736842,
            "early_stop_trigger_fraction_min": 0.05,
            "first60_hps_ratio_min": 0.85,
            "full_hps_ratio_min": 0.85,
            "entropy_median_last200_min": 0.3,
            "entropy_treatment_minus_control_min": -0.1,
            "mirror_ci95_lower_min_bb100": -20.0,
        },
        "tools": tool_hashes,
        "frozen_files": [frozen(path) for path in fixed_files],
        "official_hands": 0,
        "strength_claim": "FORBIDDEN",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": "LOCKED", "path": str(args.out.resolve()), "sha256": sha(args.out), "tools": len(tool_hashes), "frozen_files": len(fixed_files)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
