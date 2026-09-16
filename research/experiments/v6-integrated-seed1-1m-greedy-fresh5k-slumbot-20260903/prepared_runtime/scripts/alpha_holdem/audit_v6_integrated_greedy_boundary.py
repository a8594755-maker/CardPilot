"""Audit Standard10 greedy-boundary geometry for integrated policy heads."""
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
    POLICY_PARAMETER_PREFIXES,
    flatten_gradients,
    parse_named_path,
    sha256_path,
)
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.train_mp3_hybrid_h1 import (
    source_greedy_margin_preservation_loss,
)
from alpha_holdem.v6_dual_contract_gradient_conflict_audit import (
    minimum_norm_simplex,
    normalized_alignments,
)
from alpha_holdem.v6_integrated_seven_objective_update_smoke import (
    load_candidate_hands,
    prepare_dataset,
)


def boundary_loss(model, dataset: dict, max_margin: float, release: float):
    logits, _ = model(*dataset["tensors"])
    policy_rows = torch.ones_like(dataset["actions"], dtype=torch.bool)
    loss, eligible, released, violations = source_greedy_margin_preservation_loss(
        logits,
        dataset["source_logits"],
        dataset["actions"],
        dataset["normalized_advantages"],
        policy_rows,
        dataset["tensors"][3],
        max_margin,
        release,
    )
    legal = dataset["tensors"][3] > 0.0
    source_actions = dataset["source_logits"].masked_fill(~legal, -torch.inf).argmax(-1)
    current_actions = logits.masked_fill(~legal, -torch.inf).argmax(-1)
    return loss, {
        "loss": float(loss.detach()),
        "eligible_rows": int(eligible),
        "released_rows": int(released),
        "violation_rows": int(violations),
        "greedy_disagreement_rows": int((source_actions != current_actions).sum()),
        "greedy_disagreement_rate": float((source_actions != current_actions).float().mean()),
    }


