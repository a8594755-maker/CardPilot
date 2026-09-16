"""Fresh two-arm MGDA residual learning curve with multiple seeds."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.dual_contract_residual_v6 import DualContractResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import (
    action_prefix,
    decide as legacy_decide,
    load_policy,
)
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_dual_contract_gradient_conflict_audit import (
    flatten_gradients,
    residual_state_digest,
)
from alpha_holdem.v6_dual_contract_mgda_matched_smoke import (
    aggregate_policy_gradients,
    residual_state,
    set_flat_gradient,
)
from alpha_holdem.v6_dual_contract_residual_training_smoke import (
    mean_ci95,
    play_candidate_hand,
    residual_decide,
    sha256_path,
    stack_rows,
)


def collect_chunk(
    model,
    base_policy,
    opponents,
    seed: int,
    hand_offset: int,
    hand_count: int,
    arm: str,
):
    transitions = []
    hand_evidence = []
    for local_hand in range(hand_count):
        hand_index = hand_offset + local_hand
        seed_base = seed * 1_000_003 + hand_index * 101
        deck_rng = random.Random(seed_base + 11)
        hero_rng = random.Random(seed_base + 23)
        opponent_rng = random.Random(seed_base + 37)
        deck = list(range(52))
        deck_rng.shuffle(deck)
        state = ChipState.new(deck)
        hero_seat = hand_index % 2
        opponent_index = hand_index % len(opponents)
        opponent = opponents[opponent_index]
        hand_rows = []
        decisions = []
        while not state.terminal:
            if state.actor == hero_seat:
                prefix = action_prefix(state)
                action, metadata = residual_decide(
                    model,
                    base_policy,
                    state,
                    next(model.parameters()).device,
                    uniform=hero_rng.random(),
                )
                metadata["group"] = f"opponent{opponent_index}_seat{hero_seat}"
                hand_rows.append(metadata)
                decisions.append({"action_prefix": prefix, "slot": metadata["slot"]})
            else:
                action, _ = legacy_decide(
                    opponent,
                    state,
                    uniform=opponent_rng.random(),
                    policy_mode="sample",
                )
            state = apply_incr(state, action)
        reward_bb = float(state.payoffs()[hero_seat]) / 100.0
        for row in hand_rows:
            row["return"] = reward_bb / 200.0
            transitions.append(row)
        hand_evidence.append(
            {
                "arm": arm,
                "hand_index": hand_index,
                "deck": deck,
                "hero_seat": hero_seat,
                "opponent_index": opponent_index,
                "opponent_sha256": opponent.sha256,
                "reward_bb": reward_bb,
                "hero_decisions": decisions,
            }
        )
    return transitions, hand_evidence


def train_chunk(
    model,
    optimizer,
    transitions,
    steps,
    group_batch_size,
    schedule_seed,
    robust,
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
    if len(group_names) != 6:
        raise RuntimeError(f"expected six groups, got {group_names}")
    group_indices = [
        np.asarray(
            [index for index, row in enumerate(transitions) if row["group"] == group],
            dtype=np.int64,
        )
        for group in group_names
    ]
    if min(len(indices) for indices in group_indices) < group_batch_size:
        raise RuntimeError("group batch exceeds smallest group support")
    group_advantages = []
    for indices in group_indices:
        selected = torch.as_tensor(indices, dtype=torch.long, device=device)
        advantages = raw_advantages[selected]
        normalized = (advantages - advantages.mean()) / advantages.std().clamp_min(1e-6)
        full = torch.zeros_like(raw_advantages)
        full[selected] = normalized.clamp(-5.0, 5.0)
        group_advantages.append(full)
    decision_weights = np.asarray(
        [len(indices) for indices in group_indices], dtype=np.float64
    )
    decision_weights /= decision_weights.sum()
    schedule_rng = np.random.default_rng(schedule_seed)
    schedules = [
        [
            schedule_rng.choice(indices, size=group_batch_size, replace=False)
            for indices in group_indices
        ]
        for _ in range(steps)
    ]

    parameters = list(model.trainable_parameters())
    metrics = []
    update_rows = 0
    model.train()
    for step, selections in enumerate(schedules):
        group_gradients = []
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
            group_gradients.append(
                flatten_gradients(-surrogate.mean(), parameters).cpu().double().numpy()
            )
        policy_gradient, geometry = aggregate_policy_gradients(
            np.stack(group_gradients), decision_weights, robust
        )
        combined_cpu = np.concatenate(selections)
        combined = torch.as_tensor(combined_cpu, dtype=torch.long, device=device)
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
        total_gradient = torch.from_numpy(policy_gradient).to(
            device=device, dtype=auxiliary_gradient.dtype
        ) + auxiliary_gradient
        optimizer.zero_grad(set_to_none=True)
        set_flat_gradient(parameters, total_gradient)
        preclip_norm = float(torch.linalg.vector_norm(total_gradient))
        torch.nn.utils.clip_grad_norm_(parameters, 1.0)
        optimizer.step()
        update_rows += len(combined_cpu)
        metrics.append(
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
    schedule = [
        {
            "step": step,
            "groups": group_names,
            "indices": [selection.tolist() for selection in selections],
        }
        for step, selections in enumerate(schedules)
    ]
    return update_rows, metrics, schedule


def summarize_delta(rows):
    values = [row["delta_bb"] for row in rows]
    mean, half = mean_ci95(values)
    anchors = []
    for anchor_index in range(3):
        selected = [row for row in rows if row["anchor_index"] == anchor_index]
        anchor_mean, anchor_half = mean_ci95([row["delta_bb"] for row in selected])
        anchors.append(
            {
                "anchor_index": anchor_index,
                "pairs": len(selected),
                "delta_bb100": anchor_mean * 100.0,
                "delta_ci95_bb100": anchor_half * 100.0,
            }
        )
    seats = []
    for seat in (0, 1):
        seat_mean, seat_half = mean_ci95([row["seat_delta_bb"][seat] for row in rows])
        seats.append(
            {
                "seat": seat,
                "delta_bb100": seat_mean * 100.0,
                "delta_ci95_bb100": seat_half * 100.0,
            }
        )
    return {
        "pairs": len(rows),
        "pooled_delta_bb100": mean * 100.0,
        "pooled_delta_ci95_bb100": half * 100.0,
        "anchors": anchors,
        "seats": seats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--opponent", action="append", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--seeds", type=int, required=True)
    parser.add_argument("--hands-per-dose", type=int, required=True)
    parser.add_argument("--doses", type=int, required=True)
    parser.add_argument("--steps-per-dose", type=int, required=True)
    parser.add_argument("--group-batch-size", type=int, required=True)
    parser.add_argument("--pairs-per-anchor", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if len(args.opponent) != 3:
        parser.error("exactly three opponents required")
    if args.seeds < 2 or args.doses < 2 or args.hands_per_dose < 4096:
        parser.error("fresh curve requires >=2 seeds, >=2 doses, and >=4096 hands/dose")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()

    base_path = args.base_checkpoint.resolve()
    base_sha = sha256_path(base_path)
    base_policy = load_policy(base_path, args.device)
    opponents = [load_policy(path.resolve(), args.device) for path in args.opponent]
    base_state = {
        name: tensor.detach().cpu().clone()
        for name, tensor in base_policy.model.state_dict().items()
    }
    training_path = args.out_dir / "training_hands.jsonl.gz"
    schedule_path = args.out_dir / "update_schedules.jsonl.gz"
    checkpoint_rows = []
    training_rows = []
    all_seed_training = []
    with gzip.open(training_path, "xt", encoding="utf-8", newline="\n") as training_file, gzip.open(
        schedule_path, "xt", encoding="utf-8", newline="\n"
    ) as schedule_file:
        for seed_index in range(args.seeds):
            run_seed = args.seed + seed_index * 10_007
            torch.manual_seed(run_seed)
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
                raise RuntimeError("initial arm mismatch")
            optimizers = {
                "control": torch.optim.Adam(control.trainable_parameters(), lr=3e-4),
                "treatment": torch.optim.Adam(treatment.trainable_parameters(), lr=3e-4),
            }
            models = {"control": control, "treatment": treatment}
            seed_training = {
                "seed_index": seed_index,
                "seed": run_seed,
                "initial_residual_sha256": initial_sha,
                "doses": [],
            }
            for dose_index in range(args.doses):
                hand_offset = dose_index * args.hands_per_dose
                dose_hands = (dose_index + 1) * args.hands_per_dose
                dose_row = {"dose_hands": dose_hands, "arms": {}}
                first_arm_evidence = None
                initial_arm_evidence_identical = None
                for arm in ("control", "treatment"):
                    transitions, hand_rows = collect_chunk(
                        models[arm],
                        base_policy,
                        opponents,
                        run_seed,
                        hand_offset,
                        args.hands_per_dose,
                        arm,
                    )
                    if first_arm_evidence is None:
                        first_arm_evidence = hand_rows
                    elif dose_index == 0:
                        first_signature = [
                            (row["reward_bb"], row["hero_decisions"])
                            for row in first_arm_evidence
                        ]
                        second_signature = [
                            (row["reward_bb"], row["hero_decisions"])
                            for row in hand_rows
                        ]
                        if first_signature != second_signature:
                            raise RuntimeError("identical initial arms collected different first-dose data")
                        initial_arm_evidence_identical = True
                    for row in hand_rows:
                        row["seed_index"] = seed_index
                        row["dose_index"] = dose_index
                        training_file.write(json.dumps(row, sort_keys=True) + "\n")
                    update_rows, step_metrics, schedules = train_chunk(
                        models[arm],
                        optimizers[arm],
                        transitions,
                        args.steps_per_dose,
                        args.group_batch_size,
                        run_seed + dose_index * 1009,
                        arm == "treatment",
                        args.device,
                    )
                    for schedule in schedules:
                        schedule_file.write(
                            json.dumps(
                                {
                                    "seed_index": seed_index,
                                    "dose_index": dose_index,
                                    "arm": arm,
                                    **schedule,
                                },
                                sort_keys=True,
                            )
                            + "\n"
                        )
                    checkpoint_path = (
                        args.out_dir / f"seed{seed_index}_{arm}_{dose_hands}.pt"
                    )
                    torch.save(
                        {
                            "schema": "cardpilot.dual_contract_residual.v1",
                            "arm": arm,
                            "seed_index": seed_index,
                            "seed": run_seed,
                            "dose_hands": dose_hands,
                            "base_checkpoint": str(base_path),
                            "base_sha256": base_sha,
                            "initial_residual_sha256": initial_sha,
                            "hidden": 128,
                            "policy_delta_cap": 0.25,
                            "residual_state_dict": residual_state(models[arm]),
                            "optimizer": optimizers[arm].state_dict(),
                            "new_environment_hands": dose_hands,
                            "chunk_transition_rows": len(transitions),
                            "chunk_update_rows": update_rows,
                            "step_metrics": step_metrics,
                        },
                        checkpoint_path,
                    )
                    checkpoint_rows.append(
                        {
                            "seed_index": seed_index,
                            "arm": arm,
                            "dose_hands": dose_hands,
                            "path": str(checkpoint_path.resolve()),
                            "sha256": sha256_path(checkpoint_path),
                        }
                    )
                    positive_fraction = float(
                        np.mean(
                            [
                                row["applied_worst_alignment"] > 0
                                for row in step_metrics
                            ]
                        )
                    )
                    dose_row["arms"][arm] = {
                        "environment_hands": len(hand_rows),
                        "transitions": len(transitions),
                        "update_rows": update_rows,
                        "positive_worst_alignment_fraction": positive_fraction,
                    }
                    training_rows.extend(hand_rows)
                    print(
                        f"seed={seed_index} dose={dose_hands} arm={arm} "
                        f"hands={len(hand_rows)} transitions={len(transitions)} "
                        f"positive_geometry={positive_fraction:.3f}",
                        flush=True,
                    )
                dose_row["first_dose_arm_evidence_identical"] = (
                    initial_arm_evidence_identical
                )
                seed_training["doses"].append(dose_row)
            all_seed_training.append(seed_training)

    evaluation_path = args.out_dir / "evaluation_pairs.jsonl.gz"
    evaluation_rows = []
    max_deltas = {}
    with gzip.open(evaluation_path, "xt", encoding="utf-8", newline="\n") as handle:
        for seed_index in range(args.seeds):
            run_seed = args.seed + seed_index * 10_007
            for dose_index in range(args.doses):
                dose_hands = (dose_index + 1) * args.hands_per_dose
                models = {}
                for arm in ("control", "treatment"):
                    checkpoint_path = args.out_dir / f"seed{seed_index}_{arm}_{dose_hands}.pt"
                    checkpoint = torch.load(checkpoint_path, map_location=args.device, weights_only=False)
                    model = DualContractResidualPolicy(
                        base_policy.model, hidden=128, policy_delta_cap=0.25
                    ).to(args.device).eval()
                    model.load_state_dict(checkpoint["residual_state_dict"], strict=False)
                    models[arm] = model
                    max_deltas[f"seed{seed_index}_{arm}_{dose_hands}"] = 0.0
                for anchor_index, anchor in enumerate(opponents):
                    evaluation_rng = random.Random(
                        run_seed + 30_000_007 * (anchor_index + 1)
                    )
                    for pair_index in range(args.pairs_per_anchor):
                        deck = list(range(52))
                        evaluation_rng.shuffle(deck)
                        rewards = {"control": [], "treatment": []}
                        for seat in (0, 1):
                            for arm in ("control", "treatment"):
                                reward, observed = play_candidate_hand(
                                    models[arm],
                                    base_policy,
                                    anchor,
                                    deck,
                                    seat,
                                    args.device,
                                )
                                rewards[arm].append(reward)
                                key = f"seed{seed_index}_{arm}_{dose_hands}"
                                max_deltas[key] = max(max_deltas[key], observed)
                        seat_delta = [
                            rewards["treatment"][seat] - rewards["control"][seat]
                            for seat in (0, 1)
                        ]
                        row = {
                            "seed_index": seed_index,
                            "dose_hands": dose_hands,
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
                selected = [
                    row
                    for row in evaluation_rows
                    if row["seed_index"] == seed_index
                    and row["dose_hands"] == dose_hands
                ]
                interim = summarize_delta(selected)
                print(
                    f"seed={seed_index} dose={dose_hands} "
                    f"pooled_delta={interim['pooled_delta_bb100']:+.4f} "
                    f"+/- {interim['pooled_delta_ci95_bb100']:.4f}",
                    flush=True,
                )

    dose_results = []
    seed_dose_results = []
    for dose_index in range(args.doses):
        dose_hands = (dose_index + 1) * args.hands_per_dose
        selected = [row for row in evaluation_rows if row["dose_hands"] == dose_hands]
        dose_results.append({"dose_hands": dose_hands, **summarize_delta(selected)})
        for seed_index in range(args.seeds):
            seed_selected = [
                row for row in selected if row["seed_index"] == seed_index
            ]
            seed_dose_results.append(
                {
                    "seed_index": seed_index,
                    "dose_hands": dose_hands,
                    **summarize_delta(seed_selected),
                }
            )
    first_dose = args.hands_per_dose
    last_dose = args.hands_per_dose * args.doses
    lookup = {
        (row["seed_index"], row["anchor_index"], row["pair_index"], row["dose_hands"]): row
        for row in evaluation_rows
    }
    slopes = []
    for row in evaluation_rows:
        if row["dose_hands"] != first_dose:
            continue
        later = lookup[
            (row["seed_index"], row["anchor_index"], row["pair_index"], last_dose)
        ]
        slopes.append(later["delta_bb"] - row["delta_bb"])
    slope_mean, slope_half = mean_ci95(slopes)
    final_result = dose_results[-1]
    final_seed_rows = [
        row for row in seed_dose_results if row["dose_hands"] == last_dose
    ]
    geometry_fractions = [
        dose["arms"]["treatment"]["positive_worst_alignment_fraction"]
        for seed in all_seed_training
        for dose in seed["doses"]
    ]
    actual_training_hands = len(training_rows)
    planned_training_hands = (
        args.seeds * 2 * args.hands_per_dose * args.doses
    )
    gates = {
        "actual_training_hands_exact": actual_training_hands == planned_training_hands,
        "base_state_unchanged": all(
            torch.equal(base_state[name], tensor.detach().cpu())
            for name, tensor in base_policy.model.state_dict().items()
        ),
        "base_file_hash_unchanged": sha256_path(base_path) == base_sha,
        "all_residual_caps_respected": max(max_deltas.values()) <= 0.250001,
        "all_seed_doses_geometry_at_least_75pct": all(
            value >= 0.75 for value in geometry_fractions
        ),
        "both_final_seed_pooled_deltas_positive": all(
            row["pooled_delta_bb100"] > 0 for row in final_seed_rows
        ),
        "final_combined_pooled_delta_positive": final_result[
            "pooled_delta_bb100"
        ]
        > 0,
        "final_at_least_two_anchor_points_positive": sum(
            row["delta_bb100"] > 0 for row in final_result["anchors"]
        )
        >= 2,
        "final_standard10_point_nonnegative": final_result["anchors"][0][
            "delta_bb100"
        ]
        >= 0,
        "final_both_seat_points_nonnegative": all(
            row["delta_bb100"] >= 0 for row in final_result["seats"]
        ),
        "combined_4k_to_8k_slope_nonnegative": slope_mean >= 0,
    }
    admit = all(gates.values())
    summary = {
        "schema": "cardpilot.dual_contract_mgda_fresh_curve.v1",
        "status": "COMPLETED",
        "base_sha256": base_sha,
        "opponent_sha256": [opponent.sha256 for opponent in opponents],
        "actual_environment_training_hands": actual_training_hands,
        "planned_environment_training_hands": planned_training_hands,
        "training_evidence_sha256": sha256_path(training_path),
        "schedule_evidence_sha256": sha256_path(schedule_path),
        "evaluation_hands": len(evaluation_rows) * 4,
        "evaluation_evidence_sha256": sha256_path(evaluation_path),
        "seed_training": all_seed_training,
        "checkpoints": checkpoint_rows,
        "seed_dose_results": seed_dose_results,
        "dose_results": dose_results,
        "paired_first_to_last_slope_bb100": slope_mean * 100.0,
        "paired_first_to_last_slope_ci95_bb100": slope_half * 100.0,
        "max_abs_residual_logit": max_deltas,
        "gates": gates,
        "admit_next_geometric_scale": admit,
        "decision": (
            "ADMIT_MGDA_NEXT_GEOMETRIC_SCALE"
            if admit
            else "HOLD_MGDA_FRESH_SCALE"
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
