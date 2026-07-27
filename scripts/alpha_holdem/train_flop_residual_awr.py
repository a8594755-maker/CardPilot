"""Train a flop-only residual policy adapter from exploratory Slumbot hands.

The frozen source network supplies every representation and every non-flop
decision.  Only a zero-initialized residual MLP is optimized, so epoch zero is
exactly the source policy and the intervention cannot rewrite preflop, turn,
river, value, or shared representation tensors.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from offline_slumbot_awr import (
    ACTION_SHAPE,
    CARD_SHAPE,
    NUM_ACTIONS,
    atomic_torch_save,
    calculate_awr_weights,
    discover_dump_files,
    reservoir_rows,
    sha256_path,
    stack_rows,
)
from alpha_holdem.network import AlphaHoldemNet


@torch.no_grad()
def evaluate_pair(
    model: AlphaHoldemNet,
    source: AlphaHoldemNet,
    loader: DataLoader,
    device: str,
) -> dict[str, Any]:
    model.eval()
    source.eval()
    total = 0
    weighted_ce_sum = 0.0
    weight_sum = 0.0
    kl_sum = 0.0
    changed = 0
    source_counts = np.zeros(NUM_ACTIONS, dtype=np.int64)
    candidate_counts = np.zeros(NUM_ACTIONS, dtype=np.int64)
    for batch in loader:
        cards, actions, extras, legal, selected, weight, _, _ = [
            value.to(device, non_blocking=True) for value in batch
        ]
        logits, _ = model(cards, actions, extras, legal)
        source_logits, _ = source(cards, actions, extras, legal)
        row_ce = F.cross_entropy(logits, selected, reduction="none")
        source_probs = F.softmax(source_logits, dim=-1)
        row_kl = (
            source_probs
            * (
                F.log_softmax(source_logits, dim=-1)
                - F.log_softmax(logits, dim=-1)
            )
        ).sum(dim=-1)
        source_action = source_logits.argmax(dim=-1)
        candidate_action = logits.argmax(dim=-1)
        total += len(selected)
        weighted_ce_sum += float((row_ce * weight).sum())
        weight_sum += float(weight.sum())
        kl_sum += float(row_kl.sum())
        changed += int((source_action != candidate_action).sum())
        source_counts += np.bincount(
            source_action.cpu().numpy(), minlength=NUM_ACTIONS
        )
        candidate_counts += np.bincount(
            candidate_action.cpu().numpy(), minlength=NUM_ACTIONS
        )
    return {
        "rows": total,
        "weighted_awr_ce": weighted_ce_sum / max(weight_sum, 1e-12),
        "source_kl": kl_sum / max(total, 1),
        "greedy_change_rate": changed / max(total, 1),
        "source_action_frequency": (source_counts / max(total, 1)).tolist(),
        "candidate_action_frequency": (
            candidate_counts / max(total, 1)
        ).tolist(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-checkpoint", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--roots", nargs="+", required=True)
    parser.add_argument("--obs-version", choices=("v4", "v55"), default="v4")
    parser.add_argument("--max-rows", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=20260725)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--kl-coef", type=float, default=1.0)
    parser.add_argument("--return-clip-bb", type=float, default=20.0)
    parser.add_argument("--beta-bb", type=float, default=10.0)
    parser.add_argument("--min-bucket-count", type=int, default=30)
    parser.add_argument("--weight-min", type=float, default=0.10)
    parser.add_argument("--weight-max", type=float, default=5.0)
    parser.add_argument("--slice-balance-power", type=float, default=0.25)
    parser.add_argument("--val-fraction", type=float, default=0.20)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    started = time.time()
    output = Path(args.out_dir)
    if output.exists():
        raise RuntimeError(f"output directory already exists: {output}")
    output.mkdir(parents=True)

    files = discover_dump_files(args.roots, [])
    if not files:
        raise RuntimeError("no exploratory dump files found")
    rows, ingest = reservoir_rows(
        files,
        args.max_rows,
        args.seed,
        args.obs_version,
        1,
        1,
        "hero",
    )
    if len(rows) < 500:
        raise RuntimeError(f"too few reconstructed flop rows: {len(rows)}")

    hand_keys = sorted({row["hand_key"] for row in rows})
    split_rng = random.Random(args.seed + 17)
    split_rng.shuffle(hand_keys)
    val_hand_count = max(1, int(len(hand_keys) * args.val_fraction))
    val_hands = set(hand_keys[:val_hand_count])
    train_rows = [row for row in rows if row["hand_key"] not in val_hands]
    val_rows = [row for row in rows if row["hand_key"] in val_hands]
    train_weights, train_weight_report = calculate_awr_weights(
        train_rows,
        args.return_clip_bb,
        args.beta_bb,
        args.min_bucket_count,
        args.weight_min,
        args.weight_max,
        args.slice_balance_power,
        4.0,
        1.0,
        0.0,
        4.0,
    )
    val_weights, val_weight_report = calculate_awr_weights(
        val_rows,
        args.return_clip_bb,
        args.beta_bb,
        args.min_bucket_count,
        args.weight_min,
        args.weight_max,
        args.slice_balance_power,
        4.0,
        1.0,
        0.0,
        4.0,
    )
    train_loader = DataLoader(
        stack_rows(train_rows, train_weights),
        batch_size=args.batch_size,
        shuffle=True,
        pin_memory=True,
    )
    val_loader = DataLoader(
        stack_rows(val_rows, val_weights),
        batch_size=args.batch_size,
        shuffle=False,
        pin_memory=True,
    )

    device = args.device
    source_path = Path(args.source_checkpoint).resolve()
    checkpoint = torch.load(source_path, map_location=device, weights_only=False)
    norm = str(checkpoint.get("norm_layer", "bn"))
    source = AlphaHoldemNet(num_actions=NUM_ACTIONS, norm_layer=norm).to(device)
    model = AlphaHoldemNet(
        num_actions=NUM_ACTIONS,
        norm_layer=norm,
        flop_adapter_hidden=args.hidden,
    ).to(device)
    dummy_cards = torch.zeros(2, *CARD_SHAPE, device=device)
    dummy_actions = torch.zeros(2, *ACTION_SHAPE, device=device)
    dummy_extras = torch.zeros(2, 2, device=device)
    source(dummy_cards, dummy_actions, dummy_extras)
    model(dummy_cards, dummy_actions, dummy_extras)
    source.load_state_dict(checkpoint["model"])
    missing, unexpected = model.load_state_dict(checkpoint["model"], strict=False)
    expected_missing = {
        "flop_policy_adapter.0.weight",
        "flop_policy_adapter.0.bias",
        "flop_policy_adapter.2.weight",
        "flop_policy_adapter.2.bias",
    }
    if set(missing) != expected_missing or unexpected:
        raise RuntimeError(
            f"source migration mismatch: missing={missing} unexpected={unexpected}"
        )
    for parameter in source.parameters():
        parameter.requires_grad_(False)
    for name, parameter in model.named_parameters():
        parameter.requires_grad_(name.startswith("flop_policy_adapter."))
    source.eval()
    model.eval()

    trainable = [
        parameter for parameter in model.parameters() if parameter.requires_grad
    ]
    optimizer = torch.optim.AdamW(
        trainable,
        lr=args.lr,
        weight_decay=args.weight_decay,
    )

    history: list[dict[str, Any]] = []
    initial = evaluate_pair(model, source, val_loader, device)
    history.append({"epoch": 0, **initial})
    best_score = math.inf
    best_path = output / "best.pt"
    for epoch in range(1, args.epochs + 1):
        losses = []
        ce_losses = []
        kl_losses = []
        model.eval()
        for batch in train_loader:
            cards, actions, extras, legal, selected, weight, _, _ = [
                value.to(device, non_blocking=True) for value in batch
            ]
            logits, _ = model(cards, actions, extras, legal)
            with torch.no_grad():
                source_logits, _ = source(cards, actions, extras, legal)
                source_probs = F.softmax(source_logits, dim=-1)
            row_ce = F.cross_entropy(logits, selected, reduction="none")
            awr_ce = (row_ce * weight).sum() / weight.sum().clamp_min(1e-6)
            kl = (
                source_probs
                * (
                    F.log_softmax(source_logits, dim=-1)
                    - F.log_softmax(logits, dim=-1)
                )
            ).sum(dim=-1).mean()
            loss = awr_ce + args.kl_coef * kl
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optimizer.step()
            losses.append(float(loss.detach()))
            ce_losses.append(float(awr_ce.detach()))
            kl_losses.append(float(kl.detach()))

        metrics = evaluate_pair(model, source, val_loader, device)
        record = {
            "epoch": epoch,
            "train_loss": float(np.mean(losses)),
            "train_awr_ce": float(np.mean(ce_losses)),
            "train_source_kl": float(np.mean(kl_losses)),
            **metrics,
        }
        history.append(record)
        payload = dict(checkpoint)
        payload.update({
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "flop_adapter_hidden": args.hidden,
            "source_checkpoint": str(source_path),
            "source_checkpoint_sha256": sha256_path(source_path),
            "flop_residual_awr": vars(args),
            "flop_residual_epoch": epoch,
        })
        epoch_path = output / f"epoch_{epoch}.pt"
        atomic_torch_save(payload, epoch_path)
        score = metrics["weighted_awr_ce"] + args.kl_coef * metrics["source_kl"]
        if score < best_score:
            best_score = score
            atomic_torch_save(payload, best_path)
        print(json.dumps(record, sort_keys=True), flush=True)

    report = {
        "status": "finished",
        "source_checkpoint": str(source_path),
        "source_checkpoint_sha256": sha256_path(source_path),
        "selected_files": [str(path) for path in files],
        "ingest": ingest,
        "train_hands": len({row["hand_key"] for row in train_rows}),
        "val_hands": len(val_hands),
        "train_rows": len(train_rows),
        "val_rows": len(val_rows),
        "train_weight_report": train_weight_report,
        "val_weight_report": val_weight_report,
        "history": history,
        "best_checkpoint": str(best_path.resolve()),
        "best_checkpoint_sha256": sha256_path(best_path),
        "runtime_seconds": time.time() - started,
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
