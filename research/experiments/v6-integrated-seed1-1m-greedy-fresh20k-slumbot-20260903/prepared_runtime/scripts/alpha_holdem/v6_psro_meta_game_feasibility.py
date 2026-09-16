"""Three-seed empirical meta-game feasibility for a PSRO opponent mixture."""
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
from scipy.optimize import linprog
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_broad_mgda_curve import frozen_decide, load_frozen_policy
from alpha_holdem.v6_dual_contract_residual_training_smoke import sha256_path


def play(policy_i, policy_j, deck, i_seat: int) -> float:
    state = ChipState.new(deck)
    while not state.terminal:
        policy = policy_i if state.actor == i_seat else policy_j
        action = frozen_decide(policy, state, uniform=None)
        state = apply_incr(state, action)
    return float(state.payoffs()[i_seat]) / 100.0


def solve_zero_sum(matrix: np.ndarray) -> dict:
    matrix = np.asarray(matrix, dtype=np.float64)
    n = matrix.shape[0]
    if matrix.shape != (n, n) or not np.allclose(matrix, -matrix.T, atol=1e-12):
        raise ValueError("meta-game matrix must be square and skew-symmetric")
    objective = np.zeros(n + 1)
    objective[-1] = -1.0
    inequalities = np.concatenate((-matrix.T, np.ones((n, 1))), axis=1)
    result = linprog(
        objective, A_ub=inequalities, b_ub=np.zeros(n),
        A_eq=np.asarray([[*np.ones(n), 0.0]]), b_eq=np.asarray([1.0]),
        bounds=[(0.0, 1.0)] * n + [(None, None)], method="highs",
    )
    if not result.success:
        raise RuntimeError(f"meta-game LP failed: {result.status}")
    weights = np.maximum(result.x[:n], 0.0)
    weights /= weights.sum()
    pure_scores = matrix.T @ weights
    return {
        "weights": weights.tolist(), "value_bb100": float(result.x[-1] * 100.0),
        "worst_pure_response_bb100": float(pure_scores.min() * 100.0),
        "support_at_1pct": int(np.sum(weights >= 0.01)),
        "maximum_weight": float(weights.max()),
    }


def mixture_scores(matrix: np.ndarray, weights: np.ndarray, columns: range) -> list[float]:
    return [float(weights @ matrix[: len(weights), column] * 100.0) for column in columns]


def recover_matrix(path: Path, policy_count: int, pairs_per_matchup: int, seed_index: int) -> np.ndarray:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        evidence = [json.loads(line) for line in handle]
    expected = pairs_per_matchup * policy_count * (policy_count - 1) // 2
    if len(evidence) != expected:
        raise ValueError("resume evidence is not one complete seed")
    grouped = {}
    for row in evidence:
        if row["seed_index"] != seed_index or not 0 <= row["left"] < row["right"] < policy_count:
            raise ValueError("resume evidence identity mismatch")
        grouped.setdefault((row["left"], row["right"]), []).append(row)
    matrix = np.zeros((policy_count, policy_count), dtype=np.float64)
    for (left, right), rows in grouped.items():
        if [row["pair_index"] for row in rows] != list(range(pairs_per_matchup)):
            raise ValueError("resume evidence pair sequence mismatch")
        matrix[left, right] = float(np.mean([row["paired_left_reward_bb"] for row in rows]))
        matrix[right, left] = -matrix[left, right]
    if len(grouped) != policy_count * (policy_count - 1) // 2:
        raise ValueError("resume evidence matchup coverage mismatch")
    return matrix


