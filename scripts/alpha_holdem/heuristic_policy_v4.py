"""Wide-range 200bb HUNL policy built from the measured v3 leak report.

v3 lost most of its value by folding the small blind too often and by defending
the big blind with a polarized raise-or-fold strategy.  v4 plays position-aware
preflop ranges and continues more often against small flop bets while retaining
v3's conservative turn/river behavior.
"""
from __future__ import annotations

import itertools

import torch
import torch.nn as nn

try:
    from heuristic_policy_v3 import (
        HS_AIR,
        HS_STRONG,
        HS_STRONG_DRAW,
        HS_TOP_PAIR,
        HS_WEAK_PAIR,
        RANK_IDX,
        RANK_ORDER,
        _eval_postflop,
        _hand_notation,
    )
except ImportError:
    from .heuristic_policy_v3 import (
        HS_AIR,
        HS_STRONG,
        HS_STRONG_DRAW,
        HS_TOP_PAIR,
        HS_WEAK_PAIR,
        RANK_IDX,
        RANK_ORDER,
        _eval_postflop,
        _hand_notation,
    )


SUITS = "cdhs"


def _category_score(notation: str) -> float:
    """Smooth approximate HU equity ordering for the 169 preflop classes."""
    high = RANK_IDX[notation[0]] + 2
    low = RANK_IDX[notation[1]] + 2
    if high == low:
        return 130.0 + 6.0 * high
    suited = notation.endswith("s")
    gap = high - low - 1
    gap_penalty = (0.0, 0.0, 2.0, 5.0, 9.0, 13.0)[min(gap, 5)]
    score = 7.0 * high + 3.0 * low + (5.0 if suited else 0.0) - gap_penalty
    if high == 14:
        score += 4.0
    if high >= 11 and low >= 10:
        score += 4.0
    if low >= 10:
        score += 2.0
    return score


def _build_percentiles() -> dict[str, float]:
    weighted: dict[str, int] = {}
    cards = [rank + suit for rank in RANK_ORDER for suit in SUITS]
    for first, second in itertools.combinations(cards, 2):
        notation = _hand_notation([first, second])
        weighted[notation] = weighted.get(notation, 0) + 1
    ordered = sorted(
        weighted,
        key=lambda n: (_category_score(n), n.endswith("s"), n),
        reverse=True,
    )
    result: dict[str, float] = {}
    consumed = 0
    for notation in ordered:
        combos = weighted[notation]
        result[notation] = (consumed + 0.5 * combos) / 1326.0
        consumed += combos
    if consumed != 1326:
        raise AssertionError(f"preflop combo census mismatch: {consumed}")
    return result


PREFLOP_PERCENTILE = _build_percentiles()


def _top_fraction(hole_cards, fraction: float) -> bool:
    return PREFLOP_PERCENTILE[_hand_notation(hole_cards)] <= float(fraction)


def _has_ace_high_or_two_overcards(hole_cards, board) -> bool:
    if not board:
        return False
    hole_ranks = sorted((RANK_IDX[c[0]] + 2 for c in hole_cards), reverse=True)
    board_high = max(RANK_IDX[c[0]] + 2 for c in board)
    return hole_ranks[0] == 14 or min(hole_ranks) > board_high


