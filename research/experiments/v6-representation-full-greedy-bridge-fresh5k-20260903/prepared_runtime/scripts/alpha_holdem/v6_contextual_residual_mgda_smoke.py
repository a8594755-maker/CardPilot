"""Multi-seed broad MGDA smoke for a 64-hand contextual learned residual."""
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

from alpha_holdem.contextual_residual_v6 import ContextualResidualPolicy, PosteriorCenteredResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import decide as legacy_decide, load_policy
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_broad_league_domain_feasibility import collect_balanced_states
from alpha_holdem.v6_broad_mgda_curve import frozen_decide, load_frozen_policy
from alpha_holdem.v6_dual_contract_gradient_conflict_audit import flatten_gradients, residual_state_digest
from alpha_holdem.v6_dual_contract_mgda_matched_smoke import aggregate_policy_gradients, residual_state, set_flat_gradient
from alpha_holdem.v6_dual_contract_residual_training_smoke import mean_ci95, sha256_path, stack_rows, state_inputs
from alpha_holdem.v6_opponent_context_feasibility import action_bucket, context_features


def contextual_decide(model, base_policy, state, context, device, *, uniform=None):
    values, obs, table = state_inputs(base_policy, state, device)
    context_tensor = torch.as_tensor(context, dtype=torch.float32, device=device).unsqueeze(0)
    logits, value = model(*values, context_tensor)
    base_logits = model.base(values[0], values[1], values[2], values[6])[0]
    legal = np.flatnonzero(obs["legal_mask"] > 0)
    legal_logits = logits[0, legal].detach().cpu().numpy().astype(np.float64)
    weights = np.exp(legal_logits - legal_logits.max())
    probabilities = weights / weights.sum()
    if uniform is None:
        local = int(np.argmax(legal_logits))
    else:
        local = min(int(np.searchsorted(np.cumsum(probabilities), uniform, side="right")), len(legal) - 1)
    slot = int(legal[local])
    return table[slot], {
        "slot": slot,
        "log_prob": float(math.log(max(probabilities[local], 1e-300))),
        "value": float(value.item()),
        "max_abs_logit_delta": float((logits - base_logits).abs().max()),
        "inputs": tuple(tensor.squeeze(0).cpu().numpy() for tensor in values) + (np.asarray(context, dtype=np.float32).copy(),),
    }


def update_counts(counts: np.ndarray, state: ChipState, action: str) -> None:
    counts[state.street, action_bucket(action)] += 1


def warmup_context(base_policy, opponent, *, hero_seat: int, hands: int, seed: int):
    counts = np.zeros((4, 4), dtype=np.int64)
    evidence = []
    for hand_index in range(hands):
        rng = random.Random(seed + hand_index * 103)
        deck = list(range(52))
        rng.shuffle(deck)
        state = ChipState.new(deck)
        while not state.terminal:
            if state.actor == hero_seat:
                action, _ = legacy_decide(base_policy, state, uniform=rng.random(), policy_mode="sample")
            else:
                action = frozen_decide(opponent, state, uniform=rng.random())
                update_counts(counts, state, action)
            state = apply_incr(state, action)
        evidence.append({"kind": "warmup", "hand_index": hand_index, "hero_seat": hero_seat, "deck": deck, "reward_bb": float(state.payoffs()[hero_seat]) / 100.0})
    return counts, evidence


def initialize_training_groups(base_policy, opponents, *, seed: int, warmup_hands: int):
    groups = []
    evidence = []
    for opponent_index, opponent in enumerate(opponents):
        for hero_seat in (0, 1):
            group_index = opponent_index * 2 + hero_seat
            counts, warmup = warmup_context(
                base_policy,
                opponent,
                hero_seat=hero_seat,
                hands=warmup_hands,
                seed=seed * 1_000_003 + group_index * 100_003,
            )
            for row in warmup:
                row.update({"group": f"opponent{opponent_index:02d}_seat{hero_seat}", "opponent_index": opponent_index, "opponent_sha256": opponent.sha256})
            evidence.extend(warmup)
            groups.append({"opponent": opponent, "opponent_index": opponent_index, "hero_seat": hero_seat, "counts": counts})
    return groups, evidence


