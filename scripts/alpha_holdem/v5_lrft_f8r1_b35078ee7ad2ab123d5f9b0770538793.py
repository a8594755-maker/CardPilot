#!/usr/bin/env python3
"""Fresh LRFT-F8R1 kernels and zero-science resource admission.

This implementation stage deliberately exposes only two modes:

``no-model-contracts``
    Deterministic, read-only tests of the exact-cent state machine, counter RNG,
    CPU-float64 probability law, canonical batching, permanent P256 lanes,
    importance-weighted simultaneous CFR+, root averaging, and work arithmetic.

``resource-admission``
    An implementation-audit-gated synthetic benchmark.  It may load frozen H11,
    but it cannot create census hands, roots, beliefs, solver rows, evaluation
    tapes, teacher rows, or checkpoints.  Its sole possible output is a
    create-new ``resource_admission.json``.

No earlier LRFT runtime is imported or used.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from enum import IntEnum
from fractions import Fraction
import hashlib
import importlib
import importlib.metadata
import itertools
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np


ROOT = Path(r"C:\Users\a8594\CardPilot")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
IDENTITY = "b35078ee7ad2ab123d5f9b0770538793d14e7b9dfbdbb51cc7897df93e2d3198"
TOKEN = IDENTITY[:32]
PREREG = ROOT / (
    "reports/v5_lrft_f8r1_preregistration_"
    "b35078ee7ad2ab123d5f9b0770538793_20260723.json"
)
PREREG_SHA256 = "716c074f755d1a377e8752013025392721716d8a456115e7367485afa068b616"
PREAUDIT = ROOT / (
    "reports/v5_lrft_f8r1_preregistration_audit_c1_"
    "b35078ee7ad2ab123d5f9b0770538793_20260723.json"
)
PREAUDIT_SHA256 = "d29d30681ea87f90d87e05084630ae9f944383a216c4f619fca0fc2b8b90198c"
IMPLEMENTATION_AUDITOR = ROOT / (
    "scripts/alpha_holdem/audit_v5_lrft_f8r1_c2_"
    "b35078ee7ad2ab123d5f9b0770538793.py"
)
IMPLEMENTATION_AUDIT = ROOT / (
    "reports/v5_lrft_f8r1_implementation_audit_c2_"
    "b35078ee7ad2ab123d5f9b0770538793_20260723.json"
)
IMPLEMENTATION_AUDIT_SCHEMA = "v5.lrft_f8r1.implementation_audit.v1"
IMPLEMENTATION_AUDIT_PASS = (
    "LRFT_F8R1_IMPLEMENTATION_AUDIT_PASS_RESOURCE_ADMISSION_AUTHORIZED_ONLY"
)
CHECKPOINT = ROOT / (
    "models/alpha_holdem_v5_hybrid/"
    "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715/"
    "h11_control_endpoint.pt"
)
CHECKPOINT_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
NETWORK_SOURCE = ROOT / "scripts/alpha_holdem/network_hybrid_h1.py"
NETWORK_SHA256 = "25f4520d31f4ce5ffcfd23fc0d56b8736fd3b5fad537706b9cd13ee270b4a171"
SHOWDOWN_SOURCE = ROOT / "scripts/deep_cfr/hand_eval.py"
SHOWDOWN_SHA256 = "fc30df48b0ae0091311f2ff40f8e320278bc47abba606c0c1f71fcce498f490d"
OUTPUT_ROOT = ROOT / f"reports/lrft_f8r1_{TOKEN}"
RESOURCE_PATH = OUTPUT_ROOT / "resource_admission.json"

STACK = 20_000
SB = 50
BB = 100
CANONICAL_BATCH = 256
PHYSICAL_LANES = 512
LANE_STRIDE = 73
ACTIVE_LOGICAL_LANES = 8 * 2 * 2 * 9
STREET_BOARD_COUNTS = (0, 3, 4, 5)
POSTFLOP_FRACTIONS = (
    Fraction(33, 100),
    Fraction(1, 2),
    Fraction(67, 100),
    Fraction(3, 4),
    Fraction(1, 1),
    Fraction(3, 2),
)
PREFLOP_FRACTIONS = (Fraction(1, 2), Fraction(1, 1), Fraction(3, 2))

RNG_DOMAINS = (
    "CENSUS_DECK",
    "CENSUS_POLICY_P0",
    "CENSUS_POLICY_P1",
    "CENSUS_CELL",
    "CENSUS_SELECT",
    "SOLVER_A_ROOT_DEAL",
    "SOLVER_B_ROOT_DEAL",
    "SOLVER_A_CHANCE",
    "SOLVER_B_CHANCE",
    "SOLVER_A_OPPONENT_ACTION",
    "SOLVER_B_OPPONENT_ACTION",
    "SOLVER_A_LEAF_POLICY",
    "SOLVER_B_LEAF_POLICY",
    "E0_OPPONENT_HOLE",
    "E0_CHANCE",
    "E0_ROOT_ACTION",
    "E0_LEAF_POLICY",
    "E1_OPPONENT_HOLE",
    "E1_CHANCE",
    "E1_ROOT_ACTION",
    "E1_LEAF_POLICY",
    "E0_BOOTSTRAP",
    "E1_BOOTSTRAP",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


class CounterRNG:
    """Identity-bound SHA256 counter RNG with exact rejection sampling."""

    __slots__ = ("master",)

    def __init__(self, master: str = IDENTITY):
        if master != IDENTITY:
            raise ValueError("F8R1 master identity mismatch")
        self.master = master

    def digest(
        self, domain: str, fields: Sequence[Any] = (), counter: int = 0
    ) -> bytes:
        if domain not in RNG_DOMAINS:
            raise ValueError(f"unregistered RNG domain: {domain}")
        if type(counter) is not int or counter < 0:
            raise ValueError("counter")
        message = "|".join(
            (self.master, domain, *(str(field) for field in fields), str(counter))
        )
        return hashlib.sha256(message.encode("utf-8")).digest()

    def uint64(
        self, domain: str, fields: Sequence[Any] = (), counter: int = 0
    ) -> int:
        return int.from_bytes(self.digest(domain, fields, counter)[:8], "big")

    def uniform_open01(
        self, domain: str, fields: Sequence[Any] = (), counter: int = 0
    ) -> Fraction:
        return open_unit_from_uint64(self.uint64(domain, fields, counter))

    def bounded(
        self, domain: str, fields: Sequence[Any], n: int
    ) -> tuple[int, int]:
        if type(n) is not int or n <= 0 or n > 1 << 64:
            raise ValueError("bounded range")
        limit = (1 << 64) - ((1 << 64) % n)
        counter = 0
        while True:
            value = self.uint64(domain, fields, counter)
            if value < limit:
                return value % n, counter
            counter += 1

    def deck(self, hand_index: int) -> tuple[int, ...]:
        deck = list(range(52))
        for index in range(51, 0, -1):
            swap, _ = self.bounded(
                "CENSUS_DECK", (int(hand_index), index), index + 1
            )
            deck[index], deck[swap] = deck[swap], deck[index]
        return tuple(deck)

    def selection_digest(
        self, cell: int, hand_index: int, public_serialization: str
    ) -> bytes:
        return self.digest(
            "CENSUS_SELECT",
            (int(cell), int(hand_index), public_serialization),
            0,
        )


def open_unit_from_uint64(value: int) -> Fraction:
    """Exact (x+0.5)/2^64 without a binary64 endpoint conversion."""

    if type(value) is not int or value < 0 or value >= 1 << 64:
        raise ValueError("uint64")
    return Fraction(2 * value + 1, 1 << 65)


def probability_cdf(
    logits_f32: np.ndarray | Sequence[float],
    legal_mask: np.ndarray | Sequence[bool],
) -> tuple[np.ndarray, np.ndarray]:
    """LEGAL_LOGITS_CPU_F64_CDF_V1, the sole probability authority."""

    logits = np.asarray(logits_f32, dtype=np.float32)
    legal = np.asarray(legal_mask, dtype=bool)
    if logits.shape != (9,) or legal.shape != (9,) or not legal.any():
        raise ValueError("nine-slot logits/legal mask required")
    if not np.isfinite(logits[legal]).all():
        raise ValueError("nonfinite legal logit")
    legal_values = logits[legal].astype(np.float64)
    shifted = legal_values - np.max(legal_values)
    weights = np.exp(shifted)
    legal_probs = weights / np.sum(weights, dtype=np.float64)
    probabilities = np.zeros(9, dtype=np.float64)
    probabilities[legal] = legal_probs
    if (
        not np.isfinite(probabilities).all()
        or np.any(probabilities < 0)
        or abs(float(np.sum(probabilities, dtype=np.float64)) - 1.0) > 2e-15
    ):
        raise RuntimeError("probability normalization")
    cdf = np.cumsum(probabilities, dtype=np.float64)
    final_legal = int(np.flatnonzero(legal)[-1])
    cdf[final_legal] = np.float64(1.0)
    return probabilities, cdf


def sample_cdf(
    cdf: np.ndarray, legal_mask: np.ndarray, uniform: Fraction
) -> int:
    values = np.asarray(cdf, dtype=np.float64)
    legal = np.asarray(legal_mask, dtype=bool)
    if values.shape != (9,) or legal.shape != (9,):
        raise ValueError("CDF/mask")
    if not isinstance(uniform, Fraction) or not 0 < uniform < 1:
        raise ValueError("open-unit uniform")
    for slot in np.flatnonzero(legal):
        numerator, denominator = float(values[slot]).as_integer_ratio()
        if numerator * uniform.denominator > uniform.numerator * denominator:
            return int(slot)
    raise RuntimeError("CDF failed to select a legal slot")


def dense_cdf_sample(cdf: np.ndarray, uniform: Fraction) -> int:
    """Binary-search a float64 CDF using exact rational comparisons."""

    values = np.asarray(cdf, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0 or values[-1] != 1.0:
        raise ValueError("dense CDF")
    low, high = 0, len(values)
    while low < high:
        middle = (low + high) // 2
        numerator, denominator = float(values[middle]).as_integer_ratio()
        greater = (
            numerator * uniform.denominator
            > uniform.numerator * denominator
        )
        if greater:
            high = middle
        else:
            low = middle + 1
    if low == len(values):
        raise RuntimeError("dense CDF selection")
    return low


def observed_log_likelihood(probabilities: np.ndarray, slot: int) -> np.float64:
    value = np.float64(probabilities[int(slot)])
    if not np.isfinite(value) or value <= 0:
        raise ValueError("observed slot has zero/nonfinite probability")
    return np.log(value, dtype=np.float64)


def ties_to_even_product(amount: int, fraction: Fraction) -> int:
    numerator = int(amount) * fraction.numerator
    denominator = fraction.denominator
    quotient, remainder = divmod(numerator, denominator)
    twice = 2 * remainder
    if twice > denominator or (twice == denominator and quotient % 2 == 1):
        quotient += 1
    return quotient


class ActionKind(IntEnum):
    FOLD = 0
    CHECK = 1
    CALL = 2
    BET = 3
    RAISE = 4
    ALLIN = 5


@dataclass(frozen=True, slots=True)
class EngineAction:
    kind: ActionKind
    total_to_cents: int = 0


@dataclass(frozen=True, slots=True)
class HistoryItem:
    actor: int
    kind: ActionKind
    total_to_cents: int


@dataclass(frozen=True, slots=True)
class ExactCentState:
    """Fresh public exact-cent 200bb HU state with explicit public chance."""

    street: int
    board: tuple[int, ...]
    pot: int
    stacks: tuple[int, int]
    street_put: tuple[int, int]
    total_put: tuple[int, int]
    actor: int | None
    acted_since_full_raise: tuple[bool, bool]
    last_full_raise: int
    history: tuple[tuple[HistoryItem, ...], ...]
    chance_count: int = 0
    allin_runout: bool = False
    terminal: bool = False
    folded: int | None = None

    @classmethod
    def initial(cls) -> "ExactCentState":
        state = cls(
            street=0,
            board=(),
            pot=SB + BB,
            stacks=(STACK - BB, STACK - SB),
            street_put=(BB, SB),
            total_put=(BB, SB),
            actor=1,
            acted_since_full_raise=(False, False),
            last_full_raise=BB,
            history=((), (), (), ()),
        )
        state.check()
        return state

    def check(self) -> None:
        integers = (
            self.street,
            self.pot,
            *self.stacks,
            *self.street_put,
            *self.total_put,
            self.last_full_raise,
            self.chance_count,
        )
        if any(type(value) is not int for value in integers):
            raise TypeError("chip and count fields must be exact integers")
        if self.street not in range(4) or self.pot < 0:
            raise ValueError("street/pot")
        if (
            len(self.acted_since_full_raise) != 2
            or any(type(value) is not bool for value in self.acted_since_full_raise)
            or self.last_full_raise <= 0
        ):
            raise ValueError("raise/reopen state")
        if any(value < 0 for value in self.stacks + self.street_put + self.total_put):
            raise ValueError("negative chip field")
        if self.pot + sum(self.stacks) != 2 * STACK:
            raise ValueError("chip conservation")
        for player in (0, 1):
            if self.total_put[player] + self.stacks[player] != STACK:
                raise ValueError("stack/investment conservation")
            if self.street_put[player] > self.total_put[player]:
                raise ValueError("street investment")
        if len(self.history) != 4 or any(len(items) > 6 for items in self.history):
            raise ValueError("V5.5 history capacity")
        if any(card < 0 or card >= 52 for card in self.board) or len(
            set(self.board)
        ) != len(self.board):
            raise ValueError("board")
        if self.chance_count:
            if self.actor is not None or self.terminal:
                raise ValueError("chance activity")
            if self.chance_count > 5 - len(self.board):
                raise ValueError("chance count")
        elif self.terminal:
            if self.actor is not None:
                raise ValueError("terminal actor")
        elif self.actor not in (0, 1):
            raise ValueError("active actor")
        elif len(self.board) != STREET_BOARD_COUNTS[self.street]:
            raise ValueError("active board/street mismatch")

    def public_bytes(self) -> bytes:
        payload = {
            "acted_since_full_raise": list(self.acted_since_full_raise),
            "actor": self.actor,
            "allin_runout": self.allin_runout,
            "board": list(self.board),
            "chance_count": self.chance_count,
            "folded": self.folded,
            "history": [
                [[item.actor, int(item.kind), item.total_to_cents] for item in street]
                for street in self.history
            ],
            "last_full_raise": self.last_full_raise,
            "pot": self.pot,
            "stacks": list(self.stacks),
            "street": self.street,
            "street_put": list(self.street_put),
            "terminal": self.terminal,
            "total_put": list(self.total_put),
        }
        return json_bytes(payload).rstrip(b"\n")

    def _raw_actions(self) -> tuple[EngineAction, ...]:
        if self.terminal or self.chance_count or self.actor is None:
            return ()
        player = self.actor
        opponent = 1 - player
        committed = self.street_put[player]
        opponent_committed = self.street_put[opponent]
        to_call = max(0, opponent_committed - committed)
        stack = self.stacks[player]
        actions: list[EngineAction] = []
        if to_call > 0:
            actions.append(EngineAction(ActionKind.FOLD))
            actions.append(EngineAction(ActionKind.CALL))
            if to_call >= stack:
                return tuple(actions)
        else:
            actions.append(EngineAction(ActionKind.CHECK))
        if stack <= to_call:
            return tuple(actions)
        may_raise = (
            not self.acted_since_full_raise[player]
            and self.stacks[opponent] > 0
        )
        if not may_raise:
            return tuple(actions)
        fractions = PREFLOP_FRACTIONS if self.street == 0 else POSTFLOP_FRACTIONS
        aggressive_kind = ActionKind.BET if to_call == 0 else ActionKind.RAISE
        targets: set[int] = set()
        minimum_increment = BB if to_call == 0 else self.last_full_raise
        minimum_target = opponent_committed + minimum_increment
        for fraction in fractions:
            if to_call == 0:
                additional = ties_to_even_product(self.pot, fraction)
            else:
                additional = to_call + ties_to_even_product(
                    self.pot + to_call, fraction
                )
            target = max(committed + additional, minimum_target)
            if additional > 0 and additional < stack:
                if target - committed < stack:
                    targets.add(target)
        actions.extend(
            EngineAction(aggressive_kind, target) for target in sorted(targets)
        )
        actions.append(EngineAction(ActionKind.ALLIN, committed + stack))
        return tuple(actions)

    def slot_table(self) -> tuple[np.ndarray, tuple[EngineAction | None, ...]]:
        table: list[EngineAction | None] = [None] * 9
        for action in self._raw_actions():
            if action.kind == ActionKind.FOLD:
                slot = 0
            elif action.kind in (ActionKind.CHECK, ActionKind.CALL):
                slot = 1
            elif action.kind == ActionKind.ALLIN:
                slot = 8
            else:
                distances = tuple(
                    abs(
                        action.total_to_cents * fraction.denominator
                        - self.pot * fraction.numerator
                    )
                    / fraction.denominator
                    for fraction in POSTFLOP_FRACTIONS
                )
                slot = 2 + min(
                    range(6), key=lambda index: (distances[index], index)
                )
            old = table[slot]
            if old is None:
                table[slot] = action
            elif 2 <= slot <= 7:
                fraction = POSTFLOP_FRACTIONS[slot - 2]
                old_distance = abs(
                    old.total_to_cents * fraction.denominator
                    - self.pot * fraction.numerator
                )
                new_distance = abs(
                    action.total_to_cents * fraction.denominator
                    - self.pot * fraction.numerator
                )
                if (new_distance, action.total_to_cents) < (
                    old_distance,
                    old.total_to_cents,
                ):
                    table[slot] = action
        mask = np.fromiter(
            (entry is not None for entry in table), dtype=bool, count=9
        )
        if not mask.any() and not (self.terminal or self.chance_count):
            raise RuntimeError("active state has no nonnull slot")
        return mask, tuple(table)

    def _record(self, action: EngineAction) -> tuple[tuple[HistoryItem, ...], ...]:
        assert self.actor is not None
        rows = list(self.history)
        if len(rows[self.street]) >= 6:
            raise RuntimeError("seventh same-street action forbidden")
        rows[self.street] = rows[self.street] + (
            HistoryItem(self.actor, action.kind, action.total_to_cents),
        )
        return tuple(rows)

    def _close_round(self, state: "ExactCentState") -> "ExactCentState":
        # Correctly return unmatched excess when a short all-in call closes action.
        first, second = state.street_put
        if first != second and 0 in state.stacks:
            high = 0 if first > second else 1
            refund = abs(first - second)
            stacks = list(state.stacks)
            street_put = list(state.street_put)
            total_put = list(state.total_put)
            stacks[high] += refund
            street_put[high] -= refund
            total_put[high] -= refund
            state = replace(
                state,
                pot=state.pot - refund,
                stacks=tuple(stacks),
                street_put=tuple(street_put),
                total_put=tuple(total_put),
            )
        if 0 in state.stacks:
            remaining = 5 - len(state.board)
            if remaining:
                return replace(
                    state,
                    actor=None,
                    chance_count=remaining,
                    allin_runout=True,
                )
            return replace(state, actor=None, terminal=True)
        if state.street == 3:
            return replace(state, actor=None, terminal=True)
        return replace(
            state,
            actor=None,
            chance_count=3 if state.street == 0 else 1,
        )

    def act(self, slot: int) -> "ExactCentState":
        mask, table = self.slot_table()
        if type(slot) is not int or slot not in range(9) or not mask[slot]:
            raise ValueError("illegal or null V5.5 slot")
        action = table[slot]
        assert action is not None and self.actor is not None
        player = self.actor
        opponent = 1 - player
        history = self._record(action)
        if action.kind == ActionKind.FOLD:
            next_state = replace(
                self,
                actor=None,
                terminal=True,
                folded=player,
                history=history,
            )
            next_state.check()
            return next_state
        if action.kind == ActionKind.CHECK:
            acted = list(self.acted_since_full_raise)
            acted[player] = True
            next_state = replace(
                self,
                actor=opponent,
                acted_since_full_raise=tuple(acted),
                history=history,
            )
            if all(acted) and self.street_put[0] == self.street_put[1]:
                next_state = self._close_round(next_state)
            next_state.check()
            return next_state
        if action.kind == ActionKind.CALL:
            to_call = max(
                0, self.street_put[opponent] - self.street_put[player]
            )
            paid = min(to_call, self.stacks[player])
            stacks = list(self.stacks)
            street_put = list(self.street_put)
            total_put = list(self.total_put)
            stacks[player] -= paid
            street_put[player] += paid
            total_put[player] += paid
            acted = list(self.acted_since_full_raise)
            acted[player] = True
            next_state = replace(
                self,
                pot=self.pot + paid,
                stacks=tuple(stacks),
                street_put=tuple(street_put),
                total_put=tuple(total_put),
                acted_since_full_raise=tuple(acted),
                history=history,
            )
            if (
                (street_put[0] == street_put[1] and all(acted))
                or stacks[player] == 0
            ):
                next_state = self._close_round(next_state)
            else:
                next_state = replace(next_state, actor=opponent)
            next_state.check()
            return next_state
        added = action.total_to_cents - self.street_put[player]
        if added <= 0 or added > self.stacks[player]:
            raise RuntimeError("invalid aggressive exact-cent amount")
        stacks = list(self.stacks)
        street_put = list(self.street_put)
        total_put = list(self.total_put)
        stacks[player] -= added
        street_put[player] += added
        total_put[player] += added
        previous_high = max(self.street_put)
        raise_increment = action.total_to_cents - previous_high
        full_raise = raise_increment >= self.last_full_raise
        acted = list(self.acted_since_full_raise)
        acted[player] = True
        if full_raise:
            acted = [False, False]
            acted[player] = True
        next_state = replace(
            self,
            pot=self.pot + added,
            stacks=tuple(stacks),
            street_put=tuple(street_put),
            total_put=tuple(total_put),
            actor=opponent,
            acted_since_full_raise=tuple(acted),
            last_full_raise=(
                raise_increment if full_raise else self.last_full_raise
            ),
            history=history,
        )
        if stacks[opponent] == 0:
            next_state = self._close_round(next_state)
        next_state.check()
        return next_state

    def deal(self, cards: Sequence[int]) -> "ExactCentState":
        supplied = tuple(cards)
        if (
            self.terminal
            or self.actor is not None
            or self.chance_count == 0
            or len(supplied) != self.chance_count
        ):
            raise ValueError("not the registered chance transition")
        if any(type(card) is not int or card < 0 or card >= 52 for card in supplied):
            raise ValueError("card")
        if len(set(self.board + supplied)) != len(self.board) + len(supplied):
            raise ValueError("public card collision")
        board = self.board + supplied
        if self.allin_runout:
            next_state = replace(
                self,
                street=3,
                board=board,
                chance_count=0,
                terminal=True,
            )
            next_state.check()
            return next_state
        next_state = replace(
            self,
            street=self.street + 1,
            board=board,
            street_put=(0, 0),
            actor=0,
            acted_since_full_raise=(False, False),
            last_full_raise=BB,
            chance_count=0,
        )
        next_state.check()
        return next_state

    def payoff(
        self,
        player: int,
        hole0: tuple[int, int],
        hole1: tuple[int, int],
    ) -> int:
        if not self.terminal or player not in (0, 1):
            raise ValueError("terminal payoff")
        if len(set(hole0 + hole1 + self.board)) != 4 + len(self.board):
            raise ValueError("card collision")
        if self.folded is None:
            if len(self.board) != 5:
                raise ValueError("showdown board")
            module = importlib.import_module("scripts.deep_cfr.hand_eval")
            comparison = module.compare_hands(hole0, hole1, list(self.board))
            winner = 0 if comparison > 0 else 1 if comparison < 0 else -1
        else:
            winner = 1 - self.folded
        if winner == -1:
            return 0
        payoff0 = self.total_put[1] if winner == 0 else -self.total_put[0]
        return payoff0 if player == 0 else -payoff0


def canonical_holes(board: Sequence[int]) -> tuple[tuple[int, int], ...]:
    public = tuple(board)
    if len(set(public)) != len(public):
        raise ValueError("duplicate public board")
    remaining = tuple(card for card in range(52) if card not in set(public))
    return tuple(itertools.combinations(remaining, 2))


def observation_row(
    state: ExactCentState,
    actor: int,
    own_hole: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if state.actor != actor or tuple(sorted(own_hole)) != own_hole:
        raise ValueError("actor/canonical own hole")
    if len(set(own_hole + state.board)) != 2 + len(state.board):
        raise ValueError("own/public collision")
    card_tensor = np.zeros((6, 4, 13), dtype=np.float32)

    def mark(channel: int, card: int) -> None:
        card_tensor[channel, card % 4, card // 4] = np.float32(1.0)

    for card in own_hole:
        mark(0, card)
        mark(5, card)
    for position, card in enumerate(state.board):
        mark(1 if position < 3 else 2 if position == 3 else 3, card)
        mark(4, card)
        mark(5, card)
    action_tensor = np.zeros((25, 4, 5), dtype=np.float32)
    for street, records in enumerate(state.history):
        for offset, record in enumerate(records):
            channel = street * 6 + offset
            action_tensor[channel, 0, 0] = np.float32(record.actor == actor)
            action_tensor[channel, 1, min(int(record.kind), 4)] = np.float32(1.0)
            if record.total_to_cents:
                action_tensor[channel, 2, 0] = np.float32(
                    min(record.total_to_cents / max(state.pot, 100), 2.0) / 2.0
                )
            action_tensor[channel, 3, 0] = np.float32(1.0)
    action_tensor[24, 0, 0] = np.float32(1.0)
    extra = np.asarray(
        [state.stacks[actor] / STACK, state.stacks[1 - actor] / STACK],
        dtype=np.float32,
    )
    mask, _ = state.slot_table()
    return card_tensor, action_tensor, extra, mask.astype(np.float32)


@dataclass(frozen=True, slots=True)
class CanonicalChunk:
    global_start: int
    real_count: int
    holes: tuple[tuple[int, int], ...]
    target_row: int | None


def canonical_chunk_for_hole(
    board: Sequence[int], actual_hole: tuple[int, int]
) -> CanonicalChunk:
    holes = canonical_holes(board)
    target = tuple(sorted(actual_hole))
    try:
        global_index = holes.index(target)
    except ValueError as error:
        raise ValueError("actual hole unavailable") from error
    start = (global_index // CANONICAL_BATCH) * CANONICAL_BATCH
    real = holes[start : start + CANONICAL_BATCH]
    padded = real + (real[-1],) * (CANONICAL_BATCH - len(real))
    return CanonicalChunk(start, len(real), padded, global_index % CANONICAL_BATCH)


def all_canonical_chunks(board: Sequence[int]) -> tuple[CanonicalChunk, ...]:
    holes = canonical_holes(board)
    chunks: list[CanonicalChunk] = []
    for start in range(0, len(holes), CANONICAL_BATCH):
        real = holes[start : start + CANONICAL_BATCH]
        padded = real + (real[-1],) * (CANONICAL_BATCH - len(real))
        chunks.append(CanonicalChunk(start, len(real), padded, None))
    return tuple(chunks)


def logical_lane(root: int, replica: str, traverser: int, action_rank: int) -> int:
    if root not in range(8) or replica not in ("A", "B"):
        raise ValueError("root/replica")
    if traverser not in (0, 1) or action_rank not in range(9):
        raise ValueError("traverser/action rank")
    replica_index = 0 if replica == "A" else 1
    return (((root * 2 + replica_index) * 2 + traverser) * 9) + action_rank


def physical_lane(logical: int, outer_iteration: int) -> int:
    if logical not in range(ACTIVE_LOGICAL_LANES):
        raise ValueError("logical lane")
    if outer_iteration not in range(8192):
        raise ValueError("outer iteration")
    return (logical + LANE_STRIDE * outer_iteration) % PHYSICAL_LANES


def evaluation_lane(root: int, tape_index: int, tapes_per_root: int) -> tuple[int, int]:
    if root not in range(8) or tape_index not in range(tapes_per_root):
        raise ValueError("evaluation tape")
    global_index = root * tapes_per_root + tape_index
    return global_index // PHYSICAL_LANES, global_index % PHYSICAL_LANES


def lane_assignment(
    outer_iteration: int,
) -> tuple[int | None, ...]:
    positions: list[int | None] = [None] * PHYSICAL_LANES
    for logical in range(ACTIVE_LOGICAL_LANES):
        position = physical_lane(logical, outer_iteration)
        if positions[position] is not None:
            raise RuntimeError("lane collision")
        positions[position] = logical
    return tuple(positions)


def proposal_density(
    mu: np.ndarray,
    source_event: np.ndarray,
    rho: np.float64 = np.float64(0.125),
) -> tuple[np.ndarray, np.ndarray, np.float64]:
    target = np.asarray(mu, dtype=np.float64)
    source = np.asarray(source_event, dtype=bool)
    if (
        target.ndim != 1
        or source.shape != target.shape
        or not np.isfinite(target).all()
        or np.any(target < 0)
        or abs(float(target.sum(dtype=np.float64)) - 1.0) > 1e-12
    ):
        raise ValueError("target joint law")
    m_star = np.float64(target[source].sum(dtype=np.float64))
    if not 0 < m_star <= 1:
        raise ValueError("source marginal")
    conditional = np.zeros_like(target)
    conditional[source] = target[source] / m_star
    q = (np.float64(1.0) - rho) * target + rho * conditional
    weight = target / q
    if (
        abs(float(q.sum(dtype=np.float64)) - 1.0) > 2e-15
        or np.any(q <= 0)
        or float(weight.max()) > 8.0 / 7.0 + 1e-15
    ):
        raise RuntimeError("proposal contract")
    return q, weight, m_star


def regret_strategy(regret: np.ndarray, legal: np.ndarray) -> np.ndarray:
    values = np.asarray(regret, dtype=np.float64)
    mask = np.asarray(legal, dtype=bool)
    if values.shape != mask.shape or not mask.any():
        raise ValueError("regret/mask")
    positive = np.where(mask, np.maximum(values, 0.0), 0.0)
    total = positive.sum(dtype=np.float64)
    if total > 0:
        return positive / total
    output = np.zeros_like(values)
    output[mask] = np.float64(1.0 / int(mask.sum()))
    return output


def simultaneous_cfr_plus(
    frozen_regrets: Mapping[str, np.ndarray],
    sigmas: Mapping[str, np.ndarray],
    action_returns: Mapping[str, np.ndarray],
    weights: Mapping[str, float],
    legal: Mapping[str, np.ndarray],
) -> dict[str, np.ndarray]:
    deltas: dict[str, np.ndarray] = {}
    for key in frozen_regrets:
        sigma = np.asarray(sigmas[key], dtype=np.float64)
        returns = np.asarray(action_returns[key], dtype=np.float64)
        mask = np.asarray(legal[key], dtype=bool)
        if (
            sigma.shape != returns.shape
            or mask.shape != sigma.shape
            or abs(float(sigma.sum(dtype=np.float64)) - 1.0) > 2e-15
        ):
            raise ValueError("CFR table")
        node = np.dot(sigma, returns)
        delta = np.float64(weights[key]) * (returns - node)
        delta[~mask] = 0.0
        deltas[key] = delta
    # Apply only after every traverser delta has been collected.
    result: dict[str, np.ndarray] = {}
    for key, old in frozen_regrets.items():
        updated = np.maximum(
            np.float64(0.0), np.asarray(old, dtype=np.float64) + deltas[key]
        )
        updated[~np.asarray(legal[key], dtype=bool)] = 0.0
        if not np.isfinite(updated).all():
            raise RuntimeError("nonfinite CFR+ regret")
        result[key] = updated
    return result


@dataclass(slots=True)
class RootAverage:
    weighted_sum: np.ndarray
    denominator: int = 0

    @classmethod
    def empty(cls) -> "RootAverage":
        return cls(np.zeros(9, dtype=np.float64), 0)

    def add_actor_stream(self, iteration: int, sigma: np.ndarray) -> None:
        if iteration < 1 or iteration > 8192:
            raise ValueError("iteration")
        values = np.asarray(sigma, dtype=np.float64)
        if values.shape != (9,) or abs(float(values.sum()) - 1.0) > 2e-15:
            raise ValueError("root sigma")
        self.weighted_sum += np.float64(iteration) * values
        self.denominator += iteration

    def endpoint(self) -> np.ndarray:
        if self.denominator != 8192 * 8193 // 2:
            raise RuntimeError("root average is not the registered endpoint")
        output = self.weighted_sum / np.float64(self.denominator)
        if abs(float(output.sum()) - 1.0) > 2e-15:
            raise RuntimeError("root average normalization")
        return output


@dataclass(slots=True)
class TinyWeightedCFR:
    """Independent small hidden-chance, two-traverser CFR+ contract kernel."""

    regrets: dict[str, np.ndarray]

    @classmethod
    def initial(cls) -> "TinyWeightedCFR":
        return cls(
            {
                "P0": np.asarray([0.1, 0.0, 0.4], dtype=np.float64),
                "P1": np.asarray([0.0, 0.2], dtype=np.float64),
            }
        )

    def one_iteration(self) -> dict[str, np.ndarray]:
        frozen = {key: value.copy() for key, value in self.regrets.items()}
        sigmas = {
            "P0": np.asarray([0.2, 0.3, 0.5], dtype=np.float64),
            "P1": np.asarray([0.6, 0.4], dtype=np.float64),
        }
        returns = {
            "P0": np.asarray([1.5, -0.25, 2.0], dtype=np.float64),
            "P1": np.asarray([-1.0, 0.75], dtype=np.float64),
        }
        weights = {"P0": 0.7741935483870968, "P1": 1.1428571428571428}
        legal = {
            "P0": np.ones(3, dtype=bool),
            "P1": np.ones(2, dtype=bool),
        }
        self.regrets = simultaneous_cfr_plus(
            frozen, sigmas, returns, weights, legal
        )
        return self.regrets


class KuhnDescriptive:
    """Small deterministic simultaneous CFR+ convergence sanity check."""

    def __init__(self) -> None:
        self.regret: dict[tuple[int, int, str], np.ndarray] = {}
        self.average_sum: dict[tuple[int, int, str], np.ndarray] = {}

    @staticmethod
    def terminal(cards: tuple[int, int], history: str) -> float | None:
        if history == "pp":
            return 1.0 if cards[0] > cards[1] else -1.0
        if history == "bp":
            return 1.0
        if history == "pbp":
            return -1.0
        if history in ("bb", "pbb"):
            return 2.0 if cards[0] > cards[1] else -2.0
        return None

    def _walk(
        self,
        cards: tuple[int, int],
        history: str,
        traverser: int,
        reach: tuple[float, float],
        frozen: Mapping[tuple[int, int, str], np.ndarray],
        delta: dict[tuple[int, int, str], np.ndarray],
        average: dict[tuple[int, int, str], np.ndarray],
    ) -> float:
        terminal = self.terminal(cards, history)
        if terminal is not None:
            return terminal
        player = len(history) % 2
        key = (player, cards[player], history)
        sigma = regret_strategy(
            frozen.get(key, np.zeros(2, dtype=np.float64)),
            np.ones(2, dtype=bool),
        )
        values = np.zeros(2, dtype=np.float64)
        for action in (0, 1):
            next_reach = list(reach)
            next_reach[player] *= sigma[action]
            values[action] = self._walk(
                cards,
                history + ("p" if action == 0 else "b"),
                traverser,
                tuple(next_reach),
                frozen,
                delta,
                average,
            )
        node = float(np.dot(sigma, values))
        average[key] = average.get(key, np.zeros(2)) + reach[player] * sigma / 6.0
        if player == traverser:
            sign = 1.0 if player == 0 else -1.0
            delta[key] = delta.get(key, np.zeros(2)) + (
                sign * reach[1 - player] * (values - node) / 6.0
            )
        return node

    def run(self, iterations: int) -> None:
        deals = tuple(itertools.permutations(range(3), 2))
        for _ in range(iterations):
            frozen = {key: value.copy() for key, value in self.regret.items()}
            total_delta: dict[tuple[int, int, str], np.ndarray] = {}
            averages: dict[tuple[int, int, str], np.ndarray] = {}
            for traverser in (0, 1):
                local: dict[tuple[int, int, str], np.ndarray] = {}
                for cards in deals:
                    self._walk(
                        cards,
                        "",
                        traverser,
                        (1.0, 1.0),
                        frozen,
                        local,
                        averages,
                    )
                for key, value in local.items():
                    total_delta[key] = total_delta.get(key, np.zeros(2)) + value
            for key in set(frozen) | set(total_delta):
                self.regret[key] = np.maximum(
                    0.0,
                    frozen.get(key, np.zeros(2))
                    + total_delta.get(key, np.zeros(2)),
                )
            for key, value in averages.items():
                self.average_sum[key] = self.average_sum.get(key, np.zeros(2)) + value

    def value(self) -> float:
        policy = {
            key: values / values.sum(dtype=np.float64)
            for key, values in self.average_sum.items()
        }

        def descend(cards: tuple[int, int], history: str) -> float:
            terminal = self.terminal(cards, history)
            if terminal is not None:
                return terminal
            player = len(history) % 2
            sigma = policy[(player, cards[player], history)]
            return sum(
                sigma[action]
                * descend(cards, history + ("p" if action == 0 else "b"))
                for action in (0, 1)
            )

        return sum(
            descend(cards, "") for cards in itertools.permutations(range(3), 2)
        ) / 6.0


WORK = {
    "canonical_census_calls": 114_688,
    "canonical_census_rows": 29_360_128,
    "history_calls": 1_152,
    "history_rows": 294_912,
    "solver_p256_calls": 524_288,
    "solver_p256_rows": 134_217_728,
    "solver_leaf_outcomes": 2_359_296,
    "solver_transitions": 75_497_472,
    "e0_p256_calls": 16_384,
    "e0_p256_rows": 4_194_304,
    "e0_outcomes": 131_072,
    "e0_transitions": 4_194_304,
    "e1_p256_calls": 16_384,
    "e1_p256_rows": 4_194_304,
    "e1_outcomes": 131_072,
    "e1_transitions": 4_194_304,
    "total_network_calls": 672_896,
    "total_network_rows": 172_261_376,
    "total_transitions": 84_000_768,
    "total_outcome_records": 2_621_440,
    "artifact_bytes": 2_147_483_648,
    # Derived one-time and confidence work, included conservatively in admission.
    "joint_entries_max": 8 * math.comb(52, 2) * math.comb(50, 2),
    "proposal_samples": 262_144,
    "e0_bootstrap_draws": 100_000 * 8 * 4_096,
    "e1_bootstrap_draws": 100_000 * 8 * 8_192,
}


def validate_work_table() -> dict[str, bool]:
    calls = (
        WORK["canonical_census_calls"]
        + WORK["history_calls"]
        + WORK["solver_p256_calls"]
        + WORK["e0_p256_calls"]
        + WORK["e1_p256_calls"]
    )
    transitions = (
        114_688
        + 2_359_296 * 32
        + 131_072 * 32
        + 131_072 * 32
    )
    return {
        "history_formula": 8 * 24 * math.ceil(1326 / 256)
        == WORK["history_calls"],
        "solver_formula": 8192 * 32 * 2 == WORK["solver_p256_calls"],
        "e0_formula": 4 * math.ceil((8 * 4096) / 512) * 32 * 2
        == WORK["e0_p256_calls"],
        "e1_formula": 2 * math.ceil((8 * 8192) / 512) * 32 * 2
        == WORK["e1_p256_calls"],
        "total_calls": calls == WORK["total_network_calls"],
        "total_rows": calls * 256 == WORK["total_network_rows"],
        "total_transitions": transitions == WORK["total_transitions"],
        "outcomes": 2_359_296 + 131_072 + 131_072
        == WORK["total_outcome_records"],
    }


def _fixture_flop() -> ExactCentState:
    # SB completes, then BB retains the heads-up option and checks.
    chance = ExactCentState.initial().act(1).act(1)
    return chance.deal((0, 5, 10))


def no_model_contracts() -> dict[str, bool]:
    checks: dict[str, bool] = {}
    if file_sha256(PREREG) != PREREG_SHA256:
        raise RuntimeError("preregistration SHA mismatch")
    if file_sha256(PREAUDIT) != PREAUDIT_SHA256:
        raise RuntimeError("instantiated C1 audit SHA mismatch")
    audit = json.loads(PREAUDIT.read_text(encoding="utf-8"))
    checks["entry_authority"] = (
        audit["identity"] == IDENTITY
        and audit["status"]
        == "LRFT_F8R1_REGISTERED_INSTANTIATED_PREIMPLEMENTATION_AUDIT_PASS"
    )

    supplied_logits = np.asarray(
        [2.0, -5.0, 0.25, 8.0, -1.5, 0.0, 3.25, -9.0, 1.125],
        dtype=np.float32,
    )
    supplied_legal = np.asarray(
        [1, 0, 1, 0, 1, 1, 1, 0, 1], dtype=bool
    )
    probabilities, cdf = probability_cdf(supplied_logits, supplied_legal)
    expected_probability_hex = (
        "0x1.865ac7ea208acp-3",
        "0x0.0p+0",
        "0x1.0f5576a71f7c2p-5",
        "0x0.0p+0",
        "0x1.7934bd4aeeaf6p-8",
        "0x1.a6a148c8dba0cp-6",
        "0x1.549e2ca2473fcp-1",
        "0x0.0p+0",
        "0x1.4572b1bf0f5afp-4",
    )
    checks["cpu_f64_probability_exact"] = tuple(
        value.hex() for value in probabilities
    ) == expected_probability_hex
    tiny_uniforms = (
        Fraction(1, 1 << 65),
        Fraction(1, 10),
        Fraction(1, 2),
        Fraction(999_999_999_999, 1_000_000_000_000),
    )
    checks["cpu_f64_cdf_sampling_exact"] = [
        sample_cdf(cdf, supplied_legal, uniform) for uniform in tiny_uniforms
    ] == [0, 0, 6, 8]
    checks["log_likelihood_same_probability"] = (
        observed_log_likelihood(probabilities, 6)
        == np.log(probabilities[6], dtype=np.float64)
    )

    rng = CounterRNG()
    deck = rng.deck(23)
    checks["rng_digest_repeat_domain_separation"] = (
        rng.uint64("CENSUS_CELL", (17,), 0) == 12_495_432_298_052_299_647
        and rng.uint64("CENSUS_CELL", (17,), 0)
        != rng.uint64("CENSUS_SELECT", (17,), 0)
    )
    cell, rejected = rng.bounded("CENSUS_CELL", (17,), 8)
    checks["rng_bounded_and_deck"] = (
        cell == 7
        and rejected >= 0
        and hashlib.sha256(bytes(deck)).hexdigest()
        == "2e716ac903dcfdfbc588de20b4ca245995f9b19f5d41aa3fa3a49c679a8b1daa"
    )
    checks["rng_uniform_open_endpoints"] = (
        0 < rng.uniform_open01("E0_ROOT_ACTION", (0,), 0) < 1
        and len(RNG_DOMAINS) == len(set(RNG_DOMAINS))
        and open_unit_from_uint64(0) == Fraction(1, 1 << 65)
        and open_unit_from_uint64((1 << 64) - 1)
        == Fraction((1 << 65) - 1, 1 << 65)
        and sample_cdf(
            np.asarray([0.5, 1.0] + [1.0] * 7, dtype=np.float64),
            np.asarray([True, True] + [False] * 7),
            open_unit_from_uint64((1 << 64) - 1),
        )
        == 1
    )

    limp = ExactCentState.initial().act(1)
    limp_mask, _ = limp.slot_table()
    checks["sb_call_preserves_bb_option"] = (
        not limp.terminal
        and limp.chance_count == 0
        and limp.actor == 0
        and limp_mask[1]
        and bool(np.any(limp_mask[2:]))
    )
    preflop_closed = limp.act(1)
    checks["bb_check_closes_preflop_only_then"] = (
        preflop_closed.actor is None
        and preflop_closed.chance_count == 3
        and not preflop_closed.terminal
    )
    flop = _fixture_flop()
    flop.check()
    wide_flop = replace(
        flop,
        pot=400,
        stacks=(19_800, 19_800),
        total_put=(200, 200),
    )
    wide_flop.check()
    seen = set(np.flatnonzero(wide_flop.slot_table()[0]).tolist())
    normal_bet = min(slot for slot in seen if 2 <= slot <= 7)
    facing = wide_flop.act(normal_bet)
    seen.update(np.flatnonzero(facing.slot_table()[0]).tolist())
    checks["all_nine_executable_slots"] = seen == set(range(9))
    folded = facing.act(0)
    checks["fold_exact_zero_sum"] = (
        folded.terminal
        and folded.payoff(0, (12, 13), (20, 21))
        == -folded.payoff(1, (12, 13), (20, 21))
    )
    checked = flop.act(1).act(1)
    checks["check_check_explicit_chance"] = (
        checked.chance_count == 1 and checked.actor is None
    )
    turn = checked.deal((15,))
    checks["turn_exact_and_conserved"] = (
        turn.street == 2
        and turn.board == (0, 5, 10, 15)
        and turn.pot + sum(turn.stacks) == 2 * STACK
    )

    facing_mask, _ = facing.slot_table()
    full_raise_slot = int(
        min(slot for slot in np.flatnonzero(facing_mask) if 2 <= slot <= 7)
    )
    after_full_raise = facing.act(full_raise_slot)
    reopened_mask, _ = after_full_raise.slot_table()
    checks["full_raise_reopens_action"] = (
        after_full_raise.actor == 0
        and not after_full_raise.acted_since_full_raise[0]
        and bool(np.any(reopened_mask[2:]))
    )

    # Give the responding player only 150 cents behind while facing a 100-cent
    # full bet.  Its all-in raises by 50, below last_full_raise=100.
    short_stack = 150
    short_facing = replace(
        facing,
        stacks=(facing.stacks[0], short_stack),
        total_put=(facing.total_put[0], STACK - short_stack),
        pot=2 * STACK - facing.stacks[0] - short_stack,
    )
    short_facing.check()
    short_shove = short_facing.act(8)
    short_response_mask, _ = short_shove.slot_table()
    checks["short_allin_does_not_reopen"] = (
        short_shove.last_full_raise == facing.last_full_raise
        and short_shove.acted_since_full_raise == (True, True)
        and np.array_equal(
            np.flatnonzero(short_response_mask), np.asarray([0, 1])
        )
    )
    full_shove = facing.act(8)
    full_shove_mask, _ = full_shove.slot_table()
    checks["opponent_allin_offers_only_fold_call"] = np.array_equal(
        np.flatnonzero(full_shove_mask), np.asarray([0, 1])
    )
    allin = flop.act(8).act(1)
    river_terminal = allin.deal((20, 25))
    checks["allin_runout_exact_zero_sum"] = (
        allin.allin_runout
        and allin.chance_count == 2
        and river_terminal.terminal
        and river_terminal.payoff(0, (12, 13), (30, 31))
        == -river_terminal.payoff(1, (12, 13), (30, 31))
    )
    checks["public_serialization_repeat"] = flop.public_bytes() == flop.public_bytes()
    checks["ties_even_cents"] = (
        ties_to_even_product(150, Fraction(33, 100)) == 50
        and ties_to_even_product(101, Fraction(1, 2)) == 50
        and ties_to_even_product(103, Fraction(1, 2)) == 52
    )

    holes = canonical_holes(flop.board)
    final_chunk = all_canonical_chunks(flop.board)[-1]
    chosen = holes[513]
    chunk = canonical_chunk_for_hole(flop.board, chosen)
    checks["canonical_order_count_row"] = (
        holes == tuple(sorted(holes))
        and all(first < second for first, second in holes)
        and len(holes) == math.comb(49, 2)
        and chunk.global_start == 512
        and chunk.target_row == 1
    )
    checks["canonical_duplicate_final_padding"] = (
        len(final_chunk.holes) == 256
        and final_chunk.real_count == len(holes) % 256
        and len(set(final_chunk.holes[final_chunk.real_count - 1 :])) == 1
    )
    encoded = observation_row(flop, 0, holes[0])
    checks["encoder_shapes_and_dtypes"] = (
        tuple(array.shape for array in encoded)
        == ((6, 4, 13), (25, 4, 5), (2,), (9,))
        and all(array.dtype == np.float32 for array in encoded)
    )

    lane_counts = np.zeros((ACTIVE_LOGICAL_LANES, PHYSICAL_LANES), dtype=np.int16)
    collision_free = True
    for iteration in range(8192):
        assignment = lane_assignment(iteration)
        collision_free &= sum(item is not None for item in assignment) == 288
        for logical in range(ACTIVE_LOGICAL_LANES):
            lane_counts[logical, physical_lane(logical, iteration)] += 1
    checks["permanent_lanes_latin_exact16"] = (
        collision_free
        and np.all(lane_counts == 16)
        and math.gcd(LANE_STRIDE, PHYSICAL_LANES) == 1
    )
    checks["lane_formula_and_profile_independence"] = (
        logical_lane(0, "A", 0, 0) == 0
        and logical_lane(7, "B", 1, 8) == 287
        and evaluation_lane(3, 17, 4096) == evaluation_lane(3, 17, 4096)
    )
    target_logical = logical_lane(2, "B", 1, 4)
    fixed_positions = [
        physical_lane(target_logical, iteration) for iteration in (0, 1, 511, 8191)
    ]
    other_rows_a = [hashlib.sha256(f"A|{i}".encode()).digest() for i in range(512)]
    other_rows_b = [hashlib.sha256(f"B|{i}".encode()).digest() for i in range(512)]
    for position in fixed_positions:
        target = hashlib.sha256(b"target-row").digest()
        other_rows_a[position] = target
        other_rows_b[position] = target
    checks["no_model_lane_mapping_content_independence"] = all(
        other_rows_a[position] == other_rows_b[position]
        for position in fixed_positions
    )

    mu = np.asarray([0.08, 0.12, 0.20, 0.10, 0.18, 0.32], dtype=np.float64)
    source = np.asarray([False, True, False, False, True, False])
    q, weights, m_star = proposal_density(mu, source)
    function = np.asarray([-3.0, 2.5, 1.25, -0.75, 4.0, 0.5])
    checks["importance_full_density_unbiased"] = (
        m_star == np.float64(0.3)
        and abs(float(np.dot(mu, function) - np.dot(q, weights * function)))
        <= 2e-15
        and float(weights.max()) <= 8.0 / 7.0 + 1e-15
    )

    tiny = TinyWeightedCFR.initial()
    observed_regret = tiny.one_iteration()
    sigma0 = np.asarray([0.2, 0.3, 0.5])
    sigma1 = np.asarray([0.6, 0.4])
    returns0 = np.asarray([1.5, -0.25, 2.0])
    returns1 = np.asarray([-1.0, 0.75])
    delta0 = weights[1] * (returns0 - np.dot(sigma0, returns0))
    delta1 = weights[3] * (returns1 - np.dot(sigma1, returns1))
    independent0 = np.maximum(0.0, np.asarray([0.1, 0.0, 0.4]) + delta0)
    independent1 = np.maximum(0.0, np.asarray([0.0, 0.2]) + delta1)
    checks["tiny_hidden_chance_weighted_simultaneous_oracle"] = (
        np.array_equal(observed_regret["P0"], independent0)
        and np.array_equal(observed_regret["P1"], independent1)
        and abs(float(np.dot(sigma0, delta0))) <= 2e-15
        and abs(float(np.dot(sigma1, delta1))) <= 2e-15
    )
    wrong_delta = returns0 - np.dot(sigma0, returns0)
    checks["missing_mu_over_q_weight_detected"] = not np.array_equal(
        delta0, wrong_delta
    )

    average = RootAverage.empty()
    direct = np.zeros(9, dtype=np.float64)
    for iteration in range(1, 8193):
        values = np.arange(1, 10, dtype=np.float64) + (iteration % 7)
        sigma = values / values.sum(dtype=np.float64)
        average.add_actor_stream(iteration, sigma)
        direct += np.float64(iteration) * sigma
    endpoint = average.endpoint()
    checks["single_actor_root_average_bit_exact"] = np.array_equal(
        endpoint, direct / np.float64(8192 * 8193 // 2)
    )

    kuhn = KuhnDescriptive()
    kuhn.run(2_000)
    checks["kuhn_descriptive_convergence"] = abs(kuhn.value() + 1.0 / 18.0) < 0.03

    checks.update({f"work_{key}": value for key, value in validate_work_table().items()})
    checks["no_scientific_output_paths"] = not OUTPUT_ROOT.exists()
    checks = {name: bool(passed) for name, passed in checks.items()}
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise AssertionError(f"F8R1 no-model contract failures: {failures}")
    return checks


def _state_evidence(state: ExactCentState) -> dict[str, Any]:
    mask, _ = state.slot_table()
    return {
        "street": state.street,
        "board": list(state.board),
        "pot": state.pot,
        "stacks": list(state.stacks),
        "street_put": list(state.street_put),
        "total_put": list(state.total_put),
        "actor": state.actor,
        "acted_since_full_raise": list(state.acted_since_full_raise),
        "last_full_raise": state.last_full_raise,
        "chance_count": state.chance_count,
        "allin_runout": state.allin_runout,
        "terminal": state.terminal,
        "folded": state.folded,
        "legal_vector": [int(value) for value in mask],
        "public_sha256": hashlib.sha256(state.public_bytes()).hexdigest(),
    }


def contract_evidence() -> dict[str, Any]:
    """Deterministic raw values for an independent C2 reference audit."""

    limp = ExactCentState.initial().act(1)
    bb_check = limp.act(1)
    flop = bb_check.deal((0, 5, 10))
    wide = replace(
        flop,
        pot=400,
        stacks=(19_800, 19_800),
        total_put=(200, 200),
    )
    open_mask, _ = wide.slot_table()
    open_slot = int(min(slot for slot in np.flatnonzero(open_mask) if 2 <= slot <= 7))
    facing = wide.act(open_slot)
    facing_mask, _ = facing.slot_table()
    full_slot = int(
        min(slot for slot in np.flatnonzero(facing_mask) if 2 <= slot <= 7)
    )
    full_raise = facing.act(full_slot)
    short_stack = 150
    short_facing = replace(
        facing,
        stacks=(facing.stacks[0], short_stack),
        total_put=(facing.total_put[0], STACK - short_stack),
        pot=2 * STACK - facing.stacks[0] - short_stack,
    )
    short_allin = short_facing.act(8)
    opponent_allin = facing.act(8)

    rng = CounterRNG()
    lower = open_unit_from_uint64(0)
    upper = open_unit_from_uint64((1 << 64) - 1)
    deck = rng.deck(23)
    cell, cell_rejections = rng.bounded("CENSUS_CELL", (17,), 8)

    supplied_logits = np.asarray(
        [2.0, -5.0, 0.25, 8.0, -1.5, 0.0, 3.25, -9.0, 1.125],
        dtype=np.float32,
    )
    supplied_legal = np.asarray(
        [1, 0, 1, 0, 1, 1, 1, 0, 1], dtype=bool
    )
    probabilities, cdf = probability_cdf(supplied_logits, supplied_legal)
    sample_uniforms = (
        open_unit_from_uint64(0),
        Fraction(1, 10),
        Fraction(1, 2),
        Fraction(999_999_999_999, 1_000_000_000_000),
        open_unit_from_uint64((1 << 64) - 1),
    )

    mu = np.asarray([0.08, 0.12, 0.20, 0.10, 0.18, 0.32], dtype=np.float64)
    source = np.asarray([False, True, False, False, True, False])
    q, importance, m_star = proposal_density(mu, source)
    objective = np.asarray([-3.0, 2.5, 1.25, -0.75, 4.0, 0.5])
    target_expectation = np.float64(np.dot(mu, objective))
    proposal_expectation = np.float64(np.dot(q, importance * objective))

    sigma0 = np.asarray([0.2, 0.3, 0.5], dtype=np.float64)
    sigma1 = np.asarray([0.6, 0.4], dtype=np.float64)
    returns0 = np.asarray([1.5, -0.25, 2.0], dtype=np.float64)
    returns1 = np.asarray([-1.0, 0.75], dtype=np.float64)
    delta0 = importance[1] * (returns0 - np.dot(sigma0, returns0))
    delta1 = importance[3] * (returns1 - np.dot(sigma1, returns1))
    next_regret = TinyWeightedCFR.initial().one_iteration()

    average = RootAverage.empty()
    direct = np.zeros(9, dtype=np.float64)
    for iteration in range(1, 8193):
        raw = np.arange(1, 10, dtype=np.float64) + (iteration % 7)
        sigma = raw / raw.sum(dtype=np.float64)
        average.add_actor_stream(iteration, sigma)
        direct += np.float64(iteration) * sigma
    endpoint = average.endpoint()

    lane_counts = np.zeros(
        (ACTIVE_LOGICAL_LANES, PHYSICAL_LANES), dtype=np.uint16
    )
    for iteration in range(8192):
        for logical in range(ACTIVE_LOGICAL_LANES):
            lane_counts[logical, physical_lane(logical, iteration)] += 1
    lane_samples = {
        str(logical): [
            physical_lane(logical, iteration)
            for iteration in (0, 1, 2, 511, 512, 8191)
        ]
        for logical in (0, 17, 143, 287)
    }

    work_checks = validate_work_table()
    canonical = all_canonical_chunks(flop.board)
    return {
        "exact_cent": {
            "sb_call": _state_evidence(limp),
            "bb_check": _state_evidence(bb_check),
            "full_raise": _state_evidence(full_raise),
            "short_allin": _state_evidence(short_allin),
            "opponent_allin": _state_evidence(opponent_allin),
            "opening_slot": open_slot,
            "full_raise_slot": full_slot,
        },
        "rng": {
            "digest_hex": rng.digest("CENSUS_CELL", (17,), 0).hex(),
            "uint64": rng.uint64("CENSUS_CELL", (17,), 0),
            "bounded_cell": cell,
            "bounded_rejections": cell_rejections,
            "deck_sha256": hashlib.sha256(bytes(deck)).hexdigest(),
            "open01_lower": [lower.numerator, lower.denominator],
            "open01_upper": [upper.numerator, upper.denominator],
        },
        "probability": {
            "logits_f32_hex": [float(value).hex() for value in supplied_logits],
            "legal": [int(value) for value in supplied_legal],
            "probability_hex": [value.hex() for value in probabilities],
            "cdf_hex": [value.hex() for value in cdf],
            "samples": [
                sample_cdf(cdf, supplied_legal, uniform)
                for uniform in sample_uniforms
            ],
            "sample_uniform_rationals": [
                [uniform.numerator, uniform.denominator]
                for uniform in sample_uniforms
            ],
        },
        "importance": {
            "mu_hex": [value.hex() for value in mu],
            "source": [int(value) for value in source],
            "m_star_hex": m_star.hex(),
            "q_hex": [value.hex() for value in q],
            "weight_hex": [value.hex() for value in importance],
            "target_expectation_hex": target_expectation.hex(),
            "proposal_expectation_hex": proposal_expectation.hex(),
        },
        "tiny_cfr": {
            "delta0_hex": [value.hex() for value in delta0],
            "delta1_hex": [value.hex() for value in delta1],
            "rnext0_hex": [value.hex() for value in next_regret["P0"]],
            "rnext1_hex": [value.hex() for value in next_regret["P1"]],
        },
        "root_average": {
            "denominator": average.denominator,
            "endpoint_hex": [value.hex() for value in endpoint],
            "direct_equal": bool(
                np.array_equal(
                    endpoint,
                    direct / np.float64(8192 * 8193 // 2),
                )
            ),
        },
        "lanes": {
            "samples": lane_samples,
            "count_min": int(lane_counts.min()),
            "count_max": int(lane_counts.max()),
            "count_sha256": hashlib.sha256(
                lane_counts.astype("<u2", copy=False).tobytes(order="C")
            ).hexdigest(),
            "assignment_hashes": {
                str(iteration): hashlib.sha256(
                    json_bytes(list(lane_assignment(iteration)))
                ).hexdigest()
                for iteration in (0, 1, 511, 512, 8191)
            },
        },
        "canonical": {
            "hole_count": len(canonical_holes(flop.board)),
            "chunk_count": len(canonical),
            "last_real_count": canonical[-1].real_count,
            "last_padding_unique": len(
                set(canonical[-1].holes[canonical[-1].real_count - 1 :])
            ),
        },
        "work": {
            "total_calls": WORK["total_network_calls"],
            "total_rows": WORK["total_network_rows"],
            "total_transitions": WORK["total_transitions"],
            "total_outcome_records": WORK["total_outcome_records"],
            "artifact_bytes": WORK["artifact_bytes"],
            "checks": {key: bool(value) for key, value in work_checks.items()},
            "table": WORK,
        },
    }


def _probe_root_snapshot(path: Path) -> dict[str, int]:
    if not path.is_dir():
        raise ValueError("probe root must be an existing directory")
    files = [item for item in path.rglob("*") if item.is_file()]
    return {
        "files": len(files),
        "bytes": sum(item.stat().st_size for item in files),
    }


def contract_probe(probe_root: Path) -> dict[str, Any]:
    """Run all no-model contracts while proving zero probe-root writes."""

    resolved = probe_root.resolve(strict=True)
    before = _probe_root_snapshot(resolved)
    if before != {"files": 0, "bytes": 0}:
        raise RuntimeError("contract probe requires an existing empty directory")
    checks = no_model_contracts()
    evidence = contract_evidence()
    after = _probe_root_snapshot(resolved)
    if after != before:
        raise RuntimeError("contract probe modified its probe root")
    return {
        "status": "LRFT_F8R1_CONTRACT_PROBE_PASS",
        "identity": IDENTITY,
        "passed": sum(checks.values()),
        "total": len(checks),
        "checks": checks,
        "evidence": evidence,
        "probe_root": str(resolved),
        "before": before,
        "after": after,
        "torch_loaded": "torch" in sys.modules,
        "model_calls": 0,
        "files_created": 0,
        "bytes_created": 0,
    }


class FrozenH11:
    """Lazy strict H11 loader used only by resource admission."""

    def __init__(self) -> None:
        if file_sha256(CHECKPOINT) != CHECKPOINT_SHA256:
            raise RuntimeError("checkpoint SHA mismatch")
        if file_sha256(NETWORK_SOURCE) != NETWORK_SHA256:
            raise RuntimeError("network SHA mismatch")
        if file_sha256(SHOWDOWN_SOURCE) != SHOWDOWN_SHA256:
            raise RuntimeError("showdown SHA mismatch")
        torch = importlib.import_module("torch")
        network = importlib.import_module("scripts.alpha_holdem.network_hybrid_h1")
        checkpoint = torch.load(CHECKPOINT, map_location="cpu", weights_only=True)
        metadata = {
            "iteration": 35_051,
            "total_hands": 576_021_901,
            "env_version": "v55",
            "obs_version": "v55",
            "action_space_version": "9slot_v5",
            "critic_contract": "critic_v1",
            "starting_stack_bb": 200.0,
        }
        if any(checkpoint.get(key) != value for key, value in metadata.items()):
            raise RuntimeError("checkpoint metadata mismatch")
        with torch.device("meta"):
            model = network.AlphaHoldemNet(
                num_actions=9, critic_contract=network.CRITIC_V1
            )
            model(
                torch.zeros((256, 6, 4, 13), device="meta"),
                torch.zeros((256, 25, 4, 5), device="meta"),
                torch.zeros((256, 2), device="meta"),
                torch.ones((256, 9), device="meta"),
            )
        model.load_state_dict(checkpoint["model"], strict=True, assign=True)
        self.torch = torch
        self.model = model.to("cuda").eval().requires_grad_(False)

    def forward(
        self,
        rows: Sequence[
            tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
        ],
    ) -> tuple[np.ndarray, np.ndarray]:
        if len(rows) != 256:
            raise ValueError("H11 resource forward must be exact batch256")
        arrays = [
            np.ascontiguousarray(np.stack([row[index] for row in rows]))
            for index in range(4)
        ]
        tensors = [
            self.torch.from_numpy(array).to("cuda", non_blocking=False)
            for array in arrays
        ]
        with self.torch.inference_mode(), self.torch.autocast(
            device_type="cuda", enabled=False
        ):
            logits, _ = self.model(tensors[0], tensors[1], tensors[2], None)
        return (
            logits.detach().cpu().numpy().astype(np.float32, copy=True),
            arrays[3],
        )


def _fixed_rows_for_chunk(
    state: ExactCentState, actor: int, chunk: CanonicalChunk
) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    return [observation_row(state, actor, hole) for hole in chunk.holes]


def _dummy_row() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    state = ExactCentState.initial()
    return observation_row(state, 1, (0, 1))


def _p256_rows(
    active_rows_by_logical: Mapping[
        int, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
    ],
    iteration: int,
) -> tuple[
    list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
    list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
]:
    dummy = _dummy_row()
    rows = [dummy] * 512
    for logical, row in active_rows_by_logical.items():
        rows[physical_lane(logical, iteration)] = row
    return rows[:256], rows[256:]


def _process_snapshot(torch_module: Any | None = None) -> dict[str, int | bool]:
    psutil = importlib.import_module("psutil")
    current = psutil.Process()
    tree = [current] + current.children(recursive=True)
    tree_pids = {item.pid for item in tree}
    rss = sum(item.memory_info().rss for item in tree if item.is_running())
    other_training = 0
    for process in psutil.process_iter(["pid", "cmdline"]):
        if process.pid in tree_pids:
            continue
        command = " ".join(process.info.get("cmdline") or ()).lower()
        if (
            "cardpilot" in command
            and "python" in command
            and ("train_" in command or "\\train.py" in command)
        ):
            other_training += 1
    if torch_module is not None and torch_module.cuda.is_available():
        free, _ = torch_module.cuda.mem_get_info()
        allocated = torch_module.cuda.memory_allocated()
    else:
        free, allocated = 0, 0
    return {
        "process_tree_rss_bytes": int(rss),
        "other_training_processes": int(other_training),
        "gpu_free_bytes": int(free),
        "cuda_allocated_bytes": int(allocated),
        "cuda_available": bool(torch_module is not None and torch_module.cuda.is_available()),
    }


class _ProcessTreePeakSampler:
    """Conservative in-window RSS sampler for this process and descendants."""

    def __init__(self, interval_seconds: float = 0.002):
        self.interval_seconds = interval_seconds
        self.peak_rss_bytes = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample_once(self) -> None:
        psutil = importlib.import_module("psutil")
        process = psutil.Process()
        members = [process] + process.children(recursive=True)
        observed = 0
        for member in members:
            try:
                if member.is_running():
                    observed += int(member.memory_info().rss)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        self.peak_rss_bytes = max(self.peak_rss_bytes, observed)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._sample_once()
            self._stop.wait(self.interval_seconds)
        self._sample_once()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("peak sampler already started")
        self._sample_once()
        self._thread = threading.Thread(
            target=self._run,
            name="f8r1-resource-rss-peak",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> int:
        if self._thread is None:
            raise RuntimeError("peak sampler not started")
        self._stop.set()
        self._thread.join(timeout=5.0)
        if self._thread.is_alive():
            raise RuntimeError("peak sampler failed to stop")
        return self.peak_rss_bytes


def _measure_fixed_finalization() -> dict[str, Any]:
    """Measure one conservative 1 MiB create-new/fsync/hash finalization."""

    payload = json_bytes(
        {
            "schema": "LRFT_F8R1_RESOURCE_FINALIZATION_PROBE_V1",
            "identity": IDENTITY,
            "padding": "0" * ((1 << 20) - 256),
        }
    )
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="f8r1_finalization_") as directory:
        target = Path(directory) / "resource_admission.json"
        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        observed = file_sha256(target)
        expected = hashlib.sha256(payload).hexdigest()
        if observed != expected:
            raise RuntimeError("fixed finalization hash mismatch")
    elapsed = time.perf_counter() - started
    return {
        "elapsed_seconds": elapsed,
        "bytes": len(payload),
        "sha256": expected,
        "create_new": True,
        "fsync": True,
        "hash_verified": True,
    }


def _verify_implementation_audit(path: Path, runner_sha: str) -> str:
    resolved = path.resolve(strict=True)
    if resolved != IMPLEMENTATION_AUDIT.resolve(strict=False) or not resolved.is_file():
        raise RuntimeError("independent implementation audit absent")
    audit = json.loads(resolved.read_text(encoding="utf-8"))
    runner_binding = audit.get("runner")
    auditor_binding = audit.get("audit_source")
    gates = audit.get("gates")
    scientific = audit.get("scientific_output")
    exact = (
        audit.get("schema_version") == IMPLEMENTATION_AUDIT_SCHEMA
        and audit.get("identity") == IDENTITY
        and audit.get("status") == IMPLEMENTATION_AUDIT_PASS
        and isinstance(runner_binding, dict)
        and Path(str(runner_binding.get("path", ""))).resolve(strict=False)
        == Path(__file__).resolve()
        and runner_binding.get("sha256") == runner_sha
        and isinstance(auditor_binding, dict)
        and Path(str(auditor_binding.get("path", ""))).resolve(strict=False)
        == IMPLEMENTATION_AUDITOR.resolve(strict=False)
        and IMPLEMENTATION_AUDITOR.is_file()
        and auditor_binding.get("sha256") == file_sha256(IMPLEMENTATION_AUDITOR)
        and isinstance(gates, list)
        and len(gates) > 0
        and audit.get("gates_passed") == audit.get("gates_total") == len(gates)
        and all(item.get("pass") is True for item in gates if isinstance(item, dict))
        and all(isinstance(item, dict) for item in gates)
        and audit.get("model_instantiated") == 0
        and audit.get("resource_admission_runs") == 0
        and isinstance(scientific, dict)
        and len(scientific) > 0
        and all(value == 0 for value in scientific.values())
    )
    if not exact:
        raise RuntimeError("implementation audit does not authorize this runner")
    return file_sha256(resolved)


def _eight_blocks(
    name: str,
    kernel: Callable[[int], Mapping[str, int]],
) -> dict[str, Any]:
    kernel(-1)
    blocks: list[dict[str, Any]] = []
    for block in range(8):
        started = time.perf_counter()
        units = {key: int(value) for key, value in kernel(block).items()}
        elapsed = time.perf_counter() - started
        if elapsed <= 0 or not units or any(value <= 0 for value in units.values()):
            raise RuntimeError(f"invalid benchmark block: {name}")
        blocks.append(
            {
                "index": block,
                "elapsed_seconds": elapsed,
                "units": units,
                "rates_per_second": {
                    key: value / elapsed for key, value in units.items()
                },
            }
        )
    minimum = {
        key: min(block["rates_per_second"][key] for block in blocks)
        for key in blocks[0]["units"]
    }
    return {"name": name, "blocks": blocks, "minimum_rates": minimum}


def _project(stage: Mapping[str, Any], upper: Mapping[str, int]) -> float:
    rates = stage["minimum_rates"]
    return max(float(upper[key]) / float(rates[key]) for key in upper)


def resource_admission(implementation_audit: Path) -> dict[str, Any]:
    """Run zero-science exact-kernel admission and create its sole result."""

    runner_sha = file_sha256(Path(__file__).resolve())
    if file_sha256(PREREG) != PREREG_SHA256 or file_sha256(PREAUDIT) != PREAUDIT_SHA256:
        raise RuntimeError("F8R1 registration chain mismatch")
    audit_sha = _verify_implementation_audit(implementation_audit, runner_sha)
    if OUTPUT_ROOT.exists():
        raise RuntimeError("refusing to reuse F8R1 output root")
    if importlib.metadata.version("numpy") != "2.4.4":
        raise RuntimeError("numpy runtime mismatch")
    if importlib.metadata.version("torch") != "2.6.0":
        raise RuntimeError("torch runtime mismatch")

    fixed_started = time.perf_counter()
    torch = importlib.import_module("torch")
    if torch.__version__ != "2.6.0+cu124" or torch.version.cuda != "12.4":
        raise RuntimeError("torch/CUDA runtime mismatch")
    before = _process_snapshot(torch)
    if before["other_training_processes"] != 0:
        raise RuntimeError("other training process present")
    if not before["cuda_available"] or before["gpu_free_bytes"] < 6_442_450_944:
        raise RuntimeError("GPU admission start gate failed")
    rss_peak_sampler = _ProcessTreePeakSampler()
    rss_peak_sampler.start()
    model = FrozenH11()
    torch.cuda.reset_peak_memory_stats()
    flop = _fixture_flop()
    canonical_chunk = canonical_chunk_for_hole(flop.board, (1, 2))
    canonical_rows = _fixed_rows_for_chunk(flop, 0, canonical_chunk)
    dummy = _dummy_row()
    active = {logical: dummy for logical in range(ACTIVE_LOGICAL_LANES)}
    fixed_load_seconds = time.perf_counter() - fixed_started

    metamorphic_started = time.perf_counter()
    target_position = 17
    alternate = observation_row(flop, 0, canonical_holes(flop.board)[100])
    content_a = [dummy for _ in range(256)]
    content_b = [alternate for _ in range(256)]
    content_b[target_position] = dummy
    logits_a, masks_a = model.forward(content_a)
    logits_b, masks_b = model.forward(content_b)
    target_prob_a, target_cdf_a = probability_cdf(
        logits_a[target_position], masks_a[target_position].astype(bool)
    )
    target_prob_b, target_cdf_b = probability_cdf(
        logits_b[target_position], masks_b[target_position].astype(bool)
    )
    true_model_content_isolation = (
        np.array_equal(logits_a[target_position], logits_b[target_position])
        and np.array_equal(target_prob_a, target_prob_b)
        and np.array_equal(target_cdf_a, target_cdf_b)
    )
    metamorphic_seconds = time.perf_counter() - metamorphic_started

    def canonical_kernel(_: int) -> Mapping[str, int]:
        logits, masks = model.forward(canonical_rows)
        for row in range(256):
            probabilities, _ = probability_cdf(
                logits[row], masks[row].astype(bool)
            )
            observed_log_likelihood(
                probabilities, int(np.flatnonzero(masks[row])[0])
            )
        return {"canonical_calls": 1}

    def p256_kernel(block: int) -> Mapping[str, int]:
        first, second = _p256_rows(active, block % 8192)
        logits0, masks0 = model.forward(first)
        logits1, masks1 = model.forward(second)
        # Use the conservative common rate required by the 512-active E0/E1
        # waves: every physical row receives the science probability/log/CDF
        # path, including solver dummies.
        for position in range(512):
            logits = logits0 if position < 256 else logits1
            masks = masks0 if position < 256 else masks1
            row = position if position < 256 else position - 256
            probabilities, _ = probability_cdf(
                logits[row], masks[row].astype(bool)
            )
            observed_log_likelihood(
                probabilities, int(np.flatnonzero(masks[row])[0])
            )
        return {"p256_calls": 2}

    def transition_kernel(_: int) -> Mapping[str, int]:
        transitions = 0
        for _index in range(4096):
            state = ExactCentState.initial()
            state = state.act(1)
            transitions += 1
            state = state.act(1)
            transitions += 1
            state = state.deal((0, 5, 10))
            transitions += 1
            state = state.act(1)
            transitions += 1
            state = state.act(1)
            transitions += 1
        return {"exact_cent_transitions": transitions}

    joint_count = 131_072
    resource_rng = CounterRNG()
    joint_logs = np.fromiter(
        (
            -16.0
            * (
                (
                    resource_rng.uint64(
                        "SOLVER_A_ROOT_DEAL", ("resource-log", index), 0
                    )
                    >> 11
                )
                / float(1 << 53)
            )
            for index in range(joint_count)
        ),
        dtype=np.float64,
        count=joint_count,
    )
    source = np.zeros(joint_count, dtype=bool)
    source[::64] = True

    def joint_kernel(block: int) -> Mapping[str, int]:
        maximum = joint_logs.max()
        weights = np.exp(joint_logs - maximum)
        mu = weights / weights.sum(dtype=np.float64)
        q, importance, _ = proposal_density(mu, source)
        cdf = np.cumsum(q, dtype=np.float64)
        cdf[-1] = 1.0
        for index in range(4096):
            uniform = CounterRNG().uniform_open01(
                "SOLVER_A_ROOT_DEAL", ("resource", block, index), 0
            )
            selected = dense_cdf_sample(cdf, uniform)
            if not np.isfinite(importance[selected]):
                raise RuntimeError("importance sample")
        return {"joint_entries": joint_count, "proposal_samples": 4096}

    outcome = {
        "root": 0,
        "tape": 0,
        "profile": "synthetic",
        "payoff_cents": 125,
        "hash": "0" * 64,
    }
    one_record = json_bytes(outcome)

    def evidence_kernel(block: int) -> Mapping[str, int]:
        payload = one_record * 4096
        with tempfile.TemporaryDirectory(prefix="f8r1_resource_") as directory:
            target = Path(directory) / f"evidence_{block}.bin"
            descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if file_sha256(target) != hashlib.sha256(payload).hexdigest():
                raise RuntimeError("exclusive evidence hash mismatch")
        return {
            "artifact_bytes": len(payload),
            "outcome_records": 4096,
        }

    bootstrap_values = np.linspace(-2.0, 2.0, 4096, dtype=np.float64)

    def bootstrap_kernel(block: int) -> Mapping[str, int]:
        rng_local = CounterRNG()
        accumulator = 0.0
        draws = 65_536
        for index in range(draws):
            chosen, _ = rng_local.bounded(
                "E0_BOOTSTRAP", ("resource", block, index), 4096
            )
            accumulator += float(bootstrap_values[chosen])
        if not math.isfinite(accumulator):
            raise RuntimeError("bootstrap kernel")
        return {"bootstrap_draws": draws}

    stages = [
        _eight_blocks("canonical_batch256_and_cpu_f64_cdf", canonical_kernel),
        _eight_blocks("permanent512_two_chunk_p256_and_cpu_f64_cdf", p256_kernel),
        _eight_blocks("fresh_exact_cent_vector_transitions", transition_kernel),
        _eight_blocks("joint_logsumexp_q_sampling_mu_over_q", joint_kernel),
        _eight_blocks("exclusive_outcome_serialization_and_hash", evidence_kernel),
        _eight_blocks("deterministic_paired_bootstrap", bootstrap_kernel),
    ]
    canonical_upper = WORK["canonical_census_calls"] + WORK["history_calls"]
    p256_upper = (
        WORK["solver_p256_calls"] + WORK["e0_p256_calls"] + WORK["e1_p256_calls"]
    )
    projections = {
        "canonical_network": _project(
            stages[0], {"canonical_calls": canonical_upper}
        ),
        "p256_network": _project(stages[1], {"p256_calls": p256_upper}),
        "exact_cent_transitions": _project(
            stages[2], {"exact_cent_transitions": WORK["total_transitions"]}
        ),
        "joint_and_proposal": _project(
            stages[3],
            {
                "joint_entries": WORK["joint_entries_max"],
                "proposal_samples": WORK["proposal_samples"],
            },
        ),
        "evidence": _project(
            stages[4],
            {
                "artifact_bytes": WORK["artifact_bytes"],
                "outcome_records": WORK["total_outcome_records"],
            },
        ),
        "bootstrap": _project(
            stages[5],
            {
                "bootstrap_draws": WORK["e0_bootstrap_draws"]
                + WORK["e1_bootstrap_draws"]
            },
        ),
    }
    fixed_finalization = _measure_fixed_finalization()
    sampled_peak_rss = rss_peak_sampler.stop()
    cuda_peak_allocated = int(torch.cuda.max_memory_allocated())
    variable_raw = sum(projections.values())
    projected_wall = (
        fixed_load_seconds
        + metamorphic_seconds
        + float(fixed_finalization["elapsed_seconds"])
        + 1.25 * variable_raw
    )
    after = _process_snapshot(torch)
    rss = max(
        int(before["process_tree_rss_bytes"]),
        int(after["process_tree_rss_bytes"]),
        int(sampled_peak_rss),
    )
    cuda_allocated = cuda_peak_allocated
    gates = {
        "projected_total_wall_seconds_max": projected_wall <= 21_600,
        "projected_process_tree_rss_bytes_max": rss <= 21_474_836_480,
        "projected_cuda_allocated_bytes_max": cuda_allocated <= 6_442_450_944,
        "projected_artifact_bytes_max": WORK["artifact_bytes"] <= 2_147_483_648,
        "gpu_free_bytes_at_start_min": int(before["gpu_free_bytes"])
        >= 6_442_450_944,
        "other_training_processes": before["other_training_processes"] == 0
        and after["other_training_processes"] == 0,
        "true_model_fixed_row_content_isolation": true_model_content_isolation,
        "zero_science": True,
    }
    passed = all(gates.values())
    result = {
        "schema_version": "v5.lrft_f8r1.resource_admission.v1",
        "identity": IDENTITY,
        "status": (
            "LRFT_F8R1_RESOURCE_ADMISSION_PASS_SCIENCE_SEPARATELY_AUTHORIZED"
            if passed
            else "LRFT_F8R1_RESOURCE_ADMISSION_NONPASS_NO_SCIENTIFIC_ROWS"
        ),
        "runner_sha256": runner_sha,
        "preregistration_sha256": PREREG_SHA256,
        "preimplementation_audit_sha256": PREAUDIT_SHA256,
        "implementation_audit": {
            "path": str(implementation_audit.resolve()),
            "sha256": audit_sha,
        },
        "fixed_inputs": {
            str(CHECKPOINT): CHECKPOINT_SHA256,
            str(NETWORK_SOURCE): NETWORK_SHA256,
            str(SHOWDOWN_SOURCE): SHOWDOWN_SHA256,
        },
        "exact_work": WORK,
        "stages": stages,
        "projection": {
            "stage_seconds": projections,
            "fixed_load_seconds": fixed_load_seconds,
            "fixed_model_metamorphic_seconds": metamorphic_seconds,
            "fixed_finalization": fixed_finalization,
            "variable_safety_factor": 1.25,
            "projected_total_wall_seconds": projected_wall,
            "projected_process_tree_rss_bytes": rss,
            "rss_peak_sampling_interval_seconds": (
                rss_peak_sampler.interval_seconds
            ),
            "projected_cuda_allocated_bytes": cuda_allocated,
            "cuda_peak_source": (
                "torch.cuda.reset_peak_memory_stats_after_model_load_then_"
                "max_memory_allocated_after_all_kernels"
            ),
            "projected_artifact_bytes": WORK["artifact_bytes"],
        },
        "host_before": before,
        "host_after": after,
        "gates": gates,
        "scientific_counts": {
            "census_hands": 0,
            "selected_roots": 0,
            "belief_rows": 0,
            "solver_traversals": 0,
            "leaf_outcomes": 0,
            "E0_tapes": 0,
            "E1_tapes": 0,
            "teacher_rows": 0,
            "checkpoints": 0,
            "slumbot_hands": 0,
            "official_hands": 0,
        },
    }
    OUTPUT_ROOT.mkdir(parents=False, exist_ok=False)
    descriptor = os.open(RESOURCE_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "wb") as stream:
        payload = json_bytes(result)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        required=True,
        choices=("contract-probe", "no-model-contracts", "resource-admission"),
    )
    parser.add_argument("--implementation-audit", type=Path)
    parser.add_argument("--probe-root", type=Path)
    arguments = parser.parse_args()
    if arguments.mode == "contract-probe":
        if arguments.probe_root is None:
            parser.error("--probe-root is required for contract-probe")
        print(json.dumps(contract_probe(arguments.probe_root), sort_keys=True))
        return 0
    if arguments.mode == "no-model-contracts":
        checks = no_model_contracts()
        print(
            json.dumps(
                {
                    "status": "LRFT_F8R1_NO_MODEL_CONTRACTS_PASS",
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
    result = resource_admission(arguments.implementation_audit)
    print(json.dumps({"status": result["status"], "path": str(RESOURCE_PATH)}))
    return (
        0
        if result["status"]
        == "LRFT_F8R1_RESOURCE_ADMISSION_PASS_SCIENCE_SEPARATELY_AUTHORIZED"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
