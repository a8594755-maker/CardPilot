#!/usr/bin/env python3
"""Lightweight fixed-opponent strength probe for AlphaHoldem V5 checkpoints.

This is deliberately an internal trend probe, not a Slumbot benchmark and not
an L5/L6 promotion gate. It evaluates the latest checkpoint and the latest-K
pool snapshots against simple fixed opponents in the same V5.5 environment used
by training, then reports bb/100 with a rough 95% confidence interval.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
import torch.nn.functional as F

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from alpha_holdem.environment_v55 import HUNLEnvironment, NUM_ACTIONS
from alpha_holdem.network import AlphaHoldemNet


OpponentPolicy = Callable[[dict[str, Any], random.Random], int]


def legal_slots(obs: dict[str, Any]) -> list[int]:
    mask = np.asarray(obs["legal_mask"], dtype=np.float32)
    return [int(i) for i in np.where(mask > 0)[0]]


def pick_first_legal(obs: dict[str, Any], preferred: list[int]) -> int:
    legal = set(legal_slots(obs))
    for slot in preferred:
        if slot in legal:
            return int(slot)
    return min(legal) if legal else 0


def random_policy(obs: dict[str, Any], rng: random.Random) -> int:
    legal = legal_slots(obs)
    return int(rng.choice(legal)) if legal else 0


def call_station_policy(obs: dict[str, Any], rng: random.Random) -> int:
    return pick_first_legal(obs, [1, 0])


def aggressive_policy(obs: dict[str, Any], rng: random.Random) -> int:
    return pick_first_legal(obs, [8, 7, 6, 5, 4, 3, 2, 1, 0])


OPPONENTS: dict[str, OpponentPolicy] = {
    "random": random_policy,
    "call-station": call_station_policy,
    "aggressive": aggressive_policy,
}


def load_checkpoint(path: Path) -> dict[str, Any]:
    obj = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(obj, dict):
        raise TypeError(f"checkpoint is {type(obj).__name__}, not dict")
    return obj


def init_model(
    state_dict: dict[str, torch.Tensor],
    norm_layer: str,
    device: str,
    preflop_raw_action_scale: float = 1.0,
    preflop_raw_gate: str = "none",
    critic_contract: str = "critic_v1",
) -> AlphaHoldemNet:
    separate_preflop_head = (
        "preflop_policy_head.weight" in state_dict
        and "preflop_policy_head.bias" in state_dict
    )
    preflop_adapter_hidden = (
        int(state_dict["preflop_policy_adapter.0.weight"].shape[0])
        if "preflop_policy_adapter.0.weight" in state_dict
        else 0
    )
    preflop_raw_adapter_hidden = (
        int(state_dict["preflop_raw_policy_adapter.0.weight"].shape[0])
        if "preflop_raw_policy_adapter.0.weight" in state_dict
        else 0
    )
    flop_adapter_hidden = (
        int(state_dict["flop_policy_adapter.0.weight"].shape[0])
        if "flop_policy_adapter.0.weight" in state_dict
        else 0
    )
    postflop_adapter_hidden = (
        int(state_dict["postflop_policy_adapter.0.weight"].shape[0])
        if "postflop_policy_adapter.0.weight" in state_dict
        else 0
    )
    model = AlphaHoldemNet(
        num_actions=NUM_ACTIONS,
        norm_layer=norm_layer,
        separate_preflop_head=separate_preflop_head,
        preflop_adapter_hidden=preflop_adapter_hidden,
        preflop_raw_adapter_hidden=preflop_raw_adapter_hidden,
        preflop_raw_action_scale=preflop_raw_action_scale,
        preflop_raw_gate=preflop_raw_gate,
        flop_adapter_hidden=flop_adapter_hidden,
        postflop_adapter_hidden=postflop_adapter_hidden,
        critic_contract=critic_contract,
    ).to(device)
    # Lazy-init trunk before loading the full state dict.
    with torch.no_grad():
        model(
            torch.zeros(2, 6, 4, 13, device=device),
            torch.zeros(2, 25, 4, 5, device=device),
            torch.zeros(2, 2, device=device),
        )
    model.load_state_dict(state_dict)
    model.eval()
    for param in model.parameters():
        param.requires_grad_(False)
    return model


@torch.no_grad()
def model_action(
    model: AlphaHoldemNet,
    obs: dict[str, Any],
    device: str,
    *,
    policy_mode: str = "greedy",
    temperature: float = 1.0,
) -> int:
    card_t = torch.as_tensor(obs["card_info"], dtype=torch.float32, device=device).unsqueeze(0)
    action_t = torch.as_tensor(obs["action_info"], dtype=torch.float32, device=device).unsqueeze(0)
    extra_t = torch.as_tensor(obs["extra_info"], dtype=torch.float32, device=device).unsqueeze(0)
    mask_t = torch.as_tensor(obs["legal_mask"], dtype=torch.float32, device=device).unsqueeze(0)
    logits, _ = model(card_t, action_t, extra_t, mask_t)
    if policy_mode == "sample":
        logits = logits / max(float(temperature), 1e-6)
    probs = F.softmax(logits, dim=-1)
    if policy_mode == "sample":
        slot = int(torch.distributions.Categorical(probs).sample().item())
    else:
        slot = int(torch.argmax(probs, dim=-1).item())
    if obs["legal_mask"][slot] > 0:
        return slot

    # Defensive fallback if an unexpected numerical issue bypasses masking.
    legal = legal_slots(obs)
    if not legal:
        return 0
    legal_logits = logits[0, legal]
    return int(legal[int(torch.argmax(legal_logits).item())])


def evaluate_match(
    model: AlphaHoldemNet,
    opponent: OpponentPolicy,
    hands: int,
    *,
    seed: int,
    device: str,
    starting_stack: float,
    policy_mode: str,
    temperature: float,
    action_history_style: str,
    raise_action_mapping: str,
) -> dict[str, Any]:
    random.seed(seed)
    np.random.seed(seed % (2**32 - 1))
    torch.manual_seed(seed)
    rng = random.Random(seed + 17)
    env = HUNLEnvironment(
        starting_stack=starting_stack,
        action_history_style=action_history_style,
        raise_action_mapping=raise_action_mapping,
    )

    hand_rewards: list[float] = []
    wins = losses = draws = 0
    model_action_counts = {str(slot): 0 for slot in range(NUM_ACTIONS)}
    model_decisions = 0
    started = time.time()

    for hand_idx in range(hands):
        obs = env.reset()
        done = False
        hero_player = hand_idx % 2
        hand_reward = 0.0

        while not done:
            actor = int(obs["player"])
            is_hero = actor == hero_player
            if is_hero:
                action_idx = model_action(
                    model,
                    obs,
                    device,
                    policy_mode=policy_mode,
                    temperature=temperature,
                )
                model_action_counts[str(action_idx)] += 1
                model_decisions += 1
            else:
                action_idx = opponent(obs, rng)

            obs, reward, done = env.step(action_idx)
            if done:
                hand_reward = float(reward if is_hero else -reward)

        hand_rewards.append(hand_reward)
        if hand_reward > 0.01:
            wins += 1
        elif hand_reward < -0.01:
            losses += 1
        else:
            draws += 1

    elapsed = time.time() - started
    arr = np.asarray(hand_rewards, dtype=np.float64)
    avg_bb = float(arr.mean()) if len(arr) else 0.0
    std_bb = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    ci95_bb100 = 1.96 * std_bb / math.sqrt(max(len(arr), 1)) * 100.0
    bb100 = avg_bb * 100.0

    action_mix = {}
    denom = max(model_decisions, 1)
    for slot, count in model_action_counts.items():
        action_mix[slot] = count / denom

    return {
        "hands": hands,
        "bb100": bb100,
        "ci95_bb100": ci95_bb100,
        "avg_bb_per_hand": avg_bb,
        "std_bb_per_hand": std_bb,
        "total_bb": float(arr.sum()) if len(arr) else 0.0,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "model_decisions": model_decisions,
        "model_action_mix": action_mix,
        "elapsed_seconds": elapsed,
        "hands_per_second": hands / max(elapsed, 1e-9),
    }


def candidate_entries(checkpoint: dict[str, Any], max_pool_snapshots: int, include_latest: bool) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    pool = checkpoint.get("pool_snapshots") or []
    if isinstance(pool, list) and max_pool_snapshots > 0:
        for snap in pool[-max_pool_snapshots:]:
            if not isinstance(snap, dict) or "state_dict" not in snap:
                continue
            hands = int(snap.get("hands") or 0)
            snap_id = snap.get("id", len(entries))
            entries.append(
                {
                    "label": f"pool_id{snap_id}_{hands // 1_000_000}M",
                    "kind": "pool_snapshot",
                    "id": snap_id,
                    "iteration": None,
                    "hands": hands,
                    "state_dict": snap["state_dict"],
                }
            )

    latest_hands = int(checkpoint.get("total_hands") or 0)
    if include_latest and "model" in checkpoint:
        entries.append(
            {
                "label": f"latest_iter{checkpoint.get('iteration', 'na')}_{latest_hands // 1_000_000}M",
                "kind": "checkpoint_latest",
                "id": None,
                "iteration": checkpoint.get("iteration"),
                "hands": latest_hands,
                "state_dict": checkpoint["model"],
            }
        )
    return entries


def summarize_trends(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_opp: dict[str, list[dict[str, Any]]] = {}
    for row in results:
        by_opp.setdefault(row["opponent"], []).append(row)

    trends: dict[str, Any] = {}
    for opponent, rows in by_opp.items():
        ordered = sorted(rows, key=lambda r: (int(r.get("candidate_hands") or 0), str(r["candidate"])))
        scores = [float(row["bb100"]) for row in ordered]
        deltas = [scores[i] - scores[i - 1] for i in range(1, len(scores))]
        trends[opponent] = {
            "ordered_candidates": [row["candidate"] for row in ordered],
            "bb100": scores,
            "adjacent_deltas": deltas,
            "strictly_increasing": bool(deltas) and all(delta > 0 for delta in deltas),
            "latest_is_best": bool(scores) and scores[-1] >= max(scores),
            "positive_adjacent_steps": sum(1 for delta in deltas if delta > 0),
            "total_adjacent_steps": len(deltas),
        }
    return trends


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# V5 Internal Strength Probe",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Checkpoint: `{summary['checkpoint_path']}`",
        f"- Checkpoint iteration: `{summary['checkpoint']['iteration']}`",
        f"- Checkpoint hands: `{summary['checkpoint']['total_hands']:,}`",
        f"- Hands per match: `{summary['hands_per_match']}`",
        f"- Policy mode: `{summary.get('policy_mode', 'greedy')}`",
        f"- Temperature: `{summary.get('temperature', 1.0)}`",
        f"- Device: `{summary['device']}`",
        "",
        "This is an internal fixed-opponent trend probe only. It is not a Slumbot benchmark, not a promotion gate, and not an L5/L6 claim.",
        "",
        "## Results",
        "",
        "| candidate | train hands | opponent | bb/100 | 95% CI | W/L/D | h/s |",
        "|---|---:|---|---:|---:|---|---:|",
    ]
    for row in sorted(summary["results"], key=lambda r: (r["candidate_hands"], r["opponent"])):
        lines.append(
            "| {candidate} | {hands:,} | {opponent} | {bb100:+.2f} | +/-{ci:.2f} | {w}/{l}/{d} | {hps:.1f} |".format(
                candidate=row["candidate"],
                hands=int(row["candidate_hands"]),
                opponent=row["opponent"],
                bb100=float(row["bb100"]),
                ci=float(row["ci95_bb100"]),
                w=int(row["wins"]),
                l=int(row["losses"]),
                d=int(row["draws"]),
                hps=float(row["hands_per_second"]),
            )
        )

    lines.extend(["", "## Trend Flags", ""])
    for opponent, trend in summary["trends"].items():
        lines.append(f"- `{opponent}`: latest_is_best=`{trend['latest_is_best']}`, strictly_increasing=`{trend['strictly_increasing']}`, positive_steps=`{trend['positive_adjacent_steps']}/{trend['total_adjacent_steps']}`")

    lines.extend(["", "## Interpretation", ""])
    for note in summary["notes"]:
        lines.append(f"- {note}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    checkpoint_path = Path(args.checkpoint)
    checkpoint = load_checkpoint(checkpoint_path)
    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"

    norm_layer = str(checkpoint.get("norm_layer", "bn"))
    obs_version = str(checkpoint.get("obs_version") or "v55").lower()
    action_history_style = "v4" if obs_version == "v4" else "v55"
    raise_action_mapping = str(
        checkpoint.get("raise_action_mapping")
        or (
            "preflop_pot_fraction_v2"
            if checkpoint.get("action_space_version")
            == "9slot_preflop_pot_fraction_v2"
            else "legacy_total_over_pot"
        )
    )
    candidates = candidate_entries(
        checkpoint,
        max_pool_snapshots=args.max_pool_snapshots,
        include_latest=not args.no_latest,
    )
    if not candidates:
        raise RuntimeError("no candidate state_dicts found in checkpoint or pool_snapshots")

    selected_opponents = list(args.opponents or list(OPPONENTS))
    opponent_policies: dict[str, OpponentPolicy] = dict(OPPONENTS)
    checkpoint_opponent_model: AlphaHoldemNet | None = None
    checkpoint_opponent_path: Path | None = None
    if args.checkpoint_opponent:
        checkpoint_opponent_path = Path(args.checkpoint_opponent)
        opponent_checkpoint = load_checkpoint(checkpoint_opponent_path)
        opponent_state = opponent_checkpoint.get("model")
        if not isinstance(opponent_state, dict):
            raise RuntimeError(
                f"checkpoint opponent has no model state_dict: "
                f"{checkpoint_opponent_path}"
            )
        opponent_obs_version = str(
            opponent_checkpoint.get("obs_version") or "v55"
        ).lower()
        opponent_action_history_style = (
            "v4" if opponent_obs_version == "v4" else "v55"
        )
        opponent_raise_action_mapping = str(
            opponent_checkpoint.get("raise_action_mapping")
            or (
                "preflop_pot_fraction_v2"
                if opponent_checkpoint.get("action_space_version")
                == "9slot_preflop_pot_fraction_v2"
                else "legacy_total_over_pot"
            )
        )
        if opponent_action_history_style != action_history_style:
            raise RuntimeError(
                "candidate and checkpoint opponent use different observation "
                f"styles: {action_history_style} vs "
                f"{opponent_action_history_style}"
            )
        if opponent_raise_action_mapping != raise_action_mapping:
            raise RuntimeError(
                "candidate and checkpoint opponent use different action "
                f"mappings: {raise_action_mapping} vs "
                f"{opponent_raise_action_mapping}"
            )
        opponent_norm_layer = (
            "bn"
            if any(key.endswith("running_mean") for key in opponent_state)
            else str(opponent_checkpoint.get("norm_layer", "bn"))
        )
        checkpoint_opponent_model = init_model(
            opponent_state,
            norm_layer=opponent_norm_layer,
            device=device,
            critic_contract=str(
                opponent_checkpoint.get("critic_contract")
                or (opponent_checkpoint.get("config") or {}).get(
                    "critic_contract"
                )
                or "critic_v1"
            ),
            preflop_raw_action_scale=float(
                opponent_checkpoint.get("preflop_raw_action_scale")
                or (opponent_checkpoint.get("config") or {}).get(
                    "preflop_raw_action_scale"
                )
                or 1.0
            ),
            preflop_raw_gate=str(
                opponent_checkpoint.get("preflop_raw_gate")
                or (opponent_checkpoint.get("config") or {}).get(
                    "preflop_raw_gate"
                )
                or "none"
            ),
        )
        checkpoint_opponent_label = (
            f"checkpoint:{checkpoint_opponent_path.stem}"
        )

        def checkpoint_opponent_policy(
            obs: dict[str, Any],
            rng: random.Random,
        ) -> int:
            del rng
            assert checkpoint_opponent_model is not None
            return model_action(
                checkpoint_opponent_model,
                obs,
                device,
                policy_mode=args.checkpoint_opponent_policy_mode,
                temperature=args.checkpoint_opponent_temperature,
            )

        opponent_policies[checkpoint_opponent_label] = (
            checkpoint_opponent_policy
        )
        if args.checkpoint_opponent_only:
            selected_opponents = [checkpoint_opponent_label]
        else:
            selected_opponents.append(checkpoint_opponent_label)
    results: list[dict[str, Any]] = []

    for cand_index, cand in enumerate(candidates):
        candidate_norm_layer = (
            "bn"
            if any(
                key.endswith("running_mean")
                for key in cand["state_dict"]
            )
            else norm_layer
        )
        model = init_model(
            cand["state_dict"],
            norm_layer=candidate_norm_layer,
            device=device,
            critic_contract=str(
                checkpoint.get("critic_contract")
                or (checkpoint.get("config") or {}).get("critic_contract")
                or "critic_v1"
            ),
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
        )
        for opp_index, opponent_name in enumerate(selected_opponents):
            if opponent_name not in opponent_policies:
                raise ValueError(
                    f"unknown opponent {opponent_name!r}; choices: "
                    f"{sorted(opponent_policies)}"
                )
            seed = int(args.seed) + opp_index * 10_000
            stats = evaluate_match(
                model,
                opponent_policies[opponent_name],
                args.hands,
                seed=seed,
                device=device,
                starting_stack=args.starting_stack,
                policy_mode=args.policy_mode,
                temperature=args.temperature,
                action_history_style=action_history_style,
                raise_action_mapping=raise_action_mapping,
            )
            results.append(
                {
                    "candidate": cand["label"],
                    "candidate_kind": cand["kind"],
                    "candidate_id": cand["id"],
                    "candidate_iteration": cand["iteration"],
                    "candidate_hands": cand["hands"],
                    "opponent": opponent_name,
                    **stats,
                }
            )
        del model
        if device == "cuda":
            torch.cuda.empty_cache()

    if checkpoint_opponent_model is not None:
        del checkpoint_opponent_model
        if device == "cuda":
            torch.cuda.empty_cache()

    notes = [
        "Use this probe for regression detection and rough direction only.",
        "A self-play PPO checkpoint is not expected to improve monotonically at every iteration.",
        "Small hand counts have wide confidence intervals; judge trends over repeated gates, not one row.",
        "Slumbot claims still require the gated Slumbot benchmark and promotion CI.",
    ]

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checkpoint_path": str(checkpoint_path),
        "device": device,
        "hands_per_match": args.hands,
        "starting_stack": args.starting_stack,
        "policy_mode": args.policy_mode,
        "temperature": args.temperature,
        "seed": args.seed,
        "action_history_style": action_history_style,
        "raise_action_mapping": raise_action_mapping,
        "checkpoint": {
            "iteration": checkpoint.get("iteration"),
            "total_hands": int(checkpoint.get("total_hands") or 0),
            "version": checkpoint.get("version"),
            "env_version": checkpoint.get("env_version"),
            "obs_version": checkpoint.get("obs_version"),
            "action_space_version": checkpoint.get("action_space_version"),
            "pool_snapshots": len(checkpoint.get("pool_snapshots") or []),
        },
        "candidates": [
            {k: v for k, v in cand.items() if k != "state_dict"}
            for cand in candidates
        ],
        "opponents": selected_opponents,
        "checkpoint_opponent_path": (
            str(checkpoint_opponent_path)
            if checkpoint_opponent_path is not None
            else None
        ),
        "checkpoint_opponent_policy_mode": (
            args.checkpoint_opponent_policy_mode
            if checkpoint_opponent_path is not None
            else None
        ),
        "results": results,
        "trends": summarize_trends(results),
        "notes": notes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe V5 checkpoint strength against fixed internal opponents.")
    parser.add_argument("--checkpoint", required=True, help="Path to V5 latest.pt checkpoint")
    parser.add_argument("--hands", type=int, default=500, help="Hands per candidate/opponent match")
    parser.add_argument("--opponents", nargs="+", default=["call-station", "aggressive"], choices=sorted(OPPONENTS))
    parser.add_argument(
        "--checkpoint-opponent",
        default=None,
        help=(
            "Optional frozen network checkpoint used as an additional local "
            "opponent. Candidate and opponent must share observation and "
            "action-mapping contracts."
        ),
    )
    parser.add_argument(
        "--checkpoint-opponent-only",
        action="store_true",
        help="Evaluate only against --checkpoint-opponent, not scripted opponents.",
    )
    parser.add_argument(
        "--checkpoint-opponent-policy-mode",
        choices=["greedy", "sample"],
        default="greedy",
    )
    parser.add_argument(
        "--checkpoint-opponent-temperature",
        type=float,
        default=1.0,
    )
    parser.add_argument("--max-pool-snapshots", type=int, default=5)
    parser.add_argument("--no-latest", action="store_true", help="Do not include checkpoint['model'] as an extra candidate")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--starting-stack", type=float, default=200.0)
    parser.add_argument("--seed", type=int, default=20260704)
    parser.add_argument("--policy-mode", choices=["greedy", "sample"], default="greedy")
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-md", default=None)
    args = parser.parse_args()

    summary = evaluate(args)
    text = json.dumps(summary, indent=2, sort_keys=True)
    print(text)

    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(text + "\n", encoding="utf-8")
    if args.out_md:
        out_md = Path(args.out_md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        write_markdown(summary, out_md)


if __name__ == "__main__":
    main()