def choose_action(hole_cards, board, state, client_pos, legal_mask):
    street = int(state["st"])
    to_call = int(state.get("to_call", 0))
    legal = [bool(legal_mask[i]) for i in range(9)]

    def pick(preferred):
        for slot in preferred:
            if 0 <= slot < 9 and legal[slot]:
                return slot
        return next((slot for slot in range(9) if legal[slot]), 0)

    if street == 0:
        actions = list(state.get("street_actions", [[], [], [], []])[0])
        action_count = len(actions)
        hero_is_sb = int(client_pos) == 1

        if hero_is_sb and action_count == 0:
            # The button should not surrender its positional edge.  Raise the
            # stronger 58% and limp the rest; never open-fold for 0.5bb.
            return pick([7, 1]) if _top_fraction(hole_cards, 0.58) else pick([1, 0])

        if not hero_is_sb and action_count == 1 and actions[0][0] == "c":
            # Punish limps with the top quarter, otherwise realize equity.
            return pick([7, 1]) if _top_fraction(hole_cards, 0.25) else pick([1, 0])

        if not hero_is_sb and action_count == 1 and actions[0][0] == "b":
            # Versus an SB open: 3-bet 12%, flat through 76%, fold the bottom.
            if _top_fraction(hole_cards, 0.12):
                return pick([7, 1, 0])
            if _top_fraction(hole_cards, 0.76):
                return pick([1, 0])
            return pick([0, 1])

        if hero_is_sb and action_count == 2:
            opened = actions[0][0] == "b"
            if opened:
                # Facing a 3-bet after opening: 4-bet the top 6%, call through
                # 48%, then fold.  Never use the 200bb jam slot.
                if _top_fraction(hole_cards, 0.06):
                    return pick([7, 1, 0])
                if _top_fraction(hole_cards, 0.48):
                    return pick([1, 0])
                return pick([0, 1])
            # Limp-reraise or call a BB isolation raise.
            if _top_fraction(hole_cards, 0.08):
                return pick([7, 1, 0])
            if _top_fraction(hole_cards, 0.70):
                return pick([1, 0])
            return pick([0, 1])

        # Later preflop raises: continue a compact value range.
        if _top_fraction(hole_cards, 0.07):
            return pick([7, 1, 0])
        if _top_fraction(hole_cards, 0.22):
            return pick([1, 0])
        return pick([0, 1])

    strength = _eval_postflop(hole_cards, board)
    facing_bet = to_call > 0

    if not facing_bet:
        if strength == HS_STRONG:
            return pick([3, 2, 4, 1])
        if strength == HS_TOP_PAIR:
            return pick([2, 3, 1])
        if strength == HS_STRONG_DRAW and street < 3:
            return pick([1, 2])
        return pick([1, 0])

    # The exact pot is not passed to heuristic policies, but total_last_bet_to
    # gives a stable conservative scale for identifying genuinely small bets.
    scale = max(int(state.get("total_last_bet_to", 0)), 100)
    small_price = to_call <= max(100, int(0.40 * scale))
    hero_is_bb = int(client_pos) == 0

    if strength == HS_STRONG:
        return pick([1, 2, 3, 0])
    if strength == HS_TOP_PAIR:
        return pick([1, 0])
    if strength == HS_WEAK_PAIR:
        return pick([1, 0]) if small_price else pick([0, 1])
    if strength == HS_STRONG_DRAW and street < 3:
        return pick([1, 0]) if small_price else pick([0, 1])
    if (
        street == 1
        and hero_is_bb
        and small_price
        and _has_ace_high_or_two_overcards(hole_cards, board)
    ):
        return pick([1, 0])
    return pick([0, 1])


class HeuristicV4Policy(nn.Module):
    def __init__(self, num_actions: int = 9):
        super().__init__()
        self.num_actions = num_actions
        self._last_choice = None

    def decide(self, hole_cards, board, state, client_pos, legal_mask) -> int:
        self._last_choice = choose_action(
            hole_cards, board, state, client_pos, legal_mask
        )
        return int(self._last_choice)

    def forward(self, card, action_inp, extra, legal_mask=None):
        batch = card.shape[0]
        logits = torch.zeros(batch, self.num_actions, device=card.device)
        if self._last_choice is not None:
            logits[:, self._last_choice] = 1e6
        if legal_mask is not None:
            logits = logits + (1 - legal_mask) * (-1e9)
        return logits, torch.zeros(batch, 1, device=card.device)


class HeuristicV4NoLimpPolicy(HeuristicV4Policy):
    """V4 preflop ranges with the dominated bottom-range SB limp removed."""

    def decide(self, hole_cards, board, state, client_pos, legal_mask) -> int:
        selected = int(super().decide(
            hole_cards, board, state, client_pos, legal_mask
        ))
        actions = list(state.get("street_actions", [[], [], [], []])[0])
        if (
            int(state.get("st", 0)) == 0
            and int(client_pos) == 1
            and not actions
            and selected == 1
            and bool(legal_mask[0])
        ):
            selected = 0
        self._last_choice = selected
        return selected
