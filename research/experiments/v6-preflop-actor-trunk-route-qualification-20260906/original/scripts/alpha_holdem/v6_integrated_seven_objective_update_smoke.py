"""Matched one-step translation smoke for integrated seven-objective gradients."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.audit_v6_integrated_gradient_conflict import (
    POLICY_PARAMETER_PREFIXES,
    parse_named_path,
    sha256_path,
    tensor_inputs,
)
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_dual_contract_advantage_balance import reconstruct
from alpha_holdem.v6_dual_contract_gradient_conflict_audit import (
    minimum_norm_simplex,
)


def flatten_parameters(model) -> tuple[list[str], list[torch.nn.Parameter], torch.Tensor]:
    selected = [
        (name, parameter)
        for name, parameter in model.named_parameters()
        if name.startswith(POLICY_PARAMETER_PREFIXES)
    ]
    names = [name for name, _ in selected]
    parameters = [parameter for _, parameter in selected]
    flat = torch.cat([parameter.detach().reshape(-1) for parameter in parameters])
    return names, parameters, flat


def assign_flat(parameters: list[torch.nn.Parameter], flat: torch.Tensor) -> None:
    offset = 0
    with torch.no_grad():
        for parameter in parameters:
            count = parameter.numel()
            parameter.copy_(flat[offset:offset + count].reshape_as(parameter))
            offset += count
    if offset != flat.numel():
        raise ValueError("flat parameter length mismatch")


def load_candidate_hands(path: Path, candidate: str) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [
            row
            for line in handle
            if (row := json.loads(line))["candidate"] == candidate
        ]


def prepare_dataset(hands: list[dict], parent, source, device: str) -> dict:
    arrays = [[], [], [], []]
    source_arrays = [[], [], [], []]
    actions = []
    returns = []
    groups = []
    for hand in hands:
        for decision in hand["hero_decisions"]:
            state = reconstruct(hand["deck"], decision["action_prefix"])
            for index, tensor in enumerate(tensor_inputs(parent, state, "cpu")):
                arrays[index].append(tensor.squeeze(0).numpy())
            for index, tensor in enumerate(tensor_inputs(source, state, "cpu")):
                source_arrays[index].append(tensor.squeeze(0).numpy())
            actions.append(int(decision["legacy_slot"]))
            returns.append(float(hand["reward_bb"]) / 200.0)
            groups.append(str(hand["group"]))
    tensors = [
        torch.as_tensor(np.stack(values), dtype=torch.float32, device=device)
        for values in arrays
    ]
    source_tensors = [
        torch.as_tensor(np.stack(values), dtype=torch.float32, device=device)
        for values in source_arrays
    ]
    action_tensor = torch.as_tensor(actions, dtype=torch.long, device=device)
    return_tensor = torch.as_tensor(returns, dtype=torch.float32, device=device)
    with torch.no_grad():
        parent_logits, parent_values = parent.model(*tensors)
        source_logits, _ = source.model(*source_tensors)
    masks = tensors[3]
    masked_parent = parent_logits + (1.0 - masks) * -1e9
    parent_log_probs = F.log_softmax(masked_parent, dim=-1).gather(
        1, action_tensor.unsqueeze(1)
    ).squeeze(1)
    raw_advantages = return_tensor - parent_values.squeeze(1)
    group_names = sorted(set(groups))
    normalized_advantages = torch.empty_like(raw_advantages)
    group_indices = {}
    for group in group_names:
        indices = torch.as_tensor(
            [index for index, value in enumerate(groups) if value == group],
            dtype=torch.long,
            device=device,
        )
        group_indices[group] = indices
        values = raw_advantages[indices]
        normalized_advantages[indices] = (
            (values - values.mean()) / values.std().clamp_min(1e-6)
        ).clamp(-5.0, 5.0)
    return {
        "tensors": tensors,
        "actions": action_tensor,
        "parent_logits": parent_logits.detach(),
        "parent_log_probs": parent_log_probs.detach(),
        "source_logits": source_logits.detach(),
        "normalized_advantages": normalized_advantages.detach(),
        "group_names": group_names,
        "group_indices": group_indices,
    }


@torch.no_grad()
def distribution_kl(reference_logits: torch.Tensor, logits: torch.Tensor) -> torch.Tensor:
    reference = F.softmax(reference_logits, dim=-1)
    return (
        reference
        * (reference.clamp_min(1e-8).log() - F.log_softmax(logits, dim=-1))
    ).sum(dim=-1).mean()


@torch.no_grad()
def parent_kl(model, dataset: dict) -> float:
    logits, _ = model(*dataset["tensors"])
    return float(distribution_kl(dataset["parent_logits"], logits))


def calibrated_update(
    model,
    direction: np.ndarray,
    dataset: dict,
    target_kl: float,
) -> tuple[float, float]:
    _, parameters, base = flatten_parameters(model)
    direction_tensor = torch.as_tensor(
        direction, dtype=base.dtype, device=base.device
    )
    direction_tensor /= direction_tensor.norm().clamp_min(1e-12)

    def evaluate(step: float) -> float:
        assign_flat(parameters, base - step * direction_tensor)
        return parent_kl(model, dataset)

    high = 1e-5
    while evaluate(high) < target_kl:
        high *= 2.0
        if high > 10.0:
            raise RuntimeError("failed to bracket target parent KL")
    low = 0.0
    for _ in range(32):
        middle = (low + high) / 2.0
        if evaluate(middle) < target_kl:
            low = middle
        else:
            high = middle
    achieved = evaluate((low + high) / 2.0)
    return (low + high) / 2.0, achieved


@torch.no_grad()
def objective_metrics(model, dataset: dict, clip_epsilon: float = 0.2) -> dict:
    logits, _ = model(*dataset["tensors"])
    masks = dataset["tensors"][3]
    log_probs = F.log_softmax(logits + (1.0 - masks) * -1e9, dim=-1).gather(
        1, dataset["actions"].unsqueeze(1)
    ).squeeze(1)
    ratio = torch.exp(log_probs - dataset["parent_log_probs"])
    advantages = dataset["normalized_advantages"]
    group_losses = {}
    for group in dataset["group_names"]:
        indices = dataset["group_indices"][group]
        selected_ratio = ratio[indices]
        selected_advantage = advantages[indices]
        surrogate = torch.minimum(
            selected_ratio * selected_advantage,
            selected_ratio.clamp(1.0 - clip_epsilon, 1.0 + clip_epsilon)
            * selected_advantage,
        )
        group_losses[group] = float(-surrogate.mean())
    return {
        "group_policy_losses": group_losses,
        "source_forward_kl": float(
            distribution_kl(dataset["source_logits"], logits)
        ),
        "parent_forward_kl": float(
            distribution_kl(dataset["parent_logits"], logits)
        ),
    }


def save_checkpoint(
    parent_path: Path,
    model,
    out_path: Path,
    metadata: dict,
) -> dict:
    checkpoint = torch.load(parent_path, map_location="cpu", weights_only=False)
    model_state = model.state_dict()
    for name in list(checkpoint["model"]):
        if name in model_state:
            checkpoint["model"][name] = model_state[name].detach().cpu().clone()
    checkpoint["optimizer"] = {}
    checkpoint["resume_eligible"] = False
    checkpoint["offline_direction_smoke"] = metadata
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(checkpoint, out_path)
    return {"path": str(out_path.resolve()), "sha256": sha256_path(out_path)}


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
    candidates = dict(args.candidate)
    audit_summary_path = args.audit_run / "summary.json"
    raw_path = args.audit_run / "frozen_training_hands.jsonl.gz"
    gradient_path = args.audit_run / "gradient_geometry.npz"
    audit_summary = json.loads(audit_summary_path.read_text(encoding="utf-8"))
    if sha256_path(raw_path) != audit_summary["raw_hands_sha256"]:
        raise ValueError("audit raw evidence hash mismatch")
    if sha256_path(gradient_path) != audit_summary["gradient_artifact_sha256"]:
        raise ValueError("audit gradient hash mismatch")
    arrays = np.load(gradient_path)
    source = load_policy(args.source.resolve(), args.device)
    results = {}
    for candidate_name, parent_path in candidates.items():
        parent_path = parent_path.resolve()
        parent_sha = sha256_path(parent_path)
        if parent_sha != audit_summary["candidates"][candidate_name]["checkpoint_sha256"]:
            raise ValueError(f"candidate hash differs from audit: {candidate_name}")
        parent = load_policy(parent_path, args.device)
        hands = load_candidate_hands(raw_path, candidate_name)
        dataset = prepare_dataset(hands, parent, source, args.device)
        prefix = candidate_name.replace("-", "_") + "__"
        group_gradients = arrays[prefix + "group_gradients"].astype(np.float64)
        group_units = arrays[prefix + "group_unit_gradients"].astype(np.float64)
        ordinary = arrays[prefix + "ordinary_gradient"].astype(np.float64)
        source_kl = arrays[prefix + "source_kl_all"].astype(np.float64)
        source_unit = source_kl / np.linalg.norm(source_kl)
        seven_units = np.vstack([group_units, source_unit])
        objective, active, seven_weights, products = minimum_norm_simplex(
            seven_units @ seven_units.T
        )
        if not np.all(products >= objective - 1e-7):
            raise RuntimeError("seven-objective simplex KKT failure")
        directions = {
            "control": ordinary + source_kl,
            "treatment": seven_weights @ seven_units,
        }
        before = objective_metrics(parent.model, dataset)
        arm_results = {}
        for arm, direction in directions.items():
            policy = load_policy(parent_path, args.device)
            step, achieved_kl = calibrated_update(
                policy.model, direction, dataset, args.target_parent_kl
            )
            after = objective_metrics(policy.model, dataset)
            group_deltas = {
                group: after["group_policy_losses"][group]
                - before["group_policy_losses"][group]
                for group in dataset["group_names"]
            }
            source_delta = after["source_forward_kl"] - before["source_forward_kl"]
            metadata = {
                "schema": "cardpilot.integrated_seven_objective_update_smoke.v1",
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
                    "decision_weighted_reward_gradient_plus_coefficient_one_source_kl"
                    if arm == "control"
                    else "minimum_norm_convex_combination_of_six_unit_reward_gradients_and_unit_source_kl"
                ),
                "resume_eligible": False,
            }
            checkpoint = save_checkpoint(
                parent_path,
                policy.model,
                args.out_dir / candidate_name / f"{arm}.pt",
                metadata,
            )
            arm_results[arm] = {
                "checkpoint": checkpoint,
                "calibrated_step_l2": step,
                "achieved_parent_kl": achieved_kl,
                "after_objectives": after,
                "group_policy_loss_deltas": group_deltas,
                "source_forward_kl_delta": source_delta,
                "all_seven_objectives_improve_on_training_cohort": bool(
                    all(delta < 0.0 for delta in group_deltas.values())
                    and source_delta < 0.0
                ),
            }
        treatment_better = {
            group: arm_results["treatment"]["group_policy_loss_deltas"][group]
            < arm_results["control"]["group_policy_loss_deltas"][group]
            for group in dataset["group_names"]
        }
        results[candidate_name] = {
            "parent": {"path": str(parent_path), "sha256": parent_sha},
            "training_hands_reused": len(hands),
            "training_decisions_reused": len(dataset["actions"]),
            "group_names": dataset["group_names"],
            "before_objectives": before,
            "seven_objective_weights": seven_weights.tolist(),
            "seven_objective_active_indices": list(active),
            "arms": arm_results,
            "treatment_better_group_delta": treatment_better,
            "treatment_better_group_count": sum(treatment_better.values()),
        }
        del parent, dataset
        if args.device == "cuda":
            torch.cuda.empty_cache()
    gates = {
        "matched_parent_kl_within_two_percent": all(
            abs(row["arms"][arm]["achieved_parent_kl"] - args.target_parent_kl)
            <= args.target_parent_kl * 0.02
            for row in results.values()
            for arm in ("control", "treatment")
        ),
        "treatment_improves_all_seven_training_objectives_both_candidates": all(
            row["arms"]["treatment"]["all_seven_objectives_improve_on_training_cohort"]
            for row in results.values()
        ),
        "control_fails_common_descent_both_candidates": all(
            not row["arms"]["control"]["all_seven_objectives_improve_on_training_cohort"]
            for row in results.values()
        ),
    }
    summary = {
        "schema": "cardpilot.integrated_seven_objective_update_smoke.v1",
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
            "RUN_UNTOUCHED_MULTI_ANCHOR_EVALUATION"
            if all(gates.values())
            else "REJECT_SEVEN_OBJECTIVE_UPDATE_TRANSLATION"
        ),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    summary_path = args.out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