def strategy_report(matrix: np.ndarray, training_count: int) -> dict:
    train = matrix[:training_count, :training_count]
    nash = solve_zero_sum(train)
    uniform = np.full(training_count, 1.0 / training_count)
    mean_scores = np.asarray([
        np.mean([train[row, column] for column in range(training_count) if column != row])
        for row in range(training_count)
    ])
    top = np.argsort(mean_scores)[-min(5, training_count):]
    kbest = np.zeros(training_count)
    kbest[top] = 1.0 / len(top)
    holdout_columns = range(training_count, matrix.shape[0])
    def report(weights):
        training_scores = mixture_scores(matrix, weights, range(training_count))
        holdout_scores = mixture_scores(matrix, weights, holdout_columns)
        return {
            "weights": weights.tolist(),
            "training_scores_bb100": training_scores,
            "training_worst_bb100": min(training_scores),
            "holdout_scores_bb100": holdout_scores,
            "holdout_mean_bb100": float(np.mean(holdout_scores)),
            "holdout_worst_bb100": min(holdout_scores),
        }
    return {"nash": {**nash, **report(np.asarray(nash["weights"]))}, "uniform": report(uniform), "elo_k5_proxy": report(kbest), "elo_k5_indices": top.tolist(), "row_mean_scores_bb100": (mean_scores * 100.0).tolist()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--pairs-per-matchup", type=int, default=256)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--resume-complete-seeds", type=int, default=0)
    args = parser.parse_args()
    if args.out_dir.exists() and args.resume_complete_seeds == 0:
        raise FileExistsError(args.out_dir)
    if not 0 <= args.resume_complete_seeds < args.seeds:
        parser.error("resume-complete-seeds must be in [0,seeds)")
    if args.seeds < 3 or args.pairs_per_matchup < 128:
        parser.error("feasibility requires at least three seeds and 128 pairs/matchup")
    args.out_dir.mkdir(parents=True, exist_ok=args.resume_complete_seeds > 0)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    rows = [("training", row) for row in spec["training_policies"]] + [("holdout", row) for row in spec["holdout_policies"]]
    policies = [load_frozen_policy(row, args.device) for _, row in rows]
    if len(policies) != 9 or len({policy.sha256 for policy in policies}) != 9:
        raise ValueError("expected nine SHA-distinct policies")
    seed_results = []
    evidence_paths = []
    total_hands = 0
    for seed_index in range(args.seeds):
        run_seed = args.seed + seed_index * 10_007
        evidence_path = args.out_dir / f"seed{seed_index}_payoffs.jsonl.gz"
        if seed_index < args.resume_complete_seeds:
            if not evidence_path.exists():
                raise FileNotFoundError(evidence_path)
            matrix = recover_matrix(evidence_path, len(policies), args.pairs_per_matchup, seed_index)
            total_hands += 2 * args.pairs_per_matchup * (len(policies) * (len(policies) - 1) // 2)
        else:
            if evidence_path.exists():
                raise FileExistsError(evidence_path)
            matrix = np.zeros((len(policies), len(policies)), dtype=np.float64)
            with gzip.open(evidence_path, "xt", encoding="utf-8", newline="\n") as handle:
                for left in range(len(policies)):
                    for right in range(left + 1, len(policies)):
                        values = []
                        rng = random.Random(run_seed + left * 1_000_003 + right * 10_009)
                        for pair_index in range(args.pairs_per_matchup):
                            deck = list(range(52))
                            rng.shuffle(deck)
                            left_seat0 = play(policies[left], policies[right], deck, 0)
                            left_seat1 = play(policies[left], policies[right], deck, 1)
                            paired = 0.5 * (left_seat0 + left_seat1)
                            values.append(paired)
                            handle.write(json.dumps({
                                "seed_index": seed_index, "left": left, "right": right,
                                "pair_index": pair_index, "deck": deck,
                                "left_reward_seat0_bb": left_seat0,
                                "left_reward_seat1_bb": left_seat1,
                                "paired_left_reward_bb": paired,
                            }, sort_keys=True) + "\n")
                        matrix[left, right] = float(np.mean(values))
                        matrix[right, left] = -matrix[left, right]
                        total_hands += 2 * len(values)
        evidence_paths.append(evidence_path)
        seed_results.append({
            "seed_index": seed_index, "seed": run_seed,
            "matrix_bb100": (matrix * 100.0).tolist(),
            "strategy": strategy_report(matrix, 6),
            "evidence_sha256": sha256_path(evidence_path),
        })
        print(json.dumps({"seed": seed_index, "nash": seed_results[-1]["strategy"]["nash"]}), flush=True)
    aggregate_matrix = np.mean([np.asarray(row["matrix_bb100"]) / 100.0 for row in seed_results], axis=0)
    aggregate = strategy_report(aggregate_matrix, 6)
    aggregate_weights = np.asarray(aggregate["nash"]["weights"])
    seed_l1 = [float(np.abs(np.asarray(row["strategy"]["nash"]["weights"]) - aggregate_weights).sum()) for row in seed_results]
    nash_holdout_worst = aggregate["nash"]["holdout_worst_bb100"]
    gates = {
        "environment_hands_exact": total_hands == args.seeds * 2 * args.pairs_per_matchup * (len(policies) * (len(policies) - 1) // 2),
        "aggregate_nash_support_at_least_three": aggregate["nash"]["support_at_1pct"] >= 3,
        "aggregate_maximum_weight_at_most_70pct": aggregate["nash"]["maximum_weight"] <= 0.70,
        "aggregate_training_worst_improves_uniform_by_5bb100": aggregate["nash"]["training_worst_bb100"] >= aggregate["uniform"]["training_worst_bb100"] + 5.0,
        "aggregate_holdout_worst_not_5bb100_below_uniform": nash_holdout_worst >= aggregate["uniform"]["holdout_worst_bb100"] - 5.0,
        "aggregate_holdout_worst_not_5bb100_below_elo_k5": nash_holdout_worst >= aggregate["elo_k5_proxy"]["holdout_worst_bb100"] - 5.0,
        "median_seed_weight_l1_to_aggregate_at_most_0_8": float(np.median(seed_l1)) <= 0.8,
    }
    admitted = all(gates.values())
    summary = {
        "schema": "cardpilot.psro_meta_game_feasibility.v1", "status": "COMPLETED",
        "claim_scope": "FROZEN_EMPIRICAL_META_GAME_NOT_LEARNED_ORACLE_STRENGTH",
        "policies": [{"split": split, "label": policy.label, "sha256": policy.sha256} for (split, _), policy in zip(rows, policies)],
        "actual_environment_evaluation_hands": total_hands,
        "seed_results": seed_results, "aggregate_matrix_bb100": (aggregate_matrix * 100.0).tolist(),
        "aggregate_strategy": aggregate, "seed_weight_l1_to_aggregate": seed_l1,
        "gates": gates, "admit_psro_oracle_smoke": admitted,
        "decision": "ADMIT_PSRO_ORACLE_SMOKE" if admitted else "REJECT_PSRO_META_GAME_FEASIBILITY",
        "artifact_sha256": {path.name: sha256_path(path) for path in evidence_paths},
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(), "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"hands": total_hands, "gates": gates, "decision": summary["decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
