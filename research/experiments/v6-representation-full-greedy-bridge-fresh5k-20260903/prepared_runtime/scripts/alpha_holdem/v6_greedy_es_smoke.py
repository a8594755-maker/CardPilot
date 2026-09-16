"""Mirrored evolution-strategy smoke for a greedy residual poker policy."""
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
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_broad_league_domain_feasibility import collect_balanced_states
from alpha_holdem.v6_broad_mgda_curve import (
    load_frozen_policy,
    play_evaluation_hand,
    source_preservation,
)
from alpha_holdem.v6_dual_contract_mgda_matched_smoke import residual_state
from alpha_holdem.v6_dual_contract_residual_training_smoke import mean_ci95


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def robust_score(group_returns: list[list[float]], dispersion_weight: float) -> float:
    means = np.asarray([np.mean(values) for values in group_returns], dtype=np.float64)
    if means.size < 2 or not np.isfinite(means).all():
        raise ValueError("robust score requires at least two finite groups")
    return float(means.mean() - float(dispersion_weight) * means.std(ddof=0))


def es_update_direction(directions: np.ndarray, fitness_differences: np.ndarray) -> np.ndarray:
    directions = np.asarray(directions, dtype=np.float64)
    differences = np.asarray(fitness_differences, dtype=np.float64)
    if directions.ndim != 2 or differences.shape != (directions.shape[0],):
        raise ValueError("ES directions and fitness differences do not align")
    scale = float(differences.std(ddof=0))
    if scale <= 1e-12:
        return np.zeros(directions.shape[1], dtype=np.float64)
    normalized = (differences - differences.mean()) / scale
    estimate = normalized @ directions / directions.shape[0]
    norm = float(np.linalg.norm(estimate))
    return estimate / norm if norm > 1e-15 else np.zeros_like(estimate)


def policy_vector(model: DualContractResidualPolicy) -> np.ndarray:
    return np.concatenate(
        [
            model.policy_delta.weight.detach().cpu().numpy().reshape(-1),
            model.policy_delta.bias.detach().cpu().numpy().reshape(-1),
        ]
    ).astype(np.float64)


def set_policy_vector(model: DualContractResidualPolicy, vector: np.ndarray) -> None:
    vector = np.asarray(vector, dtype=np.float64)
    weight_count = model.policy_delta.weight.numel()
    if vector.shape != (weight_count + model.policy_delta.bias.numel(),):
        raise ValueError("policy vector has the wrong width")
    with torch.no_grad():
        model.policy_delta.weight.copy_(
            torch.as_tensor(
                vector[:weight_count].reshape(tuple(model.policy_delta.weight.shape)),
                device=model.policy_delta.weight.device,
                dtype=model.policy_delta.weight.dtype,
            )
        )
        model.policy_delta.bias.copy_(
            torch.as_tensor(
                vector[weight_count:],
                device=model.policy_delta.bias.device,
                dtype=model.policy_delta.bias.dtype,
            )
        )


