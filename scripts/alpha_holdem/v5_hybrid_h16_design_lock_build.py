#!/usr/bin/env python3
"""Build the one-shot immutable H16 design lock after every offline gate passes."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
PREREG = REPORTS / "v5_hybrid_h16_preregistration_20260719.json"
PREREG_AUDIT = REPORTS / "v5_hybrid_h16_preregistration_audit_20260719.json"
IMPLEMENTATION = REPORTS / "v5_hybrid_h16_implementation_audit_20260719.json"
INTEGRATION = REPORTS / "v5_h16_control_plane_integration_audit_20260719.json"
ROUTE_RESULT = REPORTS / "v5_hybrid_route_review_013_result_20260719.json"
ROUTE_AUDIT = REPORTS / "v5_hybrid_route_review_013_result_audit_20260719.json"
SOURCE_DIR = ROOT / "models/alpha_holdem_v5_hybrid/v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715"
SOURCE = SOURCE_DIR / "h11_control_endpoint.pt"
MIRROR_DIR = REPORTS / "h16_mirror_001_v3_20260719"
HOLDOUT = REPORTS / "h1_cal_001_attempt2_20260712"
PREREG_SHA = "51065761b6b291ef757ea467611203cbe79d45a5e4d54c163edaf79ef8fa1bb0"
SOURCE_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def frozen(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite immutable H16 design lock")
    prereg = load(PREREG)
    prereg_audit = load(PREREG_AUDIT)
    implementation = load(IMPLEMENTATION)
    integration = load(INTEGRATION)
    route_result = load(ROUTE_RESULT)
    route_audit = load(ROUTE_AUDIT)
    if sha(PREREG) != PREREG_SHA or sha(SOURCE) != SOURCE_SHA:
        raise SystemExit("preregistration/source identity mismatch")
    if prereg_audit.get("overall") != "PASS" or prereg_audit.get("checks_passed") != prereg_audit.get("checks_total"):
        raise SystemExit("preregistration audit missing")
    if implementation.get("overall") != "PASS_H16_IMPLEMENTATION" or implementation.get("failed_checks"):
        raise SystemExit("implementation audit missing")
    if integration.get("overall") != "PASS" or integration.get("checks_passed") != integration.get("checks_total"):
        raise SystemExit("control-plane integration audit missing")
    if route_result.get("decision", {}).get("selected_next") != "H16_REPRESENTATIVE_FULL_PPO_PERF_CAL_SAME_SCIENCE" or route_result.get("decision", {}).get("route_exhausted") is not False or route_audit.get("overall") != "PASS":
        raise SystemExit("Route Review013 authority missing")

    tools = [
        "scripts/alpha_holdem/train_v5.py",
        "scripts/alpha_holdem/train_mp3_hybrid_h1.py",
        "scripts/alpha_holdem/environment_v55.py",
        "scripts/alpha_holdem/v5_assignment_provenance_audit.py",
        "scripts/alpha_holdem/v5_h1_calibration.py",
        "scripts/alpha_holdem/v5_mirror_eval.py",
        "scripts/alpha_holdem/v5_monitor.py",
        "scripts/alpha_holdem/v5_lifecycle_guard_v2.py",
        "scripts/alpha_holdem/v5_hybrid_h16_implementation_audit.py",
        "scripts/alpha_holdem/v5_hybrid_h16_perf_cal.py",
        "scripts/alpha_holdem/v5_hybrid_h16_perf_cal_audit.py",
        "scripts/alpha_holdem/v5_hybrid_h16_health_watch.py",
        "scripts/alpha_holdem/v5_hybrid_h16_ordered_rearm.py",
        "scripts/alpha_holdem/v5_hybrid_h16_endpoint_watch.py",
        "scripts/alpha_holdem/v5_hybrid_h16_protocol_watch.py",
        "scripts/alpha_holdem/v5_hybrid_h16_treatment_launch_watch.py",
        "scripts/alpha_holdem/v5_hybrid_h16_active_window.py",
        "scripts/alpha_holdem/v5_hybrid_h16_mirror.py",
        "scripts/alpha_holdem/v5_hybrid_h16_judge.py",
        "scripts/alpha_holdem/v5_hybrid_h16_completion_watch.py",
        "scripts/alpha_holdem/v5_hybrid_h16_preflight.py",
        "scripts/alpha_holdem/v5_hybrid_h16_design_lock_audit.py",
        "scripts/alpha_holdem/v5_h16_control_plane_integration_audit.py",
        "scripts/alpha_holdem/v5_hybrid_h16_launch_control.ps1",
        "scripts/alpha_holdem/v5_hybrid_h16_launch_treatment.ps1",
        "scripts/alpha_holdem/v5_rearm_watchers.ps1",
        "scripts/alpha_holdem/v5_hybrid_h16_design_lock_build.py",
    ]
    tool_hashes = {relative: sha(ROOT / relative) for relative in tools}

    mirror_manifest = MIRROR_DIR / "manifest.json"
    mirror_lock = MIRROR_DIR / "measurement_lock.json"
    manifest = load(mirror_manifest)
    if manifest.get("preregistration_sha256") != PREREG_SHA or manifest.get("pairs") != 40_000 or manifest.get("source_checkpoint_sha256") != SOURCE_SHA:
        raise SystemExit("mirror manifest identity")
    mirror_lock_value = {
        "schema_version": "v5.hybrid.h16.mirror_lock.v1",
        "design_id": "H16-MIRROR-001",
        "status": "LOCKED",
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "preregistration_sha256": PREREG_SHA,
        "manifest_sha256": sha(mirror_manifest),
        "tool_sha256": tool_hashes["scripts/alpha_holdem/v5_hybrid_h16_mirror.py"],
        "pairs": 40_000,
        "seed": int(manifest["seed"]),
        "bootstrap_seed": 2026071906,
        "device": "cpu",
        "priority": "below-normal",
        "torch_threads": 1,
        "torch_interop_threads": 1,
        "adaptive_extension_allowed": False,
    }
    if mirror_lock.exists():
        raise SystemExit("refusing pre-existing H16 mirror lock")
    mirror_lock.write_text(json.dumps(mirror_lock_value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    arm_values = {}
    for arm, run_id, loss in (
        ("control", prereg["arms"]["control_run_id"], "mse"),
        ("treatment", prereg["arms"]["treatment_run_id"], "smooth_l1"),
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
        "inference_min_batch_slots": 256, "inference_batch_deadline_us": 1000,
        "ppo_epochs": 4, "mini_batch_size": 1024, "lr": 0.0003,
        "gamma": 0.999, "entropy_coef": 0.05, "entropy_floor": 0.3,
        "seed": 20260703, "worker_seed_base": 73000,
        "fixed_training_deal_stream": True, "opponent_assignment": "per-iteration",
        "opponent_groups": 5, "pool_strategy": "loss-kbest", "k_best": 5,
        "self_play_fraction": 0.2, "mirror_self_play_deals": True,
        "allin_runout_ev": True, "allin_runout_ev_max_runouts": 200,
        "preflop_action_prior_coef": 0.01, "postflop_action_prior_coef": 0.02,
        "preflop_sb_open_action_prior_coef": 0.0, "preflop_bb_vs_open_action_prior_coef": 0.0,
        "critic_contract": "critic_v1", "value_coef": 0.5,
        "reset_optimizer": False, "save_interval": 1, "snapshot_every": 200,
        "showdown_ev_value_targets": False,
    }
    fixed_files = [
        PREREG, PREREG_AUDIT, IMPLEMENTATION, INTEGRATION, ROUTE_RESULT, ROUTE_AUDIT,
        REPORTS / "v5_hybrid_h11_judgment_20260715.json",
        REPORTS / "v5_hybrid_h11_terminal_audit_20260716.json",
        SOURCE_DIR / "h11_control_endpoint_status.json",
        SOURCE_DIR / "h11_control_protocol_status.json",
        SOURCE_DIR / "run_manifest.json",
        mirror_manifest, mirror_lock,
        HOLDOUT / "manifest.json", HOLDOUT / "audit.json",
        HOLDOUT / "decisions.jsonl", HOLDOUT / "hands.jsonl",
    ]
    missing = [str(path) for path in fixed_files if not path.is_file()]
    if missing:
        raise SystemExit("missing frozen files: " + ", ".join(missing))

    source = {
        "path": str(SOURCE.resolve()), "sha256": SOURCE_SHA,
        "iteration": 35051, "hands": 576021901,
        "run_id": prereg["source"]["run_id"], "role": "clean_h11_control_source",
    }
    lock = {
        "schema_version": "v5.hybrid.h16.design_lock.v1",
        "design_id": "H16", "status": "LOCKED",
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "preregistration": {**frozen(PREREG), "status": prereg["status"]},
        "preregistration_audit": {**frozen(PREREG_AUDIT), "overall": "PASS", "checks": f'{prereg_audit["checks_passed"]}/{prereg_audit["checks_total"]} PASS'},
        "implementation_audit": {**frozen(IMPLEMENTATION), "overall": "PASS_H16_IMPLEMENTATION", "checks": f'{len(implementation["checks"])}/{len(implementation["checks"])} PASS'},
        "control_plane_integration_audit": {**frozen(INTEGRATION), "overall": "PASS", "checks": f'{integration["checks_passed"]}/{integration["checks_total"]} PASS'},
        "route_review": {**frozen(ROUTE_RESULT), "audit": frozen(ROUTE_AUDIT), "route_exhausted": False, "selected_next": "H16_REPRESENTATIVE_FULL_PPO_PERF_CAL_SAME_SCIENCE"},
        "single_variable": {"name": "catchup_value_loss", "control": "mse", "treatment": "smooth_l1_beta_1.0", "common_value_head_catchup": True, "common_ppo_target_kl": 0.03},
        "source": source, "source_anchor": source,
        "preregistration_source": {"checkpoint_path": str(SOURCE.resolve()), "checkpoint_sha256": SOURCE_SHA},
        "forbidden_source_labels": list(prereg["forbidden_sources"]),
        "arm_budget": {"actual_hands_each": 20_000_000, "minimum_endpoint_hands": 596_021_901, "maximum_overshoot_hands": 50_000, "order": ["control", "treatment"]},
        "arms": arm_values, "common_config": common_config,
        "representative_prearm_calibration": prereg["representative_prearm_calibration"],
        "control_plane": {
            "startup_readiness": "INITIAL_READY_BEFORE_PROCESS_SCAN_WITHIN_10_SECONDS",
            "cleanup": "FULL_REGISTERED_SEQUENCE_THEN_ONE_FINAL_TAGGED_SURVIVOR_GATE_WITHIN_15_SECONDS",
            "control_safe_boundary": "TREATMENT_LAUNCH_READY_SAFE_NO_TRAINER_BOUNDARY",
            "exact_lifecycle_child_registry": {
                "roles": ["health", "protocol", "endpoint", "treatment_launch", "completion"],
                "binding": ["pid", "parent_pid", "creation_time", "executable", "command_line_sha256", "script_sha256", "design_lock_sha256", "role"],
            },
            "ordered_rearm_stages": {
                "control": [["health", "protocol"], ["endpoint"], ["treatment_launch", "completion"]],
                "treatment": [["health", "protocol"], ["endpoint"], ["completion"]],
            },
        },
        "resource_isolation": {
            "evaluation_during_arm": "FORBIDDEN", "slumbot_during_arm": "FORBIDDEN",
            "additional_cpu_or_gpu_jobs": "FORBIDDEN_DURING_ARMS_EXCEPT_EXISTING_PATH1",
            "path1_existing_job": "MAY_CONTINUE_EXISTING_EXACT_LOCKED_SIX_BELOWNORMAL_CPU_WORKERS_NO_RESTART_EXPANSION_OR_NEW_WORKERS",
            "evaluation_start": "AFTER_BOTH_ENDPOINTS_FROZEN_PASS_AND_NO_TRAINER_ACTIVE",
            "active_window_sentinel": str((REPORTS / "v5_active_window.json").resolve()),
            "parent_or_delegated_observer_commands": "FORBIDDEN_WHILE_EITHER_ARM_ACTIVE_INCLUDING_FILE_READ_HASH_PROCESS_LIST",
            "allowed_project_processes": "EXACT_LOCKED_H16_LIFECYCLE_PLUS_EXISTING_EXACT_PATH1_ONLY",
            "full_trigger_provenance": ["pid", "parent_pid", "creation_time", "executable", "command_line", "command_line_sha256"],
            "abort_terminalization": "MUST_SUPPORT_CONTROL_OR_TREATMENT_PROTOCOL_ABORT",
            "generic_planner_command_emission": "FAIL_CLOSED_WHILE_ACTIVE",
            "violation_classification": "H16_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION",
        },
        "measurement": {
            "holdout_dir": str(HOLDOUT.resolve()), "mse_bootstrap_repetitions": 10_000, "mse_bootstrap_seed": 2026071907,
            "source_anchor_path": str(SOURCE.resolve()), "source_anchor_sha256": SOURCE_SHA,
            "mirror_dir": str(MIRROR_DIR.resolve()), "mirror_manifest_sha256": sha(mirror_manifest), "mirror_lock_sha256": sha(mirror_lock),
            "mirror_pairs": 40_000, "mirror_seed": int(manifest["seed"]), "mirror_bootstrap_seed": 2026071906,
            "start_condition": "BOTH_H16_ENDPOINTS_FROZEN_PASS_AND_NO_TRAINER_ACTIVE",
        },
        "gates": {**prereg["gates"], "mirror_ci95_lower_min_bb100": prereg["gates"]["mirror_treatment_control_ci95_lower_min_bb100"]},
        "tools": tool_hashes,
        "frozen_files": [frozen(path) for path in fixed_files],
        "official_hands": 0, "strength_claim": "FORBIDDEN",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": "LOCKED", "path": str(args.out.resolve()), "sha256": sha(args.out), "tools": len(tool_hashes), "frozen_files": len(fixed_files)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
