"""Restart-safe broad mixed-contract MGDA residual training curve."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
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
from alpha_holdem.legacy_observation_bridge_v6 import action_prefix, decide as legacy_decide, load_policy
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v5_mirror_eval import init_model, read_checkpoint
from alpha_holdem.v6_broad_league_domain_feasibility import (
    _obs_for_state,
    collect_balanced_states,
    observation_style,
    sha256_path,
)
from alpha_holdem.v6_dual_contract_gradient_conflict_audit import flatten_gradients, residual_state_digest
from alpha_holdem.v6_dual_contract_mgda_matched_smoke import (
    aggregate_policy_gradients,
    residual_state,
    set_flat_gradient,
)
from alpha_holdem.v6_dual_contract_residual_training_smoke import (
    mean_ci95,
    residual_decide,
    stack_rows,
)


@dataclass
class FrozenPolicy:
    label: str
    path: Path
    sha256: str
    observation_style: str
    model: torch.nn.Module
    device: str


def load_frozen_policy(entry: dict, device: str) -> FrozenPolicy:
    path = Path(entry["path"]).resolve()
    checkpoint = read_checkpoint(path)
    style = observation_style(checkpoint)
    model = init_model(checkpoint, device).eval()
    return FrozenPolicy(str(entry["label"]), path, sha256_path(path), style, model, device)


@torch.inference_mode()
def frozen_decide(policy: FrozenPolicy, state: ChipState, *, uniform: float | None) -> str:
    obs, table = _obs_for_state(policy.model, state, policy.observation_style)
    tensors = [
        torch.as_tensor(obs[key], dtype=torch.float32, device=policy.device).unsqueeze(0)
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ]
    logits, _ = policy.model(*tensors)
    legal = np.flatnonzero(np.asarray(obs["legal_mask"]) > 0)
    values = logits[0, legal].detach().cpu().numpy().astype(np.float64)
    weights = np.exp(values - values.max())
    probabilities = weights / weights.sum()
    if uniform is None:
        local_index = int(np.argmax(values))
    else:
        local_index = min(int(np.searchsorted(np.cumsum(probabilities), uniform, side="right")), len(legal) - 1)
    action = table[int(legal[local_index])]
    if action is None:
        raise ValueError(f"{policy.label}: selected empty action")
    return action


def collect_chunk(model, base_policy, opponents, *, seed: int, hand_offset: int, hand_count: int, device: str):
    transitions = []
    hands = []
    group_count = len(opponents) * 2
    for local_index in range(hand_count):
        hand_index = hand_offset + local_index
        seed_base = seed * 1_000_003 + hand_index * 101
        deck_rng = random.Random(seed_base + 11)
        hero_rng = random.Random(seed_base + 23)
        opponent_rng = random.Random(seed_base + 37)
        deck = list(range(52))
        deck_rng.shuffle(deck)
        state = ChipState.new(deck)
        group_index = hand_index % group_count
        opponent_index = group_index // 2
        hero_seat = group_index % 2
        opponent = opponents[opponent_index]
        rows = []
        decisions = []
        while not state.terminal:
            if state.actor == hero_seat:
                prefix = action_prefix(state)
                action, metadata = residual_decide(model, base_policy, state, device, uniform=hero_rng.random())
                metadata["group"] = f"opponent{opponent_index:02d}_seat{hero_seat}"
                rows.append(metadata)
                decisions.append({"action_prefix": prefix, "slot": metadata["slot"]})
            else:
                action = frozen_decide(opponent, state, uniform=opponent_rng.random())
            state = apply_incr(state, action)
        reward_bb = float(state.payoffs()[hero_seat]) / 100.0
        for row in rows:
            row["return"] = reward_bb / 200.0
            transitions.append(row)
        hands.append({
            "hand_index": hand_index,
            "deck": deck,
            "hero_seat": hero_seat,
            "opponent_index": opponent_index,
            "opponent_label": opponent.label,
            "opponent_sha256": opponent.sha256,
            "reward_bb": reward_bb,
            "hero_decisions": decisions,
        })
    return transitions, hands


def train_chunk(model, optimizer, transitions, *, steps: int, group_batch_size: int, expected_groups: int, schedule_seed: int, device: str):
    old_log_probs = torch.tensor([row["log_prob"] for row in transitions], dtype=torch.float32, device=device)
    old_values = torch.tensor([row["value"] for row in transitions], dtype=torch.float32, device=device)
    returns = torch.tensor([row["return"] for row in transitions], dtype=torch.float32, device=device)
    actions = torch.tensor([row["slot"] for row in transitions], dtype=torch.long, device=device)
    tensors = [stack_rows(transitions, index, device) for index in range(8)]
    raw_advantages = returns - old_values
    group_names = sorted({row["group"] for row in transitions})
    if len(group_names) != expected_groups:
        raise RuntimeError(f"expected {expected_groups} groups, got {group_names}")
    group_indices = [
        np.asarray([index for index, row in enumerate(transitions) if row["group"] == group], dtype=np.int64)
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
    decision_weights = np.full(expected_groups, 1.0 / expected_groups, dtype=np.float64)
    rng = np.random.default_rng(schedule_seed)
    schedules = [[rng.choice(indices, size=group_batch_size, replace=False) for indices in group_indices] for _ in range(steps)]
    parameters = list(model.trainable_parameters())
    metrics = []
    model.train()
    for step, selections in enumerate(schedules):
        gradients = []
        for group_index, selected_cpu in enumerate(selections):
            selected = torch.as_tensor(selected_cpu, dtype=torch.long, device=device)
            batch = [tensor[selected] for tensor in tensors]
            logits, _ = model(*batch)
            distribution = torch.distributions.Categorical(logits=logits + (1.0 - batch[6]) * -1e9)
            log_probs = distribution.log_prob(actions[selected])
            ratio = torch.exp(log_probs - old_log_probs[selected])
            advantage = group_advantages[group_index][selected]
            surrogate = torch.minimum(ratio * advantage, ratio.clamp(0.8, 1.2) * advantage)
            gradients.append(flatten_gradients(-surrogate.mean(), parameters).cpu().double().numpy())
        policy_gradient, geometry = aggregate_policy_gradients(np.stack(gradients), decision_weights, True)
        combined = torch.as_tensor(np.concatenate(selections), dtype=torch.long, device=device)
        batch = [tensor[combined] for tensor in tensors]
        logits, values = model(*batch)
        distribution = torch.distributions.Categorical(logits=logits + (1.0 - batch[6]) * -1e9)
        value_loss = (values.squeeze(1) - returns[combined]).square().mean()
        entropy = distribution.entropy().mean()
        auxiliary = flatten_gradients(value_loss - 0.005 * entropy, parameters)
        total = torch.from_numpy(policy_gradient).to(device=device, dtype=auxiliary.dtype) + auxiliary
        optimizer.zero_grad(set_to_none=True)
        set_flat_gradient(parameters, total)
        preclip = float(torch.linalg.vector_norm(total))
        torch.nn.utils.clip_grad_norm_(parameters, 1.0)
        optimizer.step()
        metrics.append({
            "step": step,
            "sample_rows": int(len(combined)),
            "value_loss": float(value_loss.detach()),
            "entropy": float(entropy.detach()),
            "total_gradient_l2_preclip": preclip,
            **geometry,
        })
    model.eval()
    schedule_rows = [{"step": step, "groups": group_names, "indices": [row.tolist() for row in selections]} for step, selections in enumerate(schedules)]
    return metrics, schedule_rows


def atomic_torch_save(payload: dict, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)


def write_gzip_jsonl(path: Path, rows: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    temporary.replace(path)


def play_evaluation_hand(*, residual, base_policy, opponent, deck, hero_seat: int, treatment: bool, device: str):
    state = ChipState.new(deck)
    max_delta = 0.0
    while not state.terminal:
        if state.actor == hero_seat:
            if treatment:
                action, metadata = residual_decide(residual, base_policy, state, device)
                max_delta = max(max_delta, metadata["max_abs_logit_delta"])
            else:
                action, _ = legacy_decide(base_policy, state, uniform=0.0, policy_mode="greedy")
        else:
            action = frozen_decide(opponent, state, uniform=None)
        state = apply_incr(state, action)
    return float(state.payoffs()[hero_seat]) / 100.0, max_delta


def summarize_evaluation(rows: list[dict]) -> dict:
    deltas = np.asarray([row["delta_bb"] for row in rows], dtype=np.float64)
    mean, half = mean_ci95(deltas)
    holdouts = []
    for label in sorted({row["holdout_label"] for row in rows}):
        selected = [row for row in rows if row["holdout_label"] == label]
        local_mean, local_half = mean_ci95([row["delta_bb"] for row in selected])
        holdouts.append({"label": label, "pairs": len(selected), "delta_bb100": local_mean * 100.0, "delta_ci95_half_bb100": local_half * 100.0})
    seats = []
    for seat in (0, 1):
        local_mean, local_half = mean_ci95([row["seat_delta_bb"][seat] for row in rows])
        seats.append({"seat": seat, "delta_bb100": local_mean * 100.0, "delta_ci95_half_bb100": local_half * 100.0})
    return {"pairs": len(rows), "pooled_delta_bb100": mean * 100.0, "pooled_delta_ci95_half_bb100": half * 100.0, "holdouts": holdouts, "seats": seats}


def source_preservation(residual, base_policy, states, device: str) -> dict:
    rows = []
    max_delta = 0.0
    for state in states:
        base_action, _ = legacy_decide(base_policy, state, uniform=0.0, policy_mode="greedy")
        candidate_action, metadata = residual_decide(residual, base_policy, state, device)
        max_delta = max(max_delta, metadata["max_abs_logit_delta"])
        rows.append({"street": state.street, "seat": state.actor, "agree": base_action == candidate_action})
    partitions = []
    for street in range(4):
        for seat in (0, 1):
            selected = [row["agree"] for row in rows if row["street"] == street and row["seat"] == seat]
            partitions.append({"street": street, "seat": seat, "states": len(selected), "agreement": float(np.mean(selected))})
    return {"states": len(rows), "overall_agreement": float(np.mean([row["agree"] for row in rows])), "minimum_partition_agreement": min(row["agreement"] for row in partitions), "partitions": partitions, "max_abs_residual_logit": max_delta}


def research_admission(curve: list[dict], slopes: list[dict], final_chunk: int, seeds: int) -> dict:
    final_rows = [row for row in curve if row["chunk_index"] == final_chunk]
    holdout_points = [
        holdout["delta_bb100"] for row in final_rows for holdout in row["holdouts"]
    ]
    seat_points = [seat["delta_bb100"] for row in final_rows for seat in row["seats"]]
    required_positive_slopes = math.ceil(2 * seeds / 3)
    positive_slopes = sum(row["slope_bb100"] > 0 for row in slopes)
    return {
        "required_positive_seed_slopes": required_positive_slopes,
        "positive_seed_slopes": positive_slopes,
        "positive_slope_in_at_least_two_thirds_seeds": positive_slopes >= required_positive_slopes,
        "median_final_seed_holdout_delta_bb100": float(np.median(holdout_points)),
        "median_final_seed_holdout_delta_nonnegative": float(np.median(holdout_points)) >= 0,
        "median_final_seed_seat_delta_bb100": float(np.median(seat_points)),
        "median_final_seed_seat_delta_nonnegative": float(np.median(seat_points)) >= 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--seeds", type=int, required=True)
    parser.add_argument("--hands-per-chunk", type=int, required=True)
    parser.add_argument("--chunks", type=int, required=True)
    parser.add_argument("--steps-per-chunk", type=int, required=True)
    parser.add_argument("--group-batch-size", type=int, required=True)
    parser.add_argument("--evaluation-chunk", action="append", type=int, required=True)
    parser.add_argument("--pairs-per-holdout", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.seeds < 1 or args.chunks < 1 or args.hands_per_chunk < 2048:
        parser.error("invalid curve dimensions")
    evaluation_chunks = sorted(set(args.evaluation_chunk))
    if not evaluation_chunks or evaluation_chunks[-1] > args.chunks or evaluation_chunks[0] < 1:
        parser.error("evaluation chunks must fall inside the training curve")
    spec_path = args.spec.resolve()
    base_path = args.base_checkpoint.resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    training_entries = list(spec["training_policies"])
    holdout_entries = list(spec["holdout_policies"])
    if len(training_entries) != 6 or len(holdout_entries) != 3:
        raise ValueError("broad curve requires exactly six training and three holdout policies")
    base_sha = sha256_path(base_path)
    spec_sha = sha256_path(spec_path)
    config = {
        "schema": "cardpilot.broad_mgda_run_manifest.v1",
        "spec_sha256": spec_sha,
        "base_sha256": base_sha,
        "seed": args.seed,
        "seeds": args.seeds,
        "hands_per_chunk": args.hands_per_chunk,
        "chunks": args.chunks,
        "steps_per_chunk": args.steps_per_chunk,
        "group_batch_size": args.group_batch_size,
        "evaluation_chunks": evaluation_chunks,
        "pairs_per_holdout": args.pairs_per_holdout,
    }
    config_sha = hashlib.sha256(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out_dir / "run_manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("config_sha256") != config_sha:
            raise ValueError("resume configuration does not match run manifest")
    else:
        manifest_path.write_text(json.dumps({**config, "config_sha256": config_sha, "created_at": datetime.now(timezone.utc).isoformat()}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    base_policy = load_policy(base_path, args.device)
    base_state = {name: tensor.detach().cpu().clone() for name, tensor in base_policy.model.state_dict().items()}
    train_policies = [load_frozen_policy(entry, args.device) for entry in training_entries]
    holdout_policies = [load_frozen_policy(entry, args.device) for entry in holdout_entries]
    train_shas = {policy.sha256 for policy in train_policies}
    holdout_shas = {policy.sha256 for policy in holdout_policies}
    if not train_shas.isdisjoint(holdout_shas):
        raise ValueError("training and holdout checkpoint identities overlap")
    checkpoints = []
    training_chunks = []
    resumed_chunks = 0
    total_transitions = 0
    optimizer_states_nonempty = True
    resume_evidence_hashes_match = True
    for seed_index in range(args.seeds):
        run_seed = args.seed + seed_index * 10_007
        torch.manual_seed(run_seed)
        model = DualContractResidualPolicy(base_policy.model, hidden=128, policy_delta_cap=0.25).to(args.device).eval()
        initial_sha = residual_state_digest(model)
        optimizer = torch.optim.Adam(model.trainable_parameters(), lr=3e-4)
        completed = 0
        for chunk_index in range(args.chunks):
            cumulative_hands = (chunk_index + 1) * args.hands_per_chunk
            checkpoint_path = args.out_dir / f"seed{seed_index}_chunk{chunk_index + 1:03d}_hands{cumulative_hands:09d}.pt"
            evidence_path = args.out_dir / f"seed{seed_index}_chunk{chunk_index + 1:03d}_hands.jsonl.gz"
            schedule_path = args.out_dir / f"seed{seed_index}_chunk{chunk_index + 1:03d}_schedule.jsonl.gz"
            if checkpoint_path.exists():
                checkpoint = torch.load(checkpoint_path, map_location=args.device, weights_only=False)
                required = {"config_sha256": config_sha, "seed": run_seed, "seed_index": seed_index, "chunk_index": chunk_index + 1, "completed_environment_hands": cumulative_hands, "base_sha256": base_sha}
                if any(checkpoint.get(key) != value for key, value in required.items()):
                    raise ValueError(f"invalid resume checkpoint: {checkpoint_path}")
                if not evidence_path.is_file() or not schedule_path.is_file():
                    raise FileNotFoundError("resume checkpoint is missing chunk evidence")
                chunk_summary = checkpoint.get("chunk_summary") or {}
                evidence_match = sha256_path(evidence_path) == chunk_summary.get("evidence_sha256")
                schedule_match = sha256_path(schedule_path) == chunk_summary.get("schedule_sha256")
                resume_evidence_hashes_match &= evidence_match and schedule_match
                if not evidence_match or not schedule_match:
                    raise ValueError("resume chunk evidence hash mismatch")
                optimizer_nonempty = bool((checkpoint.get("optimizer") or {}).get("state"))
                optimizer_states_nonempty &= optimizer_nonempty
                if not optimizer_nonempty:
                    raise ValueError("resume checkpoint has empty optimizer state")
                model.load_state_dict(checkpoint["residual_state_dict"], strict=False)
                optimizer.load_state_dict(checkpoint["optimizer"])
                completed = cumulative_hands
                resumed_chunks += 1
                total_transitions += int(checkpoint["chunk_transitions"])
                training_chunks.append(checkpoint["chunk_summary"])
                checkpoints.append({"seed_index": seed_index, "chunk_index": chunk_index + 1, "hands": cumulative_hands, "path": str(checkpoint_path.resolve()), "sha256": sha256_path(checkpoint_path), "resumed": True})
                continue
            if completed != chunk_index * args.hands_per_chunk:
                raise RuntimeError("noncontiguous training prefix")
            transitions, hands = collect_chunk(model, base_policy, train_policies, seed=run_seed, hand_offset=completed, hand_count=args.hands_per_chunk, device=args.device)
            metrics, schedules = train_chunk(model, optimizer, transitions, steps=args.steps_per_chunk, group_batch_size=args.group_batch_size, expected_groups=len(train_policies) * 2, schedule_seed=run_seed + chunk_index * 1009, device=args.device)
            for row in hands:
                row.update({"seed_index": seed_index, "chunk_index": chunk_index + 1})
            for row in schedules:
                row.update({"seed_index": seed_index, "chunk_index": chunk_index + 1})
            write_gzip_jsonl(evidence_path, hands)
            write_gzip_jsonl(schedule_path, schedules)
            positive_fraction = float(np.mean([row["applied_worst_alignment"] > 0 for row in metrics]))
            chunk_summary = {"seed_index": seed_index, "seed": run_seed, "chunk_index": chunk_index + 1, "start_hands": completed, "end_hands": cumulative_hands, "environment_hands": len(hands), "transitions": len(transitions), "positive_worst_alignment_fraction": positive_fraction, "evidence_sha256": sha256_path(evidence_path), "schedule_sha256": sha256_path(schedule_path)}
            payload = {
                "schema": "cardpilot.broad_mgda_checkpoint.v1",
                "config_sha256": config_sha,
                "base_checkpoint": str(base_path),
                "base_sha256": base_sha,
                "spec_sha256": spec_sha,
                "seed": run_seed,
                "seed_index": seed_index,
                "chunk_index": chunk_index + 1,
                "completed_environment_hands": cumulative_hands,
                "initial_residual_sha256": initial_sha,
                "residual_state_dict": residual_state(model),
                "optimizer": optimizer.state_dict(),
                "chunk_transitions": len(transitions),
                "step_metrics": metrics,
                "chunk_summary": chunk_summary,
            }
            optimizer_nonempty = bool(payload["optimizer"].get("state"))
            optimizer_states_nonempty &= optimizer_nonempty
            if not optimizer_nonempty:
                raise RuntimeError("trained checkpoint has empty optimizer state")
            atomic_torch_save(payload, checkpoint_path)
            completed = cumulative_hands
            total_transitions += len(transitions)
            training_chunks.append(chunk_summary)
            checkpoints.append({"seed_index": seed_index, "chunk_index": chunk_index + 1, "hands": cumulative_hands, "path": str(checkpoint_path.resolve()), "sha256": sha256_path(checkpoint_path), "resumed": False})
            print(f"seed={seed_index} chunk={chunk_index + 1}/{args.chunks} hands={cumulative_hands} transitions={len(transitions)} positive_geometry={positive_fraction:.3f}", flush=True)
    evaluation_rows = []
    max_eval_delta = 0.0
    for seed_index in range(args.seeds):
        run_seed = args.seed + seed_index * 10_007
        for chunk_index in evaluation_chunks:
            cumulative_hands = chunk_index * args.hands_per_chunk
            checkpoint_path = args.out_dir / f"seed{seed_index}_chunk{chunk_index:03d}_hands{cumulative_hands:09d}.pt"
            checkpoint = torch.load(checkpoint_path, map_location=args.device, weights_only=False)
            model = DualContractResidualPolicy(base_policy.model, hidden=128, policy_delta_cap=0.25).to(args.device).eval()
            model.load_state_dict(checkpoint["residual_state_dict"], strict=False)
            for holdout_index, holdout in enumerate(holdout_policies):
                rng = random.Random(run_seed + 30_000_007 * (holdout_index + 1))
                for pair_index in range(args.pairs_per_holdout):
                    deck = list(range(52))
                    rng.shuffle(deck)
                    control_rewards = []
                    treatment_rewards = []
                    for seat in (0, 1):
                        control, _ = play_evaluation_hand(residual=model, base_policy=base_policy, opponent=holdout, deck=deck, hero_seat=seat, treatment=False, device=args.device)
                        treatment, observed = play_evaluation_hand(residual=model, base_policy=base_policy, opponent=holdout, deck=deck, hero_seat=seat, treatment=True, device=args.device)
                        control_rewards.append(control)
                        treatment_rewards.append(treatment)
                        max_eval_delta = max(max_eval_delta, observed)
                    seat_delta = [treatment_rewards[seat] - control_rewards[seat] for seat in (0, 1)]
                    evaluation_rows.append({"seed_index": seed_index, "chunk_index": chunk_index, "cumulative_hands": cumulative_hands, "holdout_index": holdout_index, "holdout_label": holdout.label, "holdout_sha256": holdout.sha256, "pair_index": pair_index, "deck": deck, "control_rewards_bb": control_rewards, "treatment_rewards_bb": treatment_rewards, "seat_delta_bb": seat_delta, "delta_bb": sum(seat_delta) / 2.0})
    evaluation_path = args.out_dir / "evaluation_pairs.jsonl.gz"
    write_gzip_jsonl(evaluation_path, evaluation_rows)
    curve = []
    for seed_index in range(args.seeds):
        for chunk_index in evaluation_chunks:
            selected = [row for row in evaluation_rows if row["seed_index"] == seed_index and row["chunk_index"] == chunk_index]
            curve.append({"seed_index": seed_index, "chunk_index": chunk_index, "cumulative_hands": chunk_index * args.hands_per_chunk, **summarize_evaluation(selected)})
    final_chunk = evaluation_chunks[-1]
    final_rows = [row for row in curve if row["chunk_index"] == final_chunk]
    first_chunk = evaluation_chunks[0]
    slope_rows = []
    for seed_index in range(args.seeds):
        first = next(row for row in curve if row["seed_index"] == seed_index and row["chunk_index"] == first_chunk)
        last = next(row for row in curve if row["seed_index"] == seed_index and row["chunk_index"] == final_chunk)
        slope_rows.append({"seed_index": seed_index, "first_hands": first["cumulative_hands"], "last_hands": last["cumulative_hands"], "slope_bb100": last["pooled_delta_bb100"] - first["pooled_delta_bb100"]})
    preservation_states = collect_balanced_states(4096, int(spec["seed"]) + 991)
    preservation = []
    for seed_index in range(args.seeds):
        cumulative_hands = args.chunks * args.hands_per_chunk
        checkpoint_path = args.out_dir / f"seed{seed_index}_chunk{args.chunks:03d}_hands{cumulative_hands:09d}.pt"
        checkpoint = torch.load(checkpoint_path, map_location=args.device, weights_only=False)
        model = DualContractResidualPolicy(base_policy.model, hidden=128, policy_delta_cap=0.25).to(args.device).eval()
        model.load_state_dict(checkpoint["residual_state_dict"], strict=False)
        preservation.append({"seed_index": seed_index, **source_preservation(model, base_policy, preservation_states, args.device)})
    actual_training_hands = sum(row["environment_hands"] for row in training_chunks)
    planned_training_hands = args.seeds * args.chunks * args.hands_per_chunk
    expected_labels = {policy.label for policy in train_policies}
    observed_training_labels = set()
    for row in training_chunks:
        evidence_path = args.out_dir / f"seed{row['seed_index']}_chunk{row['chunk_index']:03d}_hands.jsonl.gz"
        with gzip.open(evidence_path, "rt", encoding="utf-8") as handle:
            observed_training_labels.update(json.loads(line)["opponent_label"] for line in handle)
    gates = {
        "actual_training_hands_exact": actual_training_hands == planned_training_hands,
        "all_training_domains_observed": observed_training_labels == expected_labels,
        "holdouts_excluded_from_training": observed_training_labels.isdisjoint({policy.label for policy in holdout_policies}),
        "all_geometry_at_least_75pct": all(row["positive_worst_alignment_fraction"] >= 0.75 for row in training_chunks),
        "all_source_overall_agreement_at_least_95pct": all(row["overall_agreement"] >= 0.95 for row in preservation),
        "all_source_partitions_at_least_90pct": all(row["minimum_partition_agreement"] >= 0.90 for row in preservation),
        "residual_cap_respected": max([max_eval_delta, *[row["max_abs_residual_logit"] for row in preservation]]) <= 0.250001,
        "base_state_unchanged": all(torch.equal(base_state[name], tensor.detach().cpu()) for name, tensor in base_policy.model.state_dict().items()),
        "base_file_hash_unchanged": sha256_path(base_path) == base_sha,
        "checkpoint_count_exact": len(checkpoints) == args.seeds * args.chunks,
        "all_optimizer_states_nonempty": optimizer_states_nonempty,
        "resume_evidence_hashes_match": resume_evidence_hashes_match,
        "mixed_training_contracts": {policy.observation_style for policy in train_policies} == {"legacy_v4", "v6"},
        "mixed_holdout_contracts": {policy.observation_style for policy in holdout_policies} == {"legacy_v4", "v6"},
    }
    performance = research_admission(curve, slope_rows, final_chunk, args.seeds)
    performance_gates = {
        key: value for key, value in performance.items() if isinstance(value, bool)
    }
    research_admitted = all(gates.values()) and all(performance_gates.values())
    summary = {
        "schema": "cardpilot.broad_mgda_curve.v1",
        "status": "COMPLETED",
        "config_sha256": config_sha,
        "base_sha256": base_sha,
        "spec_sha256": spec_sha,
        "training_policies": [{"label": policy.label, "sha256": policy.sha256, "observation_style": policy.observation_style} for policy in train_policies],
        "holdout_policies": [{"label": policy.label, "sha256": policy.sha256, "observation_style": policy.observation_style} for policy in holdout_policies],
        "actual_environment_training_hands": actual_training_hands,
        "planned_environment_training_hands": planned_training_hands,
        "transition_rows": total_transitions,
        "resumed_chunks": resumed_chunks,
        "training_chunks": training_chunks,
        "checkpoints": checkpoints,
        "evaluation_hands": len(evaluation_rows) * 4,
        "evaluation_evidence_sha256": sha256_path(evaluation_path),
        "curve": curve,
        "seed_slopes": slope_rows,
        "source_preservation": preservation,
        "maximum_observed_residual_logit": max([max_eval_delta, *[row["max_abs_residual_logit"] for row in preservation]]),
        "gates": gates,
        "performance_admission": performance,
        "admitted": research_admitted,
        "decision": "ADMIT_BROAD_MGDA_NEXT_GEOMETRIC_SCALE" if research_admitted else ("HOLD_BROAD_MGDA_CURVE" if all(gates.values()) else "REPAIR_BROAD_MGDA_TRAINER"),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    temporary_summary = args.out_dir / "summary.json.tmp"
    temporary_summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary_summary.replace(args.out_dir / "summary.json")
    print(json.dumps({"actual_environment_training_hands": actual_training_hands, "evaluation_hands": summary["evaluation_hands"], "resumed_chunks": resumed_chunks, "gates": gates, "decision": summary["decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
