"""Directly distill the corrected 200bb preflop ranges into a frozen trunk."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpha_holdem.network import AlphaHoldemNet
from heuristic_policy_v3 import _hand_notation
from heuristic_policy_v4 import PREFLOP_PERCENTILE
from play_slumbot import (
    STACK_SIZE,
    build_action_table,
    compute_commitments,
    encode_action_history,
    encode_cards,
    encode_extra,
    parse_action,
)


RANKS = "23456789TJQKA"
SUITS = "cdhs"
CARDS = [rank + suit for rank in RANKS for suit in SUITS]
COMBOS = list(itertools.combinations(CARDS, 2))


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile_target_for(context: str, hole: tuple[str, str]) -> int:
    percentile = float(PREFLOP_PERCENTILE[_hand_notation(list(hole))])
    if context == "sb_open":
        return 5 if percentile < 0.65 else (1 if percentile < 0.935 else 0)
    if context == "bb_vs_open":
        return 7 if percentile < 0.19 else (1 if percentile < 0.72 else 0)
    if context == "bb_vs_limp":
        return 7 if percentile < 0.32 else 1
    if context in {"sb_vs_3bet", "sb_vs_limp_raise"}:
        return 7 if percentile < 0.08 else (1 if percentile < 0.45 else 0)
    if context == "bb_vs_4bet":
        return 7 if percentile < 0.03 else (1 if percentile < 0.13 else 0)
    if context in {"bb_vs_jam", "sb_vs_jam"}:
        return 1 if percentile < 0.025 else 0
    raise ValueError(context)


def load_bb_vs_sb_chart(path: Path) -> dict[str, dict[str, float]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, float]] = {}
    for row in rows:
        if (
            row.get("format") == "cash_6max_100bb"
            and row.get("spot") == "BB_vs_SB_facing_open"
        ):
            mix = row.get("mix") or {}
            result[str(row["hand"])] = {
                action: float(mix.get(action, 0.0))
                for action in ("fold", "call", "raise")
            }
    if len(result) != 169:
        raise ValueError(
            f"expected 169 BB-vs-SB chart rows in {path}, found {len(result)}"
        )
    return result


def target_distribution(
    context: str,
    hole: tuple[str, str],
    teacher: str,
    bb_vs_sb_chart: dict[str, dict[str, float]] | None,
) -> np.ndarray:
    target = np.zeros(9, dtype=np.float32)
    if teacher in {
        "hu_proxy_defense_v1",
        "hu_proxy_bb_only_v1",
    } and context == "bb_vs_open":
        if bb_vs_sb_chart is None:
            raise ValueError("BB-vs-SB chart was not loaded")
        mix = bb_vs_sb_chart[_hand_notation(list(hole))]
        target[0] = mix["fold"]
        target[1] = mix["call"]
        target[7] = mix["raise"]
        total = float(target.sum())
        if total <= 0.0:
            raise ValueError(f"empty chart mix for {hole}")
        target /= total
        return target
    target[percentile_target_for(context, hole)] = 1.0
    return target


CONTEXTS = (
    ("sb_open", "", 1),
    ("bb_vs_open", "b200", 0),
    ("bb_vs_limp", "c", 0),
    ("sb_vs_3bet", "b250b750", 1),
    ("sb_vs_limp_raise", "cb300", 1),
    ("bb_vs_4bet", "b200b800b2400", 0),
    ("bb_vs_jam", "b200b800b2400b9600b20000", 0),
    ("sb_vs_jam", "b250b750b3000b20000", 1),
)


def encoded_context(
    action_string: str,
    position: int,
    obs_version: str,
):
    state = parse_action(action_string)
    if "error" in state:
        raise ValueError(state["error"])
    mask, _ = build_action_table(state, "preflop_pot_fraction_v2")
    commitments = compute_commitments(state)
    stacks = [
        STACK_SIZE - commitments["hero_total"],
        STACK_SIZE - commitments["opp_total"],
    ]
    action = encode_action_history(
        state,
        position,
        state["pos"],
        obs_version=obs_version,
    )
    extra = encode_extra(stacks)
    return state, mask.astype(np.float32), action, extra


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--epochs", type=int, default=2000)
    parser.add_argument("--lr", type=float, default=0.003)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--adapter-hidden", type=int, default=0)
    parser.add_argument("--raw-adapter-hidden", type=int, default=256)
    parser.add_argument("--raw-action-scale", type=float, default=1.0)
    parser.add_argument(
        "--raw-gate",
        choices=("none", "v4_bb_vs_open_v1"),
        default="none",
    )
    parser.add_argument("--bb-weight", type=float, default=1.0)
    parser.add_argument(
        "--teacher",
        choices=(
            "percentile_v1",
            "hu_proxy_defense_v1",
            "hu_proxy_bb_only_v1",
        ),
        default="percentile_v1",
    )
    parser.add_argument(
        "--preflop-charts",
        default="data/preflop_charts.json",
        help=(
            "Local approximate range data. hu_proxy_defense_v1 uses only the "
            "BB_vs_SB_facing_open mix and percentile_v1 elsewhere. "
            "hu_proxy_bb_only_v1 preserves the source policy elsewhere."
        ),
    )
    parser.add_argument("--seed", type=int, default=2026072597)
    args = parser.parse_args()
    if args.bb_weight <= 0.0:
        raise ValueError("--bb-weight must be positive")
    if args.raw_action_scale <= 0.0:
        raise ValueError("--raw-action-scale must be positive")

    torch.manual_seed(args.seed)
    np.random.seed(args.seed % (2**32))
    source = Path(args.source).resolve()
    output = Path(args.out).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(output)
    charts_path = Path(args.preflop_charts).resolve()
    bb_vs_sb_chart = (
        load_bb_vs_sb_chart(charts_path)
        if args.teacher in {"hu_proxy_defense_v1", "hu_proxy_bb_only_v1"}
        else None
    )

    checkpoint = torch.load(source, map_location="cpu", weights_only=False)
    model_state = checkpoint["model"]
    source_has_preflop_head = "preflop_policy_head.weight" in model_state
    inherited_adapter_hidden = (
        int(model_state["preflop_policy_adapter.0.weight"].shape[0])
        if "preflop_policy_adapter.0.weight" in model_state
        else 0
    )
    if inherited_adapter_hidden and inherited_adapter_hidden != args.adapter_hidden:
        raise ValueError(
            "source preflop adapter width differs from --adapter-hidden: "
            f"{inherited_adapter_hidden} != {args.adapter_hidden}"
        )
    inherited_raw_adapter_hidden = (
        int(model_state["preflop_raw_policy_adapter.0.weight"].shape[0])
        if "preflop_raw_policy_adapter.0.weight" in model_state
        else 0
    )
    if (
        inherited_raw_adapter_hidden
        and inherited_raw_adapter_hidden != args.raw_adapter_hidden
    ):
        raise ValueError(
            "source raw preflop adapter width differs from "
            f"--raw-adapter-hidden: {inherited_raw_adapter_hidden} != "
            f"{args.raw_adapter_hidden}"
        )
    obs_version = str(checkpoint.get("obs_version") or "v4").lower()
    if obs_version not in {"v4", "v55"}:
        raise ValueError(f"unsupported source obs_version: {obs_version}")
    if args.raw_gate == "v4_bb_vs_open_v1" and obs_version != "v4":
        raise ValueError("v4_bb_vs_open_v1 requires a v4 source observation")
    model = AlphaHoldemNet(
        num_actions=9,
        norm_layer=str(checkpoint.get("norm_layer", "bn")),
        separate_preflop_head=True,
        preflop_adapter_hidden=args.adapter_hidden,
        preflop_raw_adapter_hidden=args.raw_adapter_hidden,
        preflop_raw_action_scale=args.raw_action_scale,
        preflop_raw_gate=args.raw_gate,
    ).to(args.device)
    model(
        torch.zeros(2, 6, 4, 13, device=args.device),
        torch.zeros(2, 25, 4, 5, device=args.device),
        torch.zeros(2, 2, device=args.device),
    )
    missing, unexpected = model.load_state_dict(model_state, strict=False)
    allowed_missing = {
        "preflop_policy_head.weight",
        "preflop_policy_head.bias",
        "preflop_policy_adapter.0.weight",
        "preflop_policy_adapter.0.bias",
        "preflop_policy_adapter.2.weight",
        "preflop_policy_adapter.2.bias",
        "preflop_raw_policy_adapter.0.weight",
        "preflop_raw_policy_adapter.0.bias",
        "preflop_raw_policy_adapter.2.weight",
        "preflop_raw_policy_adapter.2.bias",
        "preflop_raw_policy_adapter.4.weight",
        "preflop_raw_policy_adapter.4.bias",
    }
    if set(missing) - allowed_missing or unexpected:
        raise ValueError(
            f"source state mismatch: missing={missing}, unexpected={unexpected}"
        )
    if not source_has_preflop_head:
        with torch.no_grad():
            model.preflop_policy_head.weight.copy_(model.policy_head.weight)
            model.preflop_policy_head.bias.copy_(model.policy_head.bias)
    if not inherited_raw_adapter_hidden:
        with torch.no_grad():
            for parameter in model.preflop_raw_policy_adapter.parameters():
                parameter.zero_()
    model.eval()

    feature_parts = []
    base_logit_parts = []
    mask_parts = []
    target_parts = []
    context_parts = []
    with torch.no_grad():
        for context_index, (name, action_string, position) in enumerate(CONTEXTS):
            _, mask, action, extra = encoded_context(
                action_string,
                position,
                obs_version,
            )
            for start in range(0, len(COMBOS), 256):
                holes = COMBOS[start : start + 256]
                cards = torch.as_tensor(
                    np.stack(
                        [
                            encode_cards(list(hole), [], 0)
                            for hole in holes
                        ]
                    ),
                    device=args.device,
                )
                actions = torch.as_tensor(
                    np.repeat(action[None], len(holes), axis=0),
                    device=args.device,
                )
                extras = torch.as_tensor(
                    np.repeat(extra[None], len(holes), axis=0),
                    device=args.device,
                )
                card_flat = model.card_cnn(cards)
                action_flat = model.action_cnn(actions)
                extra_flat = model.extra_fc(extras)
                hidden = model.trunk(
                    torch.cat(
                        [card_flat, action_flat, extra_flat],
                        dim=1,
                    )
                )
                raw_features = torch.cat(
                    [
                        cards.flatten(start_dim=1),
                        actions.flatten(start_dim=1) * args.raw_action_scale,
                        extras,
                    ],
                    dim=1,
                )
                base_logits = model.preflop_policy_head(hidden)
                if model.preflop_policy_adapter is not None:
                    base_logits = (
                        base_logits + model.preflop_policy_adapter(hidden)
                    )
                feature_parts.append(raw_features.detach().cpu())
                base_logit_parts.append(base_logits.detach().cpu())
                mask_parts.append(
                    torch.as_tensor(
                        np.repeat(mask[None], len(holes), axis=0)
                    )
                )
                target_parts.append(
                    torch.as_tensor(
                        np.stack(
                            [
                                target_distribution(
                                    name,
                                    hole,
                                    args.teacher,
                                    bb_vs_sb_chart,
                                )
                                for hole in holes
                            ]
                        )
                    )
                )
                context_parts.append(
                    torch.full(
                        (len(holes),),
                        context_index,
                        dtype=torch.long,
                    )
                )

    features = torch.cat(feature_parts).to(args.device)
    base_logits = torch.cat(base_logit_parts).to(args.device)
    masks = torch.cat(mask_parts).to(args.device)
    targets = torch.cat(target_parts).to(args.device)
    context_ids = torch.cat(context_parts).to(args.device)
    adapter = model.preflop_raw_policy_adapter
    bb_vs_open_index = next(
        index
        for index, (name, _, _) in enumerate(CONTEXTS)
        if name == "bb_vs_open"
    )
    if args.teacher == "hu_proxy_bb_only_v1":
        with torch.no_grad():
            source_logits = (
                base_logits
                + adapter(features)
                + (1.0 - masks) * -1e9
            )
            source_targets = F.softmax(source_logits, dim=-1)
            preserve = context_ids != bb_vs_open_index
            targets[preserve] = source_targets[preserve]
    labels = targets.argmax(dim=-1)
    optimizer = torch.optim.AdamW(
        adapter.parameters(),
        lr=args.lr,
        weight_decay=1e-5,
    )
    generator = torch.Generator(device="cpu").manual_seed(args.seed)
    best_accuracy = -1.0
    best_selection_score = float("-inf")
    best_state = None

    for epoch in range(1, args.epochs + 1):
        order = torch.randperm(len(features), generator=generator).to(args.device)
        for start in range(0, len(order), args.batch_size):
            indices = order[start : start + args.batch_size]
            adapter_delta = adapter(features[indices])
            if args.raw_gate == "v4_bb_vs_open_v1":
                adapter_delta = adapter_delta * (
                    context_ids[indices] == bb_vs_open_index
                ).to(adapter_delta.dtype).unsqueeze(-1)
            logits = base_logits[indices] + adapter_delta
            logits = logits + (1.0 - masks[indices]) * -1e9
            per_row_loss = -(
                targets[indices] * F.log_softmax(logits, dim=-1)
            ).sum(dim=-1)
            row_weights = torch.ones_like(per_row_loss)
            row_weights[
                context_ids[indices] == bb_vs_open_index
            ] = args.bb_weight
            loss = (per_row_loss * row_weights).sum() / row_weights.sum()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        with torch.no_grad():
            adapter_delta = adapter(features)
            if args.raw_gate == "v4_bb_vs_open_v1":
                adapter_delta = adapter_delta * (
                    context_ids == bb_vs_open_index
                ).to(adapter_delta.dtype).unsqueeze(-1)
            logits = base_logits + adapter_delta + (1.0 - masks) * -1e9
            predictions = logits.argmax(dim=-1)
            accuracy = float((predictions == labels).float().mean().item())
            context_accuracy = {
                CONTEXTS[index][0]: float(
                    (
                        predictions[context_ids == index]
                        == labels[context_ids == index]
                    )
                    .float()
                    .mean()
                    .item()
                )
                for index in range(len(CONTEXTS))
            }
        if args.teacher == "hu_proxy_bb_only_v1":
            preserve_min_accuracy = min(
                value
                for name, value in context_accuracy.items()
                if name != "bb_vs_open"
            )
            selection_score = (
                context_accuracy["bb_vs_open"]
                + 2.0 * preserve_min_accuracy
            )
        else:
            preserve_min_accuracy = None
            selection_score = accuracy
        if selection_score > best_selection_score:
            best_accuracy = accuracy
            best_selection_score = selection_score
            best_state = {
                name: value.detach().cpu().clone()
                for name, value in model.state_dict().items()
                if name.startswith("preflop_raw_policy_adapter.")
            }
        if epoch == 1 or epoch % 50 == 0 or accuracy >= 0.995:
            print(
                json.dumps(
                    {
                        "epoch": epoch,
                        "loss": float(loss.item()),
                        "accuracy": accuracy,
                        "context_accuracy": context_accuracy,
                        "preserve_min_accuracy": preserve_min_accuracy,
                        "selection_score": selection_score,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        if accuracy >= 0.995 and min(context_accuracy.values()) >= 0.99:
            break

    if best_state is None:
        raise RuntimeError("no head state produced")
    model.load_state_dict(best_state, strict=False)
    checkpoint["model"] = {
        key: value.detach().cpu()
        for key, value in model.state_dict().items()
    }
    checkpoint["run_id"] = (
        f"{checkpoint.get('run_id', source.stem)}_preflopv2_distilled"
    )
    checkpoint["raise_action_mapping"] = "preflop_pot_fraction_v2"
    checkpoint["action_space_version"] = "9slot_preflop_pot_fraction_v2"
    checkpoint["preflop_adapter_hidden"] = int(args.adapter_hidden)
    checkpoint["preflop_raw_adapter_hidden"] = int(
        args.raw_adapter_hidden
    )
    checkpoint["preflop_raw_action_scale"] = float(args.raw_action_scale)
    checkpoint["preflop_raw_gate"] = args.raw_gate
    checkpoint["env_version"] = (
        "v55preflopv2"
        if obs_version == "v55"
        else "v55preflopv2v4obs"
    )
    checkpoint["obs_version"] = obs_version
    checkpoint["preflop_distillation"] = {
        "source_checkpoint": str(source),
        "source_sha256": sha256_path(source),
        "examples": int(len(features)),
        "best_accuracy": best_accuracy,
        "best_selection_score": best_selection_score,
        "contexts": [name for name, _, _ in CONTEXTS],
        "source_had_separate_preflop_head": source_has_preflop_head,
        "adapter_hidden": int(args.adapter_hidden),
        "raw_adapter_hidden": int(args.raw_adapter_hidden),
        "raw_action_scale": float(args.raw_action_scale),
        "raw_gate": args.raw_gate,
        "obs_version": obs_version,
        "raise_action_mapping": "preflop_pot_fraction_v2",
        "teacher": args.teacher,
        "bb_weight": float(args.bb_weight),
        "preflop_charts": (
            str(charts_path)
            if args.teacher in {"hu_proxy_defense_v1", "hu_proxy_bb_only_v1"}
            else None
        ),
        "preflop_charts_sha256": (
            sha256_path(charts_path)
            if args.teacher in {"hu_proxy_defense_v1", "hu_proxy_bb_only_v1"}
            else None
        ),
        "seed": args.seed,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    checkpoint["config"] = {
        **dict(checkpoint.get("config") or {}),
        "separate_preflop_head": True,
        "preflop_adapter_hidden": int(args.adapter_hidden),
        "preflop_raw_adapter_hidden": int(args.raw_adapter_hidden),
        "preflop_raw_action_scale": float(args.raw_action_scale),
        "preflop_raw_gate": args.raw_gate,
    }
    temporary = output.with_suffix(output.suffix + ".tmp")
    torch.save(checkpoint, temporary)
    temporary.replace(output)
    print(
        json.dumps(
            {
                "output": str(output),
                "output_sha256": sha256_path(output),
                "best_accuracy": best_accuracy,
                "best_selection_score": best_selection_score,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
