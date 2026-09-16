"""Versioned, integer-chip, no-rake heads-up NLHE. Legacy engines are untouched.

Seat 0 is BB/OOP; seat 1 is SB/button. No raise cap. This core accepts physical
actions, not policy slots. All monetary state is integer chips (100 chips/bb).
State transitions are immutable; recorded actions include their true street.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import random

from deep_cfr.hand_eval import compare_hands

RULES_VERSION = "hunl_integer_chips_v1"
BB = 100
SB = 50


@dataclass(frozen=True)
class Event:
    street: int
    player: int
    kind: str                 # f/k/c/b (b is a physical bet-or-raise-to)
    amount: int = 0           # street total for b, zero for passive actions
    is_raise: bool = False    # blinds count as an existing bet


@dataclass(frozen=True)
class ChipState:
    initial: tuple[int, int]
    stacks: tuple[int, int]
    bets: tuple[int, int]
    pot: int
    deck: tuple[int, ...]
    holes: tuple[tuple[int, int], tuple[int, int]]
    board: tuple[int, ...] = ()
    street: int = 0
    actor: int = 1
    pending: tuple[int, ...] = (1, 0)
    last_full_raise: int = BB
    history: tuple[Event, ...] = ()
    terminal: bool = False
    folded: int = -1

    @classmethod
    def new(cls, deck=None, initial=(20000, 20000)):
        if deck is None:
            deck = list(range(52))
            random.shuffle(deck)
        deck = tuple(deck)
        initial = tuple(initial)
        if len(deck) != 52 or any(type(c) is not int for c in deck) or set(deck) != set(range(52)):
            raise ValueError("A full permutation of 52 distinct cards is required")
        if len(initial) != 2 or any(type(x) is not int or x <= BB for x in initial):
            raise ValueError("Two integer starting stacks greater than one BB required")
        return cls(initial, (initial[0]-BB, initial[1]-SB), (BB, SB), BB+SB,
                   deck, ((deck[0], deck[1]), (deck[2], deck[3])))

    @property
    def to_call(self):
        return max(self.bets[1-self.actor] - self.bets[self.actor], 0) if not self.terminal else 0

    @property
    def max_to(self):
        return self.bets[self.actor] + self.stacks[self.actor] if not self.terminal else 0

    @property
    def can_raise(self):
        # In HU a short all-in cannot reopen action: the only opponent has zero
        # chips. This also forbids betting into an uncontested, empty side pot.
        return (not self.terminal and self.stacks[1-self.actor] > 0
                and self.stacks[self.actor] > self.to_call)

    @property
    def min_to(self):
        return min(max(self.bets) + self.last_full_raise, self.max_to) if self.can_raise else None

    def validate_action(self, kind, amount=0):
        if self.terminal or self.actor not in (0, 1):
            raise ValueError("No action in a terminal state")
        if type(amount) is not int or amount < 0:
            raise ValueError("Action amount must be nonnegative integer chips")
        if kind != "b" and amount:
            raise ValueError("Only a bet/raise has a target amount")
        if kind == "f" and self.to_call > 0:
            return
        if kind == "k" and self.to_call == 0:
            return
        if kind == "c" and self.to_call > 0:
            return
        if kind == "b" and self.can_raise and self.min_to <= amount <= self.max_to:
            return
        raise ValueError(f"Illegal {kind}{amount}: actor={self.actor}, call={self.to_call}, min={self.min_to}")

    def act(self, kind, amount=0):
        self.validate_action(kind, amount)
        p, q = self.actor, 1-self.actor
        event = Event(self.street, p, kind, amount, kind == "b" and max(self.bets) > 0)
        s = replace(self, history=self.history + (event,))
        if kind == "f":
            return replace(s._refund_uncalled(), terminal=True, folded=p, actor=-1, pending=())
        stacks, bets = list(s.stacks), list(s.bets)
        paid = min(s.to_call, stacks[p]) if kind == "c" else amount-bets[p] if kind == "b" else 0
        stacks[p] -= paid
        bets[p] += paid
        pending = (q,) if kind == "b" else tuple(x for x in s.pending if x != p)
        increment = amount-max(s.bets) if kind == "b" else 0
        s = replace(s, stacks=tuple(stacks), bets=tuple(bets), pot=s.pot+paid,
                    pending=pending, last_full_raise=max(s.last_full_raise, increment))
        if pending:
            return replace(s, actor=pending[0])
        s = s._refund_uncalled()
        if min(s.stacks) == 0:
            return replace(s._deal_to(5), terminal=True, street=4, actor=-1, pending=())
        if s.street == 3:
            return replace(s, terminal=True, street=4, actor=-1, pending=())
        street = s.street + 1
        return replace(s._deal_to(street+2), street=street, bets=(0, 0), actor=0,
                       pending=(0, 1), last_full_raise=BB)

    def _refund_uncalled(self):
        difference = self.bets[0]-self.bets[1]
        if not difference:
            return self
        p = 0 if difference > 0 else 1
        stacks, bets = list(self.stacks), list(self.bets)
        stacks[p] += abs(difference)
        bets[p] -= abs(difference)
        return replace(self, stacks=tuple(stacks), bets=tuple(bets), pot=self.pot-abs(difference))

    def _deal_to(self, count):
        # No burn cards: drawing a uniformly shuffled unseen card has the same
        # distribution. Fixed-deal oracle feeds these exact public cards.
        if not len(self.board) <= count <= 5:
            raise ValueError("Invalid board length")
        return replace(self, board=tuple(self.deck[-i-1] for i in range(count)))

    def payoffs(self):
        if not self.terminal:
            raise ValueError("No payoff before terminal")
        winnings = [0, 0]
        if self.folded >= 0:
            winnings[1-self.folded] = self.pot
        else:
            comparison = compare_hands(self.holes[0], self.holes[1], list(self.board))
            if comparison:
                winnings[0 if comparison > 0 else 1] = self.pot
            else:
                winnings = [(self.pot+1)//2, self.pot//2]  # first seat left of button
        return tuple(self.stacks[p]+winnings[p]-self.initial[p] for p in range(2))

    def assert_invariants(self):
        assert all(type(x) is int and x >= 0 for x in (*self.stacks, *self.bets, self.pot))
        assert sum(self.stacks)+self.pot == sum(self.initial)
        assert sum(self.bets) <= self.pot
        visible = (*self.holes[0], *self.holes[1], *self.board)
        assert len(set(visible)) == len(visible)
        assert all(self.initial[p]-self.stacks[p] >= self.bets[p] for p in (0, 1))
        assert self.actor == (-1 if self.terminal else self.pending[0])
        if self.terminal:
            assert sum(self.payoffs()) == 0
        else:
            assert len(self.board) == (0 if self.street == 0 else self.street+2)
