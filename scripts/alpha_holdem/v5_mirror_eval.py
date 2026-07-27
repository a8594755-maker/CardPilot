#!/usr/bin/env python3
"""Mirrored-deal internal evaluation for AlphaHoldem V5.

This is EXP-001 from reports/v5_experiment_ledger.md. It is read-only:
it loads frozen checkpoints, plays duplicate-deal hand pairs, and writes
JSON/Markdown evidence. It does not touch the live trainer, watchers, or
training parameters.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from alpha_holdem.environment import encode_action_history as encode_action_history_v4
from alpha_holdem.environment_v55 import (
    HUNLEnvironmentV55,
    NUM_ACTIONS,
    build_action_table,
    encode_action_history as encode_action_history_v55,
    encode_cards,
    encode_extra,
)
from alpha_holdem.network import AlphaHoldemNet
from deep_cfr.game_state import ActionType, HUNLGameState, Street


POLICY_MODE = "greedy_argmax_both_sides"

DEFAULT_NATIVE_ANCHOR_LABEL = "v55_native_75M_quick5k"
DEFAULT_NATIVE_ANCHOR_PATH = (
    REPO_ROOT
    / "models"
    / "bench_v55_v5_v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1_iter4600_75M_quick5k_checkpoint.pt"
)


@dataclass
class Policy:
    label: str
    path: Path
    sha256: str
    checkpoint: dict[str, Any]
    model: torch.nn.Module
    env_version: str
    obs_version: str
    emulate_raise_cap1_legality: bool
    device: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def configure_runtime(args: argparse.Namespace) -> dict[str, Any]:
    """Apply and record the low-contention runtime required by EXP-003."""
    torch.set_num_threads(int(args.torch_threads))
    torch.set_num_interop_threads(int(args.torch_interop_threads))
    priority: dict[str, Any] = {
        "requested": str(args.priority),
        "applied": False,
        "platform": platform.system(),
    }
    if args.priority == "below-normal":
        if os.name == "nt":
            below_normal_priority_class = 0x00004000
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentProcess.argtypes = []
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            kernel32.SetPriorityClass.restype = ctypes.c_int
            kernel32.GetPriorityClass.argtypes = [ctypes.c_void_p]
            kernel32.GetPriorityClass.restype = ctypes.c_uint32
            handle = kernel32.GetCurrentProcess()
            if not kernel32.SetPriorityClass(handle, below_normal_priority_class):
                raise OSError(ctypes.get_last_error(), "SetPriorityClass(BELOW_NORMAL) failed")
            actual = int(kernel32.GetPriorityClass(handle))
            priority.update(
                {
                    "applied": actual == below_normal_priority_class,
                    "actual_class": actual,
                    "actual_label": "BelowNormal" if actual == below_normal_priority_class else f"0x{actual:08x}",
                }
            )
        else:
            before = os.nice(0)
            after = os.nice(5)
            priority.update({"applied": after > before, "niceness_before": before, "niceness_after": after})
    else:
        priority.update({"applied": True, "actual_label": "NormalOrInherited"})
    if not priority["applied"]:
        raise RuntimeError(f"requested priority was not applied: {priority}")
    return {
        "pid": os.getpid(),
        "command": [sys.executable, *sys.argv],
        "working_directory": str(Path.cwd()),
        "python": sys.version,
        "torch_version": torch.__version__,
        "torch_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(),
        "priority": priority,
        "started_at": utc_now(),
        "status": "RUNNING",
    }


def read_checkpoint(path: Path) -> dict[str, Any]:
    obj = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(obj, dict):
        raise TypeError(f"{path} loaded as {type(obj).__name__}, expected checkpoint dict")
    if not isinstance(obj.get("model"), dict):
        raise KeyError(f"{path} does not contain checkpoint['model']")
    return obj


def resolve_obs_version(checkpoint: dict[str, Any]) -> str:
    obs_version = str(checkpoint.get("obs_version") or "").lower()
    if obs_version in {"v4", "v55"}:
        return obs_version
    config = checkpoint.get("config") if isinstance(checkpoint.get("config"), dict) else {}
    env_version = str(checkpoint.get("env_version") or config.get("env_version") or "").lower()
    if env_version == "v4":
        return "v4"
    if env_version == "v55cap1v4obs":
        return "v4"
    if env_version in {"v55", "v55cap1"}:
        return "v55"
    version = str(checkpoint.get("version") or "").lower()
    if version.startswith("v5.5") or version.startswith("v5.zero"):
        return "v55"
    if "opponent_mode" in checkpoint or "mmd_anchor" in checkpoint:
        return "v55"
    return "v4"


def resolve_env_version(checkpoint: dict[str, Any], path: Path | None = None) -> str:
    config = checkpoint.get("config") if isinstance(checkpoint.get("config"), dict) else {}
    env_version = str(checkpoint.get("env_version") or config.get("env_version") or "").lower()
    if env_version:
        return env_version
    version = str(checkpoint.get("version") or "").lower()
    if version.startswith("v4"):
        return "v4"
    if path is not None and "alpha_holdem_v4" in path.name.lower():
        return "v4"
    return ""


def should_emulate_raise_cap1_legality(env_version: str) -> bool:
    return env_version in {"v4", "v55cap1", "v55cap1v4obs"}


def checkpoint_value(checkpoint: dict[str, Any], key: str, default: Any) -> Any:
    config = checkpoint.get("config") if isinstance(checkpoint.get("config"), dict) else {}
    value = checkpoint.get(key)
    if value is None:
        value = config.get(key)
    return default if value is None else value


def hidden_width(state_dict: dict[str, torch.Tensor], key: str) -> int:
    return int(state_dict[key].shape[0]) if key in state_dict else 0


def init_actor(
    checkpoint: dict[str, Any],
    state_dict: dict[str, torch.Tensor],
    device: str,
) -> torch.nn.Module:
    position_adapter_hidden = hidden_width(
        state_dict, "position_policy_adapters.0.0.weight"
    )
    position_value_adapter_hidden = hidden_width(
        state_dict, "position_value_adapters.0.0.weight"
    )
    common_kwargs = {
        "num_actions": NUM_ACTIONS,
        "norm_layer": str(checkpoint_value(checkpoint, "norm_layer", "bn")),
        "separate_preflop_head": bool(
            checkpoint_value(checkpoint, "separate_preflop_head", False)
            or "preflop_policy_head.weight" in state_dict
        ),
        "preflop_adapter_hidden": hidden_width(
            state_dict, "preflop_policy_adapter.0.weight"
        ),
        "preflop_raw_adapter_hidden": hidden_width(
            state_dict, "preflop_raw_policy_adapter.0.weight"
        ),
        "flop_adapter_hidden": hidden_width(
            state_dict, "flop_policy_adapter.0.weight"
        ),
        "postflop_adapter_hidden": hidden_width(
            state_dict, "postflop_policy_adapter.0.weight"
        ),
        "position_adapter_hidden": position_adapter_hidden,
        "critic_contract": str(
            checkpoint_value(checkpoint, "critic_contract", "critic_v1")
        ),
    }
    if position_value_adapter_hidden > 0:
        from alpha_holdem.network_hybrid_h1 import (
            AlphaHoldemNet as PositionValueAlphaHoldemNet,
        )

        model = PositionValueAlphaHoldemNet(
            **common_kwargs,
            position_value_adapter_hidden=position_value_adapter_hidden,
        ).to(device)
    else:
        model = AlphaHoldemNet(
            **common_kwargs,
            preflop_raw_action_scale=float(
                checkpoint_value(
                    checkpoint, "preflop_raw_action_scale", 1.0
                )
            ),
            preflop_raw_gate=str(
                checkpoint_value(
                    checkpoint, "preflop_raw_gate", "none"
                )
            ),
        ).to(device)
    with torch.no_grad():
        model(
            torch.zeros(2, 6, 4, 13, device=device),
            torch.zeros(2, 25, 4, 5, device=device),
            torch.zeros(
                2,
                3
                if (
                    position_adapter_hidden > 0
                    or position_value_adapter_hidden > 0
                )
                else 2,
                device=device,
            ),
        )
    model.load_state_dict(state_dict)
    model.eval()
    for param in model.parameters():
        param.requires_grad_(False)
    return model


def init_model(checkpoint: dict[str, Any], device: str) -> torch.nn.Module:
    state_dict = checkpoint["model"]
    architecture = str(checkpoint.get("architecture") or "")
    if architecture not in {"dual_seat_v1", "dual_seat_v2"}:
        return init_actor(checkpoint, state_dict, device)

    def load_seat_actor(prefix: str) -> AlphaHoldemNet:
        seat_state = {
            key[len(prefix) :]: value
            for key, value in state_dict.items()
            if key.startswith(prefix)
        }
        if not seat_state:
            raise KeyError(f"{architecture} checkpoint has no {prefix!r} tensors")
        return init_actor(checkpoint, seat_state, device)

    if architecture == "dual_seat_v1":
        from alpha_holdem.network_dual_seat import DualSeatAlphaHoldemNet

        model = DualSeatAlphaHoldemNet(
            sb_model=load_seat_actor("sb_model."),
            bb_model=load_seat_actor("bb_model."),
        ).to(device)
    else:
        from alpha_holdem.network_dual_seat_v2 import DualSeatAlphaHoldemNetV2

        model = DualSeatAlphaHoldemNetV2(
            sb_model=load_seat_actor("sb_model."),
            bb_model=load_seat_actor("bb_model."),
        ).to(device)
    model.eval()
    for param in model.parameters():
        param.requires_grad_(False)
    return model


def load_policy(label: str, path: Path, device: str) -> Policy:
    checkpoint = read_checkpoint(path)
    env_version = resolve_env_version(checkpoint, path)
    return Policy(
        label=label,
        path=path,
        sha256=sha256_file(path),
        checkpoint=checkpoint,
        model=init_model(checkpoint, device),
        env_version=env_version,
        obs_version=resolve_obs_version(checkpoint),
        emulate_raise_cap1_legality=should_emulate_raise_cap1_legality(env_version),
        device=device,
    )


def parse_anchor(text: str) -> tuple[str, Path]:
    if "=" not in text:
        path = Path(text)
        return path.stem, path
    label, path_text = text.split("=", 1)
    label = label.strip()
    if not label:
        raise ValueError(f"anchor label is empty in {text!r}")
    return label, Path(path_text)


def default_anchors() -> list[tuple[str, Path]]:
    return [(DEFAULT_NATIVE_ANCHOR_LABEL, DEFAULT_NATIVE_ANCHOR_PATH)] if DEFAULT_NATIVE_ANCHOR_PATH.exists() else []


def make_fixed_state(env: HUNLEnvironmentV55, deck: list[int]) -> HUNLGameState:
    state = HUNLGameState(config=env._make_config())
    state.deck = list(deck)
    hole0 = (int(deck[0]), int(deck[1]))
    hole1 = (int(deck[2]), int(deck[3]))
    state.hole_cards = [hole0, hole1]
    state.board = []
    return state


def observation_for(
    state: HUNLGameState,
    player: int,
    obs_version: str,
    *,
    include_position: bool,
) -> tuple[dict[str, Any], list[Any]]:
    legal_mask, slot_to_action = build_action_table(state)
    action_info = (
        encode_action_history_v55(state, player)
        if obs_version == "v55"
        else encode_action_history_v4(state, player)
    )
    extra_info = encode_extra(state, player)
    if include_position:
        extra_info = np.concatenate(
            [extra_info, np.asarray([float(player)], dtype=np.float32)]
        )
    obs = {
        "card_info": encode_cards(state, player),
        "action_info": action_info,
        "extra_info": extra_info,
        "legal_mask": legal_mask,
        "player": player,
    }
    return obs, slot_to_action


def is_raise_cap1_ood_node(state: HUNLGameState, policy: Policy) -> bool:
    if not policy.emulate_raise_cap1_legality:
        return False
    if state.street == Street.PREFLOP:
        return False
    player = int(state.current_player)
    to_call = float(state.street_committed[1 - player] - state.street_committed[player])
    return to_call > 0.0 and int(state.raise_count) >= 1


def apply_policy_legal_emulation(
    policy: Policy,
    state: HUNLGameState,
    legal_mask: np.ndarray,
    slot_to_action: list[Any],
) -> bool:
    """Apply per-policy legacy legality emulation and report whether it fired."""
    if not is_raise_cap1_ood_node(state, policy):
        return False
    for slot in range(2, NUM_ACTIONS):
        legal_mask[slot] = 0.0
        slot_to_action[slot] = None
    return True


@torch.no_grad()
def choose_action(policy: Policy, state: HUNLGameState, player: int) -> tuple[int, Any, bool]:
    include_position = bool(
        getattr(policy.model, "requires_position_feature", False)
    ) or int(getattr(policy.model, "position_adapter_hidden", 0)) > 0 or int(
        getattr(policy.model, "position_value_adapter_hidden", 0)
    ) > 0
    obs, slot_to_action = observation_for(
        state,
        player,
        policy.obs_version,
        include_position=include_position,
    )
    ood_node = apply_policy_legal_emulation(policy, state, obs["legal_mask"], slot_to_action)
    card_t = torch.as_tensor(obs["card_info"], dtype=torch.float32, device=policy.device).unsqueeze(0)
    action_t = torch.as_tensor(obs["action_info"], dtype=torch.float32, device=policy.device).unsqueeze(0)
    extra_t = torch.as_tensor(obs["extra_info"], dtype=torch.float32, device=policy.device).unsqueeze(0)
    mask_t = torch.as_tensor(obs["legal_mask"], dtype=torch.float32, device=policy.device).unsqueeze(0)
    logits, _ = policy.model(card_t, action_t, extra_t, mask_t)
    slot = int(torch.argmax(logits, dim=-1).item())
    action = slot_to_action[slot] if 0 <= slot < len(slot_to_action) else None
    if action is None:
        legal_slots = [idx for idx, item in enumerate(slot_to_action) if item is not None]
        if not legal_slots:
            raise RuntimeError("no legal action in non-terminal state")
        legal_logits = logits[0, legal_slots]
        slot = int(legal_slots[int(torch.argmax(legal_logits).item())])
        action = slot_to_action[slot]
    return slot, action, ood_node


def play_hand(
    *,
    env: HUNLEnvironmentV55,
    deck: list[int],
    candidate: Policy,
    anchor: Policy,
    candidate_seat: int,
) -> dict[str, Any]:
    state = make_fixed_state(env, deck)
    candidate_reward = 0.0
    decisions = 0
    ood_nodes = {"candidate": 0, "anchor": 0}
    policy_decisions = {"candidate": 0, "anchor": 0}
    action_counts = {
        "candidate": {str(i): 0 for i in range(NUM_ACTIONS)},
        "anchor": {str(i): 0 for i in range(NUM_ACTIONS)},
    }

    while not state.is_terminal():
        player = int(state.current_player)
        actor_policy = candidate if player == candidate_seat else anchor
        actor_key = "candidate" if player == candidate_seat else "anchor"
        slot, action, ood_node = choose_action(actor_policy, state, player)
        action_counts[actor_key][str(slot)] += 1
        policy_decisions[actor_key] += 1
        if ood_node:
            ood_nodes[actor_key] += 1
        acting_player = player
        state = state.apply(action)
        decisions += 1
        if state.is_terminal():
            candidate_reward = float(state.payoff(candidate_seat))
            if acting_player != candidate_seat:
                # payoff(candidate_seat) is already from candidate perspective.
                candidate_reward = float(state.payoff(candidate_seat))

    return {
        "candidate_reward_bb": candidate_reward,
        "decisions": decisions,
        "candidate_seat": candidate_seat,
        "action_counts": action_counts,
        "policy_decisions": policy_decisions,
        "ood_nodes": ood_nodes,
    }


def shuffled_deck(rng: random.Random) -> list[int]:
    deck = list(range(52))
    rng.shuffle(deck)
    return deck


def mean_ci(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "std": 0.0, "ci95": 0.0}
    arr = np.asarray(values, dtype=np.float64)
    mean = float(arr.mean())
    std = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    ci95 = 1.96 * std / math.sqrt(max(len(arr), 1))
    return {"mean": mean, "std": std, "ci95": ci95}


def summarize_anchor(
    *,
    candidate: Policy,
    anchor: Policy,
    pairs: int,
    seed: int,
    starting_stack: float,
    include_pair_outcomes: bool = False,
) -> dict[str, Any]:
    env = HUNLEnvironmentV55(starting_stack=starting_stack)
    rng = random.Random(seed)
    pair_bb_per_hand: list[float] = []
    hand_rewards: list[float] = []
    rewards_by_seat: dict[int, list[float]] = {0: [], 1: []}
    pair_wins = pair_losses = pair_draws = 0
    hand_wins = hand_losses = hand_draws = 0
    total_decisions = 0
    policy_decisions = {"candidate": 0, "anchor": 0}
    ood_nodes = {"candidate": 0, "anchor": 0}
    started = time.time()

    for _ in range(pairs):
        deck = shuffled_deck(rng)
        first = play_hand(
            env=env,
            deck=deck,
            candidate=candidate,
            anchor=anchor,
            candidate_seat=0,
        )
        second = play_hand(
            env=env,
            deck=deck,
            candidate=candidate,
            anchor=anchor,
            candidate_seat=1,
        )
        rewards = [float(first["candidate_reward_bb"]), float(second["candidate_reward_bb"])]
        rewards_by_seat[0].append(rewards[0])
        rewards_by_seat[1].append(rewards[1])
        pair_total = rewards[0] + rewards[1]
        pair_mean = pair_total / 2.0
        pair_bb_per_hand.append(pair_mean)
        hand_rewards.extend(rewards)
        total_decisions += int(first["decisions"]) + int(second["decisions"])
        for key in ("candidate", "anchor"):
            policy_decisions[key] += int(first["policy_decisions"][key]) + int(second["policy_decisions"][key])
            ood_nodes[key] += int(first["ood_nodes"][key]) + int(second["ood_nodes"][key])

        if pair_total > 0.01:
            pair_wins += 1
        elif pair_total < -0.01:
            pair_losses += 1
        else:
            pair_draws += 1
        for reward in rewards:
            if reward > 0.01:
                hand_wins += 1
            elif reward < -0.01:
                hand_losses += 1
            else:
                hand_draws += 1

    elapsed = time.time() - started
    pair_stats = mean_ci(pair_bb_per_hand)
    hand_stats = mean_ci(hand_rewards)
    seat_stats = {
        "bb": mean_ci(rewards_by_seat[0]),
        "sb": mean_ci(rewards_by_seat[1]),
    }
    result = {
        "anchor": anchor.label,
        "anchor_path": str(anchor.path),
        "anchor_sha256": anchor.sha256,
        "anchor_checkpoint": checkpoint_summary(anchor.checkpoint),
        "policy_mode": POLICY_MODE,
        "candidate_obs_version": candidate.obs_version,
        "candidate_env_version": candidate.env_version,
        "candidate_raise_cap1_legality_emulated": candidate.emulate_raise_cap1_legality,
        "anchor_obs_version": anchor.obs_version,
        "anchor_env_version": anchor.env_version,
        "anchor_raise_cap1_legality_emulated": anchor.emulate_raise_cap1_legality,
        "pairs": pairs,
        "hands": pairs * 2,
        "candidate_bb100": pair_stats["mean"] * 100.0,
        "candidate_ci95_bb100": pair_stats["ci95"] * 100.0,
        "candidate_std_bb_per_hand_pair_mean": pair_stats["std"],
        "unpaired_hand_bb100": hand_stats["mean"] * 100.0,
        "unpaired_hand_ci95_bb100": hand_stats["ci95"] * 100.0,
        "candidate_by_seat": {
            seat: {
                "hands": pairs,
                "candidate_bb100": stats["mean"] * 100.0,
                "candidate_ci95_bb100": stats["ci95"] * 100.0,
                "candidate_std_bb_per_hand": stats["std"],
                "total_candidate_bb": float(sum(rewards_by_seat[index])),
            }
            for seat, index, stats in (
                ("bb", 0, seat_stats["bb"]),
                ("sb", 1, seat_stats["sb"]),
            )
        },
        "total_candidate_bb": float(sum(hand_rewards)),
        "pair_wins": pair_wins,
        "pair_losses": pair_losses,
        "pair_draws": pair_draws,
        "hand_wins": hand_wins,
        "hand_losses": hand_losses,
        "hand_draws": hand_draws,
        "decisions": total_decisions,
        "policy_decisions": policy_decisions,
        "ood_nodes": ood_nodes,
        "candidate_ood_node_rate": ood_nodes["candidate"] / max(policy_decisions["candidate"], 1),
        "anchor_ood_node_rate": ood_nodes["anchor"] / max(policy_decisions["anchor"], 1),
        "elapsed_seconds": elapsed,
        "hands_per_second": (pairs * 2) / max(elapsed, 1e-9),
    }
    if include_pair_outcomes:
        result["paired_outcomes"] = {
            "overall_bb_per_hand": pair_bb_per_hand,
            "bb_bb_per_hand": rewards_by_seat[0],
            "sb_bb_per_hand": rewards_by_seat[1],
        }
    return result


def annotate_anchor_validity(row: dict[str, Any], anchor_ood_valid_threshold: float) -> None:
    anchor_ood = float(row.get("anchor_ood_node_rate", 0.0))
    is_valid = anchor_ood <= anchor_ood_valid_threshold
    row["anchor_ood_valid_threshold"] = anchor_ood_valid_threshold
    row["anchor_ood_valid"] = is_valid
    row["mirror_signal_valid"] = is_valid
    row["invalid_reason"] = (
        ""
        if is_valid
        else (
            "anchor_ood_node_rate "
            f"{anchor_ood:.6f} exceeds validity threshold {anchor_ood_valid_threshold:.6f}"
        )
    )


def checkpoint_summary(checkpoint: dict[str, Any]) -> dict[str, Any]:
    return {
        "iteration": checkpoint.get("iteration"),
        "total_hands": checkpoint.get("total_hands"),
        "version": checkpoint.get("version"),
        "env_version": checkpoint.get("env_version"),
        "obs_version": checkpoint.get("obs_version"),
        "action_space_version": checkpoint.get("action_space_version"),
        "starting_stack_bb": checkpoint.get("starting_stack_bb"),
        "fresh_from_zero_lineage": checkpoint.get("fresh_from_zero_lineage"),
        "run_id": checkpoint.get("run_id"),
        "architecture": checkpoint.get("architecture"),
        "position_adapter_hidden": checkpoint_value(
            checkpoint, "position_adapter_hidden", 0
        ),
        "position_value_adapter_hidden": checkpoint_value(
            checkpoint, "position_value_adapter_hidden", 0
        ),
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# V5 Mirrored-Deal Internal Eval",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Candidate: `{summary['candidate']['label']}`",
        f"- Candidate path: `{summary['candidate']['path']}`",
        f"- Candidate checkpoint iter/hands: `{summary['candidate']['checkpoint'].get('iteration')}` / `{summary['candidate']['checkpoint'].get('total_hands')}`",
        f"- Pairs per anchor: `{summary['pairs']}`",
        f"- Starting stack: `{summary['starting_stack']}` bb",
        f"- Device: `{summary['device']}`",
        f"- Policy mode: `{summary['policy_mode']}`",
        "",
        "This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.",
        "",
        "## Results",
        "",
        "| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|---:|",
    ]
    for row in summary["anchors"]:
        lines.append(
            "| {anchor} | {hands:,} | {bb100:+.2f} | {bb:+.2f} | {sb:+.2f} | +/-{ci:.2f} | {ood:.4f} | {gate} | {pw}/{pl}/{pd} | {hps:.1f} |".format(
                anchor=row["anchor"],
                hands=int(row["hands"]),
                bb100=float(row["candidate_bb100"]),
                bb=float(row["candidate_by_seat"]["bb"]["candidate_bb100"]),
                sb=float(row["candidate_by_seat"]["sb"]["candidate_bb100"]),
                ci=float(row["candidate_ci95_bb100"]),
                ood=float(row.get("anchor_ood_node_rate", 0.0)),
                gate="VALID" if bool(row.get("anchor_ood_valid", True)) else "INVALID",
                pw=int(row["pair_wins"]),
                pl=int(row["pair_losses"]),
                pd=int(row["pair_draws"]),
                hps=float(row["hands_per_second"]),
            )
        )
    invalid_rows = [row for row in summary["anchors"] if not bool(row.get("mirror_signal_valid", True))]
    lines.extend(
        [
            "",
            "## Validity Gate",
            "",
            f"- Anchor OOD validity threshold: `{summary['gate']['anchor_ood_valid_threshold']}`",
            f"- All anchors pass OOD gate: `{summary['gate']['all_anchors_pass_ood_gate']}`",
            f"- Internal signal gate pass: `{summary['gate']['passes_internal_signal_gate']}`",
        ]
    )
    if invalid_rows:
        lines.append("- Invalid mirror rows are quarantined: do not use their bb/100 for progress, plateau, or strength judgments.")
        for row in invalid_rows:
            lines.append(f"  - `{row['anchor']}`: {row['invalid_reason']}")
    lines.extend(
        [
            "",
            "## Gate Notes",
            "",
            "- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.",
            "- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.",
            "- Later method experiments should use this as a progress signal, not as a strength claim.",
            "- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"

    candidate_path = Path(args.candidate)
    candidate = load_policy(args.candidate_label, candidate_path, device)
    anchor_specs = [parse_anchor(item) for item in args.anchor] if args.anchor else default_anchors()
    if not anchor_specs:
        raise RuntimeError(
            "no anchors provided and the default native v55 anchor was not found: "
            f"{DEFAULT_NATIVE_ANCHOR_PATH}"
        )

    anchors: list[dict[str, Any]] = []
    for index, (label, anchor_path) in enumerate(anchor_specs):
        anchor = load_policy(label, anchor_path, device)
        row = summarize_anchor(
            candidate=candidate,
            anchor=anchor,
            pairs=args.pairs,
            seed=args.seed + index * 1_000_003,
            starting_stack=args.starting_stack,
            include_pair_outcomes=args.include_pair_outcomes,
        )
        annotate_anchor_validity(row, args.anchor_ood_valid_threshold)
        anchors.append(row)
        del anchor.model
        if device == "cuda":
            torch.cuda.empty_cache()

    passes_ci_gate = (
        all(abs(float(row["candidate_ci95_bb100"])) <= 20.0 for row in anchors)
        if args.pairs >= 10000
        else False
    )
    all_anchors_pass_ood_gate = all(bool(row.get("anchor_ood_valid", False)) for row in anchors)
    return {
        "checked_at": utc_now(),
        "experiment_id": "EXP-001",
        "kind": "mirrored_deal_internal_eval",
        "claim_scope": "internal_only_not_slumbot_not_l5_l6",
        "policy_mode": POLICY_MODE,
        "candidate": {
            "label": candidate.label,
            "path": str(candidate.path),
            "sha256": candidate.sha256,
            "env_version": candidate.env_version,
            "obs_version": candidate.obs_version,
            "raise_cap1_legality_emulated": candidate.emulate_raise_cap1_legality,
            "checkpoint": checkpoint_summary(candidate.checkpoint),
        },
        "pairs": args.pairs,
        "starting_stack": args.starting_stack,
        "seed": args.seed,
        "device": device,
        "anchors": anchors,
        "gate": {
            "target_pairs": 10000,
            "target_ci95_bb100": 20.0,
            "anchor_ood_valid_threshold": args.anchor_ood_valid_threshold,
            "passes_ci_gate": passes_ci_gate,
            "all_anchors_pass_ood_gate": all_anchors_pass_ood_gate,
            "passes_internal_signal_gate": passes_ci_gate and all_anchors_pass_ood_gate,
            "note": "CI gate is only evaluated at >=10k pairs; OOD gate must pass before mirror rows are usable as internal progress signals.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="EXP-001 mirrored-deal internal eval vs frozen anchors.")
    parser.add_argument("--candidate", required=True, help="Candidate checkpoint path")
    parser.add_argument("--candidate-label", default="candidate")
    parser.add_argument(
        "--anchor",
        action="append",
        default=[],
        help=(
            "Anchor as label=path. May be repeated. Defaults to the native v55 75M "
            "anchor if omitted; pass V4 explicitly only for legacy/cross-axis diagnostics."
        ),
    )
    parser.add_argument("--pairs", type=int, default=10000, help="Mirrored deal pairs per anchor")
    parser.add_argument("--starting-stack", type=float, default=200.0)
    parser.add_argument(
        "--include-pair-outcomes",
        action="store_true",
        help=(
            "Retain per-deck overall/BB/SB outcomes so a multi-checkpoint "
            "curve can compute paired checkpoint deltas."
        ),
    )
    parser.add_argument("--seed", type=int, default=20260706)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument(
        "--priority",
        choices=["below-normal", "normal"],
        default="below-normal",
        help="Process scheduling priority. EXP-003 requires below-normal.",
    )
    parser.add_argument("--torch-threads", type=int, default=1)
    parser.add_argument("--torch-interop-threads", type=int, default=1)
    parser.add_argument(
        "--anchor-ood-valid-threshold",
        type=float,
        default=0.15,
        help="Invalidate a mirror row as an internal progress signal when anchor_ood_node_rate exceeds this value.",
    )
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    parser.add_argument("--execution-json", default="")
    args = parser.parse_args()

    started = time.monotonic()
    execution = configure_runtime(args)
    try:
        summary = evaluate(args)
    except Exception as exc:
        execution.update(
            {
                "status": "FAILED",
                "finished_at": utc_now(),
                "elapsed_seconds": time.monotonic() - started,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        if args.execution_json:
            out_execution = Path(args.execution_json)
            out_execution.parent.mkdir(parents=True, exist_ok=True)
            out_execution.write_text(json.dumps(execution, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise
    execution.update(
        {
            "status": "COMPLETED",
            "finished_at": utc_now(),
            "elapsed_seconds": time.monotonic() - started,
        }
    )
    summary["execution"] = execution
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
    if args.execution_json:
        out_execution = Path(args.execution_json)
        out_execution.parent.mkdir(parents=True, exist_ok=True)
        out_execution.write_text(json.dumps(execution, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
