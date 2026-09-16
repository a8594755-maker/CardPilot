"""Matched global versus opponent-seat RMS residual PPO on one frozen dataset."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
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
    action_prefix, decide as legacy_decide, load_policy,
)
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_dual_contract_residual_training_smoke import (
    mean_ci95, play_candidate_hand, residual_decide, sha256_path, stack_rows,
)


def residual_state(model):
    return {
        name: tensor.detach().cpu().clone()
        for name, tensor in model.state_dict().items()
        if not name.startswith("base.")
    }


def state_digest(state):
    digest = hashlib.sha256()
    for name in sorted(state):
        digest.update(name.encode())
        digest.update(state[name].contiguous().numpy().tobytes())
    return digest.hexdigest()


def train_arm(model, tensors, actions, old_log_probs, returns, advantages, orders):
    parameters = list(model.trainable_parameters())
    optimizer = torch.optim.Adam(parameters, lr=3e-4)
    losses = []
    rows = 0
    model.train()
    for order in orders:
        for start in range(0, len(order), 512):
            selected = torch.as_tensor(order[start:start + 512], device=actions.device)
            batch = [tensor[selected] for tensor in tensors]
            logits, values = model(*batch)
            distribution = torch.distributions.Categorical(
                logits=logits + (1.0 - batch[6]) * -1e9
            )
            log_probs = distribution.log_prob(actions[selected])
            ratio = torch.exp(log_probs - old_log_probs[selected])
            surrogate = torch.minimum(
                ratio * advantages[selected],
                ratio.clamp(0.8, 1.2) * advantages[selected],
            )
            policy_loss = -surrogate.mean()
            value_loss = (values.squeeze(1) - returns[selected]).square().mean()
            loss = policy_loss + value_loss - 0.005 * distribution.entropy().mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(parameters, 1.0)
            optimizer.step()
            losses.append(float(loss.detach()))
            rows += len(selected)
    model.eval()
    return optimizer, rows, float(np.mean(losses))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--opponent", action="append", type=Path, required=True)
    parser.add_argument("--training-hands", type=int, required=True)
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
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    started = time.time()
    base_path = args.base_checkpoint.resolve()
    base_sha = sha256_path(base_path)
    base_policy = load_policy(base_path, args.device)
    opponents = [load_policy(path, args.device) for path in args.opponent]
    collector = DualContractResidualPolicy(
        base_policy.model, hidden=128, policy_delta_cap=0.25
    ).to(args.device).eval()
    initial_state = residual_state(collector)
    initial_sha = state_digest(initial_state)
    base_state = {
        name: tensor.detach().cpu().clone()
        for name, tensor in collector.base.state_dict().items()
    }

    transitions = []
    training_path = args.out_dir / "training_hands.jsonl.gz"
    with gzip.open(training_path, "xt", encoding="utf-8", newline="\n") as evidence:
        for hand_index in range(args.training_hands):
            deck = list(range(52))
            rng.shuffle(deck)
            state = ChipState.new(deck)
            seat = hand_index % 2
            opponent_index = hand_index % 3
            opponent = opponents[opponent_index]
            hand_rows = []
            decision_evidence = []
            while not state.terminal:
                if state.actor == seat:
                    prefix = action_prefix(state)
                    action, metadata = residual_decide(
                        collector, base_policy, state, args.device, uniform=rng.random()
                    )
                    metadata["group"] = f"opponent{opponent_index}_seat{seat}"
                    hand_rows.append(metadata)
                    decision_evidence.append({"action_prefix": prefix, "slot": metadata["slot"]})
                else:
                    action, _ = legacy_decide(
                        opponent, state, uniform=rng.random(), policy_mode="sample"
                    )
                state = apply_incr(state, action)
            reward_bb = float(state.payoffs()[seat]) / 100.0
            for row in hand_rows:
                row["return"] = reward_bb / 200.0
                transitions.append(row)
            evidence.write(json.dumps({
                "hand_index": hand_index, "deck": deck, "hero_seat": seat,
                "opponent_index": opponent_index, "opponent_sha256": opponent.sha256,
                "reward_bb": reward_bb, "hero_decisions": decision_evidence,
            }, sort_keys=True) + "\n")
            if (hand_index + 1) % 1024 == 0:
                print(f"training_hands={hand_index+1} transitions={len(transitions)}", flush=True)

    old_log_probs = torch.tensor([row["log_prob"] for row in transitions], dtype=torch.float32, device=args.device)
    old_values = torch.tensor([row["value"] for row in transitions], dtype=torch.float32, device=args.device)
    returns = torch.tensor([row["return"] for row in transitions], dtype=torch.float32, device=args.device)
    actions = torch.tensor([row["slot"] for row in transitions], dtype=torch.long, device=args.device)
    raw_advantages = returns - old_values
    global_advantages = (
        raw_advantages - raw_advantages.mean()
    ) / raw_advantages.std().clamp_min(1e-6)
    group_advantages = torch.empty_like(raw_advantages)
    group_metrics = []
    groups = [row["group"] for row in transitions]
    for group in sorted(set(groups)):
        selected = torch.tensor(
            [index for index, value in enumerate(groups) if value == group],
            dtype=torch.long, device=args.device,
        )
        values = raw_advantages[selected]
        group_advantages[selected] = (values - values.mean()) / values.std().clamp_min(1e-6)
        group_metrics.append({
            "group": group, "decisions": len(selected),
            "raw_advantage_mean": float(values.mean()),
            "raw_advantage_std": float(values.std()),
        })
    group_advantages.clamp_(-5.0, 5.0)
    tensors = [stack_rows(transitions, index, args.device) for index in range(8)]
    order_rng = np.random.default_rng(args.seed + 100)
    orders = []
    for _ in range(4):
        order = np.arange(len(transitions))
        order_rng.shuffle(order)
        orders.append(order)

    control = collector
    treatment = DualContractResidualPolicy(
        base_policy.model, hidden=128, policy_delta_cap=0.25
    ).to(args.device)
    treatment.load_state_dict(initial_state, strict=False)
    control_optimizer, control_rows, control_loss = train_arm(
        control, tensors, actions, old_log_probs, returns, global_advantages, orders
    )
    treatment_optimizer, treatment_rows, treatment_loss = train_arm(
        treatment, tensors, actions, old_log_probs, returns, group_advantages, orders
    )

    checkpoints = {}
    for name, model, optimizer in (
        ("control", control, control_optimizer),
        ("treatment", treatment, treatment_optimizer),
    ):
        path = args.out_dir / f"{name}_residual.pt"
        torch.save({
            "schema": "cardpilot.dual_contract_residual.v1",
            "arm": name, "base_checkpoint": str(base_path), "base_sha256": base_sha,
            "initial_residual_sha256": initial_sha, "hidden": 128,
            "policy_delta_cap": 0.25, "residual_state_dict": residual_state(model),
            "optimizer": optimizer.state_dict(), "training_hands": args.training_hands,
            "transition_rows": len(transitions), "ppo_update_rows": control_rows,
            "seed": args.seed,
        }, path)
        checkpoints[name] = {"path": str(path.resolve()), "sha256": sha256_path(path)}

    eval_path = args.out_dir / "evaluation_pairs.jsonl.gz"
    pooled = []
    pooled_seats = [[], []]
    anchor_results = []
    max_deltas = {"control": 0.0, "treatment": 0.0}
    with gzip.open(eval_path, "xt", encoding="utf-8", newline="\n") as evidence:
        for anchor_index, anchor in enumerate(opponents):
            eval_rng = random.Random(args.seed + 1_000_003 * (anchor_index + 1))
            deltas, controls, treatments = [], [], []
            seat_deltas = [[], []]
            for pair_index in range(args.pairs_per_anchor):
                deck = list(range(52))
                eval_rng.shuffle(deck)
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
                evidence.write(json.dumps({
                    "anchor_index": anchor_index, "anchor_sha256": anchor.sha256,
                    "pair_index": pair_index, "deck": deck,
                    "control_rewards_bb": control_rewards,
                    "treatment_rewards_bb": treatment_rewards,
                    "treatment_minus_control_pair_mean_bb": delta,
                }, sort_keys=True) + "\n")
            delta_mean, delta_ci = mean_ci95(deltas)
            control_mean, control_ci = mean_ci95(controls)
            treatment_mean, treatment_ci = mean_ci95(treatments)
            result = {
                "anchor_index": anchor_index, "anchor_sha256": anchor.sha256,
                "pairs": args.pairs_per_anchor,
                "control_bb100": control_mean * 100.0,
                "control_ci95_bb100": control_ci * 100.0,
                "treatment_bb100": treatment_mean * 100.0,
                "treatment_ci95_bb100": treatment_ci * 100.0,
                "delta_bb100": delta_mean * 100.0,
                "delta_ci95_bb100": delta_ci * 100.0,
                "seat_delta_bb100": [mean_ci95(values)[0] * 100.0 for values in seat_deltas],
            }
            anchor_results.append(result)
            print(f"anchor={anchor_index} treatment_control={result['delta_bb100']:+.4f} +/- {result['delta_ci95_bb100']:.4f}", flush=True)

    pooled_mean, pooled_ci = mean_ci95(pooled)
    pooled_seat_means = [mean_ci95(values)[0] * 100.0 for values in pooled_seats]
    positive_anchors = sum(row["delta_bb100"] > 0 for row in anchor_results)
    base_unchanged = all(
        torch.equal(base_state[name], tensor.detach().cpu())
        for name, tensor in base_policy.model.state_dict().items()
    )
    gates = {
        "positive_delta_on_at_least_two_anchors": positive_anchors >= 2,
        "pooled_delta_positive": pooled_mean > 0,
        "standard10_delta_nonnegative": anchor_results[0]["delta_bb100"] >= 0,
        "both_pooled_seat_deltas_nonnegative": all(value >= 0 for value in pooled_seat_means),
        "identical_update_rows": control_rows == treatment_rows,
        "base_state_unchanged": base_unchanged,
        "base_file_hash_unchanged": sha256_path(base_path) == base_sha,
        "both_residual_caps_respected": max(max_deltas.values()) <= 0.250001,
    }
    summary = {
        "schema": "cardpilot.dual_contract_group_rms_matched.v1",
        "status": "COMPLETED", "base_sha256": base_sha,
        "initial_residual_sha256": initial_sha,
        "environment_training_hands": args.training_hands,
        "transition_rows": len(transitions),
        "control_update_rows": control_rows, "treatment_update_rows": treatment_rows,
        "control_mean_loss": control_loss, "treatment_mean_loss": treatment_loss,
        "group_metrics": group_metrics,
        "evaluation_hands": args.pairs_per_anchor * 2 * 2 * 3,
        "anchors": anchor_results,
        "pooled_delta_bb100": pooled_mean * 100.0,
        "pooled_delta_ci95_bb100": pooled_ci * 100.0,
        "pooled_seat_delta_bb100": pooled_seat_means,
        "positive_anchor_count": positive_anchors,
        "max_abs_residual_logit": max_deltas,
        "checkpoints": checkpoints,
        "gates": gates, "admit_independent_replication": all(gates.values()),
        "decision": "ADMIT_GROUP_RMS_INDEPENDENT_REPLICATION" if all(gates.values()) else "REJECT_GROUP_RMS_ADVANTAGE",
        "training_evidence_sha256": sha256_path(training_path),
        "evaluation_evidence_sha256": sha256_path(eval_path),
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
