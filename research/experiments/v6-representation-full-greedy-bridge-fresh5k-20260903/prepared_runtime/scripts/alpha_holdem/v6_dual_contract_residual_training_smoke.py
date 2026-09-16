"""Small on-policy reward-training smoke for a bounded dual-contract residual."""
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
    action_prefix,
    decide as legacy_decide,
    legacy_observation,
    load_policy,
)
from alpha_holdem.policy_contract_v6 import apply_incr, observation
from alpha_holdem.rules_v6 import ChipState


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mean_ci95(values) -> tuple[float, float]:
    values = np.asarray(values, dtype=np.float64)
    mean = float(values.mean())
    half = 1.96 * float(values.std(ddof=1)) / math.sqrt(len(values))
    return mean, half


def state_inputs(policy, state, device):
    legacy_obs, legacy_table = legacy_observation(policy, state)
    native_obs, _ = observation(state)
    keys = ("card_info", "action_info", "extra_info")
    legacy_tensors = [
        torch.as_tensor(legacy_obs[key], dtype=torch.float32, device=device).unsqueeze(0)
        for key in keys
    ]
    native_tensors = [
        torch.as_tensor(native_obs[key], dtype=torch.float32, device=device).unsqueeze(0)
        for key in keys
    ]
    legacy_mask = torch.as_tensor(
        legacy_obs["legal_mask"], dtype=torch.float32, device=device
    ).unsqueeze(0)
    native_mask = torch.as_tensor(
        native_obs["legal_mask"], dtype=torch.float32, device=device
    ).unsqueeze(0)
    return (*legacy_tensors, *native_tensors, legacy_mask, native_mask), legacy_obs, legacy_table


@torch.no_grad()
def residual_decide(model, base_policy, state, device, *, uniform=None):
    values, obs, table = state_inputs(base_policy, state, device)
    logits, value = model(*values)
    base_logits = model.base(values[0], values[1], values[2], values[6])[0]
    legal = np.flatnonzero(obs["legal_mask"] > 0)
    legal_logits = logits[0, legal].detach().cpu().numpy().astype(np.float64)
    weights = np.exp(legal_logits - legal_logits.max())
    probs = weights / weights.sum()
    if uniform is None:
        local_index = int(np.argmax(legal_logits))
    else:
        local_index = min(
            int(np.searchsorted(np.cumsum(probs), uniform, side="right")),
            len(legal) - 1,
        )
    slot = int(legal[local_index])
    delta = logits - base_logits
    return table[slot], {
        "slot": slot,
        "log_prob": float(math.log(max(probs[local_index], 1e-300))),
        "value": float(value.item()),
        "max_abs_logit_delta": float(delta.abs().max()),
        "inputs": tuple(tensor.squeeze(0).cpu().numpy() for tensor in values),
    }


def stack_rows(rows, index, device):
    return torch.as_tensor(np.stack([row["inputs"][index] for row in rows]), dtype=torch.float32, device=device)


def play_candidate_hand(model, base_policy, anchor, deck, candidate_seat, device):
    state = ChipState.new(deck)
    max_delta = 0.0
    while not state.terminal:
        if state.actor == candidate_seat:
            action, metadata = residual_decide(model, base_policy, state, device)
            max_delta = max(max_delta, metadata["max_abs_logit_delta"])
        else:
            action, _ = legacy_decide(anchor, state, uniform=0.0, policy_mode="greedy")
        state = apply_incr(state, action)
    return float(state.payoffs()[candidate_seat]) / 100.0, max_delta