def cosine(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.dot(left, right) / (np.linalg.norm(left) * np.linalg.norm(right)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="append", type=parse_named_path, required=True)
    parser.add_argument("--control", action="append", type=parse_named_path, required=True)
    parser.add_argument("--treatment", action="append", type=parse_named_path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--audit-run", type=Path, required=True)
    parser.add_argument("--max-margin", type=float, default=0.1)
    parser.add_argument("--release-advantage", type=float, default=1.0)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    candidates = dict(args.candidate)
    controls = dict(args.control)
    treatments = dict(args.treatment)
    if set(candidates) != set(controls) or set(candidates) != set(treatments):
        parser.error("candidate, control and treatment names must match")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    raw_path = args.audit_run / "frozen_training_hands.jsonl.gz"
    gradient_path = args.audit_run / "gradient_geometry.npz"
    audit_summary_path = args.audit_run / "summary.json"
    audit = json.loads(audit_summary_path.read_text(encoding="utf-8"))
    if sha256_path(raw_path) != audit["raw_hands_sha256"]:
        raise ValueError("raw audit hash mismatch")
    if sha256_path(gradient_path) != audit["gradient_artifact_sha256"]:
        raise ValueError("gradient audit hash mismatch")
    arrays = np.load(gradient_path)
    source = load_policy(args.source.resolve(), args.device)
    candidate_rows = {}
    for name, path in candidates.items():
        path = path.resolve()
        parent = load_policy(path, args.device)
        hands = load_candidate_hands(raw_path, name)
        dataset = prepare_dataset(hands, parent, source, args.device)
        parameters = []
        parameter_names = []
        for parameter_name, parameter in parent.model.named_parameters():
            enabled = parameter_name.startswith(POLICY_PARAMETER_PREFIXES)
            parameter.requires_grad_(enabled)
            if enabled:
                parameter_names.append(parameter_name)
                parameters.append(parameter)
        loss, parent_boundary = boundary_loss(
            parent.model, dataset, args.max_margin, args.release_advantage
        )
        boundary_gradient = flatten_gradients(loss, parameters)
        prefix = name.replace("-", "_") + "__"
        group_units = arrays[prefix + "group_unit_gradients"].astype(np.float64)
        ordinary = arrays[prefix + "ordinary_gradient"].astype(np.float64)
        source_kl = arrays[prefix + "source_kl_all"].astype(np.float64)
        seven_units = np.vstack(
            [group_units, source_kl / np.linalg.norm(source_kl)]
        )
        seven_objective, _, seven_weights, _ = minimum_norm_simplex(
            seven_units @ seven_units.T
        )
        seven_direction = seven_weights @ seven_units
        boundary_unit = boundary_gradient / np.linalg.norm(boundary_gradient)
        eight_units = np.vstack([seven_units, boundary_unit])
        objective, active, weights, products = minimum_norm_simplex(
            eight_units @ eight_units.T
        )
        eight_direction = weights @ eight_units
        eight_alignments = normalized_alignments(eight_units, eight_direction)
        arms = {}
        for arm, arm_path in (
            ("control", controls[name]),
            ("treatment", treatments[name]),
        ):
            policy = load_policy(arm_path.resolve(), args.device)
            with torch.no_grad():
                _, metrics = boundary_loss(
                    policy.model, dataset, args.max_margin, args.release_advantage
                )
            arms[arm] = {
                "path": str(arm_path.resolve()),
                "sha256": policy.sha256,
                **metrics,
                "loss_delta_from_parent": metrics["loss"] - parent_boundary["loss"],
                "disagreement_delta_from_parent": metrics["greedy_disagreement_rate"]
                - parent_boundary["greedy_disagreement_rate"],
            }
        candidate_rows[name] = {
            "parent": {"path": str(path), "sha256": parent.sha256},
            "parameter_names": parameter_names,
            "boundary": parent_boundary,
            "boundary_gradient_l2": float(np.linalg.norm(boundary_gradient)),
            "ordinary_vs_boundary_cosine": cosine(ordinary, boundary_gradient),
            "source_kl_vs_boundary_cosine": cosine(source_kl, boundary_gradient),
            "seven_direction_vs_boundary_cosine": cosine(
                seven_direction, boundary_gradient
            ),
            "seven_minimum_norm": float(np.sqrt(max(seven_objective, 0.0))),
            "eight_objective_active_indices": list(active),
            "eight_objective_weights": weights.tolist(),
            "eight_objective_alignments": eight_alignments.tolist(),
            "eight_objective_worst_alignment": float(eight_alignments.min()),
            "eight_objective_kkt_valid": bool(
                np.all(products >= objective - 1e-7)
            ),
            "arms": arms,
        }
        del parent, dataset
        if args.device == "cuda":
            torch.cuda.empty_cache()
    gates = {
        "boundary_gradient_nonzero_both": all(
            row["boundary_gradient_l2"] > 1e-12 for row in candidate_rows.values()
        ),
        "seven_direction_conflicts_with_boundary_both": all(
            row["seven_direction_vs_boundary_cosine"] < 0.0
            for row in candidate_rows.values()
        ),
        "seven_treatment_worsens_boundary_both": all(
            row["arms"]["treatment"]["loss_delta_from_parent"] > 0.0
            for row in candidate_rows.values()
        ),
        "eight_objective_common_descent_both": all(
            row["eight_objective_worst_alignment"] > 0.0
            and row["eight_objective_kkt_valid"]
            for row in candidate_rows.values()
        ),
    }
    result = {
        "schema": "cardpilot.integrated_greedy_boundary_audit.v1",
        "status": "COMPLETED",
        "max_margin": args.max_margin,
        "release_advantage": args.release_advantage,
        "source": {"path": str(source.path), "sha256": source.sha256},
        "audit": {
            "summary_sha256": sha256_path(audit_summary_path),
            "raw_sha256": sha256_path(raw_path),
            "gradient_sha256": sha256_path(gradient_path),
        },
        "candidates": candidate_rows,
        "gates": gates,
        "admit_boundary_aware_update": all(gates.values()),
        "decision": (
            "ADMIT_EIGHT_OBJECTIVE_BOUNDARY_AWARE_UPDATE_SMOKE"
            if all(gates.values())
            else "REJECT_GREEDY_BOUNDARY_AS_REPLICATED_MISSING_OBJECTIVE"
        ),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
