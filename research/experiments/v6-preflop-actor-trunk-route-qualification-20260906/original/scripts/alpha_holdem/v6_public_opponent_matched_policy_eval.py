"""Untouched common-deck seven-versus-nine policy evaluation vs public model."""
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

from alpha_holdem.audit_v6_integrated_gradient_conflict import sha256_path
from alpha_holdem.legacy_observation_bridge_v6 import decide, load_policy
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.public_opponent_v6 import decide as public_decide
from alpha_holdem.public_opponent_v6 import load_public_opponent
from alpha_holdem.rules_v6 import ChipState


def mean_ci95(values) -> dict:
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean())
    half = 1.96 * float(array.std(ddof=1)) / math.sqrt(len(array))
    return {
        "count": int(len(array)),
        "bb100": mean * 100.0,
        "ci95_low_bb100": (mean - half) * 100.0,
        "ci95_high_bb100": (mean + half) * 100.0,
    }


def play(policy, public, deck: list[int], hero_seat: int, seed: int) -> float:
    state = ChipState.new(deck)
    rng = np.random.default_rng(seed)
    while not state.terminal:
        if state.actor == hero_seat:
            action, _ = decide(policy, state, uniform=0.5, policy_mode="greedy")
        else:
            action, _ = public_decide(public, state, rng)
        state = apply_incr(state, action)
    return float(state.payoffs()[hero_seat]) / 100.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--treatment", type=Path, required=True)
    parser.add_argument("--public-opponent", type=Path, required=True)
    parser.add_argument("--pairs", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.pairs < 256:
        parser.error("--pairs must be at least 256")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()

    paths = {
        "control": args.control.resolve(),
        "treatment": args.treatment.resolve(),
        "public_opponent": args.public_opponent.resolve(),
    }
    hashes = {name: sha256_path(path) for name, path in paths.items()}
    control = load_policy(paths["control"], args.device)
    treatment = load_policy(paths["treatment"], args.device)
    public = load_public_opponent(paths["public_opponent"])
    deck_rng = random.Random(args.seed)
    pair_deltas = []
    seat_deltas = [[], []]
    control_pairs = []
    treatment_pairs = []
    raw_path = args.out_dir / "common_deck_pairs.jsonl.gz"
    with gzip.open(raw_path, "xt", encoding="utf-8", newline="\n") as raw:
        for pair_index in range(args.pairs):
            deck = list(range(52))
            deck_rng.shuffle(deck)
            rewards = {"control": [], "treatment": []}
            for seat in (0, 1):
                action_seed = args.seed + 10_000_019 * pair_index + seat
                rewards["control"].append(
                    play(control, public, deck, seat, action_seed)
                )
                rewards["treatment"].append(
                    play(treatment, public, deck, seat, action_seed)
                )
                seat_deltas[seat].append(
                    rewards["treatment"][seat] - rewards["control"][seat]
                )
            control_mean = float(np.mean(rewards["control"]))
            treatment_mean = float(np.mean(rewards["treatment"]))
            delta = treatment_mean - control_mean
            control_pairs.append(control_mean)
            treatment_pairs.append(treatment_mean)
            pair_deltas.append(delta)
            raw.write(
                json.dumps(
                    {
                        "pair_index": pair_index,
                        "deck": deck,
                        "control_rewards_bb": rewards["control"],
                        "treatment_rewards_bb": rewards["treatment"],
                        "treatment_minus_control_pair_mean_bb": delta,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ) + "\n"
            )
    for name, path in paths.items():
        if sha256_path(path) != hashes[name]:
            raise RuntimeError(f"input changed during evaluation: {name}")
    delta = mean_ci95(pair_deltas)
    summary = {
        "schema": "cardpilot.public_opponent_matched_policy_eval.v1",
        "status": "COMPLETED",
        "policy_mode": "greedy",
        "starting_stack_bb": 200,
        "pairs": args.pairs,
        "evaluation_hands": args.pairs * 2 * 2,
        "input_paths": {name: str(path) for name, path in paths.items()},
        "input_sha256": hashes,
        "control": mean_ci95(control_pairs),
        "treatment": mean_ci95(treatment_pairs),
        "treatment_minus_control": delta,
        "seat_deltas": [mean_ci95(values) for values in seat_deltas],
        "gates": {
            "treatment_delta_positive": delta["bb100"] > 0.0,
            "both_seat_deltas_nonnegative": all(
                mean_ci95(values)["bb100"] >= 0.0 for values in seat_deltas
            ),
        },
        "raw_pairs_sha256": sha256_path(raw_path),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    summary["passed"] = all(summary["gates"].values())
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
