"""Matched optimizer-dose control on a frozen exact-v6 regret corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys

import numpy as np
import torch
import torch.nn.functional as functional

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.physical_v6_cfr import (
    TraversalStats,
    regret_strategy,
    traverse_external_sampling,
)
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_deep_cfr_neural_smoke import _passive_network
from deep_cfr.reservoir import AdvantageSample, ReservoirBuffer
from deep_cfr.train import train_advantage_net


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _arrays(samples: list[AdvantageSample]) -> dict[str, np.ndarray]:
    return {
        "states": np.stack([sample.state for sample in samples]),
        "targets": np.stack([sample.advantages for sample in samples]),
        "masks": np.stack([sample.legal_mask for sample in samples]),
        "iterations": np.asarray([sample.iteration for sample in samples], dtype=np.int64),
    }


def _buffer(arrays: dict[str, np.ndarray], indices: np.ndarray) -> ReservoirBuffer:
    buffer = ReservoirBuffer(max(len(indices), 1))
    for index in indices:
        buffer.add(AdvantageSample(
            state=arrays["states"][index].copy(),
            advantages=arrays["targets"][index].copy(),
            legal_mask=arrays["masks"][index].copy(),
            iteration=int(arrays["iterations"][index]),
        ))
    return buffer


@torch.no_grad()
def _heldout_metrics(network, arrays: dict[str, np.ndarray], indices: np.ndarray) -> dict:
    states = torch.from_numpy(arrays["states"][indices])
    targets = torch.from_numpy(arrays["targets"][indices])
    masks = torch.from_numpy(arrays["masks"][indices])
    predictions = network(states, masks)
    per_sample = (functional.smooth_l1_loss(predictions, targets, reduction="none") * masks).sum(-1)
    strategies = []
    target_strategies = []
    for prediction, target, mask in zip(predictions.numpy(), targets.numpy(), masks.numpy()):
        strategies.append(regret_strategy(prediction, mask))
        target_strategies.append(regret_strategy(target, mask))
    strategies = np.stack(strategies)
    target_strategies = np.stack(target_strategies)
    return {
        "masked_huber": float(per_sample.mean()),
        "argmax_not_passive_fraction": float(np.mean(np.argmax(strategies, axis=1) != 1)),
        "mean_tv_from_passive": float(np.mean(1.0 - strategies[:, 1])),
        "target_argmax_not_passive_fraction": float(np.mean(np.argmax(target_strategies, axis=1) != 1)),
    }


def run(args: argparse.Namespace) -> dict:
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    networks = [_passive_network(), _passive_network()]
    source_buffers = [ReservoirBuffer(200_000), ReservoirBuffer(200_000)]
    stats = TraversalStats()
    for player in range(2):
        for _ in range(args.root_traversals_per_player):
            root_stats = TraversalStats()
            traverse_external_sampling(
                ChipState.new(rng.permutation(52).tolist()), player, networks,
                source_buffers[player], 0, torch.device("cpu"), rng, root_stats,
                node_limit=args.node_limit,
            )
            for name in ("decision_nodes", "traverser_nodes", "sampled_opponent_nodes", "terminal_rollouts"):
                setattr(stats, name, getattr(stats, name) + getattr(root_stats, name))
            stats.max_depth = max(stats.max_depth, root_stats.max_depth)

    corpus = {}
    splits = {}
    for player in range(2):
        arrays = _arrays(source_buffers[player].buffer)
        permutation = np.random.default_rng(args.seed + 100 + player).permutation(len(arrays["states"]))
        heldout_count = max(1, int(round(len(permutation) * 0.2)))
        splits[player] = {
            "train": permutation[heldout_count:],
            "heldout": permutation[:heldout_count],
        }
        for name, value in arrays.items():
            corpus[f"p{player}_{name}"] = value
        corpus[f"p{player}_train_indices"] = splits[player]["train"]
        corpus[f"p{player}_heldout_indices"] = splits[player]["heldout"]
    corpus_path = args.output_dir / "frozen_corpus.npz"
    np.savez_compressed(corpus_path, **corpus)

    initial_path = args.output_dir / "initial_passive.pt"
    torch.save({"net_0": networks[0].state_dict(), "net_1": networks[1].state_dict()}, initial_path)
    initial_hash = _sha256(initial_path)
    corpus_hash = _sha256(corpus_path)

    arms = []
    for steps in args.steps:
        arm_players = []
        arm_state = {}
        for player in range(2):
            torch.manual_seed(args.seed + player)
            network = _passive_network()
            # Enforce identical initial bytes independent of constructor RNG.
            network.load_state_dict(networks[player].state_dict())
            arrays = {
                name: corpus[f"p{player}_{name}"]
                for name in ("states", "targets", "masks", "iterations")
            }
            train_indices = splits[player]["train"]
            heldout_indices = splits[player]["heldout"]
            initial = _heldout_metrics(network, arrays, heldout_indices)
            random.seed(args.seed + 10_000 + player)
            loss = train_advantage_net(
                network, _buffer(arrays, train_indices), torch.device("cpu"), 1,
                steps=steps, batch_size=args.batch_size, lr=args.lr,
                reinit=False, sizing_weight=0.0,
            )
            network.eval()
            final = _heldout_metrics(network, arrays, heldout_indices)
            reduction = 1.0 - final["masked_huber"] / max(initial["masked_huber"], 1e-12)
            arm_players.append({
                "player": player,
                "train_samples": int(len(train_indices)),
                "heldout_samples": int(len(heldout_indices)),
                "optimizer_reported_loss": float(loss),
                "initial": initial,
                "final": final,
                "heldout_loss_reduction": float(reduction),
            })
            arm_state[f"net_{player}"] = network.state_dict()
        arm_path = args.output_dir / f"arm_steps{steps}.pt"
        torch.save({
            "steps": steps,
            "source_initial_sha256": initial_hash,
            "source_corpus_sha256": corpus_hash,
            **arm_state,
        }, arm_path)
        gate = all(
            row["heldout_loss_reduction"] >= 0.20
            and row["final"]["argmax_not_passive_fraction"] >= 0.05
            and math.isfinite(row["final"]["masked_huber"])
            for row in arm_players
        )
        arms.append({
            "steps": steps,
            "players": arm_players,
            "checkpoint": str(arm_path),
            "checkpoint_sha256": _sha256(arm_path),
            "passes": gate,
        })

    selected = next((arm for arm in arms if arm["passes"]), None)
    result = {
        "schema_version": 1,
        "config": vars(args) | {"output_dir": str(args.output_dir)},
        "accounting": {
            "environment_training_hands": args.root_traversals_per_player * 2,
            "root_traversals": args.root_traversals_per_player * 2,
            "evaluation_hands": 0,
            "decision_nodes": stats.decision_nodes,
            "terminal_rollouts": stats.terminal_rollouts,
        },
        "corpus": {
            "path": str(corpus_path),
            "sha256": corpus_hash,
            "samples_by_player": [len(buffer) for buffer in source_buffers],
            "stats": vars(stats),
        },
        "initial": {"path": str(initial_path), "sha256": initial_hash},
        "arms": arms,
        "selected_steps": selected["steps"] if selected else None,
        "decision": (
            "ADMIT_SELECTED_OPTIMIZER_DOSE"
            if selected else "REJECT_FIRST_ITERATION_TARGET_LEARNABILITY"
        ),
    }
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-traversals-per-player", type=int, default=4)
    parser.add_argument("--steps", type=int, nargs="+", default=[32, 128, 512])
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--node-limit", type=int, default=250_000)
    parser.add_argument("--seed", type=int, default=60903)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
