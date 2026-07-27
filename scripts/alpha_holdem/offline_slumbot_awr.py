"""Offline policy improvement from completed Slumbot decision dumps.

The input corpus contains the observation available to the hero, the action
actually taken, and the terminal hand payoff.  We reconstruct v5.5 actor
observations and perform advantage-weighted regression (AWR): actions from hands
that outperform comparable position/street/strength/price buckets receive more
weight, while a frozen-source KL term limits unsupported extrapolation.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
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
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(THIS_DIR))

from alpha_holdem.network import AlphaHoldemNet
from heuristic_policy_v3 import _eval_postflop, _hand_notation
from heuristic_policy_v4 import PREFLOP_PERCENTILE
from play_slumbot import (
    STACK_SIZE,
    action_idx_to_incr,
    compute_commitments,
    compute_legal_mask,
    encode_action_history,
    encode_cards,
    encode_extra,
    parse_action,
    preflop_logit_bias_context,
)


CARD_SHAPE = (6, 4, 13)
ACTION_SHAPE = (25, 4, 5)
NUM_ACTIONS = 9


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_torch_save(payload: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(destination)


def discover_dump_files(
    roots: list[str],
    exclude_substrings: list[str],
    include_substrings: list[str] | None = None,
) -> list[Path]:
    candidates: list[Path] = []
    for root in roots:
        candidates.extend(Path(p) for p in glob.glob(
            str(Path(root) / "**" / "*_dump.jsonl"), recursive=True
        ))
    selected: list[Path] = []
    seen_hashes: set[str] = set()
    for path in sorted(set(p.resolve() for p in candidates)):
        text = str(path)
        if any(token and token in text for token in exclude_substrings):
            continue
        if include_substrings and not any(
            token and token in text for token in include_substrings
        ):
            continue
        digest = sha256_path(path)
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        selected.append(path)
    return selected


def action_slot(
    record: dict[str, Any],
    state: dict[str, Any],
    legal: np.ndarray,
    raise_action_mapping: str = "legacy_total_over_pot",
) -> int | None:
    move = str(record["action_move"])
    if move == "f":
        return 0 if legal[0] > 0 else None
    if move in ("c", "k"):
        return 1 if legal[1] > 0 else None
    if move != "b":
        return None
    expected = f"b{int(record['action_amount'])}"
    matches = [
        slot for slot in range(NUM_ACTIONS)
        if (
            legal[slot] > 0
            and action_idx_to_incr(
                slot,
                state,
                raise_action_mapping=raise_action_mapping,
            )
            == expected
        )
    ]
    return matches[0] if len(matches) == 1 else None


def digitize(value: float, boundaries: tuple[float, ...]) -> int:
    return int(np.searchsorted(np.asarray(boundaries), value, side="right"))


def state_bucket(
    record: dict[str, Any],
    state: dict[str, Any],
    commitments: dict[str, Any],
) -> tuple[int, ...]:
    street = int(record["street"])
    position = int(record["client_pos"])
    to_call = float(commitments["to_call"]) / 100.0
    pot = max(float(commitments["pot"]) / 100.0, 0.01)
    facing = int(to_call > 0.0)
    price = to_call / pot
    actions = state.get("street_actions", [[], [], [], []])[street]
    action_count = min(len(actions), 4)
    pot_bin = digitize(pot, (2, 5, 10, 25, 50, 100, 200))
    price_bin = digitize(price, (0.10, 0.25, 0.50, 1.00))
    if street == 0:
        notation = _hand_notation(record["hero_hole"])
        strength = min(9, int(PREFLOP_PERCENTILE[notation] * 10.0))
    else:
        strength = int(_eval_postflop(record["hero_hole"], record["board"]))
    return (
        position,
        street,
        facing,
        action_count,
        pot_bin,
        price_bin,
        strength,
    )


def reconstruct(
    record: dict[str, Any],
    obs_version: str,
    actor: str = "hero",
    raise_action_mapping: str = "legacy_total_over_pot",
) -> dict[str, Any] | None:
    required = {
        "who", "client_pos", "opp_pos", "action_str_before", "street", "board",
        "hero_hole", "opp_hole", "action_move", "action_amount", "winnings_hero",
        "hand_idx", "move_idx",
    }
    if actor not in {"hero", "opp"}:
        raise ValueError(f"unsupported actor: {actor}")
    if record.get("who") != actor or not required.issubset(record):
        return None
    actor_pos = int(record["client_pos"] if actor == "hero" else record["opp_pos"])
    actor_hole = record["hero_hole"] if actor == "hero" else record["opp_hole"]
    if not actor_hole:
        return None
    state = parse_action(str(record["action_str_before"]))
    if state.get("error") or int(state.get("pos", -1)) != actor_pos:
        return None
    commitments = compute_commitments(state)
    legal = np.asarray(
        compute_legal_mask(state, raise_action_mapping),
        dtype=np.float32,
    )
    selected = action_slot(
        record,
        state,
        legal,
        raise_action_mapping=raise_action_mapping,
    )
    if selected is None:
        return None
    client_pos = actor_pos
    street = int(record["street"])
    stacks = [
        STACK_SIZE - int(commitments["hero_total"]),
        STACK_SIZE - int(commitments["opp_total"]),
    ]
    return {
        "card": np.asarray(
            encode_cards(actor_hole, record["board"], street),
            dtype=np.float32,
        ),
        "action": np.asarray(
            encode_action_history(
                state, client_pos, int(state["pos"]), obs_version=obs_version
            ),
            dtype=np.float32,
        ),
        "extra": np.asarray(encode_extra(stacks), dtype=np.float32),
        "legal": legal,
        "selected": int(selected),
        "return_bb": (
            float(record["winnings_hero"]) / 100.0
            if actor == "hero"
            else -float(record["winnings_hero"]) / 100.0
        ),
        "bucket": state_bucket(
            {
                **record,
                "client_pos": actor_pos,
                "hero_hole": actor_hole,
            },
            state,
            commitments,
        ),
        "position": client_pos,
        "street": street,
        "decision_risk_bb": max(
            1.0,
            (
                float(commitments["pot"])
                + float(commitments["to_call"])
            )
            / 100.0,
        ),
        "hand_key": (int(record["hand_idx"]),),
        "hole_cards": list(actor_hole),
        "board": list(record["board"]),
        "action_str_before": str(record["action_str_before"]),
        "behavior_action_probability": (
            float(record["policy_behavior_action_probability"])
            if record.get("policy_behavior_action_probability") is not None
            else None
        ),
        "behavior_probs": (
            [float(value) for value in record["policy_behavior_probs"]]
            if record.get("policy_behavior_probs") is not None
            else None
        ),
        "behavior_temperature": (
            float(record["policy_temperature"])
            if record.get("policy_temperature") is not None
            else None
        ),
        "behavior_greedy_action": (
            int(record["policy_greedy_action_slot"])
            if record.get("policy_greedy_action_slot") is not None
            else None
        ),
    }


def reservoir_rows(
    files: list[Path],
    max_rows: int,
    seed: int,
    obs_version: str,
    street_min: int,
    street_max: int,
    actor: str,
    position: int | None = None,
    raise_action_mapping: str = "legacy_total_over_pot",
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    stats = Counter()
    seen = 0
    for file_index, path in enumerate(files):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                stats["physical_rows"] += 1
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    stats["json_errors"] += 1
                    continue
                if raw.get("who") != actor:
                    continue
                stats[f"{actor}_rows"] += 1
                row = reconstruct(
                    raw,
                    obs_version,
                    actor=actor,
                    raise_action_mapping=raise_action_mapping,
                )
                if row is None:
                    stats["unmapped_rows"] += 1
                    continue
                if not street_min <= int(row["street"]) <= street_max:
                    stats["street_filtered_rows"] += 1
                    continue
                if position is not None and int(row["position"]) != position:
                    stats["position_filtered_out_rows"] += 1
                    continue
                row["hand_key"] = (file_index, int(raw["hand_idx"]))
                seen += 1
                if len(rows) < max_rows:
                    rows.append(row)
                else:
                    replacement = rng.randrange(seen)
                    if replacement < max_rows:
                        rows[replacement] = row
    stats["mapped_rows"] = seen
    stats["sampled_rows"] = len(rows)
    return rows, dict(stats)


def calculate_awr_weights(
    rows: list[dict[str, Any]],
    return_clip_bb: float,
    beta_bb: float,
    min_bucket_count: int,
    weight_min: float,
    weight_max: float,
    slice_balance_power: float,
    slice_balance_cap: float,
    preflop_call_boost: float,
    decision_risk_power: float,
    decision_risk_cap: float,
    position_0_weight: float = 1.0,
    inverse_propensity_power: float = 0.0,
    inverse_propensity_cap: float = 8.0,
) -> tuple[np.ndarray, dict[str, Any]]:
    clipped = np.asarray([
        np.clip(row["return_bb"], -return_clip_bb, return_clip_bb) for row in rows
    ], dtype=np.float64)
    bucket_values: dict[tuple[int, ...], list[float]] = defaultdict(list)
    for row, value in zip(rows, clipped):
        bucket_values[row["bucket"]].append(float(value))
    global_mean = float(clipped.mean())
    baselines: dict[tuple[int, ...], float] = {}
    for bucket, values in bucket_values.items():
        count = len(values)
        local = float(np.mean(values))
        shrink = count / float(count + min_bucket_count)
        baselines[bucket] = shrink * local + (1.0 - shrink) * global_mean
    advantage = np.asarray([
        value - baselines[row["bucket"]] for row, value in zip(rows, clipped)
    ], dtype=np.float64)
    raw = np.exp(np.clip(advantage / beta_bb, -5.0, 5.0))
    raw = np.clip(raw, weight_min, weight_max)

    decisions_per_hand = Counter(row["hand_key"] for row in rows)
    hand_normalizer = np.asarray([
        1.0 / decisions_per_hand[row["hand_key"]] for row in rows
    ], dtype=np.float64)

    # The historical policy corpus is heavily multimodal: fold/check-call/raise
    # decisions share observations, while exact raise sizes split the raise class
    # across seven output slots.  Balancing exact slots would over-amplify rare
    # sizings, so balance the three semantic action classes inside each
    # position/street/betting-context slice instead.  Facing a bet and the
    # current-street action count are essential: slot 1 is a free check after a
    # limp in one context and a costly call facing an open in another.
    def coarse_action(selected: int) -> int:
        return min(int(selected), 2)

    def betting_context(row: dict[str, Any]) -> tuple[int, int, int, int]:
        bucket = row["bucket"]
        return (
            int(row["position"]),
            int(row["street"]),
            int(bucket[2]),  # facing a wager
            int(bucket[3]),  # current-street action count (capped)
        )

    slice_counts = Counter(
        (*betting_context(row), coarse_action(row["selected"]))
        for row in rows
    )
    contexts = sorted(set(betting_context(row) for row in rows))
    slice_max = {
        context: max(
            slice_counts.get((*context, action_class), 0)
            for action_class in range(3)
        )
        for context in contexts
    }
    balance = np.ones(len(rows), dtype=np.float64)
    if slice_balance_power > 0.0:
        for index, row in enumerate(rows):
            context = betting_context(row)
            key = (*context, coarse_action(row["selected"]))
            count = max(slice_counts[key], 1)
            maximum = max(slice_max[context], 1)
            balance[index] = min(
                (maximum / float(count)) ** slice_balance_power,
                slice_balance_cap,
            )
    if preflop_call_boost != 1.0:
        for index, row in enumerate(rows):
            context = betting_context(row)
            if (
                context[1] == 0
                and context[2] == 1
                and int(row["selected"]) == 1
            ):
                balance[index] *= preflop_call_boost

    decision_risk = np.asarray(
        [float(row["decision_risk_bb"]) for row in rows],
        dtype=np.float64,
    )
    risk_weight = np.ones(len(rows), dtype=np.float64)
    if decision_risk_power > 0.0:
        risk_weight = np.minimum(
            np.power(decision_risk, decision_risk_power),
            decision_risk_cap,
        )
    position_weight = np.asarray(
        [
            position_0_weight if int(row["position"]) == 0 else 1.0
            for row in rows
        ],
        dtype=np.float64,
    )

    propensity = np.asarray(
        [
            (
                float(row["behavior_action_probability"])
                if row["behavior_action_probability"] is not None
                else 1.0
            )
            for row in rows
        ],
        dtype=np.float64,
    )
    inverse_propensity = np.ones(len(rows), dtype=np.float64)
    if inverse_propensity_power > 0.0:
        inverse_propensity = np.minimum(
            np.power(np.maximum(propensity, 1e-6), -inverse_propensity_power),
            inverse_propensity_cap,
        )

    weights = (
        raw
        * hand_normalizer
        * balance
        * risk_weight
        * position_weight
        * inverse_propensity
    )
    weights /= max(float(weights.mean()), 1e-12)
    slice_action_counts = {
        f"p{context[0]}s{context[1]}f{context[2]}n{context[3]}a{action_class}": int(
            slice_counts.get((*context, action_class), 0)
        )
        for context in contexts
        for action_class in range(3)
    }
    mean_weight_by_slice_action = {}
    row_contexts = [betting_context(row) for row in rows]
    row_action_classes = [coarse_action(row["selected"]) for row in rows]
    for context in contexts:
        for action_class in range(3):
            mask = np.fromiter(
                (
                    row_context == context and row_action == action_class
                    for row_context, row_action in zip(
                        row_contexts, row_action_classes
                    )
                ),
                dtype=bool,
                count=len(rows),
            )
            key = (
                f"p{context[0]}s{context[1]}f{context[2]}"
                f"n{context[3]}a{action_class}"
            )
            mean_weight_by_slice_action[key] = (
                float(weights[mask].mean()) if mask.any() else None
            )
    report = {
        "global_clipped_return_mean_bb": global_mean,
        "bucket_count": len(bucket_values),
        "bucket_count_ge_min": sum(
            len(values) >= min_bucket_count for values in bucket_values.values()
        ),
        "advantage_mean": float(advantage.mean()),
        "advantage_std": float(advantage.std()),
        "slice_balance_power": slice_balance_power,
        "slice_balance_cap": slice_balance_cap,
        "preflop_call_boost": preflop_call_boost,
        "decision_risk_power": decision_risk_power,
        "decision_risk_cap": decision_risk_cap,
        "decision_risk_bb_mean": float(decision_risk.mean()),
        "decision_risk_bb_p90": float(np.quantile(decision_risk, 0.90)),
        "decision_risk_bb_p99": float(np.quantile(decision_risk, 0.99)),
        "risk_weight_mean_before_normalization": float(risk_weight.mean()),
        "risk_weight_max": float(risk_weight.max()),
        "position_0_weight": position_0_weight,
        "position_weight_mean_before_normalization": float(
            position_weight.mean()
        ),
        "inverse_propensity_power": inverse_propensity_power,
        "inverse_propensity_cap": inverse_propensity_cap,
        "propensity_min": float(propensity.min()),
        "propensity_mean": float(propensity.mean()),
        "inverse_propensity_mean_before_normalization": float(
            inverse_propensity.mean()
        ),
        "inverse_propensity_max": float(inverse_propensity.max()),
        "slice_action_counts": slice_action_counts,
        "mean_weight_by_slice_action": mean_weight_by_slice_action,
        "weight_min": float(weights.min()),
        "weight_mean": float(weights.mean()),
        "weight_max": float(weights.max()),
        "weight_p50": float(np.quantile(weights, 0.50)),
        "weight_p90": float(np.quantile(weights, 0.90)),
        "weight_p99": float(np.quantile(weights, 0.99)),
    }
    return weights.astype(np.float32), report


def stack_rows(rows: list[dict[str, Any]], weights: np.ndarray) -> TensorDataset:
    cards = torch.from_numpy(np.stack([row["card"] for row in rows]))
    actions = torch.from_numpy(np.stack([row["action"] for row in rows]))
    extras = torch.from_numpy(np.stack([row["extra"] for row in rows]))
    legal = torch.from_numpy(np.stack([row["legal"] for row in rows]))
    selected = torch.tensor([row["selected"] for row in rows], dtype=torch.long)
    weight = torch.from_numpy(weights)
    position = torch.tensor([row["position"] for row in rows], dtype=torch.long)
    street = torch.tensor([row["street"] for row in rows], dtype=torch.long)
    return TensorDataset(
        cards, actions, extras, legal, selected, weight, position, street
    )


def model_extras(
    model: AlphaHoldemNet,
    extras: torch.Tensor,
    position: torch.Tensor,
) -> torch.Tensor:
    """Append the observed seat only for models with position residuals."""
    if int(getattr(model, "position_adapter_hidden", 0)) <= 0:
        return extras
    return torch.cat(
        [extras, position.to(extras.dtype).unsqueeze(1)],
        dim=1,
    )


@torch.no_grad()
def evaluate(
    model: AlphaHoldemNet,
    loader: DataLoader,
    device: str,
    source: AlphaHoldemNet | None = None,
) -> dict[str, Any]:
    model.eval()
    total = correct = 0
    total_weight = correct_weight = 0.0
    weighted_nll_sum = 0.0
    source_kl_sum = 0.0
    selected_counts = np.zeros(NUM_ACTIONS, np.int64)
    predicted_counts = np.zeros(NUM_ACTIONS, np.int64)
    slice_correct = Counter()
    slice_total = Counter()
    for batch in loader:
        cards, actions, extras, legal, selected, weight, position, street = [
            value.to(device) for value in batch
        ]
        logits, _ = model(
            cards,
            actions,
            model_extras(model, extras, position),
            legal,
        )
        row_nll = F.cross_entropy(logits, selected, reduction="none")
        weighted_nll_sum += float((weight * row_nll).sum())
        if source is not None:
            source_logits, _ = source(
                cards,
                actions,
                model_extras(source, extras, position),
                legal,
            )
            source_probs = F.softmax(source_logits, dim=-1)
            row_kl = (
                source_probs
                * (
                    F.log_softmax(source_logits, dim=-1)
                    - F.log_softmax(logits, dim=-1)
                )
            ).sum(dim=-1)
            source_kl_sum += float(row_kl.sum())
        prediction = logits.argmax(dim=-1)
        total += len(selected)
        correct += int((prediction == selected).sum())
        total_weight += float(weight.sum())
        correct_weight += float(
            (weight * (prediction == selected).to(weight.dtype)).sum()
        )
        selected_counts += np.bincount(
            selected.cpu().numpy(), minlength=NUM_ACTIONS
        )
        predicted_counts += np.bincount(
            prediction.cpu().numpy(), minlength=NUM_ACTIONS
        )
        for pos in (0, 1):
            for st in (0, 1, 2, 3):
                mask = (position == pos) & (street == st)
                key = f"p{pos}s{st}"
                slice_total[key] += int(mask.sum())
                slice_correct[key] += int(((prediction == selected) & mask).sum())
    return {
        "rows": total,
        "behavior_accuracy": correct / max(total, 1),
        "weighted_behavior_accuracy": correct_weight / max(total_weight, 1e-12),
        "weighted_nll": weighted_nll_sum / max(total_weight, 1e-12),
        "source_kl": (
            source_kl_sum / max(total, 1)
            if source is not None
            else 0.0
        ),
        "selected_action_frequency": (selected_counts / max(total, 1)).tolist(),
        "predicted_action_frequency": (predicted_counts / max(total, 1)).tolist(),
        "slice_accuracy": {
            key: slice_correct[key] / max(value, 1)
            for key, value in sorted(slice_total.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-checkpoint", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--roots", nargs="+", default=["models", "eval_logs", "reports"])
    parser.add_argument(
        "--exclude-substring",
        action="append",
        default=None,
        help=(
            "Exclude dump paths containing this token. Repeatable. When omitted, "
            "the historical default excludes 20260725; pass an unused token to "
            "train explicitly on current-date evidence."
        ),
    )
    parser.add_argument(
        "--include-substring",
        action="append",
        default=None,
        help=(
            "When provided, retain dump paths matching at least one of these "
            "tokens. Repeatable."
        ),
    )
    parser.add_argument("--obs-version", choices=("v4", "v55"), default="v55")
    parser.add_argument(
        "--raise-action-mapping",
        choices=(
            "auto",
            "legacy_total_over_pot",
            "preflop_pot_fraction_v2",
            "pot_fraction_v2",
        ),
        default="auto",
        help=(
            "Action abstraction used to map observed Slumbot bet sizes to "
            "network slots. The default inherits it from the source checkpoint."
        ),
    )
    parser.add_argument("--actor", choices=("hero", "opp"), default="hero")
    parser.add_argument(
        "--position",
        type=int,
        choices=(0, 1),
        default=None,
        help=(
            "Optionally retain only decisions made from one HU position. "
            "Position 0 is the big blind and position 1 is the small blind."
        ),
    )
    parser.add_argument("--street-min", type=int, choices=range(4), default=0)
    parser.add_argument("--street-max", type=int, choices=range(4), default=3)
    parser.add_argument("--max-rows", type=int, default=500_000)
    parser.add_argument("--min-rows", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=20260725)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=2048)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--weight-decay", type=float, default=1e-5)
    parser.add_argument("--kl-coef", type=float, default=0.05)
    parser.add_argument("--return-clip-bb", type=float, default=20.0)
    parser.add_argument("--beta-bb", type=float, default=5.0)
    parser.add_argument("--min-bucket-count", type=int, default=20)
    parser.add_argument("--weight-min", type=float, default=0.05)
    parser.add_argument("--weight-max", type=float, default=20.0)
    parser.add_argument("--slice-balance-power", type=float, default=0.0)
    parser.add_argument("--slice-balance-cap", type=float, default=8.0)
    parser.add_argument("--preflop-call-boost", type=float, default=1.0)
    parser.add_argument("--decision-risk-power", type=float, default=0.0)
    parser.add_argument("--decision-risk-cap", type=float, default=4.0)
    parser.add_argument(
        "--position-0-weight",
        type=float,
        default=1.0,
        help=(
            "Multiplicative training weight for big-blind (position 0) rows. "
            "Use values above 1 to emphasize BB repair while retaining both "
            "positions in the training corpus."
        ),
    )
    parser.add_argument(
        "--inverse-propensity-power",
        type=float,
        default=0.0,
        help=(
            "Multiply AWR weights by logged behavior propensity raised to the "
            "negative power. Use only with probability-traced exploration data."
        ),
    )
    parser.add_argument(
        "--inverse-propensity-cap",
        type=float,
        default=8.0,
        help="Maximum inverse-propensity multiplier before global normalization.",
    )
    parser.add_argument("--val-fraction", type=float, default=0.05)
    parser.add_argument(
        "--separate-preflop-head-only",
        action="store_true",
        help="Freeze the source network and optimize only a copied preflop head.",
    )
    parser.add_argument(
        "--initial-preflop-only",
        action="store_true",
        help="Keep only unopened-SB and BB-vs-open first decisions.",
    )
    parser.add_argument("--postflop-adapter-hidden", type=int, default=0)
    parser.add_argument(
        "--policy-adapter-only",
        action="store_true",
        help=(
            "Freeze the source trunk and heads except the dedicated preflop "
            "head; train that head plus a zero-initialized postflop adapter."
        ),
    )
    parser.add_argument("--position-adapter-hidden", type=int, default=0)
    parser.add_argument(
        "--position-policy-adapter-only",
        action="store_true",
        help=(
            "Freeze the source network and optimize only zero-initialized "
            "position residuals. With --position 0 or 1, only that seat's "
            "residual is trainable and the other seat remains exactly source."
        ),
    )
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

    exclude_substrings = (
        args.exclude_substring
        if args.exclude_substring is not None
        else ["20260725"]
    )
    files = discover_dump_files(
        args.roots,
        exclude_substrings,
        args.include_substring,
    )
    if not files:
        raise RuntimeError("no dump files selected")
    if args.street_min > args.street_max:
        raise ValueError("--street-min must be <= --street-max")
    if args.decision_risk_power < 0.0:
        raise ValueError("--decision-risk-power must be non-negative")
    if args.decision_risk_cap < 1.0:
        raise ValueError("--decision-risk-cap must be at least 1")
    if args.position_0_weight <= 0.0:
        raise ValueError("--position-0-weight must be positive")
    if not 0.0 <= args.inverse_propensity_power <= 1.0:
        raise ValueError("--inverse-propensity-power must be in [0, 1]")
    if args.inverse_propensity_cap < 1.0:
        raise ValueError("--inverse-propensity-cap must be at least 1")
    if args.postflop_adapter_hidden < 0:
        raise ValueError("--postflop-adapter-hidden must be non-negative")
    if args.policy_adapter_only and args.postflop_adapter_hidden <= 0:
        raise ValueError(
            "--policy-adapter-only requires --postflop-adapter-hidden > 0"
        )
    if args.policy_adapter_only and args.separate_preflop_head_only:
        raise ValueError(
            "--policy-adapter-only and --separate-preflop-head-only are mutually exclusive"
        )
    if args.position_adapter_hidden < 0:
        raise ValueError("--position-adapter-hidden must be non-negative")
    if (
        args.position_policy_adapter_only
        and args.position_adapter_hidden <= 0
    ):
        raise ValueError(
            "--position-policy-adapter-only requires "
            "--position-adapter-hidden > 0"
        )
    if args.position_policy_adapter_only and (
        args.policy_adapter_only
        or args.separate_preflop_head_only
        or args.postflop_adapter_hidden > 0
    ):
        raise ValueError(
            "--position-policy-adapter-only cannot be combined with another "
            "adapter-only mode"
        )
    source_metadata = torch.load(
        args.source_checkpoint,
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
    rows, ingest = reservoir_rows(
        files,
        args.max_rows,
        args.seed,
        args.obs_version,
        args.street_min,
        args.street_max,
        args.actor,
        args.position,
        raise_action_mapping,
    )
    if args.initial_preflop_only:
        rows = [
            row for row in rows
            if preflop_logit_bias_context(parse_action(row["action_str_before"]))
            in {"sb_open", "bb_vs_open"}
        ]
        ingest["initial_preflop_rows"] = len(rows)
    if args.position is not None:
        ingest["position_filter"] = args.position
        ingest["position_selected_rows"] = len(rows)
    if len(rows) < args.min_rows:
        raise RuntimeError(f"too few reconstructed rows: {len(rows)}")
    if args.inverse_propensity_power > 0.0:
        missing_propensity = sum(
            row["behavior_action_probability"] is None for row in rows
        )
        invalid_propensity = sum(
            row["behavior_action_probability"] is not None
            and not 0.0 < float(row["behavior_action_probability"]) <= 1.0
            for row in rows
        )
        if missing_propensity or invalid_propensity:
            raise RuntimeError(
                "inverse-propensity AWR requires valid logged propensities: "
                f"missing={missing_propensity} invalid={invalid_propensity}"
            )
    weights, weight_report = calculate_awr_weights(
        rows,
        args.return_clip_bb,
        args.beta_bb,
        args.min_bucket_count,
        args.weight_min,
        args.weight_max,
        args.slice_balance_power,
        args.slice_balance_cap,
        args.preflop_call_boost,
        args.decision_risk_power,
        args.decision_risk_cap,
        args.position_0_weight,
        args.inverse_propensity_power,
        args.inverse_propensity_cap,
    )

    order = np.random.default_rng(args.seed).permutation(len(rows))
    val_count = max(1, int(len(rows) * args.val_fraction))
    val_idx = order[:val_count]
    train_idx = order[val_count:]
    train_rows = [rows[int(i)] for i in train_idx]
    val_rows = [rows[int(i)] for i in val_idx]
    train_data = stack_rows(train_rows, weights[train_idx])
    val_data = stack_rows(val_rows, weights[val_idx])
    train_loader = DataLoader(
        train_data, batch_size=args.batch_size, shuffle=True, pin_memory=True
    )
    val_loader = DataLoader(
        val_data, batch_size=args.batch_size, shuffle=False, pin_memory=True
    )

    device = args.device
    source_path = Path(args.source_checkpoint).resolve()
    checkpoint = torch.load(source_path, map_location=device, weights_only=False)
    norm_layer = str(checkpoint.get("norm_layer", "bn"))
    critic_contract = str(
        checkpoint.get("critic_contract")
        or (checkpoint.get("config") or {}).get("critic_contract")
        or "critic_v1"
    )
    critic_init_seed = int(
        checkpoint.get("critic_init_seed")
        or (checkpoint.get("config") or {}).get("critic_init_seed")
        or 2026071601
    )
    state = checkpoint["model"]
    source_separate_preflop_head = (
        "preflop_policy_head.weight" in state
    )
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
    inherited_postflop_adapter_hidden = (
        int(state["postflop_policy_adapter.0.weight"].shape[0])
        if "postflop_policy_adapter.0.weight" in state
        else 0
    )
    inherited_position_adapter_hidden = (
        int(state["position_policy_adapters.0.0.weight"].shape[0])
        if "position_policy_adapters.0.0.weight" in state
        else 0
    )
    if (
        inherited_postflop_adapter_hidden
        and args.postflop_adapter_hidden
        and inherited_postflop_adapter_hidden != args.postflop_adapter_hidden
    ):
        raise ValueError(
            "requested postflop adapter width differs from source: "
            f"{args.postflop_adapter_hidden} != "
            f"{inherited_postflop_adapter_hidden}"
        )
    model_postflop_adapter_hidden = (
        args.postflop_adapter_hidden
        or inherited_postflop_adapter_hidden
    )
    if (
        inherited_position_adapter_hidden
        and args.position_adapter_hidden
        and inherited_position_adapter_hidden != args.position_adapter_hidden
    ):
        raise ValueError(
            "requested position adapter width differs from source: "
            f"{args.position_adapter_hidden} != "
            f"{inherited_position_adapter_hidden}"
        )
    model_position_adapter_hidden = (
        args.position_adapter_hidden
        or inherited_position_adapter_hidden
    )
    architecture = {
        "num_actions": NUM_ACTIONS,
        "norm_layer": norm_layer,
        "preflop_adapter_hidden": preflop_adapter_hidden,
        "preflop_raw_adapter_hidden": preflop_raw_adapter_hidden,
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
        "flop_adapter_hidden": flop_adapter_hidden,
        "postflop_adapter_hidden": model_postflop_adapter_hidden,
        "position_adapter_hidden": model_position_adapter_hidden,
        "critic_contract": critic_contract,
        "critic_init_seed": critic_init_seed,
    }
    model = AlphaHoldemNet(
        **architecture,
        separate_preflop_head=(
            source_separate_preflop_head
            or args.separate_preflop_head_only
        ),
    ).to(device)
    source = AlphaHoldemNet(
        **{
            **architecture,
            "postflop_adapter_hidden": inherited_postflop_adapter_hidden,
            "position_adapter_hidden": inherited_position_adapter_hidden,
        },
        separate_preflop_head=source_separate_preflop_head,
    ).to(device)
    dummy_cards = torch.zeros(2, *CARD_SHAPE, device=device)
    dummy_actions = torch.zeros(2, *ACTION_SHAPE, device=device)
    model_dummy_extras = torch.zeros(
        2,
        3 if model_position_adapter_hidden > 0 else 2,
        device=device,
    )
    source_dummy_extras = torch.zeros(
        2,
        3 if inherited_position_adapter_hidden > 0 else 2,
        device=device,
    )
    model.eval()
    source.eval()
    model(dummy_cards, dummy_actions, model_dummy_extras)
    source(dummy_cards, dummy_actions, source_dummy_extras)
    adding_postflop_adapter = (
        model_postflop_adapter_hidden > 0
        and inherited_postflop_adapter_hidden == 0
    )
    adding_position_adapter = (
        model_position_adapter_hidden > 0
        and inherited_position_adapter_hidden == 0
    )
    if args.position_policy_adapter_only:
        missing, unexpected = model.load_state_dict(state, strict=False)
        expected_missing = {
            f"position_policy_adapters.{seat}.{layer}.{parameter}"
            for seat in (0, 1)
            for layer in (0, 2)
            for parameter in ("weight", "bias")
        } if adding_position_adapter else set()
        if set(missing) != expected_missing or unexpected:
            raise RuntimeError(
                "position-adapter migration mismatch: "
                f"missing={missing} unexpected={unexpected}"
            )
        trainable_seats = (
            {int(args.position)}
            if args.position is not None
            else {0, 1}
        )
        for name, parameter in model.named_parameters():
            parameter.requires_grad_(
                any(
                    name.startswith(f"position_policy_adapters.{seat}.")
                    for seat in trainable_seats
                )
            )
    elif args.policy_adapter_only:
        missing, unexpected = model.load_state_dict(state, strict=False)
        expected_missing = {
            "postflop_policy_adapter.0.weight",
            "postflop_policy_adapter.0.bias",
            "postflop_policy_adapter.2.weight",
            "postflop_policy_adapter.2.bias",
        } if adding_postflop_adapter else set()
        if set(missing) != expected_missing or unexpected:
            raise RuntimeError(
                "policy-adapter migration mismatch: "
                f"missing={missing} unexpected={unexpected}"
            )
        for name, parameter in model.named_parameters():
            parameter.requires_grad_(
                name.startswith("preflop_policy_head.")
                or name.startswith("postflop_policy_adapter.")
            )
    elif args.separate_preflop_head_only:
        if source_separate_preflop_head:
            model.load_state_dict(state)
        else:
            missing, unexpected = model.load_state_dict(state, strict=False)
            expected_missing = {
                "preflop_policy_head.weight",
                "preflop_policy_head.bias",
            }
            if set(missing) != expected_missing or unexpected:
                raise RuntimeError(
                    f"preflop-head migration mismatch: "
                    f"missing={missing} unexpected={unexpected}"
                )
            with torch.no_grad():
                model.preflop_policy_head.weight.copy_(model.policy_head.weight)
                model.preflop_policy_head.bias.copy_(model.policy_head.bias)
        for name, parameter in model.named_parameters():
            parameter.requires_grad_(
                name.startswith("preflop_policy_head.")
            )
    else:
        model.load_state_dict(state)
    source.load_state_dict(state)
    source.eval()
    for parameter in source.parameters():
        parameter.requires_grad_(False)
    trainable_parameters = [
        parameter for parameter in model.parameters() if parameter.requires_grad
    ]
    optimizer = torch.optim.AdamW(
        trainable_parameters, lr=args.lr, weight_decay=args.weight_decay
    )

    baseline = evaluate(source, val_loader, device)
    history: list[dict[str, Any]] = []
    best_objective = math.inf
    best_record: dict[str, Any] | None = None
    best_path = output / "best.pt"
    for epoch in range(args.epochs):
        model.train()
        losses = []
        ce_losses = []
        kl_losses = []
        for batch in train_loader:
            cards, actions, extras, legal, selected, weight, position, _ = [
                value.to(device, non_blocking=True) for value in batch
            ]
            logits, _ = model(
                cards,
                actions,
                model_extras(model, extras, position),
                legal,
            )
            with torch.no_grad():
                source_logits, _ = source(
                    cards,
                    actions,
                    model_extras(source, extras, position),
                    legal,
                )
                source_probs = F.softmax(source_logits, dim=-1)
            row_ce = F.cross_entropy(logits, selected, reduction="none")
            awr_ce = (row_ce * weight).sum() / weight.sum().clamp_min(1e-6)
            kl = (
                source_probs
                * (F.log_softmax(source_logits, dim=-1) - F.log_softmax(logits, dim=-1))
            ).sum(dim=-1).mean()
            loss = awr_ce + args.kl_coef * kl
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable_parameters, 1.0)
            optimizer.step()
            losses.append(float(loss.detach()))
            ce_losses.append(float(awr_ce.detach()))
            kl_losses.append(float(kl.detach()))

        metrics = evaluate(model, val_loader, device, source=source)
        validation_objective = (
            float(metrics["weighted_nll"])
            + args.kl_coef * float(metrics["source_kl"])
        )
        record = {
            "epoch": epoch + 1,
            "loss": float(np.mean(losses)),
            "awr_ce": float(np.mean(ce_losses)),
            "training_source_kl": float(np.mean(kl_losses)),
            "validation_objective": validation_objective,
            **metrics,
        }
        history.append(record)
        payload = dict(checkpoint)
        payload.update({
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "env_version": checkpoint.get("env_version", "v55"),
            "obs_version": args.obs_version,
            "action_space_version": checkpoint.get(
                "action_space_version", "9slot_v5"
            ),
            "starting_stack_bb": 200.0,
            "norm_layer": norm_layer,
            "critic_contract": critic_contract,
            "critic_init_seed": critic_init_seed,
            "version": (
                "offline.slumbot.imitation.v1"
                if args.actor == "opp" and args.return_clip_bb == 0.0
                else "offline.slumbot.awr.v2"
            ),
            "source_checkpoint": str(source_path),
            "source_checkpoint_sha256": sha256_path(source_path),
            "epoch": epoch + 1,
            "config": {
                **dict(checkpoint.get("config") or {}),
                "offline_awr": vars(args),
            },
            "ingest": ingest,
            "weight_report": weight_report,
            "history": history,
            "separate_preflop_head": bool(
                source_separate_preflop_head
                or args.separate_preflop_head_only
            ),
            "position_adapter_hidden": model_position_adapter_hidden,
        })
        atomic_torch_save(payload, output / f"epoch_{epoch + 1}.pt")
        if validation_objective < best_objective:
            best_objective = validation_objective
            best_record = dict(record)
            atomic_torch_save(payload, best_path)
        print(json.dumps(record, sort_keys=True), flush=True)

    report = {
        "status": "finished",
        "runtime_seconds": time.time() - started,
        "selected_file_count": len(files),
        "selected_files": [str(path) for path in files],
        "raise_action_mapping": raise_action_mapping,
        "ingest": ingest,
        "weight_report": weight_report,
        "train_rows": len(train_rows),
        "val_rows": len(val_rows),
        "baseline": baseline,
        "history": history,
        "best_selection_metric": "validation_weighted_nll_plus_kl",
        "best_selection_value": best_objective,
        "best_epoch": int(best_record["epoch"]),
        "best_behavior_accuracy": float(
            best_record["behavior_accuracy"]
        ),
        "best_checkpoint": str(best_path.resolve()),
        "best_checkpoint_sha256": sha256_path(best_path),
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
