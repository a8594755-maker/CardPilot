"""Three-seed decision-level frozen-expert gate smoke."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
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

from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_broad_league_domain_feasibility import _obs_for_state
from alpha_holdem.v6_broad_mgda_curve import FrozenPolicy, frozen_decide, load_frozen_policy
from alpha_holdem.v6_dual_contract_gradient_conflict_audit import flatten_gradients
from alpha_holdem.v6_dual_contract_mgda_matched_smoke import aggregate_policy_gradients, set_flat_gradient
from alpha_holdem.v6_dual_contract_residual_training_smoke import sha256_path


class ExpertGate(torch.nn.Module):
    def __init__(self, input_dim: int, hidden: int = 32, initial_weight: float = 0.05):
        super().__init__()
        self.network = torch.nn.Sequential(
            torch.nn.Linear(input_dim, hidden), torch.nn.Tanh(), torch.nn.Linear(hidden, 1),
        )
        torch.nn.init.zeros_(self.network[-1].weight)
        torch.nn.init.constant_(self.network[-1].bias, math.log(initial_weight / (1.0 - initial_weight)))

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.network(features).squeeze(-1))


def feature_vector(obs: dict) -> np.ndarray:
    return np.concatenate([
        np.asarray(obs[key], dtype=np.float32).reshape(-1)
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ])


@torch.inference_mode()
def expert_slot_probabilities(policy: FrozenPolicy, state: ChipState) -> tuple[np.ndarray, tuple, dict]:
    obs, table = _obs_for_state(policy.model, state, policy.observation_style)
    tensors = [
        torch.as_tensor(obs[key], dtype=torch.float32, device=policy.device).unsqueeze(0)
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ]
    logits, _ = policy.model(*tensors)
    legal = torch.as_tensor(obs["legal_mask"], dtype=torch.bool, device=policy.device)
    probabilities = torch.softmax(logits[0].masked_fill(~legal, -1e9), dim=0)
    return probabilities.detach().cpu().numpy().astype(np.float32), tuple(table), obs


def align_physical_probabilities(probabilities: np.ndarray, source_table: tuple,
                                 target_table: tuple) -> np.ndarray:
    source_actions = {action for action in source_table if action is not None}
    target_actions = {action for action in target_table if action is not None}
    if source_actions != target_actions:
        raise ValueError("frozen experts disagree on legal physical actions")
    by_action = {
        action: float(probabilities[index])
        for index, action in enumerate(source_table) if action is not None
    }
    return np.asarray([
        0.0 if action is None else by_action[action] for action in target_table
    ], dtype=np.float32)


def union_physical_probabilities(p0: np.ndarray, table0: tuple, p1: np.ndarray,
                                 table1: tuple, width: int = 18) -> tuple[np.ndarray, np.ndarray, tuple]:
    actions = [action for action in table0 if action is not None]
    actions.extend(action for action in table1 if action is not None and action not in actions)
    if len(actions) > width:
        raise ValueError(f"physical action union exceeds width {width}")
    union_table = tuple(actions + [None] * (width - len(actions)))
    map0 = {action: float(p0[index]) for index, action in enumerate(table0) if action is not None}
    map1 = {action: float(p1[index]) for index, action in enumerate(table1) if action is not None}
    aligned0 = np.asarray([map0.get(action, 0.0) if action is not None else 0.0 for action in union_table], dtype=np.float32)
    aligned1 = np.asarray([map1.get(action, 0.0) if action is not None else 0.0 for action in union_table], dtype=np.float32)
    if not np.isclose(aligned0.sum(), 1.0) or not np.isclose(aligned1.sum(), 1.0):
        raise ValueError("physical action union lost probability mass")
    return aligned0, aligned1, union_table


def expert_inputs(base: FrozenPolicy, alternate: FrozenPolicy, state: ChipState) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple]:
    raw_p0, table0, obs = expert_slot_probabilities(base, state)
    raw_p1, table1, _ = expert_slot_probabilities(alternate, state)
    # The contracts can permute common actions and can expose different legal
    # bet sizes.  Mix them on their physical-action union, never by raw slot.
    p0, p1, table = union_physical_probabilities(raw_p0, table0, raw_p1, table1)
    return feature_vector(obs), p0, p1, table


def gate_choice(gate: ExpertGate, features: np.ndarray, p0: np.ndarray, p1: np.ndarray,
                *, device: str, uniform: float | None) -> tuple[int, float, float]:
    with torch.inference_mode():
        x = torch.as_tensor(features, dtype=torch.float32, device=device).unsqueeze(0)
        weight = float(gate(x)[0].cpu())
    mixture = (1.0 - weight) * p0 + weight * p1
    if uniform is None:
        slot = int(np.argmax(mixture))
    else:
        slot = min(int(np.searchsorted(np.cumsum(mixture), uniform, side="right")), len(mixture) - 1)
    return slot, float(math.log(max(float(mixture[slot]), 1e-12))), weight


def collect_chunk(gate: ExpertGate, base: FrozenPolicy, alternate: FrozenPolicy,
                  opponents: list[FrozenPolicy], *, run_seed: int, hand_offset: int,
                  hand_count: int, device: str) -> tuple[list[dict], list[dict]]:
    transitions: list[dict] = []
    hands: list[dict] = []
    group_count = len(opponents) * 2
    gate.eval()
    for local in range(hand_count):
        hand_index = hand_offset + local
        seed_base = run_seed * 1_000_003 + hand_index * 101
        deck = list(range(52))
        random.Random(seed_base + 11).shuffle(deck)
        hero_rng = random.Random(seed_base + 23)
        opponent_rng = random.Random(seed_base + 37)
        state = ChipState.new(deck)
        group_index = hand_index % group_count
        opponent_index, hero_seat = divmod(group_index, 2)
        opponent = opponents[opponent_index]
        rows = []
        weights = []
        while not state.terminal:
            if state.actor == hero_seat:
                features, p0, p1, table = expert_inputs(base, alternate, state)
                slot, old_log_prob, weight = gate_choice(
                    gate, features, p0, p1, device=device, uniform=hero_rng.random(),
                )
                action = table[slot]
                if action is None:
                    raise ValueError("gate selected an empty action slot")
                rows.append({
                    "features": features, "p0": p0, "p1": p1, "slot": slot,
                    "old_log_prob": old_log_prob, "group": group_index,
                })
                weights.append(weight)
            else:
                action = frozen_decide(opponent, state, uniform=opponent_rng.random())
            state = apply_incr(state, action)
        reward_bb = float(state.payoffs()[hero_seat]) / 100.0
        for row in rows:
            row["return_bb"] = reward_bb
            transitions.append(row)
        hands.append({
            "hand_index": hand_index, "hero_seat": hero_seat,
            "opponent_index": opponent_index, "opponent_label": opponent.label,
            "reward_bb": reward_bb, "hero_decisions": len(rows),
            "mean_alternate_weight": float(np.mean(weights)) if weights else 0.0,
        })
    return transitions, hands


def train_gate(gate: ExpertGate, optimizer: torch.optim.Optimizer, transitions: list[dict],
               *, epochs: int, groups: int, device: str, reference_kl_coef: float,
               robust_mgda: bool = False) -> list[dict]:
    features = torch.as_tensor(np.stack([row["features"] for row in transitions]), device=device)
    p0 = torch.as_tensor(np.stack([row["p0"] for row in transitions]), device=device)
    p1 = torch.as_tensor(np.stack([row["p1"] for row in transitions]), device=device)
    slots = torch.as_tensor([row["slot"] for row in transitions], dtype=torch.long, device=device)
    old_log_probs = torch.as_tensor([row["old_log_prob"] for row in transitions], device=device)
    returns = torch.as_tensor([row["return_bb"] for row in transitions], device=device)
    group_ids = torch.as_tensor([row["group"] for row in transitions], dtype=torch.long, device=device)
    advantages = torch.empty_like(returns)
    for group in range(groups):
        selected = group_ids == group
        values = returns[selected]
        if int(selected.sum()) == 0:
            raise RuntimeError(f"missing opponent-seat group {group}")
        advantages[selected] = ((values - values.mean()) / values.std().clamp_min(1e-6)).clamp(-5.0, 5.0)
    metrics = []
    gate.train()
    parameters = list(gate.parameters())
    for epoch in range(epochs):
        geometry = {}
        if robust_mgda:
            group_gradients = []
            group_loss_values = []
            for group in range(groups):
                selected = group_ids == group
                group_weight = gate(features[selected])
                group_mixture = ((1.0 - group_weight[:, None]) * p0[selected]
                                 + group_weight[:, None] * p1[selected])
                group_log_probs = torch.log(
                    group_mixture.gather(1, slots[selected, None]).squeeze(1).clamp_min(1e-12)
                )
                group_ratio = torch.exp(group_log_probs - old_log_probs[selected])
                group_advantage = advantages[selected]
                group_surrogate = torch.minimum(
                    group_ratio * group_advantage,
                    group_ratio.clamp(0.8, 1.2) * group_advantage,
                )
                group_loss = -group_surrogate.mean()
                group_loss_values.append(float(group_loss.detach()))
                group_gradients.append(flatten_gradients(group_loss, parameters).cpu().double().numpy())
            policy_gradient, geometry = aggregate_policy_gradients(
                np.stack(group_gradients), np.full(groups, 1.0 / groups), True,
            )
            policy_loss_value = float(np.mean(group_loss_values))
        else:
            weight = gate(features)
            mixture = (1.0 - weight[:, None]) * p0 + weight[:, None] * p1
            log_probs = torch.log(mixture.gather(1, slots[:, None]).squeeze(1).clamp_min(1e-12))
            ratio = torch.exp(log_probs - old_log_probs)
            surrogate = torch.minimum(ratio * advantages, ratio.clamp(0.8, 1.2) * advantages)
            group_losses = [-(surrogate[group_ids == group]).mean() for group in range(groups)]
            policy_loss = torch.stack(group_losses).mean()
            policy_loss_value = float(policy_loss.detach())
        weight = gate(features)
        mixture = (1.0 - weight[:, None]) * p0 + weight[:, None] * p1
        reference_kl = (p0 * (torch.log(p0.clamp_min(1e-12)) - torch.log(mixture.clamp_min(1e-12)))).sum(1).mean()
        optimizer.zero_grad(set_to_none=True)
        if robust_mgda:
            reference_gradient = flatten_gradients(reference_kl, parameters)
            total = (torch.as_tensor(policy_gradient, device=device, dtype=reference_gradient.dtype)
                     + reference_kl_coef * reference_gradient)
            set_flat_gradient(parameters, total)
            gradient_l2 = float(torch.linalg.vector_norm(total))
        else:
            loss = policy_loss + reference_kl_coef * reference_kl
            loss.backward()
            gradient_l2 = float(torch.sqrt(sum(
                parameter.grad.detach().square().sum() for parameter in gate.parameters()
                if parameter.grad is not None
            )))
        torch.nn.utils.clip_grad_norm_(gate.parameters(), 1.0)
        optimizer.step()
        metrics.append({
            "epoch": epoch, "policy_loss": policy_loss_value,
            "reference_kl": float(reference_kl.detach()),
            "gradient_l2_preclip": gradient_l2,
            "mean_alternate_weight": float(weight.detach().mean()),
            "robust_mgda": robust_mgda,
            **geometry,
        })
    gate.eval()
    return metrics


def play_evaluation(gate: ExpertGate, base: FrozenPolicy, alternate: FrozenPolicy,
                    opponent: FrozenPolicy, deck: list[int], hero_seat: int,
                    *, treatment: bool, device: str) -> tuple[float, int, int, float]:
    state = ChipState.new(deck)
    decisions = disagreements = 0
    weights = []
    while not state.terminal:
        if state.actor == hero_seat:
            if treatment:
                features, p0, p1, table = expert_inputs(base, alternate, state)
                slot, _, weight = gate_choice(gate, features, p0, p1, device=device, uniform=None)
                base_slot = int(np.argmax(p0))
                action = table[slot]
                decisions += 1
                disagreements += int(slot != base_slot)
                weights.append(weight)
            else:
                action = frozen_decide(base, state, uniform=None)
        else:
            action = frozen_decide(opponent, state, uniform=None)
        state = apply_incr(state, action)
    return (
        float(state.payoffs()[hero_seat]) / 100.0, decisions, disagreements,
        float(np.mean(weights)) if weights else 0.0,
    )


def summarize(rows: list[dict]) -> dict:
    values = np.asarray([row["delta_bb"] for row in rows], dtype=np.float64)
    mean = float(values.mean() * 100.0)
    se = float(values.std(ddof=1) / math.sqrt(len(values)) * 100.0) if len(values) > 1 else 0.0
    decisions = sum(row["hero_decisions"] for row in rows)
    return {
        "pairs": len(rows), "delta_bb100": mean,
        "ci95": [mean - 1.96 * se, mean + 1.96 * se],
        "greedy_disagreement": sum(row["greedy_disagreements"] for row in rows) / max(decisions, 1),
        "mean_alternate_weight": float(np.mean([row["mean_alternate_weight"] for row in rows])),
    }


def write_gzip(path: Path, rows: list[dict]) -> None:
    with gzip.open(path, "xt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_transition_audit(path: Path, transitions: list[dict]) -> None:
    np.savez_compressed(
        path,
        features=np.stack([row["features"] for row in transitions]).astype(np.float32),
        p0=np.stack([row["p0"] for row in transitions]).astype(np.float32),
        p1=np.stack([row["p1"] for row in transitions]).astype(np.float32),
        slots=np.asarray([row["slot"] for row in transitions], dtype=np.int16),
        old_log_probs=np.asarray([row["old_log_prob"] for row in transitions], dtype=np.float32),
        returns_bb=np.asarray([row["return_bb"] for row in transitions], dtype=np.float32),
        groups=np.asarray([row["group"] for row in transitions], dtype=np.int16),
    )


def gate_update_report(initial_state: dict, gate: ExpertGate, feature_dim: int) -> dict:
    initial = ExpertGate(feature_dim, hidden=gate.network[0].out_features)
    initial.load_state_dict(initial_state)
    final_state = gate.state_dict()
    deltas = [
        (final_state[key].detach().cpu() - initial_state[key]).reshape(-1).double()
        for key in initial_state
    ]
    probes = torch.cat((torch.zeros((1, feature_dim)), torch.eye(feature_dim), -torch.eye(feature_dim)))
    with torch.inference_mode():
        initial_output = initial(probes)
        final_output = gate.cpu()(probes)
    output_delta = (final_output - initial_output).abs()
    return {
        "parameter_delta_l2": float(torch.linalg.vector_norm(torch.cat(deltas))),
        "probe_count": len(probes),
        "probe_mean_abs_output_delta": float(output_delta.mean()),
        "probe_max_abs_output_delta": float(output_delta.max()),
        "final_probe_output_min": float(final_output.min()),
        "final_probe_output_max": float(final_output.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--train-hands", type=int, default=4096)
    parser.add_argument("--eval-pairs", type=int, default=512)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--reference-kl-coef", type=float, default=0.1)
    parser.add_argument("--robust-mgda", action="store_true")
    parser.add_argument("--save-transition-audit", action="store_true")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    if args.train_hands < 4096 or args.eval_pairs < 512 or args.seeds < 3:
        parser.error("smoke requires train-hands>=4096, eval-pairs>=512, seeds>=3")
    if args.learning_rate <= 0 or args.epochs <= 0 or args.reference_kl_coef < 0:
        parser.error("invalid optimizer dose")
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    training_policies = [load_frozen_policy(row, args.device) for row in spec["training_policies"]]
    holdouts = [load_frozen_policy(row, args.device) for row in spec["holdout_policies"]]
    base, alternate = training_policies[0], training_policies[5]
    if base.label != "standard10" or alternate.label != "diverse_league5":
        raise ValueError("unexpected frozen expert identities")
    initial_state = ChipState.new(list(range(52)))
    feature_dim = len(expert_inputs(base, alternate, initial_state)[0])
    seed_reports = []
    all_eval_rows = []
    total_training_hands = total_evaluation_hands = 0
    all_training_metrics = []
    for seed_index in range(args.seeds):
        run_seed = args.seed + seed_index * 10_007
        torch.manual_seed(run_seed)
        gate = ExpertGate(feature_dim).to(args.device)
        initial_state = {key: value.detach().cpu().clone() for key, value in gate.state_dict().items()}
        optimizer = torch.optim.Adam(gate.parameters(), lr=args.learning_rate)
        training_hands = []
        metrics = []
        for offset in range(0, args.train_hands, 1024):
            count = min(1024, args.train_hands - offset)
            transitions, hands = collect_chunk(
                gate, base, alternate, training_policies, run_seed=run_seed,
                hand_offset=offset, hand_count=count, device=args.device,
            )
            if args.save_transition_audit:
                write_transition_audit(
                    args.out_dir / f"seed{seed_index}_chunk{offset:05d}_transitions.npz", transitions,
                )
            training_hands.extend(hands)
            chunk_metrics = train_gate(
                gate, optimizer, transitions, epochs=args.epochs, groups=len(training_policies) * 2,
                device=args.device, reference_kl_coef=args.reference_kl_coef,
                robust_mgda=args.robust_mgda,
            )
            for row in chunk_metrics:
                metrics.append({"chunk_offset": offset, **row})
        total_training_hands += len(training_hands)
        all_training_metrics.extend(metrics)
        write_gzip(args.out_dir / f"seed{seed_index}_training_hands.jsonl.gz", training_hands)
        update_report = gate_update_report(initial_state, gate, feature_dim)
        gate = gate.to(args.device)
        torch.save({
            "schema": "cardpilot.decision_expert_gate.v1", "seed": run_seed,
            "feature_dim": feature_dim, "hidden": 32,
            "base_sha256": base.sha256, "alternate_sha256": alternate.sha256,
            "state_dict": gate.state_dict(),
        }, args.out_dir / f"seed{seed_index}_gate.pt")
        evaluation = []
        for opponent_index, opponent in enumerate(holdouts):
            rng = random.Random(run_seed + 900_001 + opponent_index * 10_009)
            for pair_index in range(args.eval_pairs):
                deck = list(range(52))
                rng.shuffle(deck)
                for hero_seat in (0, 1):
                    treatment, decisions, disagreements, mean_weight = play_evaluation(
                        gate, base, alternate, opponent, deck, hero_seat,
                        treatment=True, device=args.device,
                    )
                    control, _, _, _ = play_evaluation(
                        gate, base, alternate, opponent, deck, hero_seat,
                        treatment=False, device=args.device,
                    )
                    evaluation.append({
                        "seed_index": seed_index, "seed": run_seed,
                        "opponent_index": opponent_index, "opponent_label": opponent.label,
                        "pair_index": pair_index, "hero_seat": hero_seat,
                        "treatment_reward_bb": treatment, "control_reward_bb": control,
                        "delta_bb": treatment - control, "hero_decisions": decisions,
                        "greedy_disagreements": disagreements,
                        "mean_alternate_weight": mean_weight,
                    })
                    total_evaluation_hands += 2
        write_gzip(args.out_dir / f"seed{seed_index}_evaluation.jsonl.gz", evaluation)
        all_eval_rows.extend(evaluation)
        seed_reports.append({
            "seed_index": seed_index, "seed": run_seed,
            "training_hands": len(training_hands), "training_decisions": sum(row["hero_decisions"] for row in training_hands),
            "training_mean_reward_bb": float(np.mean([row["reward_bb"] for row in training_hands])),
            "training_final_alternate_weight": metrics[-1]["mean_alternate_weight"],
            "training_max_gradient_l2": max(row["gradient_l2_preclip"] for row in metrics),
            "evaluation": summarize(evaluation),
            "update": update_report,
            "gate_sha256": sha256_path(args.out_dir / f"seed{seed_index}_gate.pt"),
        })
    pooled = summarize(all_eval_rows)
    by_opponent = {
        holdouts[index].label: summarize([row for row in all_eval_rows if row["opponent_index"] == index])
        for index in range(len(holdouts))
    }
    by_seat = {str(seat): summarize([row for row in all_eval_rows if row["hero_seat"] == seat]) for seat in (0, 1)}
    seed_deltas = [row["evaluation"]["delta_bb100"] for row in seed_reports]
    gates = {
        "environment_training_hands_exact": total_training_hands == args.seeds * args.train_hands,
        "environment_evaluation_hands_exact": total_evaluation_hands == args.seeds * len(holdouts) * args.eval_pairs * 2 * 2,
        "finite_nonzero_gate_gradients": all(math.isfinite(row["gradient_l2_preclip"]) and row["gradient_l2_preclip"] > 0 for row in all_training_metrics),
        "endpoint_alternate_weight_1_to_50pct": 0.01 <= pooled["mean_alternate_weight"] <= 0.50,
        "greedy_disagreement_0_5_to_25pct": 0.005 <= pooled["greedy_disagreement"] <= 0.25,
        "pooled_paired_delta_positive": pooled["delta_bb100"] > 0,
        "median_seed_delta_positive": float(np.median(seed_deltas)) > 0,
        "at_least_two_of_three_seed_deltas_positive": sum(value > 0 for value in seed_deltas) >= 2,
        "all_holdout_opponent_deltas_positive": all(row["delta_bb100"] > 0 for row in by_opponent.values()),
        "both_seat_deltas_positive": all(row["delta_bb100"] > 0 for row in by_seat.values()),
        "all_seed_probe_max_output_changes_at_least_1pct": all(
            row["update"]["probe_max_abs_output_delta"] >= 0.01 for row in seed_reports
        ),
        "mgda_worst_alignment_positive_every_step": (
            not args.robust_mgda
            or all(row["applied_worst_alignment"] > 0 for row in all_training_metrics)
        ),
    }
    admitted = all(gates.values())
    summary = {
        "schema": "cardpilot.decision_expert_gate_smoke.v1", "status": "COMPLETED",
        "claim_scope": "BOUNDED_INTERNAL_MECHANISM_SMOKE_NOT_EXTERNAL_STRENGTH",
        "experts": [{"label": base.label, "sha256": base.sha256}, {"label": alternate.label, "sha256": alternate.sha256}],
        "training_opponents": [{"label": row.label, "sha256": row.sha256} for row in training_policies],
        "holdout_opponents": [{"label": row.label, "sha256": row.sha256} for row in holdouts],
        "actual_environment_training_hands": total_training_hands,
        "actual_environment_evaluation_hands": total_evaluation_hands,
        "feature_dim": feature_dim, "seed_reports": seed_reports,
        "optimizer": {
            "learning_rate": args.learning_rate, "epochs_per_chunk": args.epochs,
            "reference_kl_coef": args.reference_kl_coef,
            "robust_mgda": args.robust_mgda,
            "transition_audit_saved": args.save_transition_audit,
        },
        "pooled_evaluation": pooled, "by_holdout_opponent": by_opponent, "by_seat": by_seat,
        "gates": gates, "admit_geometric_gate_curve": admitted,
        "decision": "ADMIT_DECISION_GATE_GEOMETRIC_CURVE" if admitted else "REJECT_DECISION_EXPERT_GATE_SMOKE",
        "artifact_sha256": {
            path.name: sha256_path(path) for path in args.out_dir.iterdir() if path.is_file()
        },
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"decision": summary["decision"], "gates": gates, "pooled": pooled, "seeds": seed_deltas}, sort_keys=True))


if __name__ == "__main__":
    main()
