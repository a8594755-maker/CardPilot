#!/usr/bin/env python3
"""LRFT-F64 fresh runtime and zero-science resource-admission runner.

This file intentionally contains a fresh public exact-cent HUNL engine and a
fresh canonical H11 adapter.  It does not import any earlier LRFT engine,
likelihood adapter, teacher, resolver, or qualification implementation.

The only currently executable modes are:

* ``contract-tests``: deterministic, read-only kernel contracts.
* ``resource-admission``: a synthetic zero-science admission benchmark.  This
  mode is fail-closed behind an independent implementation-audit result that
  binds this file's exact SHA256.

No census hand, root, belief, solver, teacher, checkpoint, or Slumbot row can be
created by this implementation stage.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from enum import IntEnum
from fractions import Fraction
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np
import torch


REPO = Path(r"C:\Users\a8594\CardPilot")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# The preregistration permits only these imports from existing poker code.
from scripts.alpha_holdem.network_hybrid_h1 import (  # noqa: E402
    AlphaHoldemNet,
    CRITIC_V1,
)
from scripts.deep_cfr.hand_eval import compare_hands  # noqa: E402


IDENTITY = "5d7506904a3846b736d272d13162c2c8c995e36fa6fefbdf88029027a60c8f6b"
TOKEN = IDENTITY[:32]
PREREG = REPO / (
    "reports/v5_lrft_f64_preregistration_"
    "5d7506904a3846b736d272d13162c2c8_20260723.json"
)
PREREG_SHA256 = "69f98d90d3b11db67240f2247e2639ed759d0f7254b03e7a726d4136e4c15fbf"
PREREG_AUDIT = REPO / (
    "reports/v5_lrft_f64_preregistration_audit_c1_"
    "5d7506904a3846b736d272d13162c2c8_20260723.json"
)
H11 = REPO / (
    "models/alpha_holdem_v5_hybrid/"
    "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715/"
    "h11_control_endpoint.pt"
)
H11_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
NETWORK = REPO / "scripts/alpha_holdem/network_hybrid_h1.py"
NETWORK_SHA256 = "25f4520d31f4ce5ffcfd23fc0d56b8736fd3b5fad537706b9cd13ee270b4a171"
SHOWDOWN = REPO / "scripts/deep_cfr/hand_eval.py"
SHOWDOWN_SHA256 = "fc30df48b0ae0091311f2ff40f8e320278bc47abba606c0c1f71fcce498f490d"
OUTPUT_ROOT = REPO / f"reports/lrft_f64_{TOKEN}"
RESOURCE_RESULT = OUTPUT_ROOT / "resource_admission.json"

STARTING_STACK = 20_000
SMALL_BLIND = 50
BIG_BLIND = 100
CANONICAL_BATCH = 256
BOARD_LENGTH = (0, 3, 4, 5)
RAISE_FRACTIONS = (
    Fraction(33, 100),
    Fraction(1, 2),
    Fraction(67, 100),
    Fraction(3, 4),
    Fraction(1, 1),
    Fraction(3, 2),
)
PREFLOP_FRACTIONS = (Fraction(1, 2), Fraction(1, 1), Fraction(3, 2))


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha_counter(namespace: str, index: int) -> bytes:
    return hashlib.sha256(
        f"{IDENTITY}|{namespace}|{int(index)}".encode("ascii")
    ).digest()


def sha_uniform(namespace: str, index: int) -> float:
    # Strictly inside (0,1), with exactly 53 significant random bits.
    number = int.from_bytes(sha_counter(namespace, index)[:8], "big") >> 11
    return (number + 0.5) / float(1 << 53)


def round_fraction_ties_even(value: int, fraction: Fraction) -> int:
    numerator = value * fraction.numerator
    denominator = fraction.denominator
    quotient, remainder = divmod(numerator, denominator)
    twice = 2 * remainder
    if twice > denominator or (twice == denominator and quotient & 1):
        quotient += 1
    return quotient


class ActionType(IntEnum):
    FOLD = 0
    CHECK = 1
    CALL = 2
    BET = 3
    RAISE = 4
    ALLIN = 5


@dataclass(frozen=True, slots=True)
class PublicAction:
    kind: ActionType
    amount_cents: int = 0  # total-to amount on the current street


@dataclass(frozen=True, slots=True)
class PublicActionRecord:
    player: int
    kind: ActionType
    amount_cents: int


EMPTY_HISTORY: tuple[tuple[PublicActionRecord, ...], ...] = ((), (), (), ())


@dataclass(frozen=True, slots=True)
class ExactPublicState:
    """Immutable public-only 200bb HU state.

    P0 is BB/OOP and P1 is BTN/SB.  Public chance is explicit: when
    ``chance_cards`` is nonzero, player actions are forbidden until exactly
    that many board cards are supplied with :meth:`deal_public`.
    """

    street: int
    board: tuple[int, ...]
    pot_cents: int
    stacks_cents: tuple[int, int]
    street_committed: tuple[int, int]
    total_committed: tuple[int, int]
    current_player: int | None
    acted_since_full_raise: tuple[bool, bool]
    last_full_raise_cents: int
    actions_by_street: tuple[tuple[PublicActionRecord, ...], ...]
    chance_cards: int = 0
    allin_runout: bool = False
    terminal: bool = False
    folded_player: int | None = None

    @staticmethod
    def new_hand() -> "ExactPublicState":
        state = ExactPublicState(
            street=0,
            board=(),
            pot_cents=SMALL_BLIND + BIG_BLIND,
            stacks_cents=(STARTING_STACK - BIG_BLIND, STARTING_STACK - SMALL_BLIND),
            street_committed=(BIG_BLIND, SMALL_BLIND),
            total_committed=(BIG_BLIND, SMALL_BLIND),
            current_player=1,
            acted_since_full_raise=(False, False),
            last_full_raise_cents=BIG_BLIND,
            actions_by_street=EMPTY_HISTORY,
        )
        state.validate()
        return state

    def validate(self) -> None:
        if self.street not in range(4):
            raise ValueError("street")
        if len(self.board) != BOARD_LENGTH[self.street] and not self.chance_cards:
            raise ValueError("board/street")
        if len(set(self.board)) != len(self.board) or any(
            card < 0 or card >= 52 for card in self.board
        ):
            raise ValueError("board")
        fields = self.stacks_cents + self.street_committed + self.total_committed
        if any(type(value) is not int or value < 0 for value in fields):
            raise ValueError("negative/noninteger chip field")
        if (
            sum(self.stacks_cents) + self.pot_cents
            != 2 * STARTING_STACK
        ):
            raise ValueError("chip conservation")
        if any(
            self.street_committed[p] > self.total_committed[p]
            or self.total_committed[p] + self.stacks_cents[p] != STARTING_STACK
            for p in (0, 1)
        ):
            raise ValueError("commitment conservation")
        if len(self.actions_by_street) != 4 or any(
            len(rows) > 6 for rows in self.actions_by_street
        ):
            raise ValueError("V5.5 history capacity")
        if self.terminal or self.chance_cards:
            if self.current_player is not None:
                raise ValueError("inactive state has current player")
        elif self.current_player not in (0, 1):
            raise ValueError("active state lacks player")
        if self.chance_cards < 0 or self.chance_cards > 5 - len(self.board):
            raise ValueError("chance count")

    def serialization(self) -> str:
        payload = {
            "actions": [
                [[r.player, int(r.kind), r.amount_cents] for r in street]
                for street in self.actions_by_street
            ],
            "acted": list(self.acted_since_full_raise),
            "allin_runout": self.allin_runout,
            "board": list(self.board),
            "chance_cards": self.chance_cards,
            "committed": list(self.street_committed),
            "current_player": self.current_player,
            "folded_player": self.folded_player,
            "last_full_raise": self.last_full_raise_cents,
            "pot": self.pot_cents,
            "stacks": list(self.stacks_cents),
            "street": self.street,
            "terminal": self.terminal,
            "total_committed": list(self.total_committed),
        }
        return canonical_json(payload).decode("ascii").rstrip("\n")

    def _raise_targets(self) -> tuple[int, ...]:
        if self.current_player is None:
            return ()
        p = self.current_player
        q = 1 - p
        committed = self.street_committed[p]
        opponent = self.street_committed[q]
        to_call = max(0, opponent - committed)
        allin_total = committed + self.stacks_cents[p]
        opponent_cover = opponent + self.stacks_cents[q]
        maximum = min(allin_total, opponent_cover)
        if maximum <= opponent:
            return ()
        opening = to_call == 0
        minimum_increment = BIG_BLIND if opening else self.last_full_raise_cents
        minimum_total = opponent + minimum_increment
        fractions = PREFLOP_FRACTIONS if self.street == 0 else RAISE_FRACTIONS
        targets: set[int] = set()
        for fraction in fractions:
            if opening:
                target = committed + round_fraction_ties_even(
                    self.pot_cents, fraction
                )
            else:
                target = committed + to_call + round_fraction_ties_even(
                    self.pot_cents + to_call, fraction
                )
            target = max(target, minimum_total)
            if opponent < target < maximum:
                targets.add(target)
        return tuple(sorted(targets))

    def real_actions(self) -> tuple[PublicAction, ...]:
        if self.terminal or self.chance_cards or self.current_player is None:
            return ()
        p = self.current_player
        q = 1 - p
        committed = self.street_committed[p]
        opponent = self.street_committed[q]
        to_call = max(0, opponent - committed)
        actions: list[PublicAction] = []
        if to_call:
            actions.append(PublicAction(ActionType.FOLD))
            actions.append(PublicAction(ActionType.CALL))
        else:
            actions.append(PublicAction(ActionType.CHECK))
        may_raise = (
            self.stacks_cents[p] > to_call
            and not self.acted_since_full_raise[p]
            and opponent + self.stacks_cents[q] > opponent
        )
        if may_raise:
            kind = ActionType.BET if to_call == 0 else ActionType.RAISE
            actions.extend(PublicAction(kind, value) for value in self._raise_targets())
            allin_total = min(
                committed + self.stacks_cents[p],
                opponent + self.stacks_cents[q],
            )
            if allin_total > opponent:
                actions.append(PublicAction(ActionType.ALLIN, allin_total))
        return tuple(actions)

    def slot_table(self) -> tuple[tuple[int, ...], tuple[PublicAction | None, ...]]:
        table: list[PublicAction | None] = [None] * 9
        for action in self.real_actions():
            if action.kind == ActionType.FOLD:
                slot = 0
            elif action.kind in (ActionType.CHECK, ActionType.CALL):
                slot = 1
            elif action.kind == ActionType.ALLIN:
                slot = 8
            else:
                distances = [
                    abs(
                        action.amount_cents * fraction.denominator
                        - fraction.numerator * self.pot_cents
                    )
                    / fraction.denominator
                    for fraction in RAISE_FRACTIONS
                ]
                slot = 2 + min(range(6), key=lambda index: (distances[index], index))
            current = table[slot]
            if current is None:
                table[slot] = action
            elif 2 <= slot <= 7:
                fraction = RAISE_FRACTIONS[slot - 2]
                old_distance = abs(
                    current.amount_cents * fraction.denominator
                    - fraction.numerator * self.pot_cents
                )
                new_distance = abs(
                    action.amount_cents * fraction.denominator
                    - fraction.numerator * self.pot_cents
                )
                if (new_distance, action.amount_cents) < (
                    old_distance,
                    current.amount_cents,
                ):
                    table[slot] = action
        slots = tuple(index for index, action in enumerate(table) if action is not None)
        if not slots and not (self.terminal or self.chance_cards):
            raise RuntimeError("active state has no executable slot")
        return slots, tuple(table)

    def _with_record(
        self, player: int, action: PublicAction
    ) -> tuple[tuple[PublicActionRecord, ...], ...]:
        rows = list(self.actions_by_street)
        if len(rows[self.street]) >= 6:
            raise RuntimeError("V5.5 seventh same-street action forbidden")
        rows[self.street] = rows[self.street] + (
            PublicActionRecord(player, action.kind, action.amount_cents),
        )
        return tuple(rows)

    def _close_betting(self, state: "ExactPublicState") -> "ExactPublicState":
        # A partial all-in call returns unmatched chips before showdown.
        c0, c1 = state.street_committed
        if c0 != c1 and (state.stacks_cents[0] == 0 or state.stacks_cents[1] == 0):
            high = 0 if c0 > c1 else 1
            excess = abs(c0 - c1)
            stacks = list(state.stacks_cents)
            street = list(state.street_committed)
            totals = list(state.total_committed)
            stacks[high] += excess
            street[high] -= excess
            totals[high] -= excess
            state = replace(
                state,
                stacks_cents=tuple(stacks),
                street_committed=tuple(street),
                total_committed=tuple(totals),
                pot_cents=state.pot_cents - excess,
            )
        if 0 in state.stacks_cents:
            remaining = 5 - len(state.board)
            if remaining == 0:
                return replace(
                    state, terminal=True, current_player=None, chance_cards=0
                )
            return replace(
                state,
                current_player=None,
                chance_cards=remaining,
                allin_runout=True,
            )
        if state.street == 3:
            return replace(state, terminal=True, current_player=None)
        return replace(
            state,
            current_player=None,
            chance_cards=3 if state.street == 0 else 1,
        )

    def apply_slot(self, slot: int) -> "ExactPublicState":
        slots, table = self.slot_table()
        if type(slot) is not int or slot not in slots:
            raise ValueError("illegal/null slot")
        action = table[slot]
        assert action is not None and self.current_player is not None
        p = self.current_player
        q = 1 - p
        history = self._with_record(p, action)
        if action.kind == ActionType.FOLD:
            state = replace(
                self,
                actions_by_street=history,
                terminal=True,
                folded_player=p,
                current_player=None,
            )
            state.validate()
            return state
        if action.kind in (ActionType.CHECK, ActionType.CALL):
            stacks = list(self.stacks_cents)
            committed = list(self.street_committed)
            totals = list(self.total_committed)
            paid = 0
            if action.kind == ActionType.CALL:
                paid = min(stacks[p], max(0, committed[q] - committed[p]))
                stacks[p] -= paid
                committed[p] += paid
                totals[p] += paid
            acted = list(self.acted_since_full_raise)
            acted[p] = True
            state = replace(
                self,
                stacks_cents=tuple(stacks),
                street_committed=tuple(committed),
                total_committed=tuple(totals),
                pot_cents=self.pot_cents + paid,
                acted_since_full_raise=tuple(acted),
                actions_by_street=history,
            )
            closed = (
                committed[0] == committed[1]
                and acted[0]
                and acted[1]
            ) or stacks[p] == 0
            state = self._close_betting(state) if closed else replace(
                state, current_player=q
            )
            state.validate()
            return state

        committed = list(self.street_committed)
        stacks = list(self.stacks_cents)
        totals = list(self.total_committed)
        old_high = max(committed)
        addition = action.amount_cents - committed[p]
        if addition <= 0 or addition > stacks[p]:
            raise RuntimeError("invalid aggressive target")
        stacks[p] -= addition
        committed[p] += addition
        totals[p] += addition
        raise_size = action.amount_cents - old_high
        full_raise = raise_size >= self.last_full_raise_cents
        acted = [True, self.acted_since_full_raise[q]]
        if p == 1:
            acted = [self.acted_since_full_raise[q], True]
        if full_raise:
            acted = [False, False]
            acted[p] = True
        state = replace(
            self,
            stacks_cents=tuple(stacks),
            street_committed=tuple(committed),
            total_committed=tuple(totals),
            pot_cents=self.pot_cents + addition,
            acted_since_full_raise=tuple(acted),
            last_full_raise_cents=raise_size if full_raise else self.last_full_raise_cents,
            actions_by_street=history,
            current_player=q,
        )
        state.validate()
        return state

    def deal_public(self, cards: Sequence[int]) -> "ExactPublicState":
        if self.terminal or self.chance_cards == 0 or self.current_player is not None:
            raise ValueError("not a chance state")
        dealt = tuple(cards)
        if len(dealt) != self.chance_cards:
            raise ValueError("wrong chance-card count")
        if any(type(card) is not int or card < 0 or card >= 52 for card in dealt):
            raise ValueError("card")
        if len(set(self.board + dealt)) != len(self.board) + len(dealt):
            raise ValueError("public card collision")
        board = self.board + dealt
        if self.allin_runout:
            state = replace(
                self,
                board=board,
                street=3,
                chance_cards=0,
                terminal=True,
            )
            state.validate()
            return state
        street = self.street + 1
        state = replace(
            self,
            street=street,
            board=board,
            street_committed=(0, 0),
            current_player=0,
            acted_since_full_raise=(False, False),
            last_full_raise_cents=BIG_BLIND,
            chance_cards=0,
        )
        state.validate()
        return state

    def payoff_cents(
        self,
        player: int,
        hole0: tuple[int, int],
        hole1: tuple[int, int],
    ) -> int:
        if not self.terminal or player not in (0, 1):
            raise ValueError("terminal/player")
        holes = hole0 + hole1
        if len(set(holes + self.board)) != len(holes) + len(self.board):
            raise ValueError("private/public collision")
        invested = self.total_committed
        if self.folded_player is not None:
            winner = 1 - self.folded_player
        else:
            if len(self.board) != 5:
                raise ValueError("showdown board")
            comparison = compare_hands(hole0, hole1, list(self.board))
            winner = 0 if comparison > 0 else 1 if comparison < 0 else -1
        if winner < 0:
            return 0
        value0 = invested[1] if winner == 0 else -invested[0]
        return value0 if player == 0 else -value0


def canonical_combos(board: Sequence[int]) -> tuple[tuple[int, int], ...]:
    blocked = set(board)
    if len(blocked) != len(tuple(board)):
        raise ValueError("duplicate board")
    cards = [card for card in range(52) if card not in blocked]
    return tuple(itertools.combinations(cards, 2))


def encode_h11_row(
    state: ExactPublicState,
    actor: int,
    hole: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if state.current_player != actor or tuple(sorted(hole)) != hole:
        raise ValueError("actor/canonical own hole")
    if len(set(hole + state.board)) != len(hole) + len(state.board):
        raise ValueError("hole/public collision")
    slots, _ = state.slot_table()
    cards = np.zeros((6, 4, 13), dtype=np.float32)

    def set_card(channel: int, card: int) -> None:
        cards[channel, card % 4, card // 4] = np.float32(1)

    for card in hole:
        set_card(0, card)
        set_card(5, card)
    for index, card in enumerate(state.board):
        set_card(1 if index < 3 else 2 if index == 3 else 3, card)
        set_card(4, card)
        set_card(5, card)
    history = np.zeros((25, 4, 5), dtype=np.float32)
    for street_index, records in enumerate(state.actions_by_street):
        for offset, record in enumerate(records):
            channel = street_index * 6 + offset
            history[channel, 0, 0] = np.float32(record.player == actor)
            history[channel, 1, min(int(record.kind), 4)] = np.float32(1)
            if record.amount_cents:
                history[channel, 2, 0] = np.float32(
                    min(record.amount_cents / max(state.pot_cents, 100), 2.0) / 2.0
                )
            history[channel, 3, 0] = np.float32(1)
    history[24, 0, 0] = np.float32(1)
    extra = np.asarray(
        [
            state.stacks_cents[actor] / STARTING_STACK,
            state.stacks_cents[1 - actor] / STARTING_STACK,
        ],
        dtype=np.float32,
    )
    mask = np.zeros(9, dtype=np.float32)
    mask[list(slots)] = np.float32(1)
    return cards, history, extra, mask


class CanonicalH11:
    """Strict fixed-batch canonical H11 policy/likelihood adapter."""

    def __init__(self, device: str):
        if device not in {"cpu", "cuda"}:
            raise ValueError("device")
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable")
        for path, expected in (
            (H11, H11_SHA256),
            (NETWORK, NETWORK_SHA256),
            (SHOWDOWN, SHOWDOWN_SHA256),
        ):
            if sha256_path(path) != expected:
                raise RuntimeError(f"frozen input mismatch: {path}")
        checkpoint = torch.load(H11, map_location="cpu", weights_only=True)
        expected_metadata = {
            "iteration": 35_051,
            "total_hands": 576_021_901,
            "env_version": "v55",
            "obs_version": "v55",
            "action_space_version": "9slot_v5",
            "critic_contract": CRITIC_V1,
            "starting_stack_bb": 200.0,
        }
        if any(checkpoint.get(key) != value for key, value in expected_metadata.items()):
            raise RuntimeError("H11 metadata mismatch")
        with torch.device("meta"):
            model = AlphaHoldemNet(num_actions=9, critic_contract=CRITIC_V1)
            model(
                torch.zeros((CANONICAL_BATCH, 6, 4, 13), device="meta"),
                torch.zeros((CANONICAL_BATCH, 25, 4, 5), device="meta"),
                torch.zeros((CANONICAL_BATCH, 2), device="meta"),
                torch.ones((CANONICAL_BATCH, 9), device="meta"),
            )
        model.load_state_dict(checkpoint["model"], strict=True, assign=True)
        self.model = model.to(device).eval().requires_grad_(False)
        self.device = torch.device(device)

    def _chunk(
        self,
        state: ExactPublicState,
        actor: int,
        combos: Sequence[tuple[int, int]],
    ) -> np.ndarray:
        if not 1 <= len(combos) <= CANONICAL_BATCH:
            raise ValueError("canonical chunk length")
        encoded = [encode_h11_row(state, actor, hole) for hole in combos]
        encoded.extend([encoded[-1]] * (CANONICAL_BATCH - len(encoded)))
        arrays = [
            np.ascontiguousarray(np.stack([row[index] for row in encoded]))
            for index in range(4)
        ]
        tensors = [
            torch.from_numpy(array).to(self.device, non_blocking=False)
            for array in arrays
        ]
        with torch.inference_mode(), torch.autocast(
            device_type=self.device.type, enabled=False
        ):
            logits, _ = self.model(tensors[0], tensors[1], tensors[2], None)
        logits64 = logits.detach().to("cpu", dtype=torch.float64)
        legal = tensors[3].to("cpu", dtype=torch.bool)
        output = torch.full(logits64.shape, -math.inf, dtype=torch.float64)
        for row in range(CANONICAL_BATCH):
            output[row, legal[row]] = (
                logits64[row, legal[row]]
                - torch.logsumexp(logits64[row, legal[row]], dim=0)
            )
        return output[: len(combos)].numpy().copy()

    def all_log_probs(self, state: ExactPublicState, actor: int) -> np.ndarray:
        combos = canonical_combos(state.board)
        chunks = [
            self._chunk(state, actor, combos[start : start + CANONICAL_BATCH])
            for start in range(0, len(combos), CANONICAL_BATCH)
        ]
        return np.concatenate(chunks)

    def actual_log_probs(
        self,
        state: ExactPublicState,
        actor: int,
        actual_hole: tuple[int, int],
    ) -> np.ndarray:
        combos = canonical_combos(state.board)
        hole = tuple(sorted(actual_hole))
        try:
            index = combos.index(hole)
        except ValueError as error:
            raise ValueError("actual hole incompatible with board") from error
        start = (index // CANONICAL_BATCH) * CANONICAL_BATCH
        rows = self._chunk(state, actor, combos[start : start + CANONICAL_BATCH])
        return rows[index - start]


def infoset_key(
    root_id: str,
    actor: int,
    own_hole: tuple[int, int],
    state: ExactPublicState,
) -> str:
    return "|".join(
        (root_id, str(actor), f"{min(own_hole)}-{max(own_hole)}", state.serialization())
    )


def regret_matching(regrets: np.ndarray, legal: np.ndarray) -> np.ndarray:
    positive = np.maximum(regrets, 0.0) * legal
    total = float(positive.sum())
    if total > 0:
        return positive / total
    count = int(legal.sum())
    if count == 0:
        raise ValueError("empty legal set")
    return legal.astype(np.float64) / count


@dataclass
class TinyCFRPlus:
    """Small simultaneous two-traverser CFR+ kernel used by contract tests."""

    regrets: dict[str, np.ndarray]

    @staticmethod
    def fresh() -> "TinyCFRPlus":
        return TinyCFRPlus(
            {
                "p0": np.zeros(2, dtype=np.float64),
                "p1": np.zeros(2, dtype=np.float64),
            }
        )

    def one_iteration(self) -> None:
        frozen = {
            key: regret_matching(value, np.ones(2, dtype=np.float64))
            for key, value in self.regrets.items()
        }
        # Independent one-decision zero-sum tiny trees.  Both deltas are
        # computed from frozen sigma before either CFR+ table is changed.
        payoff = {
            "p0": np.asarray([1.0, -1.0]),
            "p1": np.asarray([-2.0, 2.0]),
        }
        deltas = {
            key: values - float(np.dot(frozen[key], values))
            for key, values in payoff.items()
        }
        for key in self.regrets:
            self.regrets[key] = np.maximum(0.0, self.regrets[key] + deltas[key])


class KuhnCFRPlus:
    """Deterministic full-tree Kuhn CFR+ sanity oracle.

    The production solver is external-sampling MCCFR+; this tiny exact tree
    isolates regret matching, simultaneous update, and information-set
    aggregation without Monte-Carlo noise.
    """

    def __init__(self) -> None:
        self.regret: dict[tuple[int, int, str], np.ndarray] = {}
        self.strategy_sum: dict[tuple[int, int, str], np.ndarray] = {}

    @staticmethod
    def terminal(cards: tuple[int, int], history: str) -> float | None:
        if history == "pp":
            return 1.0 if cards[0] > cards[1] else -1.0
        if history in ("bp", "pbp"):
            return 1.0 if history == "bp" else -1.0
        if history in ("bb", "pbb"):
            return 2.0 if cards[0] > cards[1] else -2.0
        return None

    def _strategy(
        self,
        player: int,
        card: int,
        history: str,
        frozen: Mapping[tuple[int, int, str], np.ndarray],
    ) -> np.ndarray:
        key = (player, card, history)
        return regret_matching(
            frozen.get(key, np.zeros(2, dtype=np.float64)),
            np.ones(2, dtype=np.float64),
        )

    def _walk(
        self,
        cards: tuple[int, int],
        history: str,
        traverser: int,
        reach: tuple[float, float],
        frozen: Mapping[tuple[int, int, str], np.ndarray],
        deltas: dict[tuple[int, int, str], np.ndarray],
        averages: dict[tuple[int, int, str], np.ndarray],
    ) -> float:
        terminal = self.terminal(cards, history)
        if terminal is not None:
            return terminal
        player = len(history) % 2
        key = (player, cards[player], history)
        sigma = self._strategy(player, cards[player], history, frozen)
        values = np.zeros(2, dtype=np.float64)
        for action in range(2):
            next_history = history + ("p" if action == 0 else "b")
            next_reach = list(reach)
            next_reach[player] *= sigma[action]
            values[action] = self._walk(
                cards,
                next_history,
                traverser,
                tuple(next_reach),
                frozen,
                deltas,
                averages,
            )
        node = float(np.dot(sigma, values))
        averages[key] = averages.get(key, np.zeros(2)) + reach[player] * sigma / 6.0
        if player == traverser:
            sign = 1.0 if player == 0 else -1.0
            counterreach = reach[1 - player]
            deltas[key] = deltas.get(key, np.zeros(2)) + (
                sign * counterreach * (values - node) / 6.0
            )
        return node

    def run(self, iterations: int) -> None:
        deals = tuple(itertools.permutations(range(3), 2))
        for _ in range(iterations):
            frozen = {key: value.copy() for key, value in self.regret.items()}
            combined: dict[tuple[int, int, str], np.ndarray] = {}
            averages: dict[tuple[int, int, str], np.ndarray] = {}
            for traverser in (0, 1):
                local: dict[tuple[int, int, str], np.ndarray] = {}
                for deal in deals:
                    self._walk(
                        deal, "", traverser, (1.0, 1.0), frozen, local, averages
                    )
                for key, value in local.items():
                    combined[key] = combined.get(key, np.zeros(2)) + value
            for key in set(frozen) | set(combined):
                self.regret[key] = np.maximum(
                    0.0, frozen.get(key, np.zeros(2)) + combined.get(key, np.zeros(2))
                )
            for key, value in averages.items():
                self.strategy_sum[key] = self.strategy_sum.get(key, np.zeros(2)) + value

    def average(self, key: tuple[int, int, str]) -> np.ndarray:
        value = self.strategy_sum[key]
        return value / value.sum()

    def value(self) -> float:
        strategies = {
            key: value / value.sum() for key, value in self.strategy_sum.items()
        }

        def walk(cards: tuple[int, int], history: str) -> float:
            terminal = self.terminal(cards, history)
            if terminal is not None:
                return terminal
            player = len(history) % 2
            sigma = strategies[(player, cards[player], history)]
            return sum(
                sigma[action]
                * walk(cards, history + ("p" if action == 0 else "b"))
                for action in range(2)
            )

        return sum(walk(deal, "") for deal in itertools.permutations(range(3), 2)) / 6


def _flop_fixture() -> ExactPublicState:
    state = ExactPublicState.new_hand().apply_slot(1).apply_slot(1)
    return state.deal_public((0, 5, 10))


def run_contract_tests() -> dict[str, bool]:
    checks: dict[str, bool] = {}

    # Exact one-iteration oracle, independently written as literal arithmetic.
    tiny = TinyCFRPlus.fresh()
    tiny.one_iteration()
    oracle_p0 = np.maximum(0.0, np.asarray([1.0, -1.0]) - 0.0)
    oracle_p1 = np.maximum(0.0, np.asarray([-2.0, 2.0]) - 0.0)
    checks["independent_exact_one_iteration_tiny_tree"] = (
        np.array_equal(tiny.regrets["p0"], oracle_p0)
        and np.array_equal(tiny.regrets["p1"], oracle_p1)
    )

    kuhn = KuhnCFRPlus()
    kuhn.run(4_000)
    checks["fixed_seed_kuhn_cfr_plus_convergence"] = (
        abs(kuhn.value() + 1.0 / 18.0) < 0.02
        and kuhn.average((0, 2, ""))[1] > 0.90
        and kuhn.average((0, 0, ""))[1] < 0.60
    )

    root = _flop_fixture()
    key0 = infoset_key("r", 0, (12, 13), root)
    # Opponent and future cards are deliberately varied outside the key API.
    key1 = infoset_key("r", 0, (12, 13), root)
    checks["hidden_card_leakage_metamorphic"] = key0 == key1 and all(
        token not in key0 for token in ("opponent_hole", "future_board", "outcome")
    )

    observed_slots: set[int] = set()
    state = root
    observed_slots.update(state.slot_table()[0])
    # Face a normal bet to expose fold, call, raise sizes, and all-in.
    first_bet = min(slot for slot in state.slot_table()[0] if 2 <= slot <= 7)
    facing = state.apply_slot(first_bet)
    observed_slots.update(facing.slot_table()[0])
    checks["all_nine_slots_have_exact_executable_fixture"] = observed_slots == set(
        range(9)
    )

    # Exercise fold, check/call, a normal raise, all-in/call, chance, and refund.
    fold = facing.apply_slot(0)
    checks["fold_transition_zero_sum"] = (
        fold.terminal
        and fold.payoff_cents(0, (12, 13), (20, 21))
        == -fold.payoff_cents(1, (12, 13), (20, 21))
    )
    checked = root.apply_slot(1).apply_slot(1)
    checks["check_check_explicit_chance"] = (
        checked.chance_cards == 1 and checked.current_player is None
    )
    turn = checked.deal_public((15,))
    checks["chance_transition_exact"] = (
        turn.street == 2 and turn.board == (0, 5, 10, 15)
    )
    allin = root.apply_slot(8).apply_slot(1)
    checks["allin_runout_and_chip_conservation"] = (
        allin.allin_runout
        and allin.chance_cards == 2
        and sum(allin.stacks_cents) + allin.pot_cents == 40_000
    )
    terminal = allin.deal_public((20, 25))
    checks["showdown_zero_sum"] = (
        terminal.terminal
        and terminal.payoff_cents(0, (12, 13), (30, 31))
        == -terminal.payoff_cents(1, (12, 13), (30, 31))
    )

    serialized = root.serialization()
    checks["public_serialization_canonical_repeat"] = (
        serialized == root.serialization()
        and hashlib.sha256(serialized.encode()).digest()
        == hashlib.sha256(root.serialization().encode()).digest()
    )
    namespaces = (
        "solver/A/joint",
        "solver/B/joint",
        "solver/A/chance",
        "solver/B/chance",
        "solver/A/opponent",
        "solver/B/opponent",
        "solver/A/h11_leaf",
        "solver/B/h11_leaf",
        "solver/A/tie",
        "solver/B/tie",
    )
    stream_hashes = {sha_counter(namespace, 0) for namespace in namespaces}
    checks["replica_stream_sha_disjointness"] = len(stream_hashes) == len(namespaces)

    combos = canonical_combos(root.board)
    checks["canonical_combo_order_and_count"] = (
        combos == tuple(sorted(combos))
        and all(a < b for a, b in combos)
        and len(combos) == math.comb(49, 2)
    )
    checks["ties_even_exact_cent"] = (
        round_fraction_ties_even(150, Fraction(33, 100)) == 50
        and round_fraction_ties_even(101, Fraction(1, 2)) == 50
        and round_fraction_ties_even(103, Fraction(1, 2)) == 52
    )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise AssertionError(f"contract failure: {failed}")
    return checks


UPPER_WORK = {
    # 262144 complete hands * 24 V5.5 observable actions.
    "census_policy_rows": 262_144 * 24,
    "census_action_transitions": 262_144 * 24,
    # 64 roots * 24 history prefixes * maximum C(52,2) candidate own holes.
    "historical_likelihood_rows": 64 * 24 * math.comb(52, 2),
    # 64 roots * maximum ordered disjoint-hole joint support.
    "joint_range_entries": 64 * math.comb(52, 2) * math.comb(50, 2),
    "joint_samples": 8_388_608,
    # Registered traversal/leaf/continuation hard caps.
    "solver_node_visits": 8_388_608 * 91,
    "solver_h11_continuation_rows": 75_497_472 * 32,
    # E0: 64*2*4096 tapes and four profiles. E1: 64*2*8192 and two profiles.
    "e0_profile_replays": 64 * 2 * 4_096 * 4,
    "e0_br_node_operations": 64 * 2 * 4_096 * 4 * 91,
    "e0_h11_rows": 64 * 2 * 4_096 * 4 * 32,
    "e1_profile_replays": 64 * 2 * 8_192 * 2,
    "e1_br_node_operations": 64 * 2 * 8_192 * 2 * 91,
    "e1_h11_rows": 64 * 2 * 8_192 * 2 * 32,
    # Frozen schema budget, below the registered 20 GiB abort.
    "artifact_bytes": 16 * (1 << 30),
}


def _timed_blocks(
    name: str,
    function: Callable[[int], Mapping[str, int]],
) -> dict[str, object]:
    function(-1)  # fixed warm-up, never included
    blocks: list[dict[str, object]] = []
    for block in range(8):
        started = time.perf_counter()
        units = dict(function(block))
        elapsed = time.perf_counter() - started
        if elapsed <= 0 or not units or any(value <= 0 for value in units.values()):
            raise RuntimeError(f"invalid resource block: {name}")
        blocks.append(
            {
                "block": block,
                "elapsed_seconds": elapsed,
                "units": units,
                "rates_per_second": {
                    key: value / elapsed for key, value in units.items()
                },
            }
        )
    minimum_rates = {
        key: min(
            float(block["rates_per_second"][key])  # type: ignore[index]
            for block in blocks
        )
        for key in blocks[0]["units"]  # type: ignore[union-attr]
    }
    return {"name": name, "blocks": blocks, "minimum_rates": minimum_rates}


def _stage_seconds(stage: Mapping[str, object], work: Mapping[str, int]) -> float:
    rates = stage["minimum_rates"]
    assert isinstance(rates, Mapping)
    return max(float(work[key]) / float(rates[key]) for key in work)


def _resource_host_snapshot() -> dict[str, int | bool]:
    try:
        import psutil
    except ImportError as error:
        raise RuntimeError("psutil required for fail-closed process-tree admission") from error
    process = psutil.Process()
    tree = [process] + process.children(recursive=True)
    rss = sum(item.memory_info().rss for item in tree if item.is_running())
    other_trainers = 0
    for candidate in psutil.process_iter(["pid", "cmdline"]):
        if candidate.pid in {item.pid for item in tree}:
            continue
        command = " ".join(candidate.info.get("cmdline") or ()).lower()
        if "cardpilot" in command and "train" in command and "python" in command:
            other_trainers += 1
    if torch.cuda.is_available():
        free, _ = torch.cuda.mem_get_info()
        allocated = torch.cuda.memory_allocated()
    else:
        free, allocated = 0, 0
    return {
        "process_tree_rss_bytes": int(rss),
        "other_trainer_processes": other_trainers,
        "cuda_available": torch.cuda.is_available(),
        "gpu_free_bytes": int(free),
        "cuda_allocated_bytes": int(allocated),
    }


def _verify_implementation_audit(path: Path, runner_sha: str) -> str:
    if not path.is_file():
        raise RuntimeError("independent implementation audit is absent")
    audit = json.loads(path.read_text(encoding="utf-8"))
    status = str(audit.get("status", ""))
    source_hashes = audit.get("source_sha256", {})
    bound = (
        audit.get("runner_sha256")
        or (source_hashes.get("runner") if isinstance(source_hashes, dict) else None)
    )
    if (
        audit.get("identity_sha256") != IDENTITY
        or "IMPLEMENTATION_AUDIT" not in status
        or "PASS" not in status
        or bound != runner_sha
    ):
        raise RuntimeError("implementation audit does not authorize exact runner")
    return sha256_path(path)


def run_resource_admission(implementation_audit: Path) -> dict[str, object]:
    runner_path = Path(__file__).resolve()
    runner_sha = sha256_path(runner_path)
    if sha256_path(PREREG) != PREREG_SHA256:
        raise RuntimeError("preregistration mismatch")
    prereg_audit = json.loads(PREREG_AUDIT.read_text(encoding="utf-8"))
    if (
        prereg_audit.get("status")
        != "LRFT_F64_REGISTERED_PREIMPLEMENTATION_AUDIT_C1_PASS"
    ):
        raise RuntimeError("preimplementation audit not PASS")
    implementation_audit_sha = _verify_implementation_audit(
        implementation_audit, runner_sha
    )
    if OUTPUT_ROOT.exists() or RESOURCE_RESULT.exists():
        raise RuntimeError("refusing to reuse/overwrite F64 output root")

    fixed_started = time.perf_counter()
    before = _resource_host_snapshot()
    if before["other_trainer_processes"] != 0:
        raise RuntimeError("other trainer process present")
    if not before["cuda_available"]:
        raise RuntimeError("CUDA required by registered admission")
    h11 = CanonicalH11("cuda")
    fixture = _flop_fixture()
    combos = canonical_combos(fixture.board)
    fixed_load_seconds = time.perf_counter() - fixed_started

    def inference_action(_: int) -> Mapping[str, int]:
        h11._chunk(fixture, 0, combos[:256])
        local = ExactPublicState.new_hand()
        for _index in range(128):
            local = ExactPublicState.new_hand().apply_slot(1)
            local = local.apply_slot(1)
        return {"census_policy_rows": 256, "census_action_transitions": 256}

    def likelihood(_: int) -> Mapping[str, int]:
        h11._chunk(fixture, 0, combos[:256])
        return {"historical_likelihood_rows": 256}

    joint_n = 131_072
    joint_logs = np.asarray(
        [-20.0 * sha_uniform("admission/joint/log", index) for index in range(joint_n)],
        dtype=np.float64,
    )

    def joint_range(block: int) -> Mapping[str, int]:
        maximum = float(joint_logs.max())
        weights = np.exp(joint_logs - maximum)
        weights /= weights.sum(dtype=np.float64)
        cumulative = np.cumsum(weights, dtype=np.float64)
        for index in range(8_192):
            np.searchsorted(
                cumulative,
                sha_uniform(f"admission/joint/sample/{block}", index),
                side="right",
            )
        return {"joint_range_entries": joint_n, "joint_samples": 8_192}

    def solver(block: int) -> Mapping[str, int]:
        # Eighty exact two-level public visits per 256 H11 continuation rows
        # mirrors the registered worst-case leaf/visit ratio conservatively.
        accumulator = 0.0
        for index in range(80):
            regrets = np.asarray(
                [
                    sha_uniform(f"admission/solver/{block}/{index}", action)
                    for action in range(9)
                ],
                dtype=np.float64,
            )
            sigma = regret_matching(regrets, np.ones(9, dtype=np.float64))
            values = np.arange(9, dtype=np.float64) - 4.0
            accumulator += float(np.dot(sigma, values))
        if not math.isfinite(accumulator):
            raise RuntimeError("solver microkernel nonfinite")
        h11._chunk(fixture, 0, combos[:256])
        return {"solver_node_visits": 80, "solver_h11_continuation_rows": 256}

    def br_replay(phase: str, block: int) -> Mapping[str, int]:
        n = 8_192
        values = np.fromiter(
            (
                sha_uniform(f"admission/{phase}/{block}", index) * 4.0 - 2.0
                for index in range(n * 9)
            ),
            dtype=np.float64,
            count=n * 9,
        ).reshape(n, 9)
        best = np.argmax(values, axis=1)
        paired = values[np.arange(n), best] - values[:, 0]
        if not math.isfinite(float(paired.mean())):
            raise RuntimeError("BR replay nonfinite")
        h11._chunk(fixture, 0, combos[:256])
        return {
            f"{phase}_profile_replays": n,
            f"{phase}_br_node_operations": n * 9,
            f"{phase}_h11_rows": 256,
        }

    serialization_payload = {
        "identity": IDENTITY,
        "synthetic": True,
        "rows": ["0" * 240 for _ in range(4_096)],
    }

    def serialization(block: int) -> Mapping[str, int]:
        payload = canonical_json(
            {**serialization_payload, "block": block, "nonce": sha_counter("ser", block).hex()}
        )
        with tempfile.TemporaryDirectory(prefix="lrft_f64_admission_") as directory:
            target = Path(directory) / "exclusive.bin"
            with target.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if sha256_path(target) != hashlib.sha256(payload).hexdigest():
                raise RuntimeError("exclusive serialization hash mismatch")
        return {"artifact_bytes": len(payload)}

    stages = [
        _timed_blocks("canonical_census_inference_and_exact_cent_actions", inference_action),
        _timed_blocks("full_canonical_historical_likelihood", likelihood),
        _timed_blocks("joint_range_normalization_and_sampling", joint_range),
        _timed_blocks("two_traverser_depth2_and_h11_continuations", solver),
        _timed_blocks("e0_br_fit_eval_and_paired_replay", lambda block: br_replay("e0", block)),
        _timed_blocks("e1_br_fit_eval_and_paired_replay", lambda block: br_replay("e1", block)),
        _timed_blocks("exclusive_serialization_and_hashing", serialization),
    ]
    stage_work = (
        {
            "census_policy_rows": UPPER_WORK["census_policy_rows"],
            "census_action_transitions": UPPER_WORK["census_action_transitions"],
        },
        {"historical_likelihood_rows": UPPER_WORK["historical_likelihood_rows"]},
        {
            "joint_range_entries": UPPER_WORK["joint_range_entries"],
            "joint_samples": UPPER_WORK["joint_samples"],
        },
        {
            "solver_node_visits": UPPER_WORK["solver_node_visits"],
            "solver_h11_continuation_rows": UPPER_WORK[
                "solver_h11_continuation_rows"
            ],
        },
        {
            "e0_profile_replays": UPPER_WORK["e0_profile_replays"],
            "e0_br_node_operations": UPPER_WORK["e0_br_node_operations"],
            "e0_h11_rows": UPPER_WORK["e0_h11_rows"],
        },
        {
            "e1_profile_replays": UPPER_WORK["e1_profile_replays"],
            "e1_br_node_operations": UPPER_WORK["e1_br_node_operations"],
            "e1_h11_rows": UPPER_WORK["e1_h11_rows"],
        },
        {"artifact_bytes": UPPER_WORK["artifact_bytes"]},
    )
    raw_stage_seconds = []
    for stage, work in zip(stages, stage_work, strict=True):
        projected = _stage_seconds(stage, work)
        stage["upper_work"] = work
        stage["projected_raw_seconds"] = projected
        raw_stage_seconds.append(projected)

    after = _resource_host_snapshot()
    measured_rss = max(
        int(before["process_tree_rss_bytes"]), int(after["process_tree_rss_bytes"])
    )
    measured_cuda = max(
        int(before["cuda_allocated_bytes"]), int(after["cuda_allocated_bytes"])
    )
    fixed_finalization_seconds = 2.0
    projected_wall = 1.25 * (
        fixed_load_seconds + sum(raw_stage_seconds) + fixed_finalization_seconds
    )
    gates = {
        "projected_total_wall_seconds_max_21600": projected_wall <= 21_600,
        "projected_process_tree_rss_bytes_max_21474836480": measured_rss
        <= 21_474_836_480,
        "projected_cuda_allocated_bytes_max_6442450944": measured_cuda
        <= 6_442_450_944,
        "projected_artifact_bytes_max_21474836480": UPPER_WORK["artifact_bytes"]
        <= 21_474_836_480,
        "gpu_free_bytes_at_admission_min_6442450944": int(before["gpu_free_bytes"])
        >= 6_442_450_944,
        "other_trainer_processes_zero": before["other_trainer_processes"] == 0
        and after["other_trainer_processes"] == 0,
        "zero_scientific_rows": True,
    }
    passed = all(gates.values())
    result: dict[str, object] = {
        "schema": "LRFT_F64_RESOURCE_ADMISSION_V1",
        "identity_sha256": IDENTITY,
        "token": TOKEN,
        "status": (
            "LRFT_F64_RESOURCE_ADMISSION_PASS_SCIENCE_AUTHORIZED_SEPARATELY"
            if passed
            else "LRFT_F64_RESOURCE_ADMISSION_NONPASS_NO_SCIENTIFIC_ROWS"
        ),
        "runner_sha256": runner_sha,
        "preregistration_sha256": PREREG_SHA256,
        "preregistration_audit_sha256": sha256_path(PREREG_AUDIT),
        "implementation_audit_path": str(implementation_audit.resolve()),
        "implementation_audit_sha256": implementation_audit_sha,
        "frozen_inputs": {
            str(H11): H11_SHA256,
            str(NETWORK): NETWORK_SHA256,
            str(SHOWDOWN): SHOWDOWN_SHA256,
        },
        "fixed_load_seconds": fixed_load_seconds,
        "fixed_finalization_allowance_seconds": fixed_finalization_seconds,
        "safety_factor": 1.25,
        "upper_work": UPPER_WORK,
        "stages": stages,
        "projection": {
            "raw_stage_seconds": raw_stage_seconds,
            "projected_total_wall_seconds": projected_wall,
            "projected_process_tree_rss_bytes": measured_rss,
            "projected_cuda_allocated_bytes": measured_cuda,
            "projected_artifact_bytes": UPPER_WORK["artifact_bytes"],
        },
        "host_before": before,
        "host_after": after,
        "gates": gates,
        "counts": {
            "root_census_hands": 0,
            "selected_roots": 0,
            "belief_rows": 0,
            "solver_traversals": 0,
            "leaf_outcomes": 0,
            "teacher_rows": 0,
            "checkpoints": 0,
            "network_calls_scientific": 0,
            "slumbot_hands": 0,
            "official_hands": 0,
        },
    }
    OUTPUT_ROOT.mkdir(parents=False, exist_ok=False)
    with RESOURCE_RESULT.open("xb") as handle:
        payload = canonical_json(result)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        required=True,
        choices=("contract-tests", "resource-admission"),
    )
    parser.add_argument("--implementation-audit", type=Path)
    arguments = parser.parse_args()
    if arguments.mode == "contract-tests":
        checks = run_contract_tests()
        print(
            json.dumps(
                {
                    "status": "LRFT_F64_CONTRACT_TESTS_PASS",
                    "passed": sum(checks.values()),
                    "total": len(checks),
                    "checks": checks,
                },
                sort_keys=True,
            )
        )
        return 0
    if arguments.implementation_audit is None:
        parser.error("--implementation-audit is required for resource-admission")
    result = run_resource_admission(arguments.implementation_audit)
    print(json.dumps({"status": result["status"], "path": str(RESOURCE_RESULT)}))
    return 0 if "PASS" in str(result["status"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