def write_gzip_jsonl(path: Path, rows: list[dict]) -> None:
    with gzip.open(path, "xt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def paired_summary(rows: list[dict]) -> dict:
    values = [row["delta_bb"] for row in rows]
    mean, half = mean_ci95(values)
    holdouts = []
    for label in sorted({row["holdout_label"] for row in rows}):
        selected = [row for row in rows if row["holdout_label"] == label]
        local, local_half = mean_ci95([row["delta_bb"] for row in selected])
        holdouts.append(
            {
                "label": label,
                "pairs": len(selected),
                "delta_bb100": local * 100.0,
                "delta_ci95_half_bb100": local_half * 100.0,
            }
        )
    seats = []
    for seat in (0, 1):
        local, local_half = mean_ci95([row["seat_delta_bb"][seat] for row in rows])
        seats.append(
            {
                "seat": seat,
                "delta_bb100": local * 100.0,
                "delta_ci95_half_bb100": local_half * 100.0,
            }
        )
    return {
        "pairs": len(rows),
        "pooled_delta_bb100": mean * 100.0,
        "pooled_delta_ci95_half_bb100": half * 100.0,
        "holdouts": holdouts,
        "seats": seats,
    }


def correlation(left: list[float], right: list[float]) -> float:
    if len(left) < 3 or np.std(left) <= 1e-12 or np.std(right) <= 1e-12:
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--generations", type=int, default=2)
    parser.add_argument("--directions", type=int, default=8)
    parser.add_argument("--pairs-per-training-opponent", type=int, default=32)
    parser.add_argument("--pairs-per-holdout", type=int, default=128)
    parser.add_argument("--sigma", type=float, default=0.005)
    parser.add_argument("--step-l2", type=float, default=0.05)
    parser.add_argument("--max-center-l2", type=float, default=0.15)
    parser.add_argument("--dispersion-weight", type=float, default=0.25)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.generations < 1 or args.directions < 4:
        parser.error("ES smoke requires at least one generation and four directions")
    if args.pairs_per_training_opponent < 8 or args.pairs_per_holdout < 32:
        parser.error("pair budgets are below the smoke minimum")
    if args.sigma <= 0 or args.step_l2 <= 0 or args.max_center_l2 <= 0:
        parser.error("ES scales must be positive")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()

    spec_path = args.spec.resolve()
    base_path = args.base_checkpoint.resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if len(spec["training_policies"]) != 6 or len(spec["holdout_policies"]) != 3:
        raise ValueError("ES smoke requires six train and three holdout policies")
    base_sha = sha256_path(base_path)
    base_policy = load_policy(base_path, args.device)
    training = [load_frozen_policy(row, args.device) for row in spec["training_policies"]]
    holdouts = [load_frozen_policy(row, args.device) for row in spec["holdout_policies"]]
    if not {row.sha256 for row in training}.isdisjoint({row.sha256 for row in holdouts}):
        raise ValueError("training and holdout identities overlap")
    torch.manual_seed(args.seed)
    model = DualContractResidualPolicy(
        base_policy.model, hidden=128, policy_delta_cap=0.25
    ).to(args.device).eval()
    center = policy_vector(model)
    if np.count_nonzero(center) != 0:
        raise RuntimeError("ES policy output layer did not initialize at zero")
    initial_residual = residual_state(model)
    parameter_count = center.size
    rng = np.random.default_rng(args.seed + 71)
    training_rows = []
    generations = []
    checkpoint_vectors = [center.copy()]

    for generation in range(args.generations):
        directions = rng.standard_normal((args.directions, parameter_count))
        directions /= np.linalg.norm(directions, axis=1, keepdims=True)
        decks = {}
        for opponent_index in range(len(training)):
            deck_rng = random.Random(
                args.seed + (generation + 1) * 10_000_019 + opponent_index * 100_003
            )
            decks[opponent_index] = []
            for _ in range(args.pairs_per_training_opponent):
                deck = list(range(52))
                deck_rng.shuffle(deck)
                decks[opponent_index].append(deck)

        fitness = np.zeros((args.directions, 2), dtype=np.float64)
        split_fitness = np.zeros((args.directions, 2, 2), dtype=np.float64)
        for direction_index, direction in enumerate(directions):
            for sign_index, sign in enumerate((1.0, -1.0)):
                set_policy_vector(model, center + sign * args.sigma * direction)
                grouped = [[] for _ in range(len(training) * 2)]
                grouped_split = [
                    [[] for _ in range(len(training) * 2)] for _ in range(2)
                ]
                for opponent_index, opponent in enumerate(training):
                    for pair_index, deck in enumerate(decks[opponent_index]):
                        for seat in (0, 1):
                            reward, max_delta = play_evaluation_hand(
                                residual=model,
                                base_policy=base_policy,
                                opponent=opponent,
                                deck=deck,
                                hero_seat=seat,
                                treatment=True,
                                device=args.device,
                            )
                            group = opponent_index * 2 + seat
                            grouped[group].append(reward)
                            grouped_split[pair_index % 2][group].append(reward)
                            training_rows.append(
                                {
                                    "generation": generation + 1,
                                    "direction": direction_index,
                                    "sign": int(sign),
                                    "opponent_index": opponent_index,
                                    "opponent_label": opponent.label,
                                    "opponent_sha256": opponent.sha256,
                                    "pair_index": pair_index,
                                    "hero_seat": seat,
                                    "deck": deck,
                                    "reward_bb": reward,
                                    "max_abs_residual_logit": max_delta,
                                }
                            )
                fitness[direction_index, sign_index] = robust_score(
                    grouped, args.dispersion_weight
                )
                for split in (0, 1):
                    split_fitness[direction_index, sign_index, split] = robust_score(
                        grouped_split[split], args.dispersion_weight
                    )

        differences = fitness[:, 0] - fitness[:, 1]
        split_left = split_fitness[:, 0, 0] - split_fitness[:, 1, 0]
        split_right = split_fitness[:, 0, 1] - split_fitness[:, 1, 1]
        direction = es_update_direction(directions, differences)
        center = center + args.step_l2 * direction
        center_norm = float(np.linalg.norm(center))
        if center_norm > args.max_center_l2:
            center *= args.max_center_l2 / center_norm
            center_norm = args.max_center_l2
        set_policy_vector(model, center)
        checkpoint_vectors.append(center.copy())
        generations.append(
            {
                "generation": generation + 1,
                "fitness_plus": fitness[:, 0].tolist(),
                "fitness_minus": fitness[:, 1].tolist(),
                "fitness_differences": differences.tolist(),
                "positive_directions": int(np.sum(differences > 0)),
                "split_half_direction_correlation": correlation(
                    split_left.tolist(), split_right.tolist()
                ),
                "update_direction_l2": float(np.linalg.norm(direction)),
                "center_l2": center_norm,
            }
        )
        print(
            f"generation={generation + 1} positive={int(np.sum(differences > 0))}/"
            f"{args.directions} split_corr={generations[-1]['split_half_direction_correlation']:+.3f} "
            f"center_l2={center_norm:.4f}",
            flush=True,
        )

    training_path = args.out_dir / "training_hands.jsonl.gz"
    write_gzip_jsonl(training_path, training_rows)
    evaluation_rows = []
    curve = []
    for checkpoint_index, vector in enumerate(checkpoint_vectors):
        set_policy_vector(model, vector)
        rows = []
        for holdout_index, holdout in enumerate(holdouts):
            deck_rng = random.Random(args.seed + 50_000_003 + holdout_index * 1_000_003)
            for pair_index in range(args.pairs_per_holdout):
                deck = list(range(52))
                deck_rng.shuffle(deck)
                base_rewards = []
                candidate_rewards = []
                for seat in (0, 1):
                    base_reward, _ = play_evaluation_hand(
                        residual=model,
                        base_policy=base_policy,
                        opponent=holdout,
                        deck=deck,
                        hero_seat=seat,
                        treatment=False,
                        device=args.device,
                    )
                    candidate_reward, _ = play_evaluation_hand(
                        residual=model,
                        base_policy=base_policy,
                        opponent=holdout,
                        deck=deck,
                        hero_seat=seat,
                        treatment=True,
                        device=args.device,
                    )
                    base_rewards.append(base_reward)
                    candidate_rewards.append(candidate_reward)
                seat_delta = [candidate_rewards[s] - base_rewards[s] for s in (0, 1)]
                row = {
                    "checkpoint_index": checkpoint_index,
                    "holdout_index": holdout_index,
                    "holdout_label": holdout.label,
                    "holdout_sha256": holdout.sha256,
                    "pair_index": pair_index,
                    "deck": deck,
                    "base_rewards_bb": base_rewards,
                    "candidate_rewards_bb": candidate_rewards,
                    "seat_delta_bb": seat_delta,
                    "delta_bb": sum(seat_delta) / 2.0,
                }
                rows.append(row)
                evaluation_rows.append(row)
        curve.append({"checkpoint_index": checkpoint_index, **paired_summary(rows)})
        print(
            f"checkpoint={checkpoint_index} validation_delta="
            f"{curve[-1]['pooled_delta_bb100']:+.3f}",
            flush=True,
        )
    evaluation_path = args.out_dir / "evaluation_pairs.jsonl.gz"
    write_gzip_jsonl(evaluation_path, evaluation_rows)

    set_policy_vector(model, checkpoint_vectors[-1])
    preservation_states = collect_balanced_states(4096, int(spec["seed"]) + 1701)
    preservation = source_preservation(model, base_policy, preservation_states, args.device)
    final_checkpoint = args.out_dir / "final.pt"
    torch.save(
        {
            "schema": "cardpilot.greedy_es_residual.v1",
            "algorithm": "mirrored_greedy_es_random_feature_output_v1",
            "base_checkpoint": str(base_path),
            "base_sha256": base_sha,
            "hidden": 128,
            "policy_delta_cap": 0.25,
            "residual_state_dict": residual_state(model),
            "policy_parameter_count": parameter_count,
            "generations": generations,
            "completed_environment_training_hands": len(training_rows),
            "seed": args.seed,
        },
        final_checkpoint,
    )
    final_curve = curve[-1]
    positive_holdouts = sum(row["delta_bb100"] >= 0 for row in final_curve["holdouts"])
    positive_seats = sum(row["delta_bb100"] >= 0 for row in final_curve["seats"])
    slopes = [
        curve[index + 1]["pooled_delta_bb100"] - curve[index]["pooled_delta_bb100"]
        for index in range(len(curve) - 1)
    ]
    gates = {
        "training_hands_exact": len(training_rows)
        == args.generations
        * args.directions
        * 2
        * len(training)
        * args.pairs_per_training_opponent
        * 2,
        "all_generations_split_half_correlation_positive": all(
            row["split_half_direction_correlation"] > 0 for row in generations
        ),
        "all_generation_updates_nonzero": all(
            row["update_direction_l2"] > 0 for row in generations
        ),
        "all_validation_slopes_positive": all(value > 0 for value in slopes),
        "final_pooled_delta_nonnegative": final_curve["pooled_delta_bb100"] >= 0,
        "final_two_of_three_holdouts_nonnegative": positive_holdouts >= 2,
        "final_both_seats_nonnegative": positive_seats == 2,
        "source_overall_agreement_at_least_95pct": preservation["overall_agreement"] >= 0.95,
        "source_minimum_partition_agreement_at_least_90pct": preservation[
            "minimum_partition_agreement"
        ]
        >= 0.90,
        "center_l2_within_bound": float(np.linalg.norm(center)) <= args.max_center_l2 + 1e-9,
        "base_file_hash_unchanged": sha256_path(base_path) == base_sha,
    }
    admitted = all(gates.values())
    output = {
        "schema": "cardpilot.greedy_es_smoke.v1",
        "status": "COMPLETED",
        "algorithm": "mirrored_greedy_es_random_feature_output_v1",
        "base_sha256": base_sha,
        "spec_sha256": sha256_path(spec_path),
        "training_policies": [
            {"label": row.label, "sha256": row.sha256} for row in training
        ],
        "holdout_policies": [
            {"label": row.label, "sha256": row.sha256} for row in holdouts
        ],
        "policy_parameter_count": parameter_count,
        "sigma": args.sigma,
        "step_l2": args.step_l2,
        "max_center_l2": args.max_center_l2,
        "dispersion_weight": args.dispersion_weight,
        "generations": generations,
        "actual_environment_training_hands": len(training_rows),
        "evaluation_hands": len(evaluation_rows) * 4,
        "curve": curve,
        "validation_slopes_bb100": slopes,
        "source_preservation": preservation,
        "final_checkpoint": str(final_checkpoint.resolve()),
        "final_checkpoint_sha256": sha256_path(final_checkpoint),
        "training_evidence_sha256": sha256_path(training_path),
        "evaluation_evidence_sha256": sha256_path(evaluation_path),
        "gates": gates,
        "admitted": admitted,
        "decision": (
            "ADMIT_GREEDY_ES_THREE_SEED_GEOMETRIC_CURVE"
            if admitted
            else "GREEDY_ES_SMOKE_NOT_ADMITTED"
        ),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
