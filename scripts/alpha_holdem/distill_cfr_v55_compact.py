"""Distill compact 200bb CFR rows into a pure AlphaHoldem postflop adapter.

The source policy, including its learned preflop head, remains frozen.  Only a
small residual postflop adapter is optimized.  Compact rows contain public
state, cards, legal slots, and a CFR target mapped to the native V5.5 action
space; no evaluator-time strategy rule is introduced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import torch
import torch.nn.functional as F

try:
    import orjson
except ImportError:  # pragma: no cover - standard-library fallback
    orjson = None

THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = THIS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from alpha_holdem.network import AlphaHoldemNet


STREET_INDEX = {"FLOP": 1, "TURN": 2, "RIVER": 3}
ACTION_TYPE = {
    "FOLD": 0,
    "CHECK": 1,
    "CALL": 2,
    "BET": 3,
    "RAISE": 4,
    "ALLIN": 4,
}
NUM_ACTIONS = 9


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _card_tensor(hole_cards: list[int], board_cards: list[int]) -> np.ndarray:
    tensor = np.zeros((6, 4, 13), dtype=np.float32)

    def place(channel: int, card: int) -> None:
        tensor[channel, card % 4, card // 4] = 1.0

    for card in hole_cards:
        place(0, int(card))
    if len(board_cards) >= 3:
        for card in board_cards[:3]:
            place(1, int(card))
    if len(board_cards) >= 4:
        place(2, int(board_cards[3]))
    if len(board_cards) >= 5:
        place(3, int(board_cards[4]))
    for card in board_cards:
        place(4, int(card))
    for card in [*hole_cards, *board_cards]:
        place(5, int(card))
    return tensor


def _action_tensor(row: dict[str, Any], obs_version: str) -> np.ndarray:
    tensor = np.zeros((25, 4, 5), dtype=np.float32)
    hero = int(row["player"])
    final_pot = max(float(row["state"]["pot"]), 1.0)
    chronological: list[tuple[int, int, str, float | None]] = [
        # Action.amount in HUNLGameState is total committed for raises/bets,
        # while calls carry the default zero amount.
        (0, 1, "RAISE", 2.5),
        (0, 0, "CALL", None),
    ]
    for event in row["events"]:
        street = STREET_INDEX[str(event["street"])]
        amount = (
            event.get("additionalAmount")
            if str(event["actionType"]) not in {"CALL", "CHECK", "FOLD"}
            else None
        )
        chronological.append(
            (
                street,
                int(event["player"]),
                str(event["actionType"]),
                amount,
            )
        )

    if obs_version == "v55":
        by_street: dict[int, list[tuple[int, str, float | None]]] = defaultdict(list)
        for street, player, action_type, amount in chronological:
            by_street[street].append((player, action_type, amount))
        encoded = (
            (street, slot, player, action_type, amount)
            for street, events in by_street.items()
            for slot, (player, action_type, amount) in enumerate(events[:6])
        )
    elif obs_version == "v4":
        legacy_rows = []
        current_street = 0
        street_counts = [0, 0, 0, 0]
        for _, player, action_type, amount in chronological:
            if current_street >= 4:
                break
            slot = street_counts[current_street]
            if slot < 6:
                legacy_rows.append(
                    (current_street, slot, player, action_type, amount)
                )
                street_counts[current_street] += 1
            if (
                action_type in {"CALL", "CHECK"}
                and street_counts[current_street] >= 2
            ):
                current_street += 1
        encoded = iter(legacy_rows)
    else:
        raise ValueError(f"unsupported observation version: {obs_version}")

    for street, slot, player, action_type, amount in encoded:
            channel = street * 6 + slot
            tensor[channel, 0, 0] = 1.0 if player == hero else 0.0
            tensor[channel, 1, ACTION_TYPE[action_type]] = 1.0
            if amount is not None and float(amount) > 0:
                tensor[channel, 2, 0] = min(float(amount) / final_pot, 2.0) / 2.0
            tensor[channel, 3, 0] = 1.0

    tensor[24, 0, 0] = (
        1.0 if int(row["state"]["currentPlayer"]) == hero else 0.0
    )
    return tensor


def compact_row_to_numpy(
    row: dict[str, Any],
    obs_version: str = "v4",
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    if row.get("schema") != "cfr.v55.compact.v1":
        raise ValueError(f"unexpected schema: {row.get('schema')!r}")
    player = int(row["player"])
    if int(row["state"]["currentPlayer"]) != player:
        raise ValueError("CFR row actor/current-player mismatch")

    mask = np.asarray(row["legalMask"], dtype=np.float32)
    target = np.asarray(row["target"], dtype=np.float32)
    if mask.shape != (NUM_ACTIONS,) or target.shape != (NUM_ACTIONS,):
        raise ValueError("V5.5 mask/target shape mismatch")
    if np.any(target < 0) or np.any(target[mask <= 0] > 1e-7):
        raise ValueError("invalid CFR target legality")
    total = float(target.sum())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("invalid CFR target mass")
    target /= total

    stacks = row["state"]["stacks"]
    extra = np.asarray(
        [float(stacks[player]) / 200.0, float(stacks[1 - player]) / 200.0],
        dtype=np.float32,
    )
    return (
        _card_tensor(row["holeCards"], row["boardCards"]),
        _action_tensor(row, obs_version),
        extra,
        mask,
        target,
        STREET_INDEX[str(row["street"])],
    )


def iter_rows(paths: Iterable[Path], max_samples: int) -> Iterable[dict[str, Any]]:
    emitted = 0
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    row = (
                        orjson.loads(line)
                        if orjson is not None
                        else json.loads(line)
                    )
                except (json.JSONDecodeError, ValueError) as error:
                    raise ValueError(f"{path}:{line_no}: {error}") from error
                yield row
                emitted += 1
                if max_samples > 0 and emitted >= max_samples:
                    return


def count_rows(paths: Iterable[Path], max_samples: int) -> int:
    """Count JSONL rows without materializing millions of small Python arrays."""
    total = 0
    for path in paths:
        path_rows = 0
        last_byte = b""
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
                path_rows += chunk.count(b"\n")
                last_byte = chunk[-1:]
        if last_byte and last_byte != b"\n":
            path_rows += 1
        total += path_rows
        if max_samples > 0 and total >= max_samples:
            return max_samples
    return total


def load_tensors(
    paths: list[Path],
    max_samples: int,
    obs_version: str,
) -> tuple[torch.Tensor, ...]:
    sample_count = count_rows(paths, max_samples)
    if sample_count <= 0:
        raise ValueError("no compact CFR rows loaded")
    cards = np.empty((sample_count, 6, 4, 13), dtype=np.float32)
    actions = np.empty((sample_count, 25, 4, 5), dtype=np.float32)
    extras = np.empty((sample_count, 2), dtype=np.float32)
    masks = np.empty((sample_count, NUM_ACTIONS), dtype=np.float32)
    targets = np.empty((sample_count, NUM_ACTIONS), dtype=np.float32)
    streets = np.empty(sample_count, dtype=np.int64)
    board_ids = np.empty(sample_count, dtype=np.int64)
    loaded = 0
    for row in iter_rows(paths, sample_count):
        card, action, extra, mask, target, street = compact_row_to_numpy(
            row, obs_version=obs_version
        )
        cards[loaded] = card
        actions[loaded] = action
        extras[loaded] = extra
        masks[loaded] = mask
        targets[loaded] = target
        streets[loaded] = street
        board_ids[loaded] = int(row["boardId"])
        loaded += 1
    if loaded != sample_count:
        raise ValueError(
            f"JSONL row count changed while loading: expected={sample_count} "
            f"loaded={loaded}"
        )
    return (
        torch.from_numpy(cards),
        torch.from_numpy(actions),
        torch.from_numpy(extras),
        torch.from_numpy(masks),
        torch.from_numpy(targets),
        torch.from_numpy(streets),
        torch.from_numpy(board_ids),
    )


def init_model(
    checkpoint: dict[str, Any],
    adapter_hidden: int,
    device: str,
) -> AlphaHoldemNet:
    state = checkpoint["model"]
    separate_preflop_head = "preflop_policy_head.weight" in state
    preflop_adapter_hidden = (
        int(state["preflop_policy_adapter.0.weight"].shape[0])
        if "preflop_policy_adapter.0.weight" in state
        else 0
    )
    preflop_raw_adapter_hidden = (
        int(state["preflop_raw_policy_adapter.0.weight"].shape[0])
        if "preflop_raw_policy_adapter.0.weight" in state
        else 0
    )
    flop_adapter_hidden = (
        int(state["flop_policy_adapter.0.weight"].shape[0])
        if "flop_policy_adapter.0.weight" in state
        else 0
    )
    inherited_postflop_hidden = (
        int(state["postflop_policy_adapter.0.weight"].shape[0])
        if "postflop_policy_adapter.0.weight" in state
        else 0
    )
    if inherited_postflop_hidden and inherited_postflop_hidden != adapter_hidden:
        raise ValueError(
            "source postflop adapter width differs from --adapter-hidden: "
            f"{inherited_postflop_hidden} != {adapter_hidden}"
        )
    model = AlphaHoldemNet(
        num_actions=NUM_ACTIONS,
        norm_layer=str(checkpoint.get("norm_layer", "bn")),
        separate_preflop_head=separate_preflop_head,
        preflop_adapter_hidden=preflop_adapter_hidden,
        preflop_raw_adapter_hidden=preflop_raw_adapter_hidden,
        preflop_raw_action_scale=float(
            checkpoint.get("preflop_raw_action_scale")
            or (checkpoint.get("config") or {}).get(
                "preflop_raw_action_scale"
            )
            or 1.0
        ),
        preflop_raw_gate=str(
            checkpoint.get("preflop_raw_gate")
            or (checkpoint.get("config") or {}).get("preflop_raw_gate")
            or "none"
        ),
        flop_adapter_hidden=flop_adapter_hidden,
        postflop_adapter_hidden=adapter_hidden,
    ).to(device)
    with torch.no_grad():
        model(
            torch.zeros(2, 6, 4, 13, device=device),
            torch.zeros(2, 25, 4, 5, device=device),
            torch.zeros(2, 2, device=device),
        )
    missing, unexpected = model.load_state_dict(state, strict=False)
    allowed_missing = {
        "postflop_policy_adapter.0.weight",
        "postflop_policy_adapter.0.bias",
        "postflop_policy_adapter.2.weight",
        "postflop_policy_adapter.2.bias",
    }
    if set(missing) - allowed_missing or unexpected:
        raise ValueError(
            f"source state mismatch: missing={missing}, unexpected={unexpected}"
        )
    for name, parameter in model.named_parameters():
        parameter.requires_grad_(name.startswith("postflop_policy_adapter."))
    model.eval()
    return model


def base_hidden_logits(
    model: AlphaHoldemNet,
    card: torch.Tensor,
    action: torch.Tensor,
    extra: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    with torch.no_grad():
        card_flat = model.card_cnn(card)
        action_flat = model.action_cnn(action)
        extra_flat = model.extra_fc(extra)
        hidden = model.trunk(torch.cat([card_flat, action_flat, extra_flat], dim=1))
        base = model.policy_head(hidden)
        if model.flop_policy_adapter is not None:
            flop = base + model.flop_policy_adapter(hidden)
            board_count = card[:, 4].sum(dim=(1, 2))
            base = torch.where(
                ((board_count >= 2.5) & (board_count < 3.5)).unsqueeze(-1),
                flop,
                base,
            )
    return hidden.detach(), base.detach()


def precompute_frozen_features(
    model: AlphaHoldemNet,
    tensors: tuple[torch.Tensor, ...],
    batch_size: int,
    device: str,
) -> tuple[torch.Tensor, ...]:
    sample_count = len(tensors[0])
    hidden_all = torch.empty((sample_count, 256), dtype=torch.float32)
    base_all = torch.empty((sample_count, NUM_ACTIONS), dtype=torch.float32)
    with torch.no_grad():
        for start in range(0, sample_count, batch_size):
            end = min(start + batch_size, sample_count)
            card, action, extra = [
                tensor[start:end].to(device, non_blocking=True)
                for tensor in tensors[:3]
            ]
            hidden, base = base_hidden_logits(model, card, action, extra)
            hidden_all[start:end].copy_(hidden.cpu())
            base_all[start:end].copy_(base.cpu())
    return (
        hidden_all,
        base_all,
        tensors[3],
        tensors[4],
        tensors[5],
        tensors[6],
    )


def metrics_for_indices(
    model: AlphaHoldemNet,
    features: tuple[torch.Tensor, ...],
    indices: torch.Tensor,
    batch_size: int,
    device: str,
) -> dict[str, Any]:
    totals = defaultdict(float)
    street_totals: dict[int, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    with torch.no_grad():
        for start in range(0, len(indices), batch_size):
            batch_idx = indices[start : start + batch_size]
            hidden, base, mask, target, streets = [
                tensor[batch_idx].to(device, non_blocking=True)
                for tensor in features[:5]
            ]
            residual = model.postflop_policy_adapter(hidden)
            masked_base = base + (1.0 - mask) * -1e9
            masked_student = base + residual + (1.0 - mask) * -1e9
            source_log = F.log_softmax(masked_base, dim=-1)
            student_log = F.log_softmax(masked_student, dim=-1)
            source_prob = source_log.exp()
            target_ce = -(target * student_log).sum(dim=-1)
            target_entropy = -(target * target.clamp_min(1e-12).log()).sum(dim=-1)
            target_kl = target_ce - target_entropy
            source_kl = (source_prob * (source_log - student_log)).sum(dim=-1)
            changed = (
                masked_base.argmax(dim=-1) != masked_student.argmax(dim=-1)
            ).float()
            correct = (
                masked_student.argmax(dim=-1) == target.argmax(dim=-1)
            ).float()
            count = float(len(batch_idx))
            totals["count"] += count
            totals["target_kl"] += float(target_kl.sum().item())
            totals["source_kl"] += float(source_kl.sum().item())
            totals["changed"] += float(changed.sum().item())
            totals["top1"] += float(correct.sum().item())
            totals["residual_l2"] += float(
                residual.square().mean(dim=-1).sum().item()
            )
            for street in (1, 2, 3):
                selected = streets == street
                n = int(selected.sum().item())
                if not n:
                    continue
                item = street_totals[street]
                item["count"] += n
                item["target_kl"] += float(target_kl[selected].sum().item())
                item["top1"] += float(correct[selected].sum().item())
    count = max(totals["count"], 1.0)
    result: dict[str, Any] = {
        "samples": int(totals["count"]),
        "target_kl": totals["target_kl"] / count,
        "source_kl": totals["source_kl"] / count,
        "greedy_change_rate": totals["changed"] / count,
        "target_top1_accuracy": totals["top1"] / count,
        "residual_l2": totals["residual_l2"] / count,
        "by_street": {},
    }
    for street, name in ((1, "FLOP"), (2, "TURN"), (3, "RIVER")):
        item = street_totals[street]
        n = max(item["count"], 1.0)
        result["by_street"][name] = {
            "samples": int(item["count"]),
            "target_kl": item["target_kl"] / n,
            "target_top1_accuracy": item["top1"] / n,
        }
    return result


def stratified_epoch_indices(
    train_indices: torch.Tensor,
    streets: torch.Tensor,
    weights: tuple[float, float, float],
    generator: torch.Generator,
    samples_per_epoch: int = 0,
) -> torch.Tensor:
    total = (
        min(int(samples_per_epoch), len(train_indices))
        if samples_per_epoch > 0
        else len(train_indices)
    )
    selected: list[torch.Tensor] = []
    assigned = 0
    for offset, street in enumerate((1, 2, 3)):
        pool = train_indices[streets[train_indices] == street]
        if not len(pool):
            raise ValueError(f"training split contains no street={street} rows")
        count = (
            total - assigned
            if offset == 2
            else int(round(total * weights[offset]))
        )
        assigned += count
        choices = torch.randint(
            0, len(pool), (count,), generator=generator
        )
        selected.append(pool[choices])
    order = torch.cat(selected)
    return order[torch.randperm(len(order), generator=generator)]


def load_anchor_features(
    path: Path,
    expected_source_sha256: str,
) -> tuple[tuple[torch.Tensor, ...], dict[str, Any]]:
    artifact = torch.load(path, map_location="cpu", weights_only=False)
    if artifact.get("schema") != "cardpilot.postflop_source_anchor.v1":
        raise ValueError(f"unexpected anchor schema: {artifact.get('schema')!r}")
    if artifact.get("source_checkpoint_sha256") != expected_source_sha256:
        raise ValueError(
            "anchor/source checkpoint SHA256 mismatch: "
            f"{artifact.get('source_checkpoint_sha256')} != "
            f"{expected_source_sha256}"
        )
    features = (
        artifact["hidden"],
        artifact["source_logits"],
        artifact["legal_mask"],
    )
    lengths = {len(tensor) for tensor in features}
    if len(lengths) != 1 or not lengths or next(iter(lengths)) <= 0:
        raise ValueError("invalid or empty source anchor tensors")
    return features, artifact


def anchor_metrics(
    model: AlphaHoldemNet,
    features: tuple[torch.Tensor, ...],
    batch_size: int,
    device: str,
    max_samples: int = 100_000,
) -> dict[str, float | int]:
    count = min(len(features[0]), max_samples)
    total_kl = 0.0
    total_changed = 0
    with torch.no_grad():
        for start in range(0, count, batch_size):
            end = min(start + batch_size, count)
            hidden, source, mask = [
                tensor[start:end].to(device, dtype=torch.float32, non_blocking=True)
                for tensor in features
            ]
            residual = model.postflop_policy_adapter(hidden)
            source_logits = source + (1.0 - mask) * -1e9
            student_logits = source + residual + (1.0 - mask) * -1e9
            source_log = F.log_softmax(source_logits, dim=-1)
            student_log = F.log_softmax(student_logits, dim=-1)
            source_prob = source_log.exp()
            total_kl += float(
                (source_prob * (source_log - student_log)).sum().item()
            )
            total_changed += int(
                (
                    source_logits.argmax(dim=-1)
                    != student_logits.argmax(dim=-1)
                )
                .sum()
                .item()
            )
    return {
        "samples": count,
        "source_kl": total_kl / max(count, 1),
        "greedy_change_rate": total_changed / max(count, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--adapter-hidden", type=int, default=256)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--source-kl", type=float, default=0.25)
    parser.add_argument(
        "--anchor-features",
        type=Path,
        default=None,
        help="Diverse source-rollout feature artifact for off-topology KL anchoring.",
    )
    parser.add_argument(
        "--anchor-kl",
        type=float,
        default=0.0,
        help="KL coefficient on randomly sampled source-rollout anchor states.",
    )
    parser.add_argument("--residual-l2", type=float, default=1e-4)
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument(
        "--samples-per-epoch",
        type=int,
        default=0,
        help="Stratified optimizer samples per epoch; 0 uses train-set size.",
    )
    parser.add_argument("--val-fraction", type=float, default=0.1)
    parser.add_argument(
        "--val-split",
        choices=("board", "random"),
        default="board",
        help=(
            "Hold out complete board IDs when multiple boards are present; "
            "falls back to a row-random split for a single-board pilot."
        ),
    )
    parser.add_argument(
        "--street-weights",
        default="0.34,0.33,0.33",
        help="FLOP,TURN,RIVER sampling weights per training epoch",
    )
    parser.add_argument("--seed", type=int, default=20260726)
    parser.add_argument(
        "--obs-version",
        choices=("auto", "v4", "v55"),
        default="auto",
    )
    args = parser.parse_args()

    if not args.source.is_file():
        raise SystemExit(f"missing source checkpoint: {args.source}")
    if args.anchor_kl < 0:
        raise SystemExit("--anchor-kl must be non-negative")
    if args.anchor_kl > 0 and (
        args.anchor_features is None or not args.anchor_features.is_file()
    ):
        raise SystemExit("--anchor-kl > 0 requires an existing --anchor-features")
    paths = (
        sorted(args.data.glob("flop_*.jsonl"))
        if args.data.is_dir()
        else [args.data]
    )
    if not paths:
        raise SystemExit(f"no compact CFR files: {args.data}")
    if not 0.0 < args.val_fraction < 0.5:
        raise SystemExit("--val-fraction must be in (0, 0.5)")
    street_weights = tuple(
        float(value) for value in args.street_weights.split(",")
    )
    if (
        len(street_weights) != 3
        or any(value <= 0 for value in street_weights)
        or not math.isclose(sum(street_weights), 1.0, abs_tol=1e-6)
    ):
        raise SystemExit("--street-weights must be three positive values summing to 1")

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    started = time.time()
    source_checkpoint_sha256 = _sha256(args.source)
    checkpoint = torch.load(args.source, map_location="cpu", weights_only=False)
    obs_version = (
        str(checkpoint.get("obs_version") or "v55").lower()
        if args.obs_version == "auto"
        else args.obs_version
    )
    if obs_version not in {"v4", "v55"}:
        raise SystemExit(f"unsupported source obs_version: {obs_version}")
    print(f"Loading compact CFR rows from {len(paths)} file(s)...", flush=True)
    tensors = load_tensors(paths, args.max_samples, obs_version)
    sample_count = len(tensors[0])
    generator = torch.Generator().manual_seed(args.seed)
    unique_boards = torch.unique(tensors[6], sorted=True)
    val_board_ids: list[int] = []
    if args.val_split == "board" and len(unique_boards) > 1:
        board_order = unique_boards[
            torch.randperm(len(unique_boards), generator=generator)
        ]
        val_board_count = max(
            1,
            min(
                len(unique_boards) - 1,
                int(round(len(unique_boards) * args.val_fraction)),
            ),
        )
        val_boards = board_order[:val_board_count]
        val_board_ids = [int(value) for value in val_boards.tolist()]
        val_mask = torch.zeros(sample_count, dtype=torch.bool)
        for board_id in val_boards:
            val_mask |= tensors[6] == board_id
        val_indices = torch.where(val_mask)[0]
        train_indices = torch.where(~val_mask)[0]
        effective_val_split = "board"
    else:
        permutation = torch.randperm(sample_count, generator=generator)
        val_count = max(1, int(round(sample_count * args.val_fraction)))
        val_indices = permutation[:val_count]
        train_indices = permutation[val_count:]
        effective_val_split = "random"
    print(
        f"Loaded {sample_count:,} offline decision samples "
        f"({len(train_indices):,} train / {len(val_indices):,} val; "
        f"split={effective_val_split}; val_boards={val_board_ids})",
        flush=True,
    )

    model = init_model(checkpoint, args.adapter_hidden, args.device)
    adapter_params = [
        parameter
        for name, parameter in model.named_parameters()
        if name.startswith("postflop_policy_adapter.")
    ]
    optimizer = torch.optim.AdamW(adapter_params, lr=args.lr, weight_decay=0.0)
    trainable = sum(parameter.numel() for parameter in adapter_params)
    print(f"Trainable postflop adapter parameters: {trainable:,}", flush=True)
    print("Precomputing frozen source features once...", flush=True)
    features = precompute_frozen_features(
        model, tensors, args.batch_size, args.device
    )
    del tensors
    print("Frozen feature precompute complete.", flush=True)
    anchor_features: tuple[torch.Tensor, ...] | None = None
    anchor_artifact: dict[str, Any] | None = None
    anchor_features_sha256: str | None = None
    if args.anchor_features is not None:
        anchor_features, anchor_artifact = load_anchor_features(
            args.anchor_features,
            source_checkpoint_sha256,
        )
        anchor_features_sha256 = _sha256(args.anchor_features)
        print(
            f"Loaded {len(anchor_features[0]):,} diverse source anchor states "
            f"from {args.anchor_features}",
            flush=True,
        )

    history: list[dict[str, Any]] = []
    baseline_metrics = metrics_for_indices(
        model, features, val_indices, args.batch_size, args.device
    )
    baseline_anchor = (
        anchor_metrics(
            model, anchor_features, args.batch_size, args.device
        )
        if anchor_features is not None
        else None
    )
    history.append(
        {
            "epoch": 0,
            "validation": baseline_metrics,
            "source_anchor": baseline_anchor,
        }
    )
    print(f"epoch 0 val={json.dumps(baseline_metrics, sort_keys=True)}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    for epoch in range(1, args.epochs + 1):
        epoch_order = stratified_epoch_indices(
            train_indices,
            features[4],
            street_weights,
            generator,
            args.samples_per_epoch,
        )
        model.eval()
        running = defaultdict(float)
        for start in range(0, len(epoch_order), args.batch_size):
            batch_idx = epoch_order[start : start + args.batch_size]
            hidden, base, mask, target, _ = [
                tensor[batch_idx].to(args.device, non_blocking=True)
                for tensor in features[:5]
            ]
            residual = model.postflop_policy_adapter(hidden)
            source_logits = base + (1.0 - mask) * -1e9
            student_logits = base + residual + (1.0 - mask) * -1e9
            source_log = F.log_softmax(source_logits, dim=-1)
            student_log = F.log_softmax(student_logits, dim=-1)
            source_prob = source_log.exp()
            target_loss = -(target * student_log).sum(dim=-1).mean()
            source_kl = (
                source_prob * (source_log - student_log)
            ).sum(dim=-1).mean()
            anchor_kl = torch.zeros((), device=args.device)
            if anchor_features is not None and args.anchor_kl > 0:
                anchor_idx = torch.randint(
                    0,
                    len(anchor_features[0]),
                    (len(batch_idx),),
                    generator=generator,
                )
                anchor_hidden, anchor_source, anchor_mask = [
                    tensor[anchor_idx].to(
                        args.device,
                        dtype=torch.float32,
                        non_blocking=True,
                    )
                    for tensor in anchor_features
                ]
                anchor_residual = model.postflop_policy_adapter(anchor_hidden)
                masked_anchor_source = (
                    anchor_source + (1.0 - anchor_mask) * -1e9
                )
                masked_anchor_student = (
                    anchor_source
                    + anchor_residual
                    + (1.0 - anchor_mask) * -1e9
                )
                anchor_source_log = F.log_softmax(
                    masked_anchor_source, dim=-1
                )
                anchor_student_log = F.log_softmax(
                    masked_anchor_student, dim=-1
                )
                anchor_kl = (
                    anchor_source_log.exp()
                    * (anchor_source_log - anchor_student_log)
                ).sum(dim=-1).mean()
            residual_penalty = residual.square().mean()
            loss = (
                target_loss
                + args.source_kl * source_kl
                + args.anchor_kl * anchor_kl
                + args.residual_l2 * residual_penalty
            )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(adapter_params, 5.0)
            optimizer.step()
            n = len(batch_idx)
            running["samples"] += n
            running["loss"] += float(loss.item()) * n
            running["target_ce"] += float(target_loss.item()) * n
            running["source_kl"] += float(source_kl.item()) * n
            running["anchor_kl"] += float(anchor_kl.item()) * n

        validation = metrics_for_indices(
            model, features, val_indices, args.batch_size, args.device
        )
        source_anchor_metrics = (
            anchor_metrics(
                model, anchor_features, args.batch_size, args.device
            )
            if anchor_features is not None
            else None
        )
        train_n = max(running["samples"], 1.0)
        epoch_record = {
            "epoch": epoch,
            "train": {
                "samples": int(running["samples"]),
                "loss": running["loss"] / train_n,
                "target_ce": running["target_ce"] / train_n,
                "source_kl": running["source_kl"] / train_n,
                "anchor_kl": running["anchor_kl"] / train_n,
            },
            "validation": validation,
            "source_anchor": source_anchor_metrics,
        }
        history.append(epoch_record)
        print(f"epoch {epoch} {json.dumps(epoch_record, sort_keys=True)}", flush=True)

        output = dict(checkpoint)
        output["model"] = model.state_dict()
        output["postflop_adapter_hidden"] = int(args.adapter_hidden)
        output["offline_distillation"] = {
            "method": "CFR_V55_COMPACT_POSTFLOP_RESIDUAL_ADAPTER",
            "source_checkpoint": str(args.source),
            "source_checkpoint_sha256": source_checkpoint_sha256,
            "data_files": [str(path) for path in paths],
            "offline_decision_samples": sample_count,
            "new_training_hands": 0,
            "lineage_training_hands": int(
                checkpoint.get(
                    "lineage_training_hands",
                    checkpoint.get("total_hands", checkpoint.get("hands", 0)),
                )
                or 0
            ),
            "epoch": epoch,
            "adapter_hidden": int(args.adapter_hidden),
            "trainable_parameters": trainable,
            "batch_size": int(args.batch_size),
            "samples_per_epoch": int(args.samples_per_epoch),
            "lr": float(args.lr),
            "source_kl": float(args.source_kl),
            "anchor_features": (
                str(args.anchor_features)
                if args.anchor_features is not None
                else None
            ),
            "anchor_features_sha256": (
                anchor_features_sha256
            ),
            "anchor_decision_samples": (
                int(anchor_artifact["postflop_decisions"])
                if anchor_artifact is not None
                else 0
            ),
            "anchor_kl": float(args.anchor_kl),
            "residual_l2": float(args.residual_l2),
            "seed": int(args.seed),
            "obs_version": obs_version,
            "street_weights": list(street_weights),
            "validation_split": effective_val_split,
            "validation_board_ids": val_board_ids,
            "history": history,
            "runtime_seconds": float(time.time() - started),
        }
        output["config"] = {
            **dict(checkpoint.get("config") or {}),
            "postflop_adapter_hidden": int(args.adapter_hidden),
        }
        epoch_path = args.out.with_name(
            f"{args.out.stem}_epoch{epoch:02d}{args.out.suffix}"
        )
        torch.save(output, epoch_path)
        torch.save(output, args.out)
        print(f"saved {epoch_path} and {args.out}", flush=True)

    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "output": str(args.out),
                "offline_decision_samples": sample_count,
                "runtime_seconds": time.time() - started,
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