def collect_learning_rounds(model, base_policy, groups, *, seed: int, round_start: int, round_count: int, device: str):
    evidence = []
    transitions = []
    for round_index in range(round_start, round_start + round_count):
        for group_index, group in enumerate(groups):
            rng = random.Random(seed * 3_000_017 + group_index * 200_003 + round_index * 109)
            deck = list(range(52))
            rng.shuffle(deck)
            state = ChipState.new(deck)
            context = context_features(group["counts"])
            hand_rows = []
            decisions = []
            while not state.terminal:
                if state.actor == group["hero_seat"]:
                    action, metadata = contextual_decide(model, base_policy, state, context, device, uniform=rng.random())
                    metadata["group"] = f"opponent{group['opponent_index']:02d}_seat{group['hero_seat']}"
                    hand_rows.append(metadata)
                    decisions.append({"slot": metadata["slot"], "street": state.street})
                else:
                    action = frozen_decide(group["opponent"], state, uniform=rng.random())
                    update_counts(group["counts"], state, action)
                state = apply_incr(state, action)
            reward_bb = float(state.payoffs()[group["hero_seat"]]) / 100.0
            for row in hand_rows:
                row["return"] = reward_bb / 200.0
                transitions.append(row)
            evidence.append({
                "kind": "learning", "round_index": round_index, "group_index": group_index,
                "hero_seat": group["hero_seat"], "opponent_index": group["opponent_index"],
                "opponent_sha256": group["opponent"].sha256, "deck": deck,
                "context": context.tolist(), "reward_bb": reward_bb, "hero_decisions": decisions,
            })
    return transitions, evidence


def collect_training(model, base_policy, opponents, *, seed: int, warmup_hands: int, learning_hands_per_group: int, device: str):
    groups, warmup = initialize_training_groups(base_policy, opponents, seed=seed, warmup_hands=warmup_hands)
    transitions, learning = collect_learning_rounds(
        model, base_policy, groups, seed=seed, round_start=0,
        round_count=learning_hands_per_group, device=device,
    )
    return transitions, warmup + learning


