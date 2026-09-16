"""Frozen weighted-snapshot Deep CFR policy versus frozen Standard10."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import torch

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.legacy_observation_bridge_v6 import decide as legacy_decide, load_policy
from alpha_holdem.physical_v6_cfr import PhysicalV6Encoder, legal_slot_actions, regret_strategy
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_deep_cfr_exploration_control import _snapshot_networks


EXPECTED_CANDIDATE_SHA = "4025a4d4eae00147befbd9067fa9ec6195ae9e06fb58c137b5a570fb55339d94"
EXPECTED_STANDARD10_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@torch.no_grad()
def _candidate_action(network, state: ChipState, rng: np.random.Generator) -> str:
    encoded = PhysicalV6Encoder.encode(state)
    mask = PhysicalV6Encoder.legal_mask(state)
    values = network(
        torch.from_numpy(encoded).unsqueeze(0),
        torch.from_numpy(mask).unsqueeze(0),
    ).squeeze(0).numpy()
    strategy = regret_strategy(values, mask)
    slot_actions = legal_slot_actions(state)
    slots = np.asarray([slot for slot, _ in slot_actions], dtype=np.int64)
    probabilities = np.asarray([strategy[slot] for slot in slots], dtype=np.float64)
    probabilities /= probabilities.sum()
    return dict(slot_actions)[int(rng.choice(slots, p=probabilities))]


def _play(snapshot_networks, standard10, deck, candidate_seat, rng):
    choices = snapshot_networks[candidate_seat]
    weights = np.asarray([weight for _, weight in choices], dtype=np.float64)
    snapshot_index = int(rng.choice(len(choices), p=weights / weights.sum()))
    network = choices[snapshot_index][0]
    state = ChipState.new(deck)
    candidate_decisions = standard_decisions = 0
    while not state.terminal:
        if state.actor == candidate_seat:
            action = _candidate_action(network, state, rng)
            candidate_decisions += 1
        else:
            action, _ = legacy_decide(
                standard10, state, uniform=0.5, policy_mode="greedy"
            )
            standard_decisions += 1
        state = apply_incr(state, action)
    return {
        "candidate_reward_bb": state.payoffs()[candidate_seat] / 100.0,
        "candidate_seat": candidate_seat,
        "candidate_snapshot_index": snapshot_index,
        "candidate_decisions": candidate_decisions,
        "standard10_decisions": standard_decisions,
    }


def run(args):
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidate_sha = _sha256(args.candidate)
    if candidate_sha != EXPECTED_CANDIDATE_SHA:
        raise ValueError(f"candidate hash mismatch: {candidate_sha}")
    standard10 = load_policy(args.standard10, "cpu")
    if standard10.sha256 != EXPECTED_STANDARD10_SHA:
        raise ValueError(f"Standard10 hash mismatch: {standard10.sha256}")
    checkpoint = torch.load(args.candidate, map_location="cpu", weights_only=False)
    snapshot_states = [checkpoint["strategy_buffer_0"], checkpoint["strategy_buffer_1"]]
    snapshot_networks = _snapshot_networks(snapshot_states)
    deck_rng = np.random.default_rng(args.seed)
    policy_rng = np.random.default_rng(args.seed + 1_000_000)
    pairs = []
    raw_path = args.output_dir / "pairs.jsonl.gz"
    candidate_decisions = standard_decisions = 0
    with gzip.open(raw_path, "wt", encoding="utf-8") as stream:
        for pair_index in range(args.pairs):
            deck = deck_rng.permutation(52).tolist()
            first = _play(snapshot_networks, standard10, deck, 0, policy_rng)
            second = _play(snapshot_networks, standard10, deck, 1, policy_rng)
            pair_mean = (first["candidate_reward_bb"] + second["candidate_reward_bb"]) / 2.0
            pairs.append(pair_mean)
            candidate_decisions += first["candidate_decisions"] + second["candidate_decisions"]
            standard_decisions += first["standard10_decisions"] + second["standard10_decisions"]
            stream.write(json.dumps({
                "pair_index": pair_index,
                "deck": deck,
                "candidate_rewards_bb": [first["candidate_reward_bb"], second["candidate_reward_bb"]],
                "candidate_snapshot_indices": [first["candidate_snapshot_index"], second["candidate_snapshot_index"]],
                "candidate_pair_mean_bb": pair_mean,
                "candidate_decisions": first["candidate_decisions"] + second["candidate_decisions"],
                "standard10_decisions": first["standard10_decisions"] + second["standard10_decisions"],
            }, separators=(",", ":")) + "\n")
    values = np.asarray(pairs, dtype=np.float64)
    mean = float(values.mean())
    half = float(1.96 * values.std(ddof=1) / math.sqrt(len(values)))
    result = {
        "schema_version": 1,
        "config": {"pairs": args.pairs, "seed": args.seed},
        "contracts": {
            "candidate": "physical_v6_lcfr_weighted_snapshot_per_hand_regret_sampled_v1",
            "standard10": "physical_v6_legacy_v4_bridge_greedy_v1",
        },
        "candidate": {"path": str(args.candidate), "sha256": candidate_sha},
        "standard10": {"path": str(args.standard10), "sha256": standard10.sha256},
        "accounting": {
            "environment_training_hands": 0,
            "evaluation_hands": args.pairs * 2,
            "pairs": args.pairs,
            "candidate_decisions": candidate_decisions,
            "standard10_decisions": standard_decisions,
        },
        "candidate_bb100": mean * 100.0,
        "candidate_ci95_bb100": [100.0 * (mean - half), 100.0 * (mean + half)],
        "positive_pairs": int(np.sum(values > 0)),
        "zero_pairs": int(np.sum(values == 0)),
        "negative_pairs": int(np.sum(values < 0)),
        "raw_pairs": {"path": str(raw_path), "sha256": _sha256(raw_path)},
    }
    result["admit_slumbot_adapter"] = result["candidate_bb100"] > 0 and result["candidate_ci95_bb100"][0] > 0
    result["decision"] = (
        "ADMIT_FRESH_SLUMBOT_GATE"
        if result["admit_slumbot_adapter"]
        else "REJECT_CURRENT_DEEP_CFR_SNAPSHOT_TRANSFER"
    )
    (args.output_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--standard10", type=Path, required=True)
    parser.add_argument("--pairs", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=60910)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(1)
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
