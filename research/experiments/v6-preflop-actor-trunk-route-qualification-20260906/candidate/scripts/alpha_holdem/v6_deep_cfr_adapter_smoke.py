"""Deterministic mechanism smoke for the exact-v6 external-sampling adapter."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

import numpy as np
import torch

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.physical_v6_cfr import TraversalStats, traverse_external_sampling
from alpha_holdem.rules_v6 import ChipState
from deep_cfr.networks import AdvantageNetwork
from deep_cfr.reservoir import ReservoirBuffer


def _passive_network() -> AdvantageNetwork:
    network = AdvantageNetwork(max_actions=9, hidden_dims=(64, 64))
    with torch.no_grad():
        for parameter in network.parameters():
            parameter.zero_()
        network.adv_head[2].bias[1] = 1.0
    network.eval()
    return network


def run(root_traversals: int, seed: int) -> dict:
    if root_traversals < 2:
        raise ValueError("At least two traversals are required to cover both seats")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    device = torch.device("cpu")
    networks = [_passive_network(), _passive_network()]
    buffers = [ReservoirBuffer(1_000_000), ReservoirBuffer(1_000_000)]
    aggregate = TraversalStats()
    root_values = []
    deck_hashes = []
    for traversal in range(root_traversals):
        deck = rng.permutation(52).tolist()
        deck_hashes.append(hashlib.sha256(bytes(deck)).hexdigest())
        traverser = traversal % 2
        stats = TraversalStats()
        value = traverse_external_sampling(
            ChipState.new(deck), traverser, networks, buffers[traverser],
            iteration=0, device=device, rng=rng, stats=stats,
        )
        root_values.append({"traverser": traverser, "value_bb": value})
        for name in ("decision_nodes", "traverser_nodes", "sampled_opponent_nodes", "terminal_rollouts"):
            setattr(aggregate, name, getattr(aggregate, name) + getattr(stats, name))
        aggregate.max_depth = max(aggregate.max_depth, stats.max_depth)

    finite_targets = all(
        np.isfinite(sample.advantages).all() and np.isfinite(sample.state).all()
        for buffer in buffers for sample in buffer.buffer
    )
    legal_targets_zero = all(
        np.all(sample.advantages[sample.legal_mask == 0] == 0)
        for buffer in buffers for sample in buffer.buffer
    )
    result = {
        "schema_version": 1,
        "seed": seed,
        "sampled_root_traversals": root_traversals,
        "unique_decks": len(set(deck_hashes)),
        "environment_training_hands": 0,
        "optimized_weights": False,
        "root_values": root_values,
        "buffer_samples_by_traverser": [len(buffer) for buffer in buffers],
        "stats": vars(aggregate),
        "gates": {
            "both_seats_sampled": {row["traverser"] for row in root_values} == {0, 1},
            "all_decks_unique": len(set(deck_hashes)) == root_traversals,
            "both_buffers_nonempty": all(len(buffer) > 0 for buffer in buffers),
            "terminal_rollouts_positive": aggregate.terminal_rollouts > 0,
            "finite_targets": finite_targets,
            "illegal_targets_zero": legal_targets_zero,
        },
    }
    result["admit_training_smoke"] = all(result["gates"].values())
    result["decision"] = (
        "ADMIT_BOUNDED_EXACT_V6_NEURAL_REGRET_SMOKE"
        if result["admit_training_smoke"]
        else "REJECT_EXACT_V6_CFR_ADAPTER"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-traversals", type=int, default=16)
    parser.add_argument("--seed", type=int, default=60901)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.root_traversals, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