def train_mgda(model, transitions, *, steps: int, group_batch_size: int, seed: int, device: str, optimizer=None):
    old_log_probs = torch.tensor([r["log_prob"] for r in transitions], dtype=torch.float32, device=device)
    old_values = torch.tensor([r["value"] for r in transitions], dtype=torch.float32, device=device)
    returns = torch.tensor([r["return"] for r in transitions], dtype=torch.float32, device=device)
    actions = torch.tensor([r["slot"] for r in transitions], dtype=torch.long, device=device)
    tensors = [stack_rows(transitions, index, device) for index in range(9)]
    group_names = sorted({r["group"] for r in transitions})
    group_indices = [np.asarray([i for i, r in enumerate(transitions) if r["group"] == group]) for group in group_names]
    group_support = [len(indices) for indices in group_indices]
    if len(group_names) != 12 or min(group_support) < group_batch_size:
        raise RuntimeError(f"insufficient support for twelve balanced MGDA groups: {group_support}")
    raw_advantages = returns - old_values
    group_advantages = []
    for indices in group_indices:
        selected = torch.as_tensor(indices, dtype=torch.long, device=device)
        local = raw_advantages[selected]
        local = ((local - local.mean()) / local.std().clamp_min(1e-6)).clamp(-5.0, 5.0)
        full = torch.zeros_like(raw_advantages)
        full[selected] = local
        group_advantages.append(full)
    parameters = list(model.trainable_parameters())
    if optimizer is None:
        optimizer = torch.optim.Adam(parameters, lr=3e-4)
    rng = np.random.default_rng(seed + 991)
    schedules = [[rng.choice(indices, size=group_batch_size, replace=False) for indices in group_indices] for _ in range(steps)]
    conditioning_module = model.context_encoder if hasattr(model, "context_encoder") else model.policy_heads
    initial_context = {name: tensor.detach().cpu().clone() for name, tensor in conditioning_module.state_dict().items()}
    metrics = []
    model.train()
    for step, selections in enumerate(schedules):
        gradients = []
        for group_index, selection in enumerate(selections):
            selected = torch.as_tensor(selection, dtype=torch.long, device=device)
            batch = [tensor[selected] for tensor in tensors]
            logits, _ = model(*batch)
            distribution = torch.distributions.Categorical(logits=logits + (1.0 - batch[6]) * -1e9)
            ratio = torch.exp(distribution.log_prob(actions[selected]) - old_log_probs[selected])
            advantage = group_advantages[group_index][selected]
            surrogate = torch.minimum(ratio * advantage, ratio.clamp(0.8, 1.2) * advantage)
            gradients.append(flatten_gradients(-surrogate.mean(), parameters).cpu().double().numpy())
        aggregate, geometry = aggregate_policy_gradients(np.stack(gradients), np.full(12, 1 / 12), True)
        combined = torch.as_tensor(np.concatenate(selections), dtype=torch.long, device=device)
        batch = [tensor[combined] for tensor in tensors]
        logits, values = model(*batch)
        distribution = torch.distributions.Categorical(logits=logits + (1.0 - batch[6]) * -1e9)
        value_loss = (values.squeeze(1) - returns[combined]).square().mean()
        entropy = distribution.entropy().mean()
        auxiliary = flatten_gradients(value_loss - 0.005 * entropy, parameters)
        total = torch.as_tensor(aggregate, dtype=auxiliary.dtype, device=device) + auxiliary
        optimizer.zero_grad(set_to_none=True)
        set_flat_gradient(parameters, total)
        torch.nn.utils.clip_grad_norm_(parameters, 1.0)
        optimizer.step()
        metrics.append({"step": step, "value_loss": float(value_loss.detach()), "entropy": float(entropy.detach()), **geometry})
    model.eval()
    context_update_l2 = math.sqrt(sum(float((tensor.detach().cpu() - initial_context[name]).square().sum()) for name, tensor in conditioning_module.state_dict().items()))
    return optimizer, metrics, schedules, context_update_l2, dict(zip(group_names, group_support))


def greedy_reward(model, base_policy, opponent, deck, hero_seat: int, context, device, arm: str):
    state = ChipState.new(deck)
    max_delta = 0.0
    while not state.terminal:
        if state.actor == hero_seat:
            if arm == "base":
                action, _ = legacy_decide(base_policy, state, uniform=0.0, policy_mode="greedy")
            else:
                action, metadata = contextual_decide(model, base_policy, state, context, device)
                max_delta = max(max_delta, metadata["max_abs_logit_delta"])
        else:
            action = frozen_decide(opponent, state, uniform=None)
        state = apply_incr(state, action)
    return float(state.payoffs()[hero_seat]) / 100.0, max_delta


def evaluate(model, base_policy, policies, *, seed: int, warmup_hands: int, pairs_per_policy: int, device: str):
    contexts = {}
    warmup_rows = []
    for index, (_, opponent) in enumerate(policies):
        for seat in (0, 1):
            counts, rows = warmup_context(base_policy, opponent, hero_seat=seat, hands=warmup_hands, seed=seed + index * 900_001 + seat * 70_001)
            contexts[(index, seat)] = context_features(counts)
            warmup_rows.extend(rows)
    rows = []
    max_delta = 0.0
    for index, (split, opponent) in enumerate(policies):
        wrong_index = (index + 1) % len(policies)
        rng = random.Random(seed + 40_000_003 * (index + 1))
        for pair_index in range(pairs_per_policy):
            deck = list(range(52))
            rng.shuffle(deck)
            for seat in (0, 1):
                base, _ = greedy_reward(model, base_policy, opponent, deck, seat, contexts[(index, seat)], device, "base")
                correct, delta1 = greedy_reward(model, base_policy, opponent, deck, seat, contexts[(index, seat)], device, "correct")
                wrong, delta2 = greedy_reward(model, base_policy, opponent, deck, seat, contexts[(wrong_index, seat)], device, "wrong")
                max_delta = max(max_delta, delta1, delta2)
                rows.append({
                    "split": split, "opponent_index": index, "opponent_label": opponent.label,
                    "opponent_sha256": opponent.sha256, "pair_index": pair_index, "hero_seat": seat,
                    "deck": deck, "base_reward_bb": base, "correct_reward_bb": correct,
                    "wrong_reward_bb": wrong, "correct_minus_base_bb": correct - base,
                    "correct_minus_wrong_bb": correct - wrong,
                })
    return rows, warmup_rows, max_delta, contexts


