"""Matched ordinary versus MGDA residual PPO on immutable hand evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.dual_contract_residual_v6 import DualContractResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_dual_contract_advantage_balance import reconstruct
from alpha_holdem.v6_dual_contract_gradient_conflict_audit import (
    flatten_gradients,
    minimum_norm_simplex,
    normalized_alignments,
    residual_state_digest,
)
from alpha_holdem.v6_dual_contract_residual_training_smoke import (
    mean_ci95,
    play_candidate_hand,
    sha256_path,
    state_inputs,
)


def residual_state(model: torch.nn.Module):
    return {
        name: tensor.detach().cpu().clone()
        for name, tensor in model.state_dict().items()
        if not name.startswith("base.")
    }


def set_flat_gradient(
    parameters: list[torch.nn.Parameter], flat_gradient: torch.Tensor
) -> None:
    offset = 0
    for parameter in parameters:
        count = parameter.numel()
        gradient = flat_gradient[offset : offset + count].view_as(parameter)
        parameter.grad = gradient.detach().clone()
        offset += count
    if offset != flat_gradient.numel():
        raise ValueError("flat gradient width does not match parameters")


def aggregate_policy_gradients(
    gradients: np.ndarray, decision_weights: np.ndarray, robust: bool
):
    ordinary = decision_weights @ gradients
    norms = np.linalg.norm(gradients, axis=1)
    if np.any(norms <= 1e-15):
        raise RuntimeError("one or more group policy gradients are zero")
    unit = gradients / norms[:, None]
    gram = unit @ unit.T
    ordinary_alignments = normalized_alignments(unit, ordinary)
    if not robust:
        return ordinary, {
            "pairwise_cosine_minimum": float(
                min(gram[left, right] for left in range(len(gram)) for right in range(left + 1, len(gram)))
            ),
            "ordinary_worst_alignment": float(ordinary_alignments.min()),
            "applied_worst_alignment": float(ordinary_alignments.min()),
            "robust_weights": None,
        }
    objective, _, weights, _ = minimum_norm_simplex(gram)
    direction = weights @ unit
    direction_norm = float(np.linalg.norm(direction))
    ordinary_norm = float(np.linalg.norm(ordinary))
    if direction_norm <= 1e-15:
        aggregate = np.zeros_like(ordinary)
    else:
        aggregate = direction * (ordinary_norm / direction_norm)
    applied_alignments = normalized_alignments(unit, aggregate)
    return aggregate, {
        "pairwise_cosine_minimum": float(
            min(gram[left, right] for left in range(len(gram)) for right in range(left + 1, len(gram)))
        ),
        "ordinary_worst_alignment": float(ordinary_alignments.min()),
        "applied_worst_alignment": float(applied_alignments.min()),
        "minimum_norm_objective": float(objective),
        "robust_weights": weights.tolist(),
    }


def train_arm(
    model,
    tensors,
    actions,
    old_log_probs,
    returns,
    group_advantages,
    group_indices,
    decision_weights,
    schedules,
    robust,
):
    parameters = list(model.trainable_parameters())
    optimizer = torch.optim.Adam(parameters, lr=3e-4)
    rows = 0
    step_metrics = []
    model.train()
    for step, selections in enumerate(schedules):
        group_gradients = []
        for group_index, selected_cpu in enumerate(selections):
            selected = torch.as_tensor(selected_cpu, dtype=torch.long, device=actions.device)
            batch = [tensor[selected] for tensor in tensors]
            logits, _ = model(*batch)
            distribution = torch.distributions.Categorical(
                logits=logits + (1.0 - batch[6]) * -1e9
            )
            log_probs = distribution.log_prob(actions[selected])
            ratio = torch.exp(log_probs - old_log_probs[selected])
            advantage = group_advantages[group_index][selected]
            surrogate = torch.minimum(
                ratio * advantage,
                ratio.clamp(0.8, 1.2) * advantage,
            )
            group_gradients.append(
                flatten_gradients(-surrogate.mean(), parameters).cpu().double().numpy()
            )
        group_gradients_array = np.stack(group_gradients)
        policy_gradient, geometry = aggregate_policy_gradients(
            group_gradients_array, decision_weights, robust
        )

        combined_cpu = np.concatenate(selections)
        combined = torch.as_tensor(combined_cpu, dtype=torch.long, device=actions.device)
        batch = [tensor[combined] for tensor in tensors]
        logits, values = model(*batch)
        distribution = torch.distributions.Categorical(
            logits=logits + (1.0 - batch[6]) * -1e9
        )
        value_loss = (values.squeeze(1) - returns[combined]).square().mean()
        entropy = distribution.entropy().mean()
        auxiliary_gradient = flatten_gradients(
            value_loss - 0.005 * entropy, parameters
        )
        total_gradient = (
            torch.from_numpy(policy_gradient).to(
                device=actions.device, dtype=auxiliary_gradient.dtype
            )
            + auxiliary_gradient
        )
        optimizer.zero_grad(set_to_none=True)
        set_flat_gradient(parameters, total_gradient)
        preclip_norm = float(torch.linalg.vector_norm(total_gradient))
        torch.nn.utils.clip_grad_norm_(parameters, 1.0)
        optimizer.step()
        rows += len(combined_cpu)
        step_metrics.append(
            {
                "step": step,
                "sample_rows": int(len(combined_cpu)),
                "value_loss": float(value_loss.detach()),
                "entropy": float(entropy.detach()),
                "total_gradient_l2_preclip": preclip_norm,
                **geometry,
            }
        )
    model.eval()
    return optimizer, rows, step_metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--opponent", action="append", type=Path, required=True)
    parser.add_argument("--training-evidence", type=Path, required=True)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--group-batch-size", type=int, required=True)
    parser.add_argument("--pairs-per-anchor", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--expected-initial-residual-sha")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if len(args.opponent) != 3:
        parser.error("exactly three --opponent checkpoints are required")
    if args.steps < 1 or args.group_batch_size < 32 or args.pairs_per_anchor < 128:
        parser.error("training/evaluation budget below smoke minimum")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(args.seed)
    started = time.time()

    base_path = args.base_checkpoint.resolve()
    training_path = args.training_evidence.resolve()
    base_sha = sha256_path(base_path)
    base_policy = load_policy(base_path, args.device)
    opponents = [load_policy(path.resolve(), args.device) for path in args.opponent]
    control = DualContractResidualPolicy(
        base_policy.model, hidden=128, policy_delta_cap=0.25
    ).to(args.device).eval()
    initial_state = residual_state(control)
    initial_sha = residual_state_digest(control)
    treatment = DualContractResidualPolicy(
        base_policy.model, hidden=128, policy_delta_cap=0.25
    ).to(args.device).eval()
    treatment.load_state_dict(initial_state, strict=False)
    if residual_state_digest(treatment) != initial_sha:
        raise RuntimeError("control/treatment initial residual mismatch")
    base_state = {
        name: tensor.detach().cpu().clone()
        for name, tensor in base_policy.model.state_dict().items()
    }

    hands = [
        json.loads(line)
        for line in gzip.open(training_path, "rt", encoding="utf-8")
    ]
    input_rows = []
    action_rows = []
    return_rows = []
    group_rows = []
    for hand in hands:
        group = f"opponent{hand['opponent_index']}_seat{hand['hero_seat']}"
        for decision in hand["hero_decisions"]:
            state = reconstruct(hand["deck"], decision["action_prefix"])
            values, _, _ = state_inputs(base_policy, state, args.device)
            input_rows.append(
                tuple(tensor.squeeze(0).detach().cpu().numpy() for tensor in values)
            )
            action_rows.append(int(decision["slot"]))
            return_rows.append(float(hand["reward_bb"]) / 200.0)
            group_rows.append(group)
    tensors = [
        torch.as_tensor(
            np.stack([row[index] for row in input_rows]),
            dtype=torch.float32,
            device=args.device,
        )
        for index in range(8)
    ]
    actions = torch.tensor(action_rows, dtype=torch.long, device=args.device)
    returns = torch.tensor(return_rows, dtype=torch.float32, device=args.device)
    with torch.no_grad():
        logits, values = control(*tensors)
        distribution = torch.distributions.Categorical(
            logits=logits + (1.0 - tensors[6]) * -1e9
        )
        old_log_probs = distribution.log_prob(actions)
        raw_advantages = returns - values.squeeze(1)

    group_names = sorted(set(group_rows))
    group_indices = [
        np.asarray(
            [index for index, value in enumerate(group_rows) if value == group],
            dtype=np.int64,
        )
        for group in group_names
    ]
    group_advantages = []
    for indices in group_indices:
        selected = torch.as_tensor(indices, dtype=torch.long, device=args.device)
        advantages = raw_advantages[selected]
        normalized = (advantages - advantages.mean()) / advantages.std().clamp_min(1e-6)
        full = torch.zeros_like(raw_advantages)
        full[selected] = normalized.clamp(-5.0, 5.0)
        group_advantages.append(full)
    decision_weights = np.asarray([len(indices) for indices in group_indices], dtype=np.float64)
    decision_weights /= decision_weights.sum()

    schedule_rng = np.random.default_rng(args.seed + 200)
    schedules = [
        [
            schedule_rng.choice(indices, size=args.group_batch_size, replace=False)
            for indices in group_indices
        ]
        for _ in range(args.steps)
    ]
    schedule_path = args.out_dir / "training_schedule.jsonl.gz"
    with gzip.open(schedule_path, "xt", encoding="utf-8", newline="\n") as handle:
        for step, selections in enumerate(schedules):
            handle.write(
                json.dumps(
                    {
                        "step": step,
                        "groups": group_names,
                        "indices": [selection.tolist() for selection in selections],
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    control_optimizer, control_rows, control_steps = train_arm(
        control,
        tensors,
        actions,
        old_log_probs,
        returns,
        group_advantages,
        group_indices,
        decision_weights,
        schedules,
        False,
    )
    treatment_optimizer, treatment_rows, treatment_steps = train_arm(
        treatment,
        tensors,
        actions,
        old_log_probs,
        returns,
        group_advantages,
        group_indices,
        decision_weights,
        schedules,
        True,
    )

    checkpoints = {}
    for name, model, optimizer, steps in (
        ("control", control, control_optimizer, control_steps),
        ("treatment", treatment, treatment_optimizer, treatment_steps),
    ):
        path = args.out_dir / f"{name}_residual.pt"
        torch.save(
            {
                "schema": "cardpilot.dual_contract_residual.v1",
                "arm": name,
                "base_checkpoint": str(base_path),
                "base_sha256": base_sha,
                "initial_residual_sha256": initial_sha,
                "hidden": 128,
                "policy_delta_cap": 0.25,
                "residual_state_dict": residual_state(model),
                "optimizer": optimizer.state_dict(),
                "source_training_hands": len(hands),
                "source_transition_rows": len(input_rows),
                "ppo_update_rows": control_rows,
                "steps": args.steps,
                "seed": args.seed,
                "step_metrics": steps,
            },
            path,
        )
        checkpoints[name] = {
            "path": str(path.resolve()),
            "sha256": sha256_path(path),
        }

    evaluation_path = args.out_dir / "evaluation_pairs.jsonl.gz"
    pooled = []
    pooled_seats = [[], []]
    anchor_results = []
    max_deltas = {"control": 0.0, "treatment": 0.0}
    with gzip.open(evaluation_path, "xt", encoding="utf-8", newline="\n") as handle:
        for anchor_index, anchor in enumerate(opponents):
            evaluation_rng = random.Random(
                args.seed + 20_000_003 * (anchor_index + 1)
            )
            deltas, controls, treatments = [], [], []
            seat_deltas = [[], []]
            for pair_index in range(args.pairs_per_anchor):
                deck = list(range(52))
                evaluation_rng.shuffle(deck)
                control_rewards, treatment_rewards = [], []
                for seat in (0, 1):
                    reward, observed = play_candidate_hand(
                        control, base_policy, anchor, deck, seat, args.device
                    )
                    control_rewards.append(reward)
                    max_deltas["control"] = max(max_deltas["control"], observed)
                    reward, observed = play_candidate_hand(
                        treatment, base_policy, anchor, deck, seat, args.device
                    )
                    treatment_rewards.append(reward)
                    max_deltas["treatment"] = max(max_deltas["treatment"], observed)
                    delta = treatment_rewards[-1] - control_rewards[-1]
                    seat_deltas[seat].append(delta)
                    pooled_seats[seat].append(delta)
                control_pair = sum(control_rewards) / 2.0
                treatment_pair = sum(treatment_rewards) / 2.0
                delta = treatment_pair - control_pair
                controls.append(control_pair)
                treatments.append(treatment_pair)
                deltas.append(delta)
                pooled.append(delta)
                handle.write(
                    json.dumps(
                        {
                            "anchor_index": anchor_index,
                            "anchor_sha256": anchor.sha256,
                            "pair_index": pair_index,
                            "deck": deck,
                            "control_rewards_bb": control_rewards,
                            "treatment_rewards_bb": treatment_rewards,
                            "treatment_minus_control_pair_mean_bb": delta,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
            delta_mean, delta_ci = mean_ci95(deltas)
            control_mean, control_ci = mean_ci95(controls)
            treatment_mean, treatment_ci = mean_ci95(treatments)
            anchor_results.append(
                {
                    "anchor_index": anchor_index,
                    "anchor_sha256": anchor.sha256,
                    "pairs": args.pairs_per_anchor,
                    "control_bb100": control_mean * 100.0,
                    "control_ci95_bb100": control_ci * 100.0,
                    "treatment_bb100": treatment_mean * 100.0,
                    "treatment_ci95_bb100": treatment_ci * 100.0,
                    "delta_bb100": delta_mean * 100.0,
                    "delta_ci95_bb100": delta_ci * 100.0,
                    "seat_delta_bb100": [
                        mean_ci95(values)[0] * 100.0 for values in seat_deltas
                    ],
                }
            )
            print(
                f"anchor={anchor_index} treatment_control={delta_mean * 100.0:+.4f} "
                f"+/- {delta_ci * 100.0:.4f}",
                flush=True,
            )

    pooled_mean, pooled_ci = mean_ci95(pooled)
    pooled_seat_means = [mean_ci95(values)[0] * 100.0 for values in pooled_seats]
    positive_anchors = sum(row["delta_bb100"] > 0 for row in anchor_results)
    robust_positive_fraction = float(
        np.mean([row["applied_worst_alignment"] > 0 for row in treatment_steps])
    )
    base_unchanged = all(
        torch.equal(base_state[name], tensor.detach().cpu())
        for name, tensor in base_policy.model.state_dict().items()
    )
    gates = {
        "initial_residual_matches_expected": (
            args.expected_initial_residual_sha is None
            or initial_sha == args.expected_initial_residual_sha
        ),
        "control_treatment_initial_residual_shared": True,
        "positive_delta_on_at_least_two_anchors": positive_anchors >= 2,
        "pooled_delta_positive": pooled_mean > 0,
        "standard10_delta_nonnegative": anchor_results[0]["delta_bb100"] >= 0,
        "both_pooled_seat_deltas_nonnegative": all(
            value >= 0 for value in pooled_seat_means
        ),
        "identical_update_rows": control_rows == treatment_rows,
        "base_state_unchanged": base_unchanged,
        "base_file_hash_unchanged": sha256_path(base_path) == base_sha,
        "both_residual_caps_respected": max(max_deltas.values()) <= 0.250001,
        "robust_positive_worst_alignment_at_least_75pct_steps": robust_positive_fraction
        >= 0.75,
    }
    admit = all(gates.values())
    summary = {
        "schema": "cardpilot.dual_contract_mgda_matched_smoke.v1",
        "status": "COMPLETED",
        "base_sha256": base_sha,
        "opponent_sha256": [opponent.sha256 for opponent in opponents],
        "source_training_sha256": sha256_path(training_path),
        "source_training_hands": len(hands),
        "source_transition_rows": len(input_rows),
        "initial_residual_sha256": initial_sha,
        "steps": args.steps,
        "group_batch_size": args.group_batch_size,
        "control_update_rows": control_rows,
        "treatment_update_rows": treatment_rows,
        "schedule_sha256": sha256_path(schedule_path),
        "control_steps": control_steps,
        "treatment_steps": treatment_steps,
        "robust_positive_worst_alignment_fraction": robust_positive_fraction,
        "evaluation_hands": args.pairs_per_anchor * 2 * 2 * 3,
        "anchors": anchor_results,
        "pooled_delta_bb100": pooled_mean * 100.0,
        "pooled_delta_ci95_bb100": pooled_ci * 100.0,
        "pooled_seat_delta_bb100": pooled_seat_means,
        "positive_anchor_count": positive_anchors,
        "max_abs_residual_logit": max_deltas,
        "checkpoints": checkpoints,
        "gates": gates,
        "admit_independent_new_hand_replication": admit,
        "decision": (
            "ADMIT_MGDA_NEW_HAND_MULTI_SEED_REPLICATION"
            if admit
            else "MGDA_SMOKE_NOT_ADMITTED"
        ),
        "evaluation_evidence_sha256": sha256_path(evaluation_path),
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
