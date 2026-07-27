#!/usr/bin/env python3
"""Offline fail-closed implementation audit for H10 robust catch-up-only loss."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.alpha_holdem.test_v5_hybrid_h8_implementation import (
    TinyPolicy,
    assert_state_equal,
    named_optimizer_state,
    transitions,
)
from scripts.alpha_holdem.test_v5_hybrid_h10_implementation import run_update
from scripts.alpha_holdem.train_mp3_hybrid_h1 import trinal_clip_ppo_update


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--expected-preregistration-sha256", required=True)
    parser.add_argument("--trainer", type=Path, required=True)
    parser.add_argument("--ppo", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    checks: dict[str, bool] = {}
    details: dict[str, object] = {}
    errors: list[str] = []

    def check(name: str, passed: bool, detail: object = None) -> None:
        checks[name] = bool(passed)
        if detail is not None:
            details[name] = detail
        if not passed:
            errors.append(name)

    try:
        prereg = json.loads(args.preregistration.read_text(encoding="utf-8-sig"))
        trainer_source = args.trainer.read_text(encoding="utf-8")
        ppo_source = args.ppo.read_text(encoding="utf-8")
        check(
            "preregistration_identity",
            sha(args.preregistration) == args.expected_preregistration_sha256.lower()
            and prereg.get("experiment_id") == "H10"
            and prereg.get("status") == "REGISTERED_NO_LAUNCH",
        )
        check(
            "single_variable_lock",
            prereg["single_variable"] == {
                "name": "catchup_value_loss",
                "control": "MSE",
                "treatment": "SmoothL1",
                "treatment_beta_raw_bb": 1.0,
                "standard_ppo_critic_loss_both_arms": "MSE",
                "beta_selection": "unchanged from H9 canonical SmoothL1 default; no holdout, H9 partial-outcome or CAL score search",
            },
        )
        check(
            "trainer_cli_identity",
            all(token in trainer_source for token in (
                "--h10-window-arm", "--h10-catchup-loss",
                "--h10-catchup-smooth-l1-beta", "--h10-preregistration", "--h10-design-lock",
            )),
        )
        check(
            "trainer_fail_closed_contract",
            all(token in trainer_source for token in (
                "H10 arm run_id or fixed endpoint mismatch",
                "H10 exact canonical source checkpoint identity/hash mismatch",
                "H10 forbidden H9/CAL source path",
                "H10 arms require target-KL0.03 and value-head catch-up enabled",
                "catch-up loss identity mismatch",
            )),
        )
        check(
            "ppo_robust_loss_scope",
            "F.smooth_l1_loss(" in ppo_source
            and "beta=float(value_head_catchup_smooth_l1_beta)" in ppo_source
            and "catchup_vloss = F.mse_loss(" in ppo_source
            and ppo_source.count("F.smooth_l1_loss(") == 1,
        )
        active_source = (REPO / "scripts/alpha_holdem/v5_hybrid_h10_active_window.py").read_text(encoding="utf-8")
        planner_source = (REPO / "scripts/alpha_holdem/v5_slumbot_benchmark_plan.py").read_text(encoding="utf-8")
        check(
            "active_window_fail_closed_contract",
            "v5.active_window.v1" in active_source
            and "generic_planner_command_emission" in active_source
            and "active_window_sentinel" in planner_source
            and 'command = "" if active_window_block' in planner_source,
        )

        torch.manual_seed(2026071902)
        initial = TinyPolicy()
        data = transitions(initial)
        control, control_optimizer, control_stats, control_rng = run_update(initial, data, loss_mode="mse")
        treatment, treatment_optimizer, treatment_stats, treatment_rng = run_update(initial, data, loss_mode="smooth_l1")
        check(
            "forced_trigger_accounting",
            control_stats["kl_early_stop_triggered"]
            and treatment_stats["kl_early_stop_triggered"]
            and control_stats["kl_early_stop_epoch"] == treatment_stats["kl_early_stop_epoch"]
            and control_stats["value_head_catchup_epochs"] == treatment_stats["value_head_catchup_epochs"]
            and control_stats["value_head_catchup_minibatches"] == treatment_stats["value_head_catchup_minibatches"] > 0,
            {"control": control_stats, "treatment": treatment_stats},
        )
        check(
            "loss_identity",
            control_stats["value_head_catchup_loss_mode"] == "mse"
            and treatment_stats["value_head_catchup_loss_mode"] == "smooth_l1"
            and treatment_stats["value_head_catchup_smooth_l1_beta"] == 1.0,
        )
        check("global_rng_unchanged", torch.equal(control_rng, treatment_rng))
        actor_equal = all(
            torch.equal(tensor, treatment.state_dict()[name])
            for name, tensor in control.state_dict().items()
            if not name.startswith("value_head.")
        )
        value_changed = all(
            not torch.equal(tensor, treatment.state_dict()[name])
            for name, tensor in control.state_dict().items()
            if name.startswith("value_head.")
        )
        check("actor_trunk_parameters_and_buffers_bitwise_unchanged", actor_equal)
        check("value_head_effect_differs", value_changed)
        control_state = named_optimizer_state(control, control_optimizer)
        treatment_state = named_optimizer_state(treatment, treatment_optimizer)
        optimizer_equal = True
        for name in control_state:
            if name.startswith("value_head."):
                continue
            try:
                assert_state_equal(control_state[name], treatment_state[name])
            except AssertionError:
                optimizer_equal = False
        check("non_value_optimizer_state_bitwise_unchanged", optimizer_equal)
        check("model_buffers_bitwise_unchanged", torch.equal(control.audit_buffer, treatment.audit_buffer))

        legacy = copy.deepcopy(initial)
        legacy_optimizer = torch.optim.Adam(legacy.parameters(), lr=0.02)
        torch.manual_seed(2026071901)
        legacy_stats = trinal_clip_ppo_update(
            legacy, legacy_optimizer, data, "cpu", epochs=4, mini_batch_size=6,
            entropy_coef=0.0, action_prior_coef=0.0, preflop_action_prior_coef=0.0,
            target_kl=1e-12, value_head_catchup=True,
        )
        legacy_equal = all(
            torch.equal(tensor, legacy.state_dict()[name])
            for name, tensor in control.state_dict().items()
        ) and legacy_stats == control_stats
        check("mse_control_bitwise_legacy_equivalent", legacy_equal)

        result = {
            "schema_version": "v5.hybrid.h10.implementation_audit.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "PASS_H10_IMPLEMENTATION" if not errors else "FAIL_CLOSED",
            "checks": checks,
            "details": details,
            "failed_checks": errors,
            "source_sha256": {
                "preregistration": sha(args.preregistration),
                "trainer": sha(args.trainer),
                "ppo": sha(args.ppo),
                "test": sha(args.test),
            },
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
            "strength_claim": "FORBIDDEN",
        }
        code = 0 if not errors else 2
    except Exception as exc:
        result = {
            "schema_version": "v5.hybrid.h10.implementation_audit.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "FAIL_CLOSED",
            "checks": checks,
            "details": details,
            "failed_checks": errors + [f"{type(exc).__name__}: {exc}"],
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
            "strength_claim": "FORBIDDEN",
        }
        code = 2
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
