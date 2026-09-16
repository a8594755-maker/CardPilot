"""Generic v6 physical-state adapter for frozen legacy-v4 learned policies.

The adapter changes observation compatibility only. It does not contain poker
tactics, action overrides, or benchmark-dependent branches. A legacy physical
action must already be exactly legal under the v6 action table.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np
import torch

from alpha_holdem.play_slumbot import (
    STACK_SIZE,
    build_action_table as legacy_action_table,
    compute_commitments,
    encode_action_history,
    encode_cards,
    encode_extra,
    parse_action,
)
from alpha_holdem.policy_contract_v6 import (
    CONTRACT_VERSION,
    LEGACY_V4_BRIDGE_CONTRACT,
    action_table as v6_action_table,
)
from alpha_holdem.policy_contract_v6 import from_external
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v5_mirror_eval import init_model, resolve_obs_version

BRIDGE_CONTRACT = LEGACY_V4_BRIDGE_CONTRACT
RANKS = "23456789TJQKA"
SUITS = "cdhs"


@dataclass(frozen=True)
class LegacyObservationBridgePolicy:
    model: torch.nn.Module
    checkpoint: dict
    path: Path
    sha256: str
    device: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def action_prefix(state: ChipState) -> str:
    if state.terminal:
        raise ValueError("No observation for a terminal state")
    groups = [[] for _ in range(state.street + 1)]
    for event in state.history:
        if event.street > state.street:
            raise ValueError("State history contains a future-street event")
        groups[event.street].append(
            f"b{event.amount}" if event.kind == "b" else event.kind
        )
    return "/".join("".join(group) for group in groups)


def card_string(card: int) -> str:
    return RANKS[card // 4] + SUITS[card % 4]


def reconstruct_legacy_state(state: ChipState) -> tuple[dict, dict]:
    prefix = action_prefix(state)
    parsed = parse_action(prefix)
    if "error" in parsed:
        raise ValueError(f"Legacy parser rejected v6 history {prefix!r}: {parsed['error']}")
    commitments = compute_commitments(parsed)
    expected = {
        "st": state.street,
        "pos": state.actor,
        "hero_total": state.initial[state.actor] - state.stacks[state.actor],
        "opp_total": state.initial[1 - state.actor] - state.stacks[1 - state.actor],
        "hero_street": state.bets[state.actor],
        "opp_street": state.bets[1 - state.actor],
        "to_call": state.to_call,
        "pot": state.pot,
        "stack": state.stacks[state.actor],
    }
    actual = {
        "st": int(parsed["st"]),
        "pos": int(parsed["pos"]),
        **{key: int(commitments[key]) for key in (
            "hero_total", "opp_total", "hero_street", "opp_street", "to_call", "pot", "stack"
        )},
    }
    if actual != expected:
        raise ValueError(f"Legacy reconstruction parity failure: expected={expected}, actual={actual}")
    return parsed, commitments


def load_policy(path: str | Path, device: str = "cpu") -> LegacyObservationBridgePolicy:
    path = Path(path).resolve()
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    if resolve_obs_version(checkpoint) != "v4":
        raise ValueError("Legacy observation bridge requires a v4-observation checkpoint")
    trained_bridge = checkpoint.get("observation_bridge_contract") == BRIDGE_CONTRACT
    expected_mapping = "preflop_pot_fraction_v2"
    if checkpoint.get("raise_action_mapping") != expected_mapping:
        raise ValueError(
            f"Legacy observation bridge requires {expected_mapping} for this checkpoint"
        )
    if trained_bridge:
        required = {
            "env_version": "v6legacyv4obs",
            "policy_contract": CONTRACT_VERSION,
            "obs_version": "v4",
            "model_obs_version": "v4",
        }
        for key, value in required.items():
            if checkpoint.get(key) != value:
                raise ValueError(f"Trained bridge checkpoint requires {key}={value!r}")
    for key in (
        "policy_logit_bias", "policy_range_override", "policy_context_override",
        "preflop_strategy_profile",
    ):
        if checkpoint.get(key) is not None:
            raise ValueError(f"Learned-only legacy bridge forbids {key}")
    model = init_model(checkpoint, device)
    # Historical play_slumbot.load_checkpoint_model binds execution metadata
    # onto the network object. Preserve that behavior for independent parity
    # calls through play_slumbot.decide_action.
    model.raise_action_mapping = checkpoint["raise_action_mapping"]
    model.obs_version = "v4"
    model.eval()
    return LegacyObservationBridgePolicy(
        model=model,
        checkpoint=checkpoint,
        path=path,
        sha256=sha256_file(path),
        device=device,
    )


def legacy_observation_from_state(
    state: ChipState, *, include_position: bool = False,
    restrict_to_v6_action_table: bool = True,
) -> tuple[dict, list[str | None]]:
    parsed, commitments = reconstruct_legacy_state(state)
    hole = [card_string(card) for card in state.holes[state.actor]]
    board = [card_string(card) for card in state.board]
    legal_mask, table = legacy_action_table(parsed, "preflop_pot_fraction_v2")
    if restrict_to_v6_action_table:
        _, physical_table = v6_action_table(state)
        physical_actions = {action for action in physical_table if action is not None}
        for slot, action in enumerate(table):
            if action is not None and action not in physical_actions:
                legal_mask[slot] = 0.0
                table[slot] = None
    extra = encode_extra([
        STACK_SIZE - commitments["hero_total"],
        STACK_SIZE - commitments["opp_total"],
    ])
    if include_position:
        extra = np.concatenate([extra, np.asarray([float(state.actor)], dtype=np.float32)])
    return {
        "card_info": encode_cards(hole, board, parsed["st"]),
        "action_info": encode_action_history(parsed, state.actor, parsed["pos"], obs_version="v4"),
        "extra_info": extra,
        "legal_mask": legal_mask,
        "player": state.actor,
    }, table


def legacy_observation(policy: LegacyObservationBridgePolicy, state: ChipState) -> tuple[dict, list[str | None]]:
    return legacy_observation_from_state(
        state,
        include_position=bool(getattr(policy.model, "requires_position_feature", False)),
    )


@torch.no_grad()
def decide(
    policy: LegacyObservationBridgePolicy,
    state: ChipState,
    *,
    uniform: float,
    policy_mode: str = "greedy",
) -> tuple[str, dict]:
    if not 0 <= uniform < 1:
        raise ValueError("Uniform variate must be in [0,1)")
    if policy_mode not in {"greedy", "sample"}:
        raise ValueError("policy_mode must be greedy or sample")
    obs, legacy_table = legacy_observation(policy, state)
    tensors = [
        torch.as_tensor(obs[key], dtype=torch.float32, device=policy.device).unsqueeze(0)
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ]
    logits, _ = policy.model(*tensors)
    values = logits[0].detach().cpu().numpy().astype(np.float64)
    legal = np.flatnonzero(obs["legal_mask"])
    legal_values = values[legal]
    weights = np.exp(legal_values - np.max(legal_values))
    probs = weights / weights.sum()
    greedy_slot = int(legal[int(np.argmax(legal_values))])
    if policy_mode == "greedy":
        selected_slot = greedy_slot
        behavior_probability = 1.0
        temperature = 0.0
    else:
        selected_index = min(
            int(np.searchsorted(np.cumsum(probs), uniform, side="right")),
            len(legal) - 1,
        )
        selected_slot = int(legal[selected_index])
        behavior_probability = float(probs[selected_index])
        temperature = 1.0
    selected_action = legacy_table[selected_slot]
    current_mask, current_table = v6_action_table(state)
    matching_slots = [
        slot for slot, action in enumerate(current_table) if action == selected_action
    ]
    if not matching_slots:
        raise ValueError(
            f"Legacy physical action {selected_action!r} is not exactly legal under v6; "
            f"v6_table={current_table}"
        )
    mapped_model_probs = np.zeros(9, dtype=np.float64)
    for probability, legacy_slot in zip(probs, legal):
        action = legacy_table[int(legacy_slot)]
        slots = [slot for slot, current in enumerate(current_table) if current == action]
        if not slots:
            raise ValueError(f"Legacy probability action {action!r} is not legal under v6")
        mapped_model_probs[slots[0]] += float(probability)
    mapped_greedy_slots = [
        slot for slot, action in enumerate(current_table)
        if action == legacy_table[greedy_slot]
    ]
    if not mapped_greedy_slots:
        raise ValueError("Legacy greedy action is not legal under v6")
    if policy_mode == "greedy":
        behavior_probs = np.zeros(9, dtype=np.float64)
        behavior_probs[matching_slots[0]] = 1.0
    else:
        behavior_probs = mapped_model_probs.copy()
    return selected_action, {
        "policy_contract": CONTRACT_VERSION,
        "observation_bridge_contract": BRIDGE_CONTRACT,
        "source_checkpoint_sha256": policy.sha256,
        "policy_mode": policy_mode,
        "temperature": temperature,
        "legacy_selected_action_slot": selected_slot,
        "selected_action_slot": matching_slots[0],
        "direct_increment": selected_action,
        "greedy_action_slot": mapped_greedy_slots[0],
        "legacy_greedy_action_slot": greedy_slot,
        "behavior_action_probability": behavior_probability,
        "behavior_probs": behavior_probs.tolist(),
        "model_probs": mapped_model_probs.tolist(),
        "legal_mask": current_mask.tolist(),
        "action_table": current_table,
        "legacy_legal_mask": obs["legal_mask"].tolist(),
        "legacy_action_table": legacy_table,
        "v6_action_table": current_table,
        "uniform": float(uniform),
    }


def external_decision(
    policy: LegacyObservationBridgePolicy,
    response: dict,
    *,
    uniform: float,
    device: str = "cpu",
    policy_mode: str = "greedy",
) -> tuple[str, dict]:
    if device != policy.device:
        raise ValueError(f"Bridge policy is on {policy.device}, requested {device}")
    state = from_external(
        response["action"], response["hole_cards"], response.get("board", []),
        response["client_pos"],
    )
    return decide(policy, state, uniform=uniform, policy_mode=policy_mode)
