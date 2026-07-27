#!/usr/bin/env python3
"""Offline fail-closed implementation audit for H8 value-head-only catch-up."""
from __future__ import annotations

import argparse
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
    run_update,
    transitions,
)


def sha256(path: Path) -> str:
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
            sha256(args.preregistration) == args.expected_preregistration_sha256.lower()
            and prereg.get("experiment_id") == "H8"
            and prereg.get("status") == "REGISTERED_NO_LAUNCH",
        )
        check(
            "trainer_cli_identity",
            all(
                token in trainer_source
                for token in (
                    "--h8-window-arm",
                    "--h8-value-head-catchup-after-kl-stop",
                    "--h8-preregistration",
                    "--h8-design-lock",
                )
            ),
        )
        check(
            "trainer_fail_closed_contract",
            all(
                token in trainer_source
                for token in (
                    "H8 arms require exact --ppo-target-kl 0.03",
                    "H8 exact source checkpoint identity/hash mismatch",
                    "H8 arms require --resume --allow-resume and --no-reset-optimizer",
                    "H8 arm run_id or fixed endpoint mismatch",
                )
            ),
        )
        check(
            "ppo_catchup_contract",
            all(
                token in ppo_source
                for token in (
                    "remaining_epochs = max(int(epochs) - int(epochs_completed), 0)",
                    "sequential_indices = torch.arange(n, device=device)",
                    "model.eval()",
                    "nn.utils.clip_grad_norm_(value_params, max_grad_norm)",
                    "H8 value-head catch-up changed actor/trunk parameters or buffers",
                )
            ),
        )
        check(
            "required_logging",
            all(
                token in trainer_source
                for token in prereg["catchup_contract"]["logging_required"]
            ),
        )

        torch.manual_seed(2026071803)
        initial = TinyPolicy()
        data = transitions(initial)
        control, control_optimizer, control_stats = run_update(initial, data, catchup=False)
        treatment, treatment_optimizer, treatment_stats = run_update(initial, data, catchup=True)
        check(
            "forced_trigger_accounting",
            control_stats["kl_early_stop_triggered"]
            and treatment_stats["kl_early_stop_triggered"]
            and control_stats["ppo_epochs_completed"] == treatment_stats["ppo_epochs_completed"] < 4
            and treatment_stats["value_head_catchup_epochs"]
            == 4 - treatment_stats["ppo_epochs_completed"]
            and treatment_stats["value_head_catchup_minibatches"] > 0,
            {
                "control": control_stats,
                "treatment": treatment_stats,
            },
        )
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
        check(
            "actor_trunk_parameters_and_buffers_bitwise_unchanged",
            actor_equal and treatment_stats["value_head_catchup_actor_state_unchanged"],
        )
        check("value_head_updated", value_changed)

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

        failed = [name for name, passed in checks.items() if not passed]
        result = {
            "schema_version": "v5.hybrid.h8.implementation_audit.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "PASS_H8_IMPLEMENTATION" if not failed else "FAIL_CLOSED",
            "checks": checks,
            "details": details,
            "failed_checks": failed,
            "source_sha256": {
                "preregistration": sha256(args.preregistration),
                "trainer": sha256(args.trainer),
                "ppo": sha256(args.ppo),
                "test": sha256(args.test),
            },
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
            "strength_claim": "FORBIDDEN",
        }
        return_code = 0 if not failed else 2
    except Exception as exc:
        result = {
            "schema_version": "v5.hybrid.h8.implementation_audit.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "FAIL_CLOSED",
            "checks": checks,
            "details": details,
            "failed_checks": errors + [f"{type(exc).__name__}: {exc}"],
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
            "strength_claim": "FORBIDDEN",
        }
        return_code = 2
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