def summarize(rows: list[dict]) -> dict:
    def metric(selected, key):
        mean, half = mean_ci95([r[key] for r in selected])
        return {"bb100": mean * 100.0, "ci95_half_bb100": half * 100.0, "hands": len(selected)}
    result = {"pooled_correct_minus_base": metric(rows, "correct_minus_base_bb"), "pooled_correct_minus_wrong": metric(rows, "correct_minus_wrong_bb")}
    result["splits"] = {}
    for split in ("training", "holdout"):
        selected = [r for r in rows if r["split"] == split]
        result["splits"][split] = {"correct_minus_base": metric(selected, "correct_minus_base_bb"), "correct_minus_wrong": metric(selected, "correct_minus_wrong_bb")}
    result["seats"] = {str(seat): metric([r for r in rows if r["hero_seat"] == seat], "correct_minus_base_bb") for seat in (0, 1)}
    return result


def active_preservation(model, base_policy, states, contexts, device):
    rows = []
    max_delta = 0.0
    ordered_contexts = [contexts[key] for key in sorted(contexts)]
    for index, state in enumerate(states):
        context = ordered_contexts[index % len(ordered_contexts)]
        base_action, _ = legacy_decide(base_policy, state, uniform=0.0, policy_mode="greedy")
        action, metadata = contextual_decide(model, base_policy, state, context, device)
        rows.append({"street": state.street, "seat": state.actor, "agree": action == base_action})
        max_delta = max(max_delta, metadata["max_abs_logit_delta"])
    partitions = []
    for street in range(4):
        for seat in (0, 1):
            local = [r["agree"] for r in rows if r["street"] == street and r["seat"] == seat]
            partitions.append(float(np.mean(local)))
    zero_context_exact = True
    zero = np.zeros(20, dtype=np.float32)
    for state in states[:128]:
        base_action, _ = legacy_decide(base_policy, state, uniform=0.0, policy_mode="greedy")
        action, metadata = contextual_decide(model, base_policy, state, zero, device)
        zero_context_exact &= action == base_action and metadata["max_abs_logit_delta"] == 0.0
    return {
        "states": len(rows), "overall_agreement": float(np.mean([r["agree"] for r in rows])),
        "minimum_partition_agreement": min(partitions), "active_disagreement_rate": 1.0 - float(np.mean([r["agree"] for r in rows])),
        "max_abs_residual_logit": max_delta, "zero_context_exact": bool(zero_context_exact),
    }