def play_control_hand(base_policy, anchor, deck, candidate_seat):
    state = ChipState.new(deck)
    while not state.terminal:
        policy = base_policy if state.actor == candidate_seat else anchor
        action, _ = legacy_decide(policy, state, uniform=0.0, policy_mode="greedy")
        state = apply_incr(state, action)
    return float(state.payoffs()[candidate_seat]) / 100.0


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
        parser.error("exactly three --opponent checkpoints are required")
    if args.training_hands < 512 or args.pairs_per_anchor < 128:
        parser.error("training/evaluation budgets are below smoke minimum")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed % (2**32))
    rng = random.Random(args.seed)
    started = time.time()

    base_path = args.base_checkpoint.resolve()
    base_file_sha = sha256_path(base_path)
    base_policy = load_policy(base_path, args.device)
    opponents = [load_policy(path, args.device) for path in args.opponent]
    model = DualContractResidualPolicy(
        base_policy.model, hidden=128, policy_delta_cap=0.25
    ).to(args.device)
    base_state = {
        name: tensor.detach().cpu().clone()
        for name, tensor in model.base.state_dict().items()
    }

    transitions = []
    training_path = args.out_dir / "training_hands.jsonl.gz"
    reward_sum = 0.0
    with gzip.open(training_path, "xt", encoding="utf-8", newline="\n") as evidence:
        for hand_index in range(args.training_hands):
            deck = list(range(52))
            rng.shuffle(deck)
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
                        model, base_policy, state, args.device, uniform=rng.random()
                    )
                    hand_rows.append(metadata)
                    decisions.append({"action_prefix": prefix, "slot": metadata["slot"]})
                else:
                    action, _ = legacy_decide(
                        opponent, state, uniform=rng.random(), policy_mode="sample"
                    )
                state = apply_incr(state, action)
            reward_bb = float(state.payoffs()[hero_seat]) / 100.0
            reward_sum += reward_bb
            normalized_return = reward_bb / 200.0
            for row in hand_rows:
                row["return"] = normalized_return
                transitions.append(row)
            evidence.write(json.dumps({
                "hand_index": hand_index, "deck": deck, "hero_seat": hero_seat,
                "opponent_index": opponent_index,
                "opponent_sha256": opponent.sha256,
                "reward_bb": reward_bb, "hero_decisions": decisions,
            }, sort_keys=True) + "\n")
            if (hand_index + 1) % 1024 == 0:
                print(f"training_hands={hand_index + 1} transitions={len(transitions)} reward_bb_per_hand={reward_sum/(hand_index+1):+.4f}", flush=True)

    old_log_probs = torch.tensor([row["log_prob"] for row in transitions], dtype=torch.float32, device=args.device)
    old_values = torch.tensor([row["value"] for row in transitions], dtype=torch.float32, device=args.device)
    returns = torch.tensor([row["return"] for row in transitions], dtype=torch.float32, device=args.device)
    actions = torch.tensor([row["slot"] for row in transitions], dtype=torch.long, device=args.device)
    advantages = returns - old_values
    advantages = (advantages - advantages.mean()) / advantages.std().clamp_min(1e-6)
    tensors = [stack_rows(transitions, index, args.device) for index in range(8)]
    parameters = list(model.trainable_parameters())
    optimizer = torch.optim.Adam(parameters, lr=3e-4)
    indices = np.arange(len(transitions))
    update_rows = 0
    losses = []
    model.train()
    for epoch in range(4):
        np.random.default_rng(args.seed + 100 + epoch).shuffle(indices)
        for start in range(0, len(indices), 512):
            selected = torch.as_tensor(indices[start:start + 512], device=args.device)
            batch = [tensor[selected] for tensor in tensors]
            logits, values = model(*batch)
            masked_logits = logits + (1.0 - batch[6]) * -1e9
            distribution = torch.distributions.Categorical(logits=masked_logits)
            log_probs = distribution.log_prob(actions[selected])
            ratio = torch.exp(log_probs - old_log_probs[selected])
            unclipped = ratio * advantages[selected]
            clipped = ratio.clamp(0.8, 1.2) * advantages[selected]
            policy_loss = -torch.minimum(unclipped, clipped).mean()
            value_loss = (values.squeeze(1) - returns[selected]).square().mean()
            loss = policy_loss + value_loss - 0.005 * distribution.entropy().mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(parameters, 1.0)
            optimizer.step()
            update_rows += len(selected)
            losses.append(float(loss.detach()))
    model.eval()

    base_unchanged = all(
        torch.equal(base_state[name], tensor.detach().cpu())
        for name, tensor in model.base.state_dict().items()
    )
    residual_path = args.out_dir / "trained_residual.pt"
    torch.save({
        "schema": "cardpilot.dual_contract_residual.v1",
        "base_checkpoint": str(base_path), "base_sha256": base_file_sha,
        "hidden": 128, "policy_delta_cap": 0.25,
        "residual_state_dict": {
            name: tensor.detach().cpu()
            for name, tensor in model.state_dict().items()
            if not name.startswith("base.")
        },
        "optimizer": optimizer.state_dict(),
        "environment_training_hands": args.training_hands,
        "transition_rows": len(transitions), "ppo_update_rows": update_rows,
        "seed": args.seed,
    }, residual_path)

    evaluation_path = args.out_dir / "evaluation_pairs.jsonl.gz"
    anchor_rows = []
    pooled = []
    pooled_seats = [[], []]
    max_eval_delta = 0.0
    with gzip.open(evaluation_path, "xt", encoding="utf-8", newline="\n") as evidence:
        for anchor_index, anchor in enumerate(opponents):
            local_rng = random.Random(args.seed + 1_000_003 * (anchor_index + 1))
            deltas = []
            seat_deltas = [[], []]
            treatment_values = []
            control_values = []
            for pair_index in range(args.pairs_per_anchor):
                deck = list(range(52))
                local_rng.shuffle(deck)
                control_rewards = []
                treatment_rewards = []
                for seat in (0, 1):
                    control_rewards.append(play_control_hand(base_policy, anchor, deck, seat))
                    reward, observed_delta = play_candidate_hand(
                        model, base_policy, anchor, deck, seat, args.device
                    )
                    treatment_rewards.append(reward)
                    max_eval_delta = max(max_eval_delta, observed_delta)
                    seat_delta = reward - control_rewards[-1]
                    seat_deltas[seat].append(seat_delta)
                    pooled_seats[seat].append(seat_delta)
                control_pair = sum(control_rewards) / 2.0
                treatment_pair = sum(treatment_rewards) / 2.0
                delta = treatment_pair - control_pair
                control_values.append(control_pair)
                treatment_values.append(treatment_pair)
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
            control_mean, control_ci = mean_ci95(control_values)
            treatment_mean, treatment_ci = mean_ci95(treatment_values)
            anchor_rows.append({
                "anchor_index": anchor_index, "anchor_sha256": anchor.sha256,
                "pairs": args.pairs_per_anchor,
                "control_bb100": control_mean * 100.0,
                "control_ci95_bb100": control_ci * 100.0,
                "treatment_bb100": treatment_mean * 100.0,
                "treatment_ci95_bb100": treatment_ci * 100.0,
                "delta_bb100": delta_mean * 100.0,
                "delta_ci95_bb100": delta_ci * 100.0,
                "seat_delta_bb100": [mean_ci95(values)[0] * 100.0 for values in seat_deltas],
            })
            print(f"anchor={anchor_index} delta_bb100={delta_mean*100:+.4f} ci95_half={delta_ci*100:.4f}", flush=True)

    pooled_mean, pooled_ci = mean_ci95(pooled)
    pooled_seat_means = [mean_ci95(values)[0] * 100.0 for values in pooled_seats]
    positive_anchors = sum(row["delta_bb100"] > 0 for row in anchor_rows)
    gates = {
        "positive_delta_on_at_least_two_anchors": positive_anchors >= 2,
        "pooled_delta_positive": pooled_mean > 0,
        "standard10_delta_nonnegative": anchor_rows[0]["delta_bb100"] >= 0,
        "both_pooled_seat_deltas_nonnegative": all(value >= 0 for value in pooled_seat_means),
        "base_state_unchanged": base_unchanged,
        "base_file_hash_unchanged": sha256_path(base_path) == base_file_sha,
        "residual_logit_cap_respected": max_eval_delta <= 0.250001,
    }
    summary = {
        "schema": "cardpilot.dual_contract_residual_reward_smoke.v1",
        "status": "COMPLETED", "base_sha256": base_file_sha,
        "opponent_sha256": [policy.sha256 for policy in opponents],
        "environment_training_hands": args.training_hands,
        "transition_rows": len(transitions), "ppo_update_rows": update_rows,
        "training_reward_bb_per_hand": reward_sum / args.training_hands,
        "mean_training_loss": float(np.mean(losses)),
        "evaluation_hands": args.pairs_per_anchor * 2 * 2 * len(opponents),
        "anchors": anchor_rows,
        "pooled_delta_bb100": pooled_mean * 100.0,
        "pooled_delta_ci95_bb100": pooled_ci * 100.0,
        "pooled_seat_delta_bb100": pooled_seat_means,
        "positive_anchor_count": positive_anchors,
        "max_abs_residual_logit": max_eval_delta,
        "gates": gates, "admit_independent_replication": all(gates.values()),
        "decision": "ADMIT_DUAL_CONTRACT_REPLICATION" if all(gates.values()) else "REJECT_DUAL_CONTRACT_REWARD_SMOKE",
        "residual_sha256": sha256_path(residual_path),
        "training_evidence_sha256": sha256_path(training_path),
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
