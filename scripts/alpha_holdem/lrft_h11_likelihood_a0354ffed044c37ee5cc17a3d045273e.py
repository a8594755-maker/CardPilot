"""Neutral arbitrary-hole H11 likelihood interface for LRFT-I00.

This module is deliberately read-only and inference-only.  It accepts an exact
public-state view, the acting player, that player's hole cards, and a legal
nine-slot mask.  Opponent cards, future cards, outcomes, training-state
machinery, sampling, and frozen resolver runtimes are outside the interface.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import threading
from typing import Sequence

import numpy as np
import torch

from .network_hybrid_h1 import (
    AlphaHoldemNet,
    CRITIC_V1,
)


LRFT_I00_IDENTITY = (
    "a0354ffed044c37ee5cc17a3d045273ecf7751f256a0199f23140d311e55f704"
)
LRFT_I00_TOKEN = "a0354ffed044c37ee5cc17a3d045273e"

H11_CHECKPOINT_SHA256 = (
    "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
)
H11_ITERATION = 35051
H11_TOTAL_HANDS = 576_021_901
H11_STARTING_STACK_CENTS = 20_000

NUM_ACTIONS = 9
NUM_STREETS = 4
MAX_ACTIONS_PER_STREET = 6
ACTION_HISTORY_CHANNELS = NUM_STREETS * MAX_ACTIONS_PER_STREET + 1
NUM_CARD_CHANNELS = 6
NUM_SUITS = 4
NUM_RANKS = 13

_REPO_ROOT = Path(__file__).resolve().parents[2]
H11_CHECKPOINT_PATH = (
    _REPO_ROOT
    / "models"
    / "alpha_holdem_v5_hybrid"
    / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715"
    / "h11_control_endpoint.pt"
)


@dataclass(frozen=True, slots=True)
class PublicActionRecord:
    """One already-observed public action.

    ``amount_cents`` is the V5.5 action amount field expressed in integer
    cents.  Passive actions (fold/check/call) must use zero.
    """

    player: int
    action_type: int
    amount_cents: int = 0


@dataclass(frozen=True, slots=True)
class PublicLikelihoodState:
    """The complete public view needed by the frozen V5.5 observation."""

    street: int
    button: int
    current_player: int
    board: tuple[int, ...]
    pot_cents: int
    stacks_cents: tuple[int, int]
    starting_stack_cents: int
    actions_by_street: tuple[
        tuple[PublicActionRecord, ...],
        tuple[PublicActionRecord, ...],
        tuple[PublicActionRecord, ...],
        tuple[PublicActionRecord, ...],
    ]


def _require_plain_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an int")
    return value


def _validate_public_inputs(
    public_state: PublicLikelihoodState,
    acting_player: int,
    own_hole: Sequence[int],
    legal_mask: Sequence[float],
) -> tuple[tuple[int, int], np.ndarray]:
    if not isinstance(public_state, PublicLikelihoodState):
        raise TypeError("public_state must be PublicLikelihoodState")

    acting = _require_plain_int(acting_player, "acting_player")
    if acting not in (0, 1):
        raise ValueError("acting_player must be 0 or 1")
    if _require_plain_int(public_state.current_player, "current_player") != acting:
        raise ValueError("acting_player must equal public_state.current_player")
    if _require_plain_int(public_state.button, "button") not in (0, 1):
        raise ValueError("button must be 0 or 1")

    street = _require_plain_int(public_state.street, "street")
    if street not in range(NUM_STREETS):
        raise ValueError("street must be in [0, 3]")
    expected_board_cards = (0, 3, 4, 5)[street]
    if len(public_state.board) != expected_board_cards:
        raise ValueError(
            f"street {street} requires {expected_board_cards} board cards"
        )

    if len(own_hole) != 2:
        raise ValueError("own_hole must contain exactly two cards")
    hole = (
        _require_plain_int(own_hole[0], "own_hole[0]"),
        _require_plain_int(own_hole[1], "own_hole[1]"),
    )
    board = tuple(
        _require_plain_int(card, f"board[{index}]")
        for index, card in enumerate(public_state.board)
    )
    cards = hole + board
    if any(card < 0 or card >= 52 for card in cards):
        raise ValueError("cards must use canonical indices 0..51")
    if len(set(cards)) != len(cards):
        raise ValueError("own_hole and board cards must be distinct")

    pot_cents = _require_plain_int(public_state.pot_cents, "pot_cents")
    if pot_cents <= 0:
        raise ValueError("pot_cents must be positive")
    start = _require_plain_int(
        public_state.starting_stack_cents, "starting_stack_cents"
    )
    if start != H11_STARTING_STACK_CENTS:
        raise ValueError(
            f"H11 requires starting_stack_cents={H11_STARTING_STACK_CENTS}"
        )
    if len(public_state.stacks_cents) != 2:
        raise ValueError("stacks_cents must contain exactly two entries")
    for index, stack in enumerate(public_state.stacks_cents):
        stack_int = _require_plain_int(stack, f"stacks_cents[{index}]")
        if stack_int < 0 or stack_int > start:
            raise ValueError("stack must be in [0, starting_stack_cents]")

    if len(public_state.actions_by_street) != NUM_STREETS:
        raise ValueError("actions_by_street must contain exactly four streets")
    for street_index, actions in enumerate(public_state.actions_by_street):
        if street_index > street and actions:
            raise ValueError("future streets must not contain actions")
        if len(actions) > MAX_ACTIONS_PER_STREET:
            raise ValueError("V5.5 cannot represent more than six actions per street")
        for action_index, action in enumerate(actions):
            if not isinstance(action, PublicActionRecord):
                raise TypeError("every public action must be PublicActionRecord")
            player = _require_plain_int(
                action.player, f"actions[{street_index}][{action_index}].player"
            )
            action_type = _require_plain_int(
                action.action_type,
                f"actions[{street_index}][{action_index}].action_type",
            )
            amount = _require_plain_int(
                action.amount_cents,
                f"actions[{street_index}][{action_index}].amount_cents",
            )
            if player not in (0, 1):
                raise ValueError("action player must be 0 or 1")
            if action_type not in range(6):
                raise ValueError("action_type must be in [0, 5]")
            if amount < 0:
                raise ValueError("action amount must be nonnegative")
            if action_type <= 2 and amount != 0:
                raise ValueError("fold/check/call amount_cents must be zero")
            if action_type >= 3 and amount <= 0:
                raise ValueError("bet/raise/all-in amount_cents must be positive")

    mask = np.asarray(legal_mask, dtype=np.float32)
    if mask.shape != (NUM_ACTIONS,):
        raise ValueError("legal_mask must have shape (9,)")
    if not np.isfinite(mask).all():
        raise ValueError("legal_mask must be finite")
    if not np.logical_or(mask == 0.0, mask == 1.0).all():
        raise ValueError("legal_mask must be exactly binary")
    if int(mask.sum()) < 1:
        raise ValueError("legal_mask must enable at least one slot")

    return hole, np.ascontiguousarray(mask)


def _set_card(tensor: np.ndarray, channel: int, card: int) -> None:
    tensor[channel, card % NUM_SUITS, card // NUM_SUITS] = np.float32(1.0)


def encode_h11_tensors(
    public_state: PublicLikelihoodState,
    acting_player: int,
    own_hole: Sequence[int],
    legal_mask: Sequence[float],
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Build the exact four frozen V5.5 network inputs on CPU.

    Returned tensors are contiguous float32 tensors with a leading batch
    dimension of one.
    """

    hole, mask = _validate_public_inputs(
        public_state, acting_player, own_hole, legal_mask
    )

    cards = np.zeros(
        (NUM_CARD_CHANNELS, NUM_SUITS, NUM_RANKS), dtype=np.float32
    )
    for card in hole:
        _set_card(cards, 0, card)
        _set_card(cards, 5, card)
    board = public_state.board
    if len(board) >= 3:
        for card in board[:3]:
            _set_card(cards, 1, card)
    if len(board) >= 4:
        _set_card(cards, 2, board[3])
    if len(board) >= 5:
        _set_card(cards, 3, board[4])
    for card in board:
        _set_card(cards, 4, card)
        _set_card(cards, 5, card)

    history = np.zeros(
        (ACTION_HISTORY_CHANNELS, NUM_STREETS, 5), dtype=np.float32
    )
    pot_denominator_cents = max(public_state.pot_cents, 100)
    for street_index, actions in enumerate(public_state.actions_by_street):
        for slot, action in enumerate(actions):
            channel = street_index * MAX_ACTIONS_PER_STREET + slot
            history[channel, 0, 0] = np.float32(
                1.0 if action.player == acting_player else 0.0
            )
            history[channel, 1, min(action.action_type, 4)] = np.float32(1.0)
            if action.amount_cents > 0:
                fraction = action.amount_cents / pot_denominator_cents
                history[channel, 2, 0] = np.float32(min(fraction, 2.0) / 2.0)
            history[channel, 3, 0] = np.float32(1.0)
    history[ACTION_HISTORY_CHANNELS - 1, 0, 0] = np.float32(1.0)

    hero_stack = public_state.stacks_cents[acting_player]
    villain_stack = public_state.stacks_cents[1 - acting_player]
    start = public_state.starting_stack_cents
    extra = np.asarray(
        [hero_stack / start, villain_stack / start], dtype=np.float32
    )

    return (
        torch.from_numpy(np.ascontiguousarray(cards[None, ...])),
        torch.from_numpy(np.ascontiguousarray(history[None, ...])),
        torch.from_numpy(np.ascontiguousarray(extra[None, ...])),
        torch.from_numpy(np.ascontiguousarray(mask[None, ...])),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1 << 20)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _strict_load_h11() -> AlphaHoldemNet:
    if not H11_CHECKPOINT_PATH.is_file():
        raise FileNotFoundError(f"missing exact H11 checkpoint: {H11_CHECKPOINT_PATH}")
    observed_sha = _sha256_file(H11_CHECKPOINT_PATH)
    if observed_sha != H11_CHECKPOINT_SHA256:
        raise RuntimeError(
            f"H11 checkpoint SHA mismatch: {observed_sha} != "
            f"{H11_CHECKPOINT_SHA256}"
        )

    checkpoint = torch.load(
        H11_CHECKPOINT_PATH,
        map_location="cpu",
        weights_only=True,
    )
    exact_metadata = {
        "iteration": H11_ITERATION,
        "total_hands": H11_TOTAL_HANDS,
        "env_version": "v55",
        "obs_version": "v55",
        "action_space_version": "9slot_v5",
        "critic_contract": CRITIC_V1,
        "starting_stack_bb": 200.0,
    }
    for key, expected in exact_metadata.items():
        if checkpoint.get(key) != expected:
            raise RuntimeError(
                f"H11 checkpoint metadata mismatch for {key}: "
                f"{checkpoint.get(key)!r} != {expected!r}"
            )
    state_dict = checkpoint.get("model")
    if not isinstance(state_dict, dict):
        raise RuntimeError("H11 checkpoint has no model state_dict")

    # Meta-device construction and shape materialization consume no RNG.  The
    # CPU tensors from the exact checkpoint are then assigned directly.
    with torch.device("meta"):
        model = AlphaHoldemNet(num_actions=NUM_ACTIONS, critic_contract=CRITIC_V1)
        model(
            torch.zeros((1, 6, 4, 13), device="meta"),
            torch.zeros((1, 25, 4, 5), device="meta"),
            torch.zeros((1, 2), device="meta"),
            torch.ones((1, NUM_ACTIONS), device="meta"),
        )
    model.load_state_dict(state_dict, strict=True, assign=True)
    model.eval()
    model.requires_grad_(False)
    if any(parameter.device.type != "cpu" for parameter in model.parameters()):
        raise RuntimeError("H11 likelihood model must remain on CPU")
    return model


