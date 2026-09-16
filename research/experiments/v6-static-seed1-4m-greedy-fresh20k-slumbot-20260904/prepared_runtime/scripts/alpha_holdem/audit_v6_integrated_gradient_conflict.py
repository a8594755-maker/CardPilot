"""Audit frozen integrated-policy opponent/seat gradients and league exposure."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.legacy_observation_bridge_v6 import (
    action_prefix,
    decide,
    legacy_observation,
    load_policy,
)
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_dual_contract_advantage_balance import reconstruct
from alpha_holdem.v6_dual_contract_gradient_conflict_audit import (
    minimum_norm_simplex,
    normalized_alignments,
)


POLICY_PARAMETER_PREFIXES = ("policy_head.", "preflop_policy_head.")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_named_path(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected NAME=PATH")
    name, raw_path = value.split("=", 1)
    if not name or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise argparse.ArgumentTypeError("NAME must contain only letters, digits, _ or -")
    return name, Path(raw_path)


def tensor_inputs(policy, state: ChipState, device: str) -> list[torch.Tensor]:
    obs, _ = legacy_observation(policy, state)
    return [
        torch.as_tensor(obs[key], dtype=torch.float32, device=device).unsqueeze(0)
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ]


def flatten_gradients(
    loss: torch.Tensor, parameters: list[torch.nn.Parameter]
) -> np.ndarray:
    values = torch.autograd.grad(loss, parameters, allow_unused=True)
    return np.concatenate(
        [
            np.zeros(parameter.numel(), dtype=np.float64)
            if gradient is None
            else gradient.detach().cpu().double().reshape(-1).numpy()
            for parameter, gradient in zip(parameters, values)
        ]
    )


def cosine(left: np.ndarray, right: np.ndarray) -> float | None:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= 1e-18:
        return None
    return float(np.dot(left, right) / denominator)


def collect_candidate(
    candidate_name: str,
    candidate,
    opponents: list[tuple[str, object]],
    hands_per_group: int,
    seed: int,
) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    group_summaries = []
    for opponent_index, (opponent_name, opponent) in enumerate(opponents):
        for hero_seat in (0, 1):
            group_index = opponent_index * 2 + hero_seat
            rewards = []
            decisions = 0
            for local_hand_index in range(hands_per_group):
                deck_rng = random.Random(
                    seed + 10_000_019 * group_index + 1_000_003 * local_hand_index
                )
                action_rng = random.Random(
                    seed + 700_000_027 + 10_000_019 * group_index
                    + 1_000_003 * local_hand_index
                )
                deck = list(range(52))
                deck_rng.shuffle(deck)
                state = ChipState.new(deck)
                hero_decisions = []
                while not state.terminal:
                    policy = candidate if state.actor == hero_seat else opponent
                    prefix = action_prefix(state)
                    action, metadata = decide(
                        policy,
                        state,
                        uniform=action_rng.random(),
                        policy_mode="sample",
                    )
                    if state.actor == hero_seat:
                        hero_decisions.append(
                            {
                                "action_prefix": prefix,
                                "legacy_slot": int(metadata["legacy_selected_action_slot"]),
                                "behavior_probability": float(
                                    metadata["behavior_action_probability"]
                                ),
                            }
                        )
                    state = apply_incr(state, action)
                reward_bb = float(state.payoffs()[hero_seat]) / 100.0
                rewards.append(reward_bb)
                decisions += len(hero_decisions)
                rows.append(
                    {
                        "candidate": candidate_name,
                        "deck": deck,
                        "group": f"{opponent_name}_seat{hero_seat}",
                        "group_index": group_index,
                        "hero_decisions": hero_decisions,
                        "hero_seat": hero_seat,
                        "local_hand_index": local_hand_index,
                        "opponent": opponent_name,
                        "opponent_index": opponent_index,
                        "opponent_sha256": opponent.sha256,
                        "reward_bb": reward_bb,
                    }
                )
            group_summaries.append(
                {
                    "group": f"{opponent_name}_seat{hero_seat}",
                    "hands": hands_per_group,
                    "decisions": decisions,
                    "reward_bb_per_hand": float(np.mean(rewards)),
                    "reward_bb_per_100": 100.0 * float(np.mean(rewards)),
                }
            )
            print(
                f"candidate={candidate_name} group={opponent_name}_seat{hero_seat} "
                f"hands={hands_per_group} decisions={decisions}",
                flush=True,
            )
    return rows, {"groups": group_summaries}


def decision_rows(hands: list[dict], predicate) -> list[dict]:
    rows = []
    for hand in hands:
        if not predicate(hand):
            continue
        for decision_index, decision_row in enumerate(hand["hero_decisions"]):
            rows.append(
                {
                    **decision_row,
                    "deck": hand["deck"],
                    "decision_index": decision_index,
                    "group": hand["group"],
                    "group_index": hand["group_index"],
                    "hero_seat": hand["hero_seat"],
                    "local_hand_index": hand["local_hand_index"],
                    "return_normalized": float(hand["reward_bb"]) / 200.0,
                }
            )
    return rows


def prepare_batch(rows: list[dict], candidate, source, device: str):
    candidate_arrays = [[], [], [], []]
    source_arrays = [[], [], [], []]
    actions = []
    returns = []
    for row in rows:
        state = reconstruct(row["deck"], row["action_prefix"])
        for index, tensor in enumerate(tensor_inputs(candidate, state, "cpu")):
            candidate_arrays[index].append(tensor.squeeze(0).numpy())
        for index, tensor in enumerate(tensor_inputs(source, state, "cpu")):
            source_arrays[index].append(tensor.squeeze(0).numpy())
        actions.append(int(row["legacy_slot"]))
        returns.append(float(row["return_normalized"]))
    candidate_tensors = [
        torch.as_tensor(np.stack(values), dtype=torch.float32, device=device)
        for values in candidate_arrays
    ]
    source_tensors = [
        torch.as_tensor(np.stack(values), dtype=torch.float32, device=device)
        for values in source_arrays
    ]
    return (
        candidate_tensors,
        source_tensors,
        torch.as_tensor(actions, dtype=torch.long, device=device),
        torch.as_tensor(returns, dtype=torch.float32, device=device),
    )


def policy_gradient(
    rows: list[dict], candidate, source, parameters, device: str
) -> tuple[np.ndarray, dict]:
    candidate_tensors, _, actions, returns = prepare_batch(
        rows, candidate, source, device
    )
    with torch.no_grad():
        _, values = candidate.model(*candidate_tensors)
        raw_advantages = returns - values.squeeze(1)
        normalized = (
            (raw_advantages - raw_advantages.mean())
            / raw_advantages.std().clamp_min(1e-6)
        ).clamp(-5.0, 5.0)
    logits, _ = candidate.model(*candidate_tensors)
    masked_logits = logits + (1.0 - candidate_tensors[3]) * -1e9
    log_probs = F.log_softmax(masked_logits, dim=-1).gather(
        1, actions.unsqueeze(1)
    ).squeeze(1)
    loss = -(log_probs * normalized.detach()).mean()
    gradient = flatten_gradients(loss, parameters)
    return gradient, {
        "decisions": len(rows),
        "gradient_l2": float(np.linalg.norm(gradient)),
        "loss": float(loss.detach()),
        "raw_advantage_mean": float(raw_advantages.mean()),
        "raw_advantage_std": float(raw_advantages.std()),
    }


def source_kl_gradient(
    rows: list[dict], candidate, source, parameters, device: str
) -> tuple[np.ndarray, dict]:
    candidate_tensors, source_tensors, _, _ = prepare_batch(
        rows, candidate, source, device
    )
    logits, _ = candidate.model(*candidate_tensors)
    with torch.no_grad():
        reference_logits, _ = source.model(*source_tensors)
    reference_probs = F.softmax(reference_logits, dim=-1)
    current_log_probs = F.log_softmax(logits, dim=-1)
    kl = (
        reference_probs
        * (reference_probs.clamp_min(1e-8).log() - current_log_probs)
    ).sum(dim=-1).mean()
    gradient = flatten_gradients(kl, parameters)
    return gradient, {
        "decisions": len(rows),
        "gradient_l2": float(np.linalg.norm(gradient)),
        "forward_kl": float(kl.detach()),
    }


def geometry_for_subset(
    hands: list[dict], candidate, source, device: str
) -> tuple[dict, dict[str, np.ndarray]]:
    for name, parameter in candidate.model.named_parameters():
        parameter.requires_grad_(name.startswith(POLICY_PARAMETER_PREFIXES))
    parameters = [
        parameter
        for name, parameter in candidate.model.named_parameters()
        if name.startswith(POLICY_PARAMETER_PREFIXES)
    ]
    parameter_names = [
        name
        for name, _ in candidate.model.named_parameters()
        if name.startswith(POLICY_PARAMETER_PREFIXES)
    ]
    group_names = sorted({hand["group"] for hand in hands})
    gradient_rows = []
    group_metrics = []
    for group in group_names:
        rows = decision_rows(hands, lambda hand, group=group: hand["group"] == group)
        gradient, metrics = policy_gradient(
            rows, candidate, source, parameters, device
        )
        gradient_rows.append(gradient)
        group_metrics.append({"group": group, **metrics})
    gradients = np.stack(gradient_rows)
    norms = np.linalg.norm(gradients, axis=1)
    if np.any(norms <= 1e-18):
        raise RuntimeError("one or more opponent-seat gradients are zero")
    units = gradients / norms[:, None]
    cosine_matrix = units @ units.T
    decision_weights = np.asarray(
        [row["decisions"] for row in group_metrics], dtype=np.float64
    )
    decision_weights /= decision_weights.sum()
    ordinary = decision_weights @ gradients
    ordinary_alignments = normalized_alignments(units, ordinary)
    objective, active, robust_weights, products = minimum_norm_simplex(
        cosine_matrix
    )
    robust = robust_weights @ units
    robust_alignments = normalized_alignments(units, robust)
    kl_gradients = {}
    kl_metrics = {}
    for label, predicate in (
        ("all", lambda hand: True),
        ("seat0", lambda hand: hand["hero_seat"] == 0),
        ("seat1", lambda hand: hand["hero_seat"] == 1),
    ):
        rows = decision_rows(hands, predicate)
        kl_gradients[label], kl_metrics[label] = source_kl_gradient(
            rows, candidate, source, parameters, device
        )
    opponent_aggregates = {}
    seat_aggregates = {}
    for opponent in sorted({hand["opponent"] for hand in hands}):
        selected = [index for index, group in enumerate(group_names) if group.startswith(opponent + "_")]
        weights = decision_weights[selected]
        weights /= weights.sum()
        opponent_aggregates[opponent] = weights @ gradients[selected]
    for seat in (0, 1):
        selected = [index for index, group in enumerate(group_names) if group.endswith(f"seat{seat}")]
        weights = decision_weights[selected]
        weights /= weights.sum()
        seat_aggregates[f"seat{seat}"] = weights @ gradients[selected]
    off_diagonal = [
        float(cosine_matrix[left, right])
        for left in range(len(group_names))
        for right in range(left + 1, len(group_names))
    ]
    summary = {
        "parameter_names": parameter_names,
        "parameter_count": int(sum(parameter.numel() for parameter in parameters)),
        "group_metrics": group_metrics,
        "pairwise_cosine_matrix": cosine_matrix.tolist(),
        "pairwise_cosine_minimum": min(off_diagonal),
        "pairwise_negative_count": int(sum(value < 0.0 for value in off_diagonal)),
        "pairwise_below_negative_0_10": int(sum(value < -0.10 for value in off_diagonal)),
        "ordinary_decision_weights": decision_weights.tolist(),
        "ordinary_alignments": ordinary_alignments.tolist(),
        "ordinary_worst_alignment": float(ordinary_alignments.min()),
        "ordinary_harmful_group_count": int(sum(ordinary_alignments <= 0.0)),
        "robust_active_groups": [group_names[index] for index in active],
        "robust_weights": robust_weights.tolist(),
        "robust_alignments": robust_alignments.tolist(),
        "robust_worst_alignment": float(robust_alignments.min()),
        "robust_objective": float(objective),
        "robust_kkt_valid": bool(np.all(products >= objective - 1e-7)),
        "source_kl": kl_metrics,
        "ordinary_vs_source_kl_cosine": cosine(ordinary, kl_gradients["all"]),
        "group_vs_source_kl_cosines": {
            group: cosine(gradients[index], kl_gradients["all"])
            for index, group in enumerate(group_names)
        },
        "standard10_vs_other_opponent_gradient_cosines": {
            name: cosine(opponent_aggregates["standard10"], gradient)
            for name, gradient in opponent_aggregates.items()
            if name != "standard10"
        },
        "seat0_vs_seat1_gradient_cosine": cosine(
            seat_aggregates["seat0"], seat_aggregates["seat1"]
        ),
        "source_kl_seat0_vs_seat1_cosine": cosine(
            kl_gradients["seat0"], kl_gradients["seat1"]
        ),
    }
    arrays = {
        "group_names": np.asarray(group_names),
        "group_gradients": gradients,
        "group_unit_gradients": units,
        "cosine_matrix": cosine_matrix,
        "decision_weights": decision_weights,
        "ordinary_gradient": ordinary,
        "ordinary_alignments": ordinary_alignments,
        "robust_weights": robust_weights,
        "robust_alignments": robust_alignments,
        **{f"source_kl_{key}": value for key, value in kl_gradients.items()},
    }
    return summary, arrays


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def exposure_audit(assignments_path: Path, metrics_path: Path) -> dict:
    assignments = read_jsonl(assignments_path)
    metrics = read_jsonl(metrics_path)
    if len(assignments) != len(metrics) or not assignments:
        raise ValueError("assignment and metric logs must have equal nonzero rows")
    categories = {0: "standard10", 1: "legacy_anchor", 2: "cfr4"}
    segment_bounds = [(1, 32), (33, 64), (65, 96), (97, 128), (129, 160), (161, 192), (193, 220)]
    totals = defaultdict(lambda: {"hands": 0, "reward_sum": 0.0, "probabilities": []})
    segments = []
    previous_completed = 0
    total_environment = 0
    self_play_estimate = 0
    stable_fixed_ids = True
    for assignment, metric in zip(assignments, metrics):
        iteration = int(metric["iteration"])
        if int(assignment["applies_to_iteration"]) != iteration:
            raise ValueError("assignment/metric iteration mismatch")
        refs = assignment["pool_snapshot_refs"]
        stable_fixed_ids &= all(
            len(refs) > index
            and int(refs[index]["local_index"]) == index
            and int(refs[index]["snapshot_id"]) == index
            for index in categories
        )
        completed = int(metric["environment_hand_accounting"]["completed_hands"])
        environment_increment = completed - previous_completed
        previous_completed = completed
        total_environment += environment_increment
        pool_hands = 0
        metric_by_id = {
            int(row["opponent_id"]): row
            for row in metric["adaptive_opponent_league"]
        }
        weights = [float(value) for value in assignment["pool_sampling_weights"]]
        for opponent_id, row in metric_by_id.items():
            category = categories.get(opponent_id, "dynamic_snapshot")
            hands = int(row["iteration_hands"])
            observed = row["iteration_hero_reward_mean"]
            totals[category]["hands"] += hands
            if observed is not None:
                totals[category]["reward_sum"] += hands * float(observed)
            if opponent_id < len(weights):
                totals[category]["probabilities"].append(weights[opponent_id])
            pool_hands += hands
        self_play_estimate += environment_increment - pool_hands
    for first, last in segment_bounds:
        if first > len(metrics):
            continue
        bucket = defaultdict(lambda: {"hands": 0, "reward_sum": 0.0})
        env_start = (
            int(metrics[first - 2]["environment_hand_accounting"]["completed_hands"])
            if first > 1 else 0
        )
        env_end = int(metrics[min(last, len(metrics)) - 1]["environment_hand_accounting"]["completed_hands"])
        for metric in metrics[first - 1:min(last, len(metrics))]:
            for row in metric["adaptive_opponent_league"]:
                category = categories.get(int(row["opponent_id"]), "dynamic_snapshot")
                hands = int(row["iteration_hands"])
                bucket[category]["hands"] += hands
                if row["iteration_hero_reward_mean"] is not None:
                    bucket[category]["reward_sum"] += hands * float(row["iteration_hero_reward_mean"])
        segments.append(
            {
                "iterations": [first, min(last, len(metrics))],
                "environment_hands": env_end - env_start,
                "categories": {
                    category: {
                        "hands": values["hands"],
                        "reward_bb_per_hand": (
                            values["reward_sum"] / values["hands"]
                            if values["hands"] else None
                        ),
                    }
                    for category, values in sorted(bucket.items())
                },
            }
        )
    pool_total = sum(values["hands"] for values in totals.values())
    return {
        "assignment_rows": len(assignments),
        "metric_rows": len(metrics),
        "stable_fixed_anchor_local_ids": stable_fixed_ids,
        "total_environment_hands": total_environment,
        "pool_opponent_hands": pool_total,
        "estimated_self_play_hands": self_play_estimate,
        "categories": {
            category: {
                "hands": values["hands"],
                "share_of_pool_hands": values["hands"] / pool_total,
                "share_of_all_environment_hands": values["hands"] / total_environment,
                "reward_bb_per_hand": values["reward_sum"] / values["hands"],
                "mean_assignment_probability": float(np.mean(values["probabilities"])),
            }
            for category, values in sorted(totals.items())
        },
        "segments": segments,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="append", type=parse_named_path, required=True)
    parser.add_argument("--opponent", action="append", type=parse_named_path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--assignments", action="append", type=parse_named_path, required=True)
    parser.add_argument("--metrics", action="append", type=parse_named_path, required=True)
    parser.add_argument("--hands-per-group", type=int, required=True)
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if len(args.opponent) != 3:
        parser.error("exactly three named opponents are required")
    if args.opponent[0][0] != "standard10":
        parser.error("the first opponent must be named standard10")
    if args.hands_per_group < args.folds or args.folds < 2:
        parser.error("hands-per-group must be >= folds >= 2")
    candidates = dict(args.candidate)
    assignments = dict(args.assignments)
    metrics = dict(args.metrics)
    if set(candidates) != set(assignments) or set(candidates) != set(metrics):
        parser.error("candidate, assignments and metrics names must match")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(args.seed)
    started = time.time()

    source_path = args.source.resolve()
    source = load_policy(source_path, args.device)
    opponent_rows = [
        (name, load_policy(path.resolve(), args.device))
        for name, path in args.opponent
    ]
    raw_path = args.out_dir / "frozen_training_hands.jsonl.gz"
    summary_candidates = {}
    npz_arrays = {}
    with gzip.open(raw_path, "xt", encoding="utf-8", newline="\n") as raw_handle:
        for candidate_name, candidate_path in candidates.items():
            candidate_path = candidate_path.resolve()
            candidate = load_policy(candidate_path, args.device)
            hands, collection = collect_candidate(
                candidate_name,
                candidate,
                opponent_rows,
                args.hands_per_group,
                args.seed,
            )
            for hand in hands:
                raw_handle.write(json.dumps(hand, sort_keys=True) + "\n")
            full, arrays = geometry_for_subset(
                hands, candidate, source, args.device
            )
            folds = []
            for fold in range(args.folds):
                fold_hands = [
                    hand for hand in hands
                    if hand["local_hand_index"] % args.folds == fold
                ]
                fold_summary, _ = geometry_for_subset(
                    fold_hands, candidate, source, args.device
                )
                folds.append(
                    {
                        "fold": fold,
                        "pairwise_below_negative_0_10": fold_summary["pairwise_below_negative_0_10"],
                        "ordinary_worst_alignment": fold_summary["ordinary_worst_alignment"],
                        "ordinary_harmful_group_count": fold_summary["ordinary_harmful_group_count"],
                        "ordinary_vs_source_kl_cosine": fold_summary["ordinary_vs_source_kl_cosine"],
                        "seat0_vs_seat1_gradient_cosine": fold_summary["seat0_vs_seat1_gradient_cosine"],
                        "standard10_vs_other_opponent_gradient_cosines": fold_summary["standard10_vs_other_opponent_gradient_cosines"],
                    }
                )
            exposure = exposure_audit(
                assignments[candidate_name].resolve(), metrics[candidate_name].resolve()
            )
            summary_candidates[candidate_name] = {
                "checkpoint": str(candidate_path),
                "checkpoint_sha256": candidate.sha256,
                "collection": collection,
                "full_geometry": full,
                "folds": folds,
                "exposure": exposure,
            }
            safe_name = candidate_name.replace("-", "_")
            for key, value in arrays.items():
                npz_arrays[f"{safe_name}__{key}"] = value
            del candidate
            if args.device == "cuda":
                torch.cuda.empty_cache()

    gradient_path = args.out_dir / "gradient_geometry.npz"
    np.savez_compressed(gradient_path, **npz_arrays)
    material_by_candidate = {
        name: bool(
            row["full_geometry"]["pairwise_below_negative_0_10"] >= 2
            or row["full_geometry"]["ordinary_harmful_group_count"] >= 1
        )
        for name, row in summary_candidates.items()
    }
    material_fold_counts = {
        name: sum(
            fold["pairwise_below_negative_0_10"] >= 2
            or fold["ordinary_harmful_group_count"] >= 1
            for fold in row["folds"]
        )
        for name, row in summary_candidates.items()
    }
    reproducible_material_conflict = bool(
        all(material_by_candidate.values())
        and all(count >= math.ceil(0.75 * args.folds) for count in material_fold_counts.values())
    )
    seat_conflict_fold_counts = {
        name: sum(fold["seat0_vs_seat1_gradient_cosine"] < 0.0 for fold in row["folds"])
        for name, row in summary_candidates.items()
    }
    reproducible_seat_conflict = bool(
        all(row["full_geometry"]["seat0_vs_seat1_gradient_cosine"] < 0.0 for row in summary_candidates.values())
        and all(count >= math.ceil(0.75 * args.folds) for count in seat_conflict_fold_counts.values())
    )
    source_conflict_fold_counts = {
        name: sum(fold["ordinary_vs_source_kl_cosine"] < 0.0 for fold in row["folds"])
        for name, row in summary_candidates.items()
    }
    reproducible_source_conflict = bool(
        all(row["full_geometry"]["ordinary_vs_source_kl_cosine"] < 0.0 for row in summary_candidates.values())
        and all(count >= math.ceil(0.75 * args.folds) for count in source_conflict_fold_counts.values())
    )
    standard10_underexposed = bool(
        all(
            row["exposure"]["categories"]["standard10"]["share_of_pool_hands"]
            < 0.15
            for row in summary_candidates.values()
        )
    )
    summary = {
        "schema": "cardpilot.integrated_gradient_conflict_audit.v1",
        "status": "COMPLETED",
        "source_checkpoint": str(source_path),
        "source_sha256": source.sha256,
        "opponents": [
            {"name": name, "path": str(policy.path), "sha256": policy.sha256}
            for name, policy in opponent_rows
        ],
        "hands_per_group": args.hands_per_group,
        "folds": args.folds,
        "seed": args.seed,
        "candidates": summary_candidates,
        "gates": {
            "all_fixed_anchor_ids_stable": all(
                row["exposure"]["stable_fixed_anchor_local_ids"]
                for row in summary_candidates.values()
            ),
            "material_gradient_conflict_replicates": reproducible_material_conflict,
            "seat_gradient_conflict_replicates": reproducible_seat_conflict,
            "ordinary_gradient_conflicts_with_source_kl_replicates": reproducible_source_conflict,
            "standard10_underexposed_below_15pct_pool_hands": standard10_underexposed,
        },
        "fold_reproducibility": {
            "material_conflict_folds": material_fold_counts,
            "seat_conflict_folds": seat_conflict_fold_counts,
            "source_kl_conflict_folds": source_conflict_fold_counts,
            "required_of_total": [math.ceil(0.75 * args.folds), args.folds],
        },
        "interpretation": {
            "league_floor_intervention_supported": standard10_underexposed,
            "conflict_aware_intervention_supported": bool(
                reproducible_material_conflict or reproducible_seat_conflict
            ),
            "source_preservation_constraint_supported": reproducible_source_conflict,
            "unchanged_scale_supported": not (
                reproducible_material_conflict
                or reproducible_seat_conflict
                or reproducible_source_conflict
            ),
        },
        "raw_hands_sha256": sha256_path(raw_path),
        "gradient_artifact_sha256": sha256_path(gradient_path),
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
