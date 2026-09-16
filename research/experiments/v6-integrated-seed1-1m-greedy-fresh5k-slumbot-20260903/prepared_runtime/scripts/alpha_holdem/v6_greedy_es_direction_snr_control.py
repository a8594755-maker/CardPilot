"""Extend one frozen ES direction cohort to measure estimator sample efficiency."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
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
from alpha_holdem.v6_broad_mgda_curve import load_frozen_policy, play_evaluation_hand
from alpha_holdem.v6_greedy_es_smoke import (
    policy_vector,
    robust_score,
    set_policy_vector,
    write_gzip_jsonl,
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rank_correlation(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    if left.shape != right.shape or left.size < 3:
        raise ValueError("rank correlation inputs do not align")
    if np.std(left) <= 1e-12 or np.std(right) <= 1e-12:
        return 0.0
    left_ranks = np.argsort(np.argsort(left, kind="stable"), kind="stable")
    right_ranks = np.argsort(np.argsort(right, kind="stable"), kind="stable")
    return float(np.corrcoef(left_ranks, right_ranks)[0, 1])


def stable_direction_count(quarter_differences: list[np.ndarray]) -> int:
    values = np.stack(quarter_differences)
    count = 0
    for column in values.T:
        signs = np.sign(column)
        positive = int(np.sum(signs > 0))
        negative = int(np.sum(signs < 0))
        count += max(positive, negative) >= 3
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--prior-run", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--directions", type=int, default=8)
    parser.add_argument("--sigma", type=float, required=True)
    parser.add_argument("--prior-pairs", type=int, default=32)
    parser.add_argument("--target-pairs", type=int, default=128)
    parser.add_argument("--dispersion-weight", type=float, default=0.25)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.target_pairs != 128 or args.prior_pairs != 32 or args.directions != 8:
        parser.error("this fixed control requires 8 directions and 32-to-128 pairs")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()

    spec_path = args.spec.resolve()
    prior_run = args.prior_run.resolve()
    base_path = args.base_checkpoint.resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    prior_summary = json.loads((prior_run / "summary.json").read_text(encoding="utf-8"))
    if prior_summary["sigma"] != args.sigma or prior_summary["generations"][0]["generation"] != 1:
        raise ValueError("prior run does not match fixed sigma/generation")
    base_sha = sha256_path(base_path)
    if prior_summary["base_sha256"] != base_sha:
        raise ValueError("prior run base identity differs")
    base_policy = load_policy(base_path, args.device)
    training = [load_frozen_policy(row, args.device) for row in spec["training_policies"]]
    torch.manual_seed(args.seed)
    model = DualContractResidualPolicy(
        base_policy.model, hidden=128, policy_delta_cap=0.25
    ).to(args.device).eval()
    center = policy_vector(model)
    rng = np.random.default_rng(args.seed + 71)
    directions = rng.standard_normal((args.directions, center.size))
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)

    prior_rows = []
    with gzip.open(prior_run / "training_hands.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["generation"] != 1:
                raise ValueError("prior evidence includes unexpected generation")
            prior_rows.append(row)
    expected_prior = args.directions * 2 * len(training) * args.prior_pairs * 2
    if len(prior_rows) != expected_prior:
        raise ValueError("prior evidence hand count differs")

    deck_sequences = {}
    for opponent_index in range(len(training)):
        deck_rng = random.Random(args.seed + 10_000_019 + opponent_index * 100_003)
        sequence = []
        for _ in range(args.target_pairs):
            deck = list(range(52))
            deck_rng.shuffle(deck)
            sequence.append(deck)
        deck_sequences[opponent_index] = sequence
    for row in prior_rows:
        if row["deck"] != deck_sequences[row["opponent_index"]][row["pair_index"]]:
            raise ValueError("prior deck prefix is not reproducible")

    supplemental = []
    for direction_index, direction in enumerate(directions):
        for sign in (1, -1):
            set_policy_vector(model, center + sign * args.sigma * direction)
            for opponent_index, opponent in enumerate(training):
                for pair_index in range(args.prior_pairs, args.target_pairs):
                    deck = deck_sequences[opponent_index][pair_index]
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
                        supplemental.append(
                            {
                                "generation": 1,
                                "direction": direction_index,
                                "sign": sign,
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
        print(f"direction={direction_index + 1}/{args.directions}", flush=True)
    supplemental_path = args.out_dir / "supplemental_hands.jsonl.gz"
    write_gzip_jsonl(supplemental_path, supplemental)
    all_rows = prior_rows + supplemental

    def differences(start_pair: int, end_pair: int) -> np.ndarray:
        fitness = np.zeros((args.directions, 2), dtype=np.float64)
        for direction_index in range(args.directions):
            for sign_index, sign in enumerate((1, -1)):
                grouped = [[] for _ in range(len(training) * 2)]
                for row in all_rows:
                    if (
                        row["direction"] == direction_index
                        and row["sign"] == sign
                        and start_pair <= row["pair_index"] < end_pair
                    ):
                        grouped[row["opponent_index"] * 2 + row["hero_seat"]].append(
                            row["reward_bb"]
                        )
                if min(map(len, grouped)) != end_pair - start_pair:
                    raise ValueError("incomplete fixed pair window")
                fitness[direction_index, sign_index] = robust_score(
                    grouped, args.dispersion_weight
                )
        return fitness[:, 0] - fitness[:, 1]

    quarters = [differences(start, start + 32) for start in range(0, 128, 32)]
    halves = [differences(0, 64), differences(64, 128)]
    full = differences(0, 128)
    prior_recorded = np.asarray(
        prior_summary["generations"][0]["fitness_differences"], dtype=np.float64
    )
    quarter_correlations = []
    for left in range(4):
        for right in range(left + 1, 4):
            quarter_correlations.append(rank_correlation(quarters[left], quarters[right]))
    stable_count = stable_direction_count(quarters)
    gates = {
        "prior_32pair_differences_exact": bool(np.array_equal(quarters[0], prior_recorded)),
        "supplemental_hands_exact": len(supplemental)
        == args.directions * 2 * len(training) * (args.target_pairs - args.prior_pairs) * 2,
        "half_rank_correlation_positive": rank_correlation(halves[0], halves[1]) > 0,
        "mean_quarter_rank_correlation_positive": float(np.mean(quarter_correlations)) > 0,
        "at_least_half_directions_sign_stable_three_of_four_quarters": stable_count >= 4,
        "all_full_differences_nonzero": bool(np.all(full != 0)),
        "base_file_hash_unchanged": sha256_path(base_path) == base_sha,
    }
    admitted = all(gates.values())
    output = {
        "schema": "cardpilot.greedy_es_direction_snr_control.v1",
        "status": "COMPLETED",
        "claim_scope": "FIXED_CENTER_DIRECTION_ESTIMATOR_RELIABILITY_NOT_POLICY_STRENGTH",
        "base_sha256": base_sha,
        "spec_sha256": sha256_path(spec_path),
        "prior_summary_sha256": sha256_path(prior_run / "summary.json"),
        "prior_evidence_sha256": sha256_path(prior_run / "training_hands.jsonl.gz"),
        "supplemental_evidence_sha256": sha256_path(supplemental_path),
        "prior_training_hands": len(prior_rows),
        "new_environment_training_hands": len(supplemental),
        "combined_environment_training_hands": len(all_rows),
        "quarter_differences": [row.tolist() for row in quarters],
        "half_differences": [row.tolist() for row in halves],
        "full_differences": full.tolist(),
        "half_rank_correlation": rank_correlation(halves[0], halves[1]),
        "quarter_rank_correlations": quarter_correlations,
        "mean_quarter_rank_correlation": float(np.mean(quarter_correlations)),
        "sign_stable_directions_three_of_four_quarters": stable_count,
        "gates": gates,
        "admitted": admitted,
        "decision": (
            "ADMIT_GREEDY_ES_FULL128_DIRECTION_UPDATE"
            if admitted
            else "REJECT_CURRENT_GREEDY_ES_AS_SAMPLE_INEFFICIENT"
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
