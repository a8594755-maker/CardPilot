"""Fresh fixed-batch H11 likelihood correction for LRFT-I00C1.

Every forward pass has exactly 256 rows. Short inputs are padded by duplicating
their final validated row, and padding outputs are discarded. This removes the
terminal parent's batch-shape-dependent inference contract without changing the
checkpoint, observation, legal mask, logits, or normalization equations.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import threading
from typing import Sequence

import numpy as np
import torch

from .network_hybrid_h1 import AlphaHoldemNet, CRITIC_V1


LRFT_I00C1_IDENTITY = (
    "5d1ead27b90a8a2485ae4128d602bf26d50c3a42455e7e289a5dd44429b87a6d"
)
LRFT_I00C1_TOKEN = "5d1ead27b90a8a2485ae4128d602bf26"
PARENT_IDENTITY = (
    "a0354ffed044c37ee5cc17a3d045273ecf7751f256a0199f23140d311e55f704"
)
PARENT_RESULT_SHA256 = (
    "2c30c5570cb39e6b4286f6d5800addf860ec6420c32b3e95a0fd05226883e837"
)
SOLE_CORRECTION = "FIXED_BATCH_256_CANONICAL_DUPLICATE_PADDING"

H11_CHECKPOINT_SHA256 = (
    "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
)
H11_ITERATION = 35_051
H11_TOTAL_HANDS = 576_021_901
H11_STARTING_STACK_CENTS = 20_000
CANONICAL_BATCH_SIZE = 256
NUM_ACTIONS = 9
NUM_STREETS = 4
MAX_ACTIONS_PER_STREET = 6
ACTION_HISTORY_CHANNELS = 25

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
    player: int
    action_type: int
    amount_cents: int = 0


@dataclass(frozen=True, slots=True)
class PublicLikelihoodState:
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


def _plain_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be a plain int")
    return value


def _validate(
    public_state: PublicLikelihoodState,
    acting_player: int,
    own_hole: Sequence[int],
    legal_mask: Sequence[float],
) -> tuple[tuple[int, int], np.ndarray]:
    if not isinstance(public_state, PublicLikelihoodState):
        raise TypeError("public_state must be PublicLikelihoodState")
    acting = _plain_int(acting_player, "acting_player")
    if acting not in (0, 1) or public_state.current_player != acting:
        raise ValueError("acting player mismatch")
    if public_state.button not in (0, 1):
        raise ValueError("button")
    street = _plain_int(public_state.street, "street")
    if street not in range(4):
        raise ValueError("street")
    if len(public_state.board) != (0, 3, 4, 5)[street]:
        raise ValueError("board/street")
    if len(own_hole) != 2:
        raise ValueError("own_hole shape")
    hole = (
        _plain_int(own_hole[0], "own_hole[0]"),
        _plain_int(own_hole[1], "own_hole[1]"),
    )
    board = tuple(
        _plain_int(card, f"board[{index}]")
        for index, card in enumerate(public_state.board)
    )
    if any(card < 0 or card >= 52 for card in hole + board):
        raise ValueError("card range")
    if len(set(hole + board)) != len(hole + board):
        raise ValueError("card collision")
    if public_state.starting_stack_cents != H11_STARTING_STACK_CENTS:
        raise ValueError("starting stack")
    if public_state.pot_cents <= 0:
        raise ValueError("pot")
    if (
        len(public_state.stacks_cents) != 2
        or any(
            _plain_int(stack, f"stack[{index}]") < 0
            or stack > H11_STARTING_STACK_CENTS
            for index, stack in enumerate(public_state.stacks_cents)
        )
    ):
        raise ValueError("stacks")
    if len(public_state.actions_by_street) != 4:
        raise ValueError("actions_by_street")
    for street_index, records in enumerate(public_state.actions_by_street):
        if street_index > street and records:
            raise ValueError("future action")
        if len(records) > MAX_ACTIONS_PER_STREET:
            raise ValueError("V5.5 action-history overflow")
        for record in records:
            if not isinstance(record, PublicActionRecord):
                raise TypeError("public action record")
            if record.player not in (0, 1) or record.action_type not in range(6):
                raise ValueError("public action fields")
            if not isinstance(record.amount_cents, int) or record.amount_cents < 0:
                raise ValueError("public action amount")
            if record.action_type <= 2 and record.amount_cents != 0:
                raise ValueError("passive amount")
            if record.action_type >= 3 and record.amount_cents <= 0:
                raise ValueError("aggressive amount")
    mask = np.asarray(legal_mask, dtype=np.float32)
    if (
        mask.shape != (9,)
        or not np.isfinite(mask).all()
        or not np.logical_or(mask == 0.0, mask == 1.0).all()
        or int(mask.sum()) < 1
    ):
        raise ValueError("legal mask")
    return hole, np.ascontiguousarray(mask)


def _set_card(array: np.ndarray, channel: int, card: int) -> None:
    array[channel, card % 4, card // 4] = np.float32(1.0)


def encode_h11_tensors(
    public_state: PublicLikelihoodState,
    acting_player: int,
    own_hole: Sequence[int],
    legal_mask: Sequence[float],
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    hole, mask = _validate(public_state, acting_player, own_hole, legal_mask)
    cards = np.zeros((6, 4, 13), dtype=np.float32)
    for card in hole:
        _set_card(cards, 0, card)
        _set_card(cards, 5, card)
    for index, card in enumerate(public_state.board):
        _set_card(cards, 1 if index < 3 else 2 if index == 3 else 3, card)
        _set_card(cards, 4, card)
        _set_card(cards, 5, card)

    history = np.zeros((25, 4, 5), dtype=np.float32)
    for street_index, records in enumerate(public_state.actions_by_street):
        for slot, record in enumerate(records):
            channel = street_index * 6 + slot
            history[channel, 0, 0] = np.float32(
                1.0 if record.player == acting_player else 0.0
            )
            history[channel, 1, min(record.action_type, 4)] = np.float32(1.0)
            if record.amount_cents:
                history[channel, 2, 0] = np.float32(
                    min(record.amount_cents / max(public_state.pot_cents, 100), 2.0)
                    / 2.0
                )
            history[channel, 3, 0] = np.float32(1.0)
    history[24, 0, 0] = np.float32(1.0)
    extra = np.asarray(
        [
            public_state.stacks_cents[acting_player] / H11_STARTING_STACK_CENTS,
            public_state.stacks_cents[1 - acting_player] / H11_STARTING_STACK_CENTS,
        ],
        dtype=np.float32,
    )
    return (
        torch.from_numpy(np.ascontiguousarray(cards[None])),
        torch.from_numpy(np.ascontiguousarray(history[None])),
        torch.from_numpy(np.ascontiguousarray(extra[None])),
        torch.from_numpy(np.ascontiguousarray(mask[None])),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _strict_load_h11() -> AlphaHoldemNet:
    if _sha256_file(H11_CHECKPOINT_PATH) != H11_CHECKPOINT_SHA256:
        raise RuntimeError("H11 checkpoint SHA mismatch")
    checkpoint = torch.load(H11_CHECKPOINT_PATH, map_location="cpu", weights_only=True)
    expected = {
        "iteration": H11_ITERATION,
        "total_hands": H11_TOTAL_HANDS,
        "env_version": "v55",
        "obs_version": "v55",
        "action_space_version": "9slot_v5",
        "critic_contract": CRITIC_V1,
        "starting_stack_bb": 200.0,
    }
    if any(checkpoint.get(key) != value for key, value in expected.items()):
        raise RuntimeError("H11 metadata mismatch")
    with torch.device("meta"):
        model = AlphaHoldemNet(num_actions=9, critic_contract=CRITIC_V1)
        model(
            torch.zeros((CANONICAL_BATCH_SIZE, 6, 4, 13), device="meta"),
            torch.zeros((CANONICAL_BATCH_SIZE, 25, 4, 5), device="meta"),
            torch.zeros((CANONICAL_BATCH_SIZE, 2), device="meta"),
            torch.ones((CANONICAL_BATCH_SIZE, 9), device="meta"),
        )
    model.load_state_dict(checkpoint["model"], strict=True, assign=True)
    model.eval().requires_grad_(False)
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


def _normalized_log_probs(logits: torch.Tensor, masks: torch.Tensor) -> np.ndarray:
    outputs = torch.full(
        logits.shape, float("-inf"), dtype=torch.float64, device="cpu"
    )
    rows = logits.detach().cpu().to(dtype=torch.float64)
    legal = masks.detach().cpu().to(dtype=torch.bool)
    for index in range(rows.shape[0]):
        outputs[index, legal[index]] = (
            rows[index, legal[index]]
            - torch.logsumexp(rows[index, legal[index]], dim=0)
        )
    result = outputs.numpy().copy()
    if not np.isfinite(result[legal.numpy()]).all():
        raise RuntimeError("nonfinite legal log probability")
    return result


def evaluate_h11_log_probs_batch(
    public_states: Sequence[PublicLikelihoodState],
    acting_players: Sequence[int],
    own_holes: Sequence[Sequence[int]],
    legal_masks: Sequence[Sequence[float]],
) -> np.ndarray:
    """Evaluate in exact 256-row chunks with canonical final-row padding."""
    count = len(public_states)
    if (
        count < 1
        or len(acting_players) != count
        or len(own_holes) != count
        or len(legal_masks) != count
    ):
        raise ValueError("parallel input lengths")
    encoded = [
        encode_h11_tensors(state, actor, hole, mask)
        for state, actor, hole, mask in zip(
            public_states, acting_players, own_holes, legal_masks, strict=True
        )
    ]
    model = _exact_h11_model()
    chunks: list[np.ndarray] = []
    for start in range(0, count, CANONICAL_BATCH_SIZE):
        rows = encoded[start:start + CANONICAL_BATCH_SIZE]
        real_count = len(rows)
        if real_count < CANONICAL_BATCH_SIZE:
            rows = rows + [rows[-1]] * (CANONICAL_BATCH_SIZE - real_count)
        cards = torch.cat([row[0] for row in rows])
        histories = torch.cat([row[1] for row in rows])
        extras = torch.cat([row[2] for row in rows])
        masks = torch.cat([row[3] for row in rows])
        with torch.inference_mode():
            logits, _ = model(cards, histories, extras, None)
        chunks.append(_normalized_log_probs(logits, masks)[:real_count])
    return np.concatenate(chunks, axis=0)


def evaluate_h11_log_probs(
    public_state: PublicLikelihoodState,
    acting_player: int,
    own_hole: Sequence[int],
    legal_mask: Sequence[float],
) -> np.ndarray:
    return evaluate_h11_log_probs_batch(
        [public_state], [acting_player], [own_hole], [legal_mask]
    )[0]


__all__ = [
    "CANONICAL_BATCH_SIZE",
    "H11_CHECKPOINT_PATH",
    "H11_CHECKPOINT_SHA256",
    "LRFT_I00C1_IDENTITY",
    "LRFT_I00C1_TOKEN",
    "PARENT_IDENTITY",
    "PARENT_RESULT_SHA256",
    "PublicActionRecord",
    "PublicLikelihoodState",
    "SOLE_CORRECTION",
    "encode_h11_tensors",
    "evaluate_h11_log_probs",
    "evaluate_h11_log_probs_batch",
]