def write_jsonl_gz(path: Path, rows: list[dict]):
    with gzip.open(path, "xt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--seeds", type=int, default=2)
    parser.add_argument("--warmup-hands", type=int, default=64)
    parser.add_argument("--learning-hands-per-group", type=int, default=128)
    parser.add_argument("--steps", type=int, default=32)
    parser.add_argument("--group-batch-size", type=int, default=64)
    parser.add_argument("--pairs-per-policy", type=int, default=64)
    parser.add_argument("--context-mode", choices=("raw-interaction", "posterior-centered"), default="raw-interaction")
    parser.add_argument("--context-classifier", type=Path)
    parser.add_argument("--expected-context-classifier-sha256")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    if args.warmup_hands != 64 or args.seeds < 2 or args.learning_hands_per_group < 64:
        parser.error("smoke requires 64 warmup hands, at least two seeds, and at least 64 learning hands/group")
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    base_sha = sha256_path(args.base_checkpoint)
    base_policy = load_policy(args.base_checkpoint, args.device)
    base_state = {name: tensor.detach().cpu().clone() for name, tensor in base_policy.model.state_dict().items()}
    training = [load_frozen_policy(row, args.device) for row in spec["training_policies"]]
    holdouts = [load_frozen_policy(row, args.device) for row in spec["holdout_policies"]]
    if len(training) != 6 or len(holdouts) != 3 or not {p.sha256 for p in training}.isdisjoint({p.sha256 for p in holdouts}):
        raise ValueError("expected six training and three SHA-disjoint holdout policies")
    classifier = None
    classifier_sha = None
    if args.context_mode == "posterior-centered":
        if args.context_classifier is None or args.expected_context_classifier_sha256 is None:
            parser.error("posterior-centered mode requires a classifier and expected SHA256")
        classifier_sha = sha256_path(args.context_classifier)
        if classifier_sha != args.expected_context_classifier_sha256:
            raise ValueError("context classifier SHA mismatch")
        classifier_payload = torch.load(args.context_classifier, map_location="cpu", weights_only=False)
        classifier = classifier_payload["models"]["64"]
    elif args.context_classifier is not None or args.expected_context_classifier_sha256 is not None:
        parser.error("raw-interaction mode does not accept a context classifier")
    states = collect_balanced_states(2048, int(spec["seed"]) + 1777)
    seed_summaries = []
    artifacts = []
    for seed_index in range(args.seeds):
        run_seed = args.seed + seed_index * 10_007
        torch.manual_seed(run_seed)
        if args.context_mode == "posterior-centered":
            model = PosteriorCenteredResidualPolicy(base_policy.model, classifier, hidden=128, policy_delta_cap=0.25).to(args.device).eval()
        else:
            model = ContextualResidualPolicy(base_policy.model, hidden=128, policy_delta_cap=0.25).to(args.device).eval()
        initial_sha = residual_state_digest(model)
        training_path = args.out_dir / f"seed{seed_index}_training_hands.jsonl.gz"
        transitions, training_rows = collect_training(
            model, base_policy, training, seed=run_seed, warmup_hands=args.warmup_hands,
            learning_hands_per_group=args.learning_hands_per_group, device=args.device,
        )
        # Persist rollout evidence before any support or optimizer failure.
        write_jsonl_gz(training_path, training_rows)
        optimizer, geometry, schedules, context_update_l2, group_support = train_mgda(
            model, transitions, steps=args.steps, group_batch_size=args.group_batch_size, seed=run_seed, device=args.device
        )
        policies = [("training", row) for row in training] + [("holdout", row) for row in holdouts]
        eval_rows, eval_warmups, max_eval_delta, contexts = evaluate(
            model, base_policy, policies, seed=run_seed + 70_000_001, warmup_hands=args.warmup_hands,
            pairs_per_policy=args.pairs_per_policy, device=args.device,
        )
        preservation = active_preservation(model, base_policy, states, contexts, args.device)
        checkpoint_path = args.out_dir / f"seed{seed_index}_contextual_residual.pt"
        torch.save({
            "schema": "cardpilot.contextual_residual.v1", "seed": run_seed, "base_sha256": base_sha,
            "context_mode": args.context_mode, "context_classifier_sha256": classifier_sha,
            "initial_residual_sha256": initial_sha, "residual_state_dict": residual_state(model),
            "optimizer": optimizer.state_dict(), "warmup_hands": args.warmup_hands,
            "learning_hands_per_group": args.learning_hands_per_group,
        }, checkpoint_path)
        eval_path = args.out_dir / f"seed{seed_index}_evaluation_hands.jsonl.gz"
        schedule_path = args.out_dir / f"seed{seed_index}_schedule.jsonl.gz"
        write_jsonl_gz(eval_path, eval_warmups + eval_rows)
        write_jsonl_gz(schedule_path, [{"step": i, "indices": [row.tolist() for row in schedule]} for i, schedule in enumerate(schedules)])
        seed_summary = {
            "seed_index": seed_index, "seed": run_seed,
            "training_environment_hands": len(training_rows), "learning_hands": 12 * args.learning_hands_per_group,
            "transition_rows": len(transitions), "evaluation_environment_hands": len(eval_warmups) + 3 * len(eval_rows),
            "group_decision_support": group_support,
            "positive_worst_alignment_fraction": float(np.mean([r["applied_worst_alignment"] > 0 for r in geometry])),
            "conditioning_parameter_update_l2": context_update_l2, "evaluation": summarize(eval_rows),
            "preservation": preservation, "maximum_evaluation_delta": max_eval_delta,
            "checkpoint": str(checkpoint_path.resolve()), "checkpoint_sha256": sha256_path(checkpoint_path),
            "training_evidence_sha256": sha256_path(training_path), "evaluation_evidence_sha256": sha256_path(eval_path),
            "schedule_sha256": sha256_path(schedule_path),
        }
        seed_summaries.append(seed_summary)
        artifacts.extend([checkpoint_path, training_path, eval_path, schedule_path])
        print(json.dumps({"seed": seed_index, "train_hands": len(training_rows), "pooled_delta": seed_summary["evaluation"]["pooled_correct_minus_base"]["bb100"], "correct_minus_wrong": seed_summary["evaluation"]["pooled_correct_minus_wrong"]["bb100"], "agreement": preservation["overall_agreement"]}), flush=True)
    gates = {
        "training_hands_exact": sum(r["training_environment_hands"] for r in seed_summaries) == args.seeds * 12 * (args.warmup_hands + args.learning_hands_per_group),
        "all_geometry_positive_at_least_75pct": all(r["positive_worst_alignment_fraction"] >= 0.75 for r in seed_summaries),
        "all_conditioning_parameters_updated": all(r["conditioning_parameter_update_l2"] > 0 for r in seed_summaries),
        "all_zero_context_exact": all(r["preservation"]["zero_context_exact"] for r in seed_summaries),
        "all_active_source_agreement_at_least_95pct": all(r["preservation"]["overall_agreement"] >= 0.95 for r in seed_summaries),
        "all_active_source_partitions_at_least_90pct": all(r["preservation"]["minimum_partition_agreement"] >= 0.90 for r in seed_summaries),
        "all_residual_caps_respected": all(max(r["maximum_evaluation_delta"], r["preservation"]["max_abs_residual_logit"]) <= 0.250001 for r in seed_summaries),
        "base_state_unchanged": all(torch.equal(base_state[name], tensor.detach().cpu()) for name, tensor in base_policy.model.state_dict().items()),
        "base_file_hash_unchanged": sha256_path(args.base_checkpoint) == base_sha,
        "median_correct_context_delta_nonnegative": float(np.median([r["evaluation"]["pooled_correct_minus_base"]["bb100"] for r in seed_summaries])) >= 0,
        "median_correct_context_beats_wrong_context": float(np.median([r["evaluation"]["pooled_correct_minus_wrong"]["bb100"] for r in seed_summaries])) > 0,
    }
    admitted = all(gates.values())
    summary = {
        "schema": "cardpilot.contextual_residual_mgda_smoke.v1", "status": "COMPLETED",
        "claim_scope": "BROAD_CONTEXTUAL_POLICY_MECHANISM_NOT_SLUMBOT_STRENGTH",
        "base_sha256": base_sha, "spec_sha256": sha256_path(args.spec),
        "context_mode": args.context_mode, "context_classifier_sha256": classifier_sha,
        "training_policies": [{"label": p.label, "sha256": p.sha256} for p in training],
        "holdout_policies": [{"label": p.label, "sha256": p.sha256} for p in holdouts],
        "actual_environment_training_hands": sum(r["training_environment_hands"] for r in seed_summaries),
        "actual_learning_hands": sum(r["learning_hands"] for r in seed_summaries),
        "evaluation_hands": sum(r["evaluation_environment_hands"] for r in seed_summaries),
        "seed_summaries": seed_summaries, "gates": gates, "admitted": admitted,
        "decision": "ADMIT_CONTEXTUAL_RESIDUAL_GEOMETRIC_SCALE" if admitted else "HOLD_CONTEXTUAL_RESIDUAL_AFTER_SMOKE",
        "wall_time_seconds": time.time() - started, "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv], "artifact_sha256": {str(path.name): sha256_path(path) for path in artifacts},
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"hands": summary["actual_environment_training_hands"], "evaluation_hands": summary["evaluation_hands"], "gates": gates, "decision": summary["decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
