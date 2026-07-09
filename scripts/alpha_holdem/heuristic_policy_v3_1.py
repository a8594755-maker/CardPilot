"""Heuristic v3.1 — diagnostic for BB jam sizing.

DIAGNOSTIC HYPOTHESIS:
  "Path B's BB edge (+23 above floor) is mainly caused by jam sizing / fold equity,
  not just by polarized fold-or-raise."

v3 used pick([7, 5, 8, 0]) for BB defense — prefers slot 7 (1.5x pot raise) over slot 8 (jam).
  Observed: BB 3-bet rate 22.2%, opp_fold 11.3% × +3.62 BB
  Path B 10M:                                opp_fold 18.0% × +3.81 BB
  → ~28 bb/100 of fold equity left on the table

v3.1 changes ONLY one line: BB facing SB raise → pick([8, 7, 5, 0]) prefer JAM.

Everything else identical to v3:
  - SB: PREMIUM_3 raise / STRONG_12 limp / rest fold; NEVER open-jam
  - BB facing SB raise: PLAYABLE_21 3-bet, else fold; NO flat-call
  - postflop: same v2/v3 tier-based logic

NOT a new training direction. Pure diagnostic. Even if v3.1 wins big,
do NOT call it 'general strength' — it only tells us BB jam sizing is load-bearing
for the SL anchor / structure design.
"""
from __future__ import annotations
import torch
import torch.nn as nn

# Reuse all v3 helpers
from heuristic_policy_v3 import (
    _hand_notation, _is_premium, _is_strong, _is_playable,
    _eval_postflop, _classify_pair, _has_flush_draw, _has_oesd,
    HS_STRONG, HS_TOP_PAIR, HS_WEAK_PAIR, HS_STRONG_DRAW, HS_AIR,
)


def choose_action(hole_cards, board, state, client_pos, legal_mask):
    st = state['st']
    to_call = state.get('to_call', 0)
    is_hero_sb = (client_pos == 1)
    facing_bet = to_call > 0
    legal = [bool(legal_mask[i]) for i in range(9)]

    def pick(preferred):
        for s in preferred:
            if 0 <= s < 9 and legal[s]:
                return s
        for s in range(9):
            if legal[s]:
                return s
        return 0

    # ── PREFLOP ──
    if st == 0:
        n = _hand_notation(hole_cards)

        if is_hero_sb:
            # SB: identical to v3 — facing_bet=True always due to BB blind
            # PREMIUM raise small (slot 5/7, NEVER slot 8 jam) / STRONG limp / else fold
            if _is_premium(n):
                return pick([5, 7, 1, 0])   # ← critical: 5 first, then 7. NO slot 8. No open-jam.
            if _is_strong(n):
                return pick([1, 0])
            return pick([0, 1])

        # Hero is BB
        if not facing_bet:
            return pick([1, 2, 0])

        # BB facing SB raise — KEY CHANGE: PREFER JAM (slot 8), THEN slot 7, THEN slot 5
        # Tests whether jam sizing is the load-bearing piece of Path B's BB edge.
        if _is_playable(n):
            return pick([8, 7, 5, 0])       # ← v3.1 diagnostic: JAM-first
        return pick([0, 1])

    # ── POSTFLOP — same as v3 ──
    hs = _eval_postflop(hole_cards, board)

    if not facing_bet:
        if hs == HS_STRONG:
            return pick([3, 4, 2, 1])
        if hs == HS_TOP_PAIR:
            return pick([2, 3, 1])
        if hs == HS_WEAK_PAIR:
            return pick([1, 2])
        if hs == HS_STRONG_DRAW:
            if st < 3:
                return pick([2, 1])
            return pick([1, 0])
        return pick([1, 0])

    if hs == HS_STRONG:
        return pick([1, 5, 2, 0])
    if hs == HS_TOP_PAIR:
        return pick([1, 0])
    if hs == HS_WEAK_PAIR:
        pot = max(state.get('pot_before', state.get('pot', 100)), 1)
        if to_call * 2 <= pot:
            return pick([1, 0])
        return pick([0, 1])
    if hs == HS_STRONG_DRAW:
        return pick([1, 0])
    return pick([0, 1])


class HeuristicV3_1Policy(nn.Module):
    def __init__(self, num_actions: int = 9):
        super().__init__()
        self.num_actions = num_actions
        self._last_choice = None

    def decide(self, hole_cards, board, state, client_pos, legal_mask) -> int:
        self._last_choice = choose_action(hole_cards, board, state, client_pos, legal_mask)
        return self._last_choice

    def forward(self, card, action_inp, extra, legal_mask=None):
        B = card.shape[0]
        logits = torch.zeros(B, self.num_actions, device=card.device)
        if self._last_choice is not None:
            logits[:, self._last_choice] = 1e6
        if legal_mask is not None:
            logits = logits + (1 - legal_mask) * (-1e9)
        return logits, torch.zeros(B, 1, device=card.device)
