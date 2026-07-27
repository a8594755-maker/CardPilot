"""Conservative policy-gradient updates from randomized Slumbot trajectories.

The collector records the exact tempered behavior probability for every hero
action.  This trainer reconstructs the actor observation, computes a
state-bucket baseline from complete-hand returns, and applies a clipped PPO
surrogate at the same behavior temperature.  A frozen-source KL term keeps the
deploy-time (temperature 1) policy near the source checkpoint.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = THIS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(THIS_DIR))

from alpha_holdem.network import AlphaHoldemNet
from offline_slumbot_awr import (
    ACTION_SHAPE,
    CARD_SHAPE,
    NUM_ACTIONS,
    atomic_torch_save,
    reservoir_rows,
    sha256_path,
)


def split_by_hand(
    rows: list[dict[str, Any]],
    val_fraction: float,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    keys = sorted(set(tuple(row["hand_key"]) for row in rows))
    rng = random.Random(seed)
    rng.shuffle(keys)
    val_count = max(1, round(len(keys) * val_fraction))
    val_keys = set(keys[:val_count])
    train = [row for row in rows if tuple(row["hand_key"]) not in val_keys]
    val = [row for row in rows if tuple(row["hand_key"]) in val_keys]
    return train, val


def calculate_advantages(
    train_rows: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    return_clip_bb: float,
    min_bucket_count: int,
    advantage_scale_bb: float,
    advantage_clip: float,
) -> tuple[np.ndarray, dict[str, Any], np.ndarray]:
    train_returns = np.asarray(
        [
            np.clip(float(row["return_bb"]), -return_clip_bb, return_clip_bb)
            for row in train_rows
        ],
        dtype=np.float64,
    )
    global_mean = float(train_returns.mean())
    bucket_values: dict[tuple[int, ...], list[float]] = defaultdict(list)
    for row, value in zip(train_rows, train_returns):
        bucket_values[tuple(row["bucket"])].append(float(value))
    baselines: dict[tuple[int, ...], float] = {}
    for bucket, values in bucket_values.items():
        shrink = len(values) / float(len(values) + min_bucket_count)
        baselines[bucket] = (
            shrink * float(np.mean(values)) + (1.0 - shrink) * global_mean
        )

    clipped_returns = np.asarray(
        [
            np.clip(float(row["return_bb"]), -return_clip_bb, return_clip_bb)
            for row in rows
        ],
        dtype=np.float64,
    )
    raw_advantage = np.asarray(
        [
            value - baselines.get(tuple(row["bucket"]), global_mean)
            for row, value in zip(rows, clipped_returns)
        ],
        dtype=np.float64,
    )
    normalized = np.clip(
        raw_advantage / max(float(advantage_scale_bb), 1e-6),
        -float(advantage_clip),
        float(advantage_clip),
    )
    decisions_per_hand = Counter(tuple(row["hand_key"]) for row in rows)
    hand_weight = np.asarray(
        [1.0 / decisions_per_hand[tuple(row["hand_key"])] for row in rows],
        dtype=np.float64,
    )
    hand_weight /= max(float(hand_weight.mean()), 1e-12)
    return normalized.astype(np.float32), {
        "train_global_clipped_return_mean_bb": global_mean,
        "bucket_count": len(bucket_values),
        "bucket_count_ge_min": int(
            sum(len(values) >= min_bucket_count for values in bucket_values.values())
        ),
        "raw_advantage_mean_bb": float(raw_advantage.mean()),
        "raw_advantage_std_bb": float(raw_advantage.std()),
        "normalized_advantage_mean": float(normalized.mean()),
        "normalized_advantage_std": float(normalized.std()),
        "normalized_advantage_min": float(normalized.min()),
        "normalized_advantage_max": float(normalized.max()),
        "hand_weight_mean": float(hand_weight.mean()),
        "hand_weight_min": float(hand_weight.min()),
        "hand_weight_max": float(hand_weight.max()),
    }, hand_weight.astype(np.float32)


def stack_rows(
    rows: list[dict[str, Any]],
    advantage: np.ndarray,
    hand_weight: np.ndarray,
) -> TensorDataset:
    behavior_prob = np.asarray(
        [float(row["behavior_action_probability"]) for row in rows],
        dtype=np.float32,
    )
    temperature = np.asarray(
        [float(row["behavior_temperature"]) for row in rows],
        dtype=np.float32,
    )
    return TensorDataset(
        torch.from_numpy(np.stack([row["card"] for row in rows])),
        torch.from_numpy(np.stack([row["action"] for row in rows])),
        torch.from_numpy(np.stack([row["extra"] for row in rows])),
        torch.from_numpy(np.stack([row["legal"] for row in rows])),
        torch.tensor([row["selected"] for row in rows], dtype=torch.long),
        torch.from_numpy(advantage),
        torch.from_numpy(hand_weight),
        torch.from_numpy(behavior_prob),
        torch.from_numpy(temperature),
    )


@torch.no_grad()
def compare_to_source(
    model: AlphaHoldemNet,
    source: AlphaHoldemNet,
    loader: DataLoader,
    device: str,
) -> dict[str, Any]:
    model.eval()
    source.eval()
    rows = switches = selected_match = source_selected_match = 0
    kl_sum = tv_sum = 0.0
    for batch in loader:
        cards, actions, extras, legal, selected = [
            value.to(device) for value in batch[:5]
        ]
        logits, _ = model(cards, actions, extras, legal)
        source_logits, _ = source(cards, actions, extras, legal)
        probs = F.softmax(logits, dim=-1)
        source_probs = F.softmax(source_logits, dim=-1)
        prediction = probs.argmax(dim=-1)
        source_prediction = source_probs.argmax(dim=-1)
        rows += len(selected)
        switches += int((prediction != source_prediction).sum())
        selected_match += int((prediction == selected).sum())
        source_selected_match += int((source_prediction == selected).sum())
        kl_sum += float(
            (
                source_probs
                * (
                    source_probs.clamp_min(1e-12).log()
                    - probs.clamp_min(1e-12).log()
                )
            ).sum()
        )
        tv_sum += float((0.5 * (source_probs - probs).abs().sum(dim=-1)).sum())
    return {
        "rows": rows,
        "greedy_switch_rate_vs_source": switches / max(rows, 1),
        "greedy_matches_sampled_action_rate": selected_match / max(rows, 1),
        "source_greedy_matches_sampled_action_rate": (
            source_selected_match / max(rows, 1)
        ),
        "source_to_candidate_kl_mean": kl_sum / max(rows, 1),
        "total_variation_mean": tv_sum / max(rows, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-checkpoint", required=True)
    parser.add_argument("--dumps", nargs="+", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--obs-version", choices=("v4", "v55"), default="v4")
    parser.add_argument(
        "--raise-action-mapping",
        choices=(
            "auto",
            "legacy_total_over_pot",
            "preflop_pot_fraction_v2",
            "pot_fraction_v2",
        ),
        default="auto",
    )
    parser.add_argument("--max-rows", type=int, default=100_000)
    parser.add_argument("--min-rows", type=int, default=2_000)
    parser.add_argument("--street-min", type=int, default=0)
    parser.add_argument("--street-max", type=int, default=3)
    parser.add_argument(
        "--first-preflop-only",
        action="store_true",
        help="Train only the hero's first SB-open or BB-vs-first-action decision.",
    )
    parser.add_argument("--seed", type=int, default=20260725)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--weight-decay", type=float, default=1e-5)
    parser.add_argument("--clip-ratio", type=float, default=0.10)
    parser.add_argument("--source-kl-coef", type=float, default=1.0)
    parser.add_argument("--return-clip-bb", type=float, default=20.0)
    parser.add_argument("--min-bucket-count", type=int, default=20)
    parser.add_argument("--advantage-scale-bb", type=float, default=5.0)
    parser.add_argument("--advantage-clip", type=float, default=4.0)
    parser.add_argument("--val-fraction", type=float, default=0.10)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    output = Path(args.out_dir)
    if output.exists():
        raise RuntimeError(f"output directory already exists: {output}")
    output.mkdir(parents=True)
    dump_paths = [Path(value).resolve() for value in args.dumps]
    missing = [str(path) for path in dump_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing dump files: {missing}")

    source_path = Path(args.source_checkpoint).resolve()
    source_metadata = torch.load(
        source_path,
        map_location="cpu",
        weights_only=False,
    )
    if args.raise_action_mapping == "auto":
        raise_action_mapping = str(
            source_metadata.get("raise_action_mapping")
            or (
                "preflop_pot_fraction_v2"
                if source_metadata.get("action_space_version")
                == "9slot_preflop_pot_fraction_v2"
                else "legacy_total_over_pot"
            )
        )
    else:
        raise_action_mapping = str(args.raise_action_mapping)
    del source_metadata

    started = time.time()
    rows, ingest = reservoir_rows(
        dump_paths,
        args.max_rows,
        args.seed,
        args.obs_version,
        args.street_min,
        args.street_max,
        "hero",
        raise_action_mapping=raise_action_mapping,
    )
    sampled_rows = [
        row
        for row in rows
        if row["behavior_action_probability"] is not None
        and row["behavior_probs"] is not None
        and row["behavior_temperature"] is not None
        and 0.0 < float(row["behavior_action_probability"]) <= 1.0
        and (
            not args.first_preflop_only
            or (
                int(row["street"]) == 0
                and (
                    (
                        int(row["position"]) == 1
                        and str(row["action_str_before"]) == ""
                    )
                    or (
                        int(row["position"]) == 0
                        and (
                            str(row["action_str_before"]) == "c"
                            or (
                                str(row["action_str_before"]).startswith("b")
                                and str(row["action_str_before"])[1:].isdigit()
                            )
                        )
                    )
                )
            )
        )
    ]
    if len(sampled_rows) < args.min_rows:
        raise RuntimeError(
            f"too few probability-traced randomized rows: {len(sampled_rows)}"
        )
    train_rows, val_rows = split_by_hand(
        sampled_rows, args.val_fraction, args.seed
    )
    train_advantage, advantage_report, train_hand_weight = calculate_advantages(
        train_rows,
        train_rows,
        args.return_clip_bb,
        args.min_bucket_count,
        args.advantage_scale_bb,
        args.advantage_clip,
    )
    val_advantage, _, val_hand_weight = calculate_advantages(
        train_rows,
        val_rows,
        args.return_clip_bb,
        args.min_bucket_count,
        args.advantage_scale_bb,
        args.advantage_clip,
    )
    train_loader = DataLoader(
        stack_rows(train_rows, train_advantage, train_hand_weight),
        batch_size=args.batch_size,
        shuffle=True,
        pin_memory=True,
    )
    val_loader = DataLoader(
        stack_rows(val_rows, val_advantage, val_hand_weight),
        batch_size=args.batch_size,
        shuffle=False,
        pin_memory=True,
    )

    device = args.device
    checkpoint = torch.load(source_path, map_location=device, weights_only=False)
    norm_layer = str(checkpoint.get("norm_layer", "bn"))
    state = checkpoint["model"]
    architecture = {
        "num_actions": NUM_ACTIONS,
        "norm_layer": norm_layer,
        "separate_preflop_head": (
            "preflop_policy_head.weight" in state
        ),
        "preflop_adapter_hidden": (
            int(state["preflop_policy_adapter.0.weight"].shape[0])
            if "preflop_policy_adapter.0.weight" in state
            else 0
        ),
        "preflop_raw_adapter_hidden": (
            int(state["preflop_raw_policy_adapter.0.weight"].shape[0])
            if "preflop_raw_policy_adapter.0.weight" in state
            else 0
        ),
        "preflop_raw_action_scale": float(
            checkpoint.get("preflop_raw_action_scale")
            or (checkpoint.get("config") or {}).get(
                "preflop_raw_action_scale"
            )
            or 1.0
        ),
        "preflop_raw_gate": str(
            checkpoint.get("preflop_raw_gate")
            or (checkpoint.get("config") or {}).get("preflop_raw_gate")
            or "none"
        ),
        "flop_adapter_hidden": (
            int(state["flop_policy_adapter.0.weight"].shape[0])
            if "flop_policy_adapter.0.weight" in state
            else 0
        ),
        "postflop_adapter_hidden": (
            int(state["postflop_policy_adapter.0.weight"].shape[0])
            if "postflop_policy_adapter.0.weight" in state
            else 0
        ),
    }
    model = AlphaHoldemNet(**architecture).to(device)
    source = AlphaHoldemNet(**architecture).to(device)
    dummy_cards = torch.zeros(2, *CARD_SHAPE, device=device)
    dummy_actions = torch.zeros(2, *ACTION_SHAPE, device=device)
    dummy_extras = torch.zeros(2, 2, device=device)
    model.eval()
    source.eval()
    model(dummy_cards, dummy_actions, dummy_extras)
    source(dummy_cards, dummy_actions, dummy_extras)
    model.load_state_dict(state)
    source.load_state_dict(state)
    source.eval()
    for parameter in source.parameters():
        parameter.requires_grad_(False)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.lr, weight_decay=args.weight_decay
    )

    history: list[dict[str, Any]] = []
    best_objective = math.inf
    best_path = output / "best.pt"
    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss = []
        epoch_policy = []
        epoch_kl = []
        epoch_clip = []
        for batch in train_loader:
            (
                cards,
                actions,
                extras,
                legal,
                selected,
                advantage,
                hand_weight,
                old_prob,
                temperature,
            ) = [value.to(device, non_blocking=True) for value in batch]
            logits, _ = model(cards, actions, extras, legal)
            with torch.no_grad():
                source_logits, _ = source(cards, actions, extras, legal)
                source_probs = F.softmax(source_logits, dim=-1)

            tempered_log_probs = F.log_softmax(
                logits / temperature.unsqueeze(-1).clamp_min(1e-6),
                dim=-1,
            )
            selected_log_prob = tempered_log_probs.gather(
                1, selected.unsqueeze(1)
            ).squeeze(1)
            ratio = torch.exp(
                selected_log_prob - old_prob.clamp_min(1e-8).log()
            )
            unclipped = ratio * advantage
            clipped = ratio.clamp(
                1.0 - args.clip_ratio, 1.0 + args.clip_ratio
            ) * advantage
            policy_loss = -(
                hand_weight * torch.minimum(unclipped, clipped)
            ).sum() / hand_weight.sum().clamp_min(1e-6)
            candidate_log_probs = F.log_softmax(logits, dim=-1)
            source_kl = (
                source_probs
                * (
                    F.log_softmax(source_logits, dim=-1)
                    - candidate_log_probs
                )
            ).sum(dim=-1).mean()
            loss = policy_loss + args.source_kl_coef * source_kl
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            epoch_loss.append(float(loss.detach()))
            epoch_policy.append(float(policy_loss.detach()))
            epoch_kl.append(float(source_kl.detach()))
            epoch_clip.append(
                float(((ratio - 1.0).abs() > args.clip_ratio).float().mean())
            )

        validation = compare_to_source(model, source, val_loader, device)
        metrics = {
            "epoch": epoch,
            "loss": float(np.mean(epoch_loss)),
            "policy_loss": float(np.mean(epoch_policy)),
            "source_kl": float(np.mean(epoch_kl)),
            "clip_fraction": float(np.mean(epoch_clip)),
            "validation": validation,
        }
        history.append(metrics)
        payload = {
            **checkpoint,
            "model": model.state_dict(),
            "iteration": int(checkpoint.get("iteration", 0)) + epoch,
            "total_hands": int(checkpoint.get("total_hands", 0)),
            "offline_slumbot_reinforce": {
                "schema": "offline.slumbot.reinforce.v1",
                "source_checkpoint": str(source_path),
                "source_checkpoint_sha256": sha256_path(source_path),
                "epoch": epoch,
                "street_min": int(args.street_min),
                "street_max": int(args.street_max),
                "first_preflop_only": bool(args.first_preflop_only),
                "metrics": metrics,
                "advantage_report": advantage_report,
            },
        }
        epoch_path = output / f"epoch_{epoch}.pt"
        atomic_torch_save(payload, epoch_path)
        objective = metrics["loss"]
        if objective < best_objective:
            best_objective = objective
            atomic_torch_save(payload, best_path)
        print(json.dumps(metrics, sort_keys=True))

    report = {
        "status": "COMPLETE",
        "source_checkpoint": str(source_path),
        "source_checkpoint_sha256": sha256_path(source_path),
        "raise_action_mapping": raise_action_mapping,
        "dump_files": [
            {"path": str(path), "sha256": sha256_path(path)}
            for path in dump_paths
        ],
        "ingest": ingest,
        "probability_traced_rows": len(sampled_rows),
        "train_rows": len(train_rows),
        "val_rows": len(val_rows),
        "advantage_report": advantage_report,
        "history": history,
        "best_checkpoint": str(best_path.resolve()),
        "best_checkpoint_sha256": sha256_path(best_path),
        "runtime_seconds": time.time() - started,
        "config": vars(args),
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "rows": len(sampled_rows),
        "best_checkpoint": report["best_checkpoint"],
        "runtime_seconds": report["runtime_seconds"],
    }, indent=2))


if __name__ == "__main__":
    main()
