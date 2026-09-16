"""Matched MGDA continuation with Standard10 KL as a seventh objective."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
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
from alpha_holdem.v6_dual_contract_mgda_fresh_curve import (
    collect_chunk,
    summarize_delta,
)
from alpha_holdem.v6_dual_contract_mgda_matched_smoke import (
    aggregate_policy_gradients,
    residual_state,
    set_flat_gradient,
)
from alpha_holdem.v6_dual_contract_residual_training_smoke import (
    mean_ci95,
    play_candidate_hand,
    sha256_path,
    stack_rows,
    state_inputs,
)
from alpha_holdem.v6_mgda_source_boundary_audit import distribution_metrics


def source_constrained_aggregate(
    reward_gradients: np.ndarray,
    decision_weights: np.ndarray,
    source_gradient: np.ndarray,
):
    ordinary = decision_weights @ reward_gradients
    gradients = np.concatenate([reward_gradients, source_gradient[None, :]], axis=0)
    norms = np.linalg.norm(gradients, axis=1)
    if np.any(norms <= 1e-15):
        raise RuntimeError("zero objective gradient in source-constrained aggregation")
    unit = gradients / norms[:, None]
    gram = unit @ unit.T
    objective, _, weights, _ = minimum_norm_simplex(gram)
    direction = weights @ unit
    direction_norm = float(np.linalg.norm(direction))
    ordinary_norm = float(np.linalg.norm(ordinary))
    aggregate = direction * (ordinary_norm / direction_norm)
    alignments = normalized_alignments(unit, aggregate)
    return aggregate, {
        "minimum_norm_objective": float(objective),
        "objective_weights": weights.tolist(),
        "reward_worst_alignment": float(alignments[:6].min()),
        "source_kl_alignment": float(alignments[6]),
        "source_gradient_l2": float(norms[6]),
    }


def train_arm(
    model,
    optimizer,
    transitions,
    steps,
    group_batch_size,
    schedule_seed,
    include_source,
    device,
):
    old_log_probs = torch.tensor(
        [row["log_prob"] for row in transitions], dtype=torch.float32, device=device
    )
    old_values = torch.tensor(
        [row["value"] for row in transitions], dtype=torch.float32, device=device
    )
    returns = torch.tensor(
        [row["return"] for row in transitions], dtype=torch.float32, device=device
    )
    actions = torch.tensor(
        [row["slot"] for row in transitions], dtype=torch.long, device=device
    )
    tensors = [stack_rows(transitions, index, device) for index in range(8)]
    raw_advantages = returns - old_values
    group_names = sorted({row["group"] for row in transitions})
    group_indices = [
        np.asarray(
            [index for index, row in enumerate(transitions) if row["group"] == group],
            dtype=np.int64,
        )
        for group in group_names
    ]
    if len(group_names) != 6 or min(map(len, group_indices)) < group_batch_size:
        raise RuntimeError("insufficient six-group support")
    group_advantages = []
    for indices in group_indices:
        selected = torch.as_tensor(indices, dtype=torch.long, device=device)
        advantage = raw_advantages[selected]
        normalized = (advantage - advantage.mean()) / advantage.std().clamp_min(1e-6)
        full = torch.zeros_like(raw_advantages)
        full[selected] = normalized.clamp(-5.0, 5.0)
        group_advantages.append(full)
    decision_weights = np.asarray(list(map(len, group_indices)), dtype=np.float64)
    decision_weights /= decision_weights.sum()
    rng = np.random.default_rng(schedule_seed)
    schedules = [
        [rng.choice(indices, size=group_batch_size, replace=False) for indices in group_indices]
        for _ in range(steps)
    ]
    parameters = list(model.trainable_parameters())
    metrics = []
    model.train()
    for step, selections in enumerate(schedules):
        reward_gradients = []
        for group_index, selected_cpu in enumerate(selections):
            selected = torch.as_tensor(selected_cpu, dtype=torch.long, device=device)
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
            reward_gradients.append(
                flatten_gradients(-surrogate.mean(), parameters).cpu().double().numpy()
            )
        reward_array = np.stack(reward_gradients)
        combined_cpu = np.concatenate(selections)
        combined = torch.as_tensor(combined_cpu, dtype=torch.long, device=device)
        batch = [tensor[combined] for tensor in tensors]
        logits, values = model(*batch)
        with torch.no_grad():
            base_logits = model.base(batch[0], batch[1], batch[2], batch[6])[0]
            base_log_prob = torch.log_softmax(
                base_logits + (1.0 - batch[6]) * -1e9, dim=1
            )
            base_prob = base_log_prob.exp()
        candidate_log_prob = torch.log_softmax(
            logits + (1.0 - batch[6]) * -1e9, dim=1
        )
        source_kl = (
            base_prob * (base_log_prob - candidate_log_prob)
        ).sum(dim=1).mean()
        source_gradient = flatten_gradients(source_kl, parameters).cpu().double().numpy()
        if include_source:
            policy_gradient, geometry = source_constrained_aggregate(
                reward_array, decision_weights, source_gradient
            )
        else:
            policy_gradient, reward_geometry = aggregate_policy_gradients(
                reward_array, decision_weights, True
            )
            reward_unit = reward_array / np.linalg.norm(reward_array, axis=1)[:, None]
            source_alignment = float(
                source_gradient
                @ policy_gradient
                / max(np.linalg.norm(source_gradient) * np.linalg.norm(policy_gradient), 1e-15)
            )
            geometry = {
                "reward_worst_alignment": reward_geometry["applied_worst_alignment"],
                "source_kl_alignment": source_alignment,
                "source_gradient_l2": float(np.linalg.norm(source_gradient)),
                "minimum_norm_objective": reward_geometry["minimum_norm_objective"],
                "objective_weights": reward_geometry["robust_weights"],
            }
        # source_gradient consumed the source-KL forward graph.  Use an
        # independent forward for the shared value/entropy gradient so neither
        # objective depends on retain_graph side effects.
        auxiliary_logits, auxiliary_values = model(*batch)
        distribution = torch.distributions.Categorical(
            logits=auxiliary_logits + (1.0 - batch[6]) * -1e9
        )
        value_loss = (
            auxiliary_values.squeeze(1) - returns[combined]
        ).square().mean()
        entropy = distribution.entropy().mean()
        auxiliary_gradient = flatten_gradients(
            value_loss - 0.005 * entropy, parameters
        )
        total_gradient = torch.from_numpy(policy_gradient).to(
            device=device, dtype=auxiliary_gradient.dtype
        ) + auxiliary_gradient
        optimizer.zero_grad(set_to_none=True)
        set_flat_gradient(parameters, total_gradient)
        torch.nn.utils.clip_grad_norm_(parameters, 1.0)
        optimizer.step()
        metrics.append(
            {
                "step": step,
                "source_kl": float(source_kl.detach()),
                "value_loss": float(value_loss.detach()),
                "entropy": float(entropy.detach()),
                **geometry,
            }
        )
    model.eval()
    return metrics, schedules


def panel_metric(model, base_policy, panel_path, device):
    panel = [json.loads(line) for line in gzip.open(panel_path, "rt", encoding="utf-8")]
    inputs = []
    for row in panel:
        state = reconstruct(row["deck"], row["action_prefix"])
        tensors, _, _ = state_inputs(base_policy, state, device)
        inputs.append(tuple(tensor.squeeze(0).cpu().numpy() for tensor in tensors))
    stacked = [
        torch.as_tensor(
            np.stack([row[index] for row in inputs]), dtype=torch.float32, device=device
        )
        for index in range(8)
    ]
    with torch.no_grad():
        base_logits = base_policy.model(stacked[0], stacked[1], stacked[2], stacked[6])[0]
        candidate_logits = model(*stacked)[0]
        agreement, kl, mean_delta, max_delta = distribution_metrics(
            base_logits, candidate_logits, stacked[6]
        )
    return {
        "states": len(panel),
        "greedy_agreement": float(agreement.float().mean()),
        "greedy_disagreement": float(1.0 - agreement.float().mean()),
        "mean_kl_base_to_candidate": float(kl.mean()),
        "p95_kl_base_to_candidate": float(torch.quantile(kl, 0.95)),
        "mean_abs_legal_logit_delta": float(mean_delta.mean()),
        "maximum_abs_legal_logit_delta": float(max_delta.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--opponent", action="append", type=Path, required=True)
    parser.add_argument("--start-checkpoint", type=Path, required=True)
    parser.add_argument("--state-panel", type=Path, required=True)
    parser.add_argument("--continuation-hands", type=int, required=True)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--group-batch-size", type=int, required=True)
    parser.add_argument("--pairs-per-anchor", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if len(args.opponent) != 3:
        parser.error("exactly three opponents required")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()

    base_path = args.base_checkpoint.resolve()
    start_path = args.start_checkpoint.resolve()
    panel_path = args.state_panel.resolve()
    base_sha = sha256_path(base_path)
    start_sha = sha256_path(start_path)
    base_policy = load_policy(base_path, args.device)
    opponents = [load_policy(path.resolve(), args.device) for path in args.opponent]
    start = torch.load(start_path, map_location=args.device, weights_only=False)
    if start["base_sha256"] != base_sha or start["dose_hands"] != 8192:
        raise RuntimeError("invalid continuation checkpoint lineage")
    parent_summary = json.loads((start_path.parent / "summary.json").read_text(encoding="utf-8"))
    expected_sha = next(
        row["sha256"] for row in parent_summary["checkpoints"] if Path(row["path"]).name == start_path.name
    )
    if expected_sha != start_sha:
        raise RuntimeError("start checkpoint hash mismatch")

    models = {}
    optimizers = {}
    for arm in ("control", "treatment"):
        model = DualContractResidualPolicy(
            base_policy.model, hidden=128, policy_delta_cap=0.25
        ).to(args.device).eval()
        model.load_state_dict(start["residual_state_dict"], strict=False)
        optimizer = torch.optim.Adam(model.trainable_parameters(), lr=3e-4)
        optimizer.load_state_dict(start["optimizer"])
        models[arm] = model
        optimizers[arm] = optimizer
    shared_start_sha = residual_state_digest(models["control"])
    if residual_state_digest(models["treatment"]) != shared_start_sha:
        raise RuntimeError("cloned arms do not share start state")

    collected = {}
    hand_rows_by_arm = {}
    for arm in ("control", "treatment"):
        transitions, hand_rows = collect_chunk(
            models[arm],
            base_policy,
            opponents,
            args.seed,
            8192,
            args.continuation_hands,
            arm,
        )
        collected[arm] = transitions
        hand_rows_by_arm[arm] = hand_rows
    signatures = {
        arm: [(row["reward_bb"], row["hero_decisions"]) for row in rows]
        for arm, rows in hand_rows_by_arm.items()
    }
    if signatures["control"] != signatures["treatment"]:
        raise RuntimeError("shared-start continuation evidence differs")
    training_path = args.out_dir / "training_hands.jsonl.gz"
    with gzip.open(training_path, "xt", encoding="utf-8", newline="\n") as handle:
        for arm in ("control", "treatment"):
            for row in hand_rows_by_arm[arm]:
                handle.write(json.dumps(row, sort_keys=True) + "\n")

    arm_metrics = {}
    schedules = {}
    checkpoints = {}
    for arm in ("control", "treatment"):
        metrics, schedule = train_arm(
            models[arm],
            optimizers[arm],
            collected[arm],
            args.steps,
            args.group_batch_size,
            args.seed + 300,
            arm == "treatment",
            args.device,
        )
        arm_metrics[arm] = metrics
        schedules[arm] = schedule
        checkpoint_path = args.out_dir / f"{arm}_residual_12288.pt"
        torch.save(
            {
                "schema": "cardpilot.dual_contract_residual.v1",
                "arm": arm,
                "base_checkpoint": str(base_path),
                "base_sha256": base_sha,
                "start_checkpoint": str(start_path),
                "start_checkpoint_sha256": start_sha,
                "shared_start_residual_sha256": shared_start_sha,
                "dose_hands": 12288,
                "new_environment_hands": args.continuation_hands,
                "residual_state_dict": residual_state(models[arm]),
                "optimizer": optimizers[arm].state_dict(),
                "step_metrics": metrics,
            },
            checkpoint_path,
        )
        checkpoints[arm] = {
            "path": str(checkpoint_path.resolve()),
            "sha256": sha256_path(checkpoint_path),
        }
    schedule_path = args.out_dir / "update_schedules.json"
    serializable_schedules = {
        arm: [
            [selection.tolist() for selection in step]
            for step in arm_schedules
        ]
        for arm, arm_schedules in schedules.items()
    }
    schedule_path.write_text(
        json.dumps(serializable_schedules, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    panel_metrics = {
        arm: panel_metric(model, base_policy, panel_path, args.device)
        for arm, model in models.items()
    }
    evaluation_path = args.out_dir / "evaluation_pairs.jsonl.gz"
    evaluation_rows = []
    max_deltas = {"control": 0.0, "treatment": 0.0}
    with gzip.open(evaluation_path, "xt", encoding="utf-8", newline="\n") as handle:
        for anchor_index, anchor in enumerate(opponents):
            rng = random.Random(args.seed + 40_000_009 * (anchor_index + 1))
            for pair_index in range(args.pairs_per_anchor):
                deck = list(range(52))
                rng.shuffle(deck)
                rewards = {"control": [], "treatment": []}
                for seat in (0, 1):
                    for arm in ("control", "treatment"):
                        reward, observed = play_candidate_hand(
                            models[arm], base_policy, anchor, deck, seat, args.device
                        )
                        rewards[arm].append(reward)
                        max_deltas[arm] = max(max_deltas[arm], observed)
                seat_delta = [
                    rewards["treatment"][seat] - rewards["control"][seat]
                    for seat in (0, 1)
                ]
                row = {
                    "anchor_index": anchor_index,
                    "anchor_sha256": anchor.sha256,
                    "pair_index": pair_index,
                    "deck": deck,
                    "control_rewards_bb": rewards["control"],
                    "treatment_rewards_bb": rewards["treatment"],
                    "seat_delta_bb": seat_delta,
                    "delta_bb": sum(seat_delta) / 2.0,
                }
                evaluation_rows.append(row)
                handle.write(json.dumps(row, sort_keys=True) + "\n")
            selected = [row for row in evaluation_rows if row["anchor_index"] == anchor_index]
            mean, half = mean_ci95([row["delta_bb"] for row in selected])
            print(f"anchor={anchor_index} delta={mean*100:+.4f} +/- {half*100:.4f}", flush=True)

    evaluation = summarize_delta(evaluation_rows)
    treatment_reward_alignment_fraction = float(
        np.mean([row["reward_worst_alignment"] > 0 for row in arm_metrics["treatment"]])
    )
    treatment_source_alignment_fraction = float(
        np.mean([row["source_kl_alignment"] > 0 for row in arm_metrics["treatment"]])
    )
    gates = {
        "shared_start_checkpoint_and_optimizer": True,
        "identical_continuation_evidence": signatures["control"] == signatures["treatment"],
        "treatment_reward_alignment_at_least_75pct": treatment_reward_alignment_fraction >= 0.75,
        "treatment_source_alignment_at_least_75pct": treatment_source_alignment_fraction >= 0.75,
        "treatment_panel_kl_no_greater_than_control": panel_metrics["treatment"]["mean_kl_base_to_candidate"] <= panel_metrics["control"]["mean_kl_base_to_candidate"],
        "treatment_panel_agreement_within_half_point_control": panel_metrics["treatment"]["greedy_agreement"] >= panel_metrics["control"]["greedy_agreement"] - 0.005,
        "pooled_delta_positive": evaluation["pooled_delta_bb100"] > 0,
        "standard10_delta_nonnegative": evaluation["anchors"][0]["delta_bb100"] >= 0,
        "positive_delta_on_at_least_two_anchors": sum(row["delta_bb100"] > 0 for row in evaluation["anchors"]) >= 2,
        "both_seat_deltas_nonnegative": all(row["delta_bb100"] >= 0 for row in evaluation["seats"]),
        "base_file_hash_unchanged": sha256_path(base_path) == base_sha,
        "both_residual_caps_respected": max(max_deltas.values()) <= 0.250001,
    }
    admit = all(gates.values())
    summary = {
        "schema": "cardpilot.mgda_source_objective_continuation.v1",
        "status": "COMPLETED",
        "base_sha256": base_sha,
        "start_checkpoint_sha256": start_sha,
        "shared_start_residual_sha256": shared_start_sha,
        "state_panel_sha256": sha256_path(panel_path),
        "actual_environment_training_hands": sum(len(rows) for rows in hand_rows_by_arm.values()),
        "transition_rows": {arm: len(rows) for arm, rows in collected.items()},
        "training_evidence_sha256": sha256_path(training_path),
        "schedule_sha256": sha256_path(schedule_path),
        "arm_metrics": arm_metrics,
        "treatment_reward_alignment_fraction": treatment_reward_alignment_fraction,
        "treatment_source_alignment_fraction": treatment_source_alignment_fraction,
        "panel_metrics": panel_metrics,
        "evaluation_hands": len(evaluation_rows) * 4,
        "evaluation": evaluation,
        "evaluation_evidence_sha256": sha256_path(evaluation_path),
        "max_abs_residual_logit": max_deltas,
        "checkpoints": checkpoints,
        "gates": gates,
        "admit_seed1_replication": admit,
        "decision": "ADMIT_SOURCE_OBJECTIVE_SEED1_REPLICATION" if admit else "REJECT_SOURCE_OBJECTIVE_FORMULATION",
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
