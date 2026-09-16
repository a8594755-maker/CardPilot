"""Matched seven-versus-nine-objective offline update translation smoke."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.audit_v6_integrated_gradient_conflict import (
    parse_named_path,
    sha256_path,
)
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_dual_contract_gradient_conflict_audit import (
    minimum_norm_simplex,
)
from alpha_holdem.v6_integrated_seven_objective_update_smoke import (
    calibrated_update,
    load_candidate_hands,
    objective_metrics,
    prepare_dataset,
    save_checkpoint,
)


def objective_direction(
    group_names: list[str],
    group_units: np.ndarray,
    source_kl: np.ndarray,
    *,
    include_public: bool,
) -> tuple[np.ndarray, dict]:
    indices = [
        index for index, name in enumerate(group_names)
        if include_public or not name.startswith("public_slumbot_")
    ]
    source_unit = source_kl / np.linalg.norm(source_kl)
    units = np.vstack([group_units[indices], source_unit])
    names = [group_names[index] for index in indices] + ["standard10_source_kl"]
    objective, active, weights, products = minimum_norm_simplex(units @ units.T)
    if not np.all(products >= objective - 1e-7):
        raise RuntimeError("objective simplex KKT failure")
    return weights @ units, {
        "objective_names": names,
        "objective_weights": weights.tolist(),
        "active_objectives": [names[index] for index in active],
        "minimum_norm": float(np.sqrt(max(objective, 0.0))),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="append", type=parse_named_path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--audit-run", type=Path, required=True)
    parser.add_argument("--target-parent-kl", type=float, default=5e-5)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    if not 0.0 < args.target_parent_kl < 0.01:
        parser.error("target-parent-kl must be in (0, 0.01)")
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()

    audit_summary_path = args.audit_run / "summary.json"
    raw_path = args.audit_run / "frozen_training_hands.jsonl.gz"
    gradient_path = args.audit_run / "gradient_geometry.npz"
    audit = json.loads(audit_summary_path.read_text(encoding="utf-8"))
    if not audit.get("passed"):
        raise ValueError("public-objective audit did not pass")
    if sha256_path(raw_path) != audit["raw_hands_sha256"]:
        raise ValueError("audit raw evidence hash mismatch")
    if sha256_path(gradient_path) != audit["gradient_artifact_sha256"]:
        raise ValueError("audit gradient evidence hash mismatch")
    arrays = np.load(gradient_path)
    source = load_policy(args.source.resolve(), args.device)
    if source.sha256 != audit["source_sha256"]:
        raise ValueError("source checkpoint differs from audit")

    results = {}
    for candidate_name, parent_path in dict(args.candidate).items():
        parent_path = parent_path.resolve()
        parent_sha = sha256_path(parent_path)
        if parent_sha != audit["candidates"][candidate_name]["checkpoint_sha256"]:
            raise ValueError(f"candidate differs from audit: {candidate_name}")
        parent = load_policy(parent_path, args.device)
        hands = load_candidate_hands(raw_path, candidate_name)
        dataset = prepare_dataset(hands, parent, source, args.device)
        prefix = candidate_name.replace("-", "_") + "__"
        group_names = [str(name) for name in arrays[prefix + "group_names"].tolist()]
        if group_names != dataset["group_names"]:
            raise ValueError("gradient and reconstructed dataset group order differ")
        group_units = arrays[prefix + "group_unit_gradients"].astype(np.float64)
        source_kl = arrays[prefix + "source_kl_all"].astype(np.float64)
        directions = {}
        geometry = {}
        for arm, include_public in (("seven_control", False), ("nine_treatment", True)):
            directions[arm], geometry[arm] = objective_direction(
                group_names, group_units, source_kl, include_public=include_public
            )

        before = objective_metrics(parent.model, dataset)
        arms = {}
        for arm, direction in directions.items():
            policy = load_policy(parent_path, args.device)
            step, achieved_kl = calibrated_update(
                policy.model, direction, dataset, args.target_parent_kl
            )
            after = objective_metrics(policy.model, dataset)
            deltas = {
                group: after["group_policy_losses"][group]
                - before["group_policy_losses"][group]
                for group in group_names
            }
            source_delta = after["source_forward_kl"] - before["source_forward_kl"]
            intended_groups = [
                group for group in group_names
                if arm == "nine_treatment" or not group.startswith("public_slumbot_")
            ]
            all_intended_improve = bool(
                all(deltas[group] < 0.0 for group in intended_groups)
                and source_delta < 0.0
            )
            all_nine_improve = bool(
                all(delta < 0.0 for delta in deltas.values()) and source_delta < 0.0
            )
            metadata = {
                "schema": "cardpilot.integrated_public_objective_update_smoke.v1",
                "arm": arm,
                "parent_checkpoint": str(parent_path),
                "parent_sha256": parent_sha,
                "audit_summary_sha256": sha256_path(audit_summary_path),
                "audit_raw_sha256": sha256_path(raw_path),
                "audit_gradient_sha256": sha256_path(gradient_path),
                "reused_training_hands": len(hands),
                "reused_training_decisions": len(dataset["actions"]),
                "target_parent_kl": args.target_parent_kl,
                "calibrated_step_l2": step,
                "achieved_parent_kl": achieved_kl,
                "direction": (
                    "minimum_norm_six_anchor_seat_reward_plus_source_kl"
                    if arm == "seven_control"
                    else "minimum_norm_eight_opponent_seat_reward_plus_source_kl"
                ),
                "resume_eligible": False,
            }
            checkpoint = save_checkpoint(
                parent_path,
                policy.model,
                args.out_dir / candidate_name / f"{arm}.pt",
                metadata,
            )
            arms[arm] = {
                "checkpoint": checkpoint,
                "calibrated_step_l2": step,
                "achieved_parent_kl": achieved_kl,
                "after_objectives": after,
                "group_policy_loss_deltas": deltas,
                "source_forward_kl_delta": source_delta,
                "all_intended_objectives_improve": all_intended_improve,
                "all_nine_objectives_improve": all_nine_improve,
            }
        public_groups = [
            group for group in group_names if group.startswith("public_slumbot_")
        ]
        results[candidate_name] = {
            "parent": {"path": str(parent_path), "sha256": parent_sha},
            "training_hands_reused": len(hands),
            "training_decisions_reused": len(dataset["actions"]),
            "group_names": group_names,
            "before_objectives": before,
            "geometry": geometry,
            "arms": arms,
            "nine_minus_seven_public_loss_delta": {
                group: arms["nine_treatment"]["group_policy_loss_deltas"][group]
                - arms["seven_control"]["group_policy_loss_deltas"][group]
                for group in public_groups
            },
        }
        del parent, dataset
        if args.device == "cuda":
            torch.cuda.empty_cache()

    gates = {
        "matched_parent_kl_within_two_percent": all(
            abs(row["arms"][arm]["achieved_parent_kl"] - args.target_parent_kl)
            <= args.target_parent_kl * 0.02
            for row in results.values()
            for arm in ("seven_control", "nine_treatment")
        ),
        "seven_control_improves_its_seven_objectives_both_lineages": all(
            row["arms"]["seven_control"]["all_intended_objectives_improve"]
            for row in results.values()
        ),
        "nine_treatment_improves_all_nine_objectives_both_lineages": all(
            row["arms"]["nine_treatment"]["all_nine_objectives_improve"]
            for row in results.values()
        ),
        "nine_treatment_beats_seven_on_both_public_seats_both_lineages": all(
            all(delta < 0.0 for delta in row["nine_minus_seven_public_loss_delta"].values())
            for row in results.values()
        ),
    }
    summary = {
        "schema": "cardpilot.integrated_public_objective_update_smoke.v1",
        "status": "COMPLETED",
        "target_parent_kl": args.target_parent_kl,
        "source": {"path": str(source.path), "sha256": source.sha256},
        "audit": {
            "summary_sha256": sha256_path(audit_summary_path),
            "raw_sha256": sha256_path(raw_path),
            "gradient_sha256": sha256_path(gradient_path),
        },
        "candidates": results,
        "gates": gates,
        "admit_untouched_evaluation": all(gates.values()),
        "decision": (
            "RUN_UNTOUCHED_SEVEN_VS_NINE_EVALUATION"
            if all(gates.values())
            else "REJECT_NINE_OBJECTIVE_FINITE_UPDATE_AT_THIS_DOSE"
        ),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