_MODEL: AlphaHoldemNet | None = None
_MODEL_LOCK = threading.Lock()


def _exact_h11_model() -> AlphaHoldemNet:
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                _MODEL = _strict_load_h11()
    return _MODEL


def evaluate_h11_log_probs(
    public_state: PublicLikelihoodState,
    acting_player: int,
    own_hole: Sequence[int],
    legal_mask: Sequence[float],
) -> np.ndarray:
    """Return canonical float64 masked log-probabilities for all nine slots."""

    cards, history, extra, mask = encode_h11_tensors(
        public_state, acting_player, own_hole, legal_mask
    )
    model = _exact_h11_model()
    with torch.inference_mode():
        logits, _ = model(cards, history, extra, None)
    logits64 = logits[0].detach().to(device="cpu", dtype=torch.float64)
    legal = mask[0].to(dtype=torch.bool)
    legal_logits = logits64[legal]
    log_normalizer = torch.logsumexp(legal_logits, dim=0)
    result = torch.full(
        (NUM_ACTIONS,), float("-inf"), dtype=torch.float64, device="cpu"
    )
    result[legal] = legal_logits - log_normalizer
    output = result.numpy().copy()
    if output.dtype != np.float64:
        raise RuntimeError("internal error: log-probabilities are not float64")
    if not np.isfinite(output[np.asarray(legal_mask, dtype=bool)]).all():
        raise RuntimeError("internal error: legal log-probability is nonfinite")
    return output


__all__ = [
    "H11_CHECKPOINT_PATH",
    "H11_CHECKPOINT_SHA256",
    "LRFT_I00_IDENTITY",
    "LRFT_I00_TOKEN",
    "PublicActionRecord",
    "PublicLikelihoodState",
    "encode_h11_tensors",
    "evaluate_h11_log_probs",
]
