"""Heuristic v3 — combination test: v2's tight SB + Path B's polarized BB.

Hypothesis from 2026-05-20 per-position analysis:
  v2:    as SB -28.4 (+22 above floor)  ⭐  as BB -89.7 (-6)
  PathB: as SB -44.8 (+5)                  as BB -60.9 (+23) ⭐
  Combo prediction: ~ -44 bb/100 (+23 above floor)

v3 reuses:
  SB: v2's "PREMIUM 3% raise / STRONG 12% call / rest fold" (preflop SB always
      faces to_call=50 from BB blind, so this is the actual `facing_bet=True`
      branch that v2 ran in practice). Never open-jam.
  BB: Path B-style polarized fold/raise — top ~21% 3-bet/jam, else fold,
      no flat-call. Targets Path B's observed 17.9% BB 3-bet rate.

Range count notes (combos out of 1326):
  PREMIUM_3   = 40 combos  ~ 3.0%   (AA-JJ, AKs, AKo)
  STRONG_12   = 160 combos ~ 12.1%
  PLAYABLE_21 = 278 combos ~ 21.0%
"""
from __future__ import annotations
import torch
import torch.nn as nn

try:
    from treys import Card as TreysCard, Evaluator as TreysEvaluator
    _evaluator = TreysEvaluator()
    _treys_available = True
except ImportError:
    _evaluator = None
    _treys_available = False


RANK_ORDER = '23456789TJQKA'
RANK_IDX = {r: i for i, r in enumerate(RANK_ORDER)}


def _hand_notation(hole_cards):
    r1, s1 = hole_cards[0][0], hole_cards[0][1]
    r2, s2 = hole_cards[1][0], hole_cards[1][1]
    if RANK_IDX[r1] < RANK_IDX[r2]:
        r1, r2 = r2, r1
        s1, s2 = s2, s1
    if r1 == r2:
        return r1 + r2
    return r1 + r2 + ('s' if s1 == s2 else 'o')


PREMIUM_3 = {  # 40/1326 ≈ 3.0%
    'AA','KK','QQ','JJ','AKs','AKo',
}
STRONG_12 = PREMIUM_3 | {  # 160/1326 ≈ 12.1%
    'TT','99','88','77',
    'AQs','AQo','AJs','AJo','KQs','KQo','KJs','QJs','JTs',
    'ATs','A9s','A8s','A7s','A6s','A5s','A4s','A3s','A2s',
}
PLAYABLE_21 = STRONG_12 | {  # 278/1326 ≈ 21.0%
    '66','55','44','33','22',
    'ATo','KTs','KJo','QTs','JTo','T9s','98s','87s',
    'K9s','K8s','K7s','Q9s','J9s','76s','65s','54s',
}


def _is_premium(n): return n in PREMIUM_3
def _is_strong(n): return n in STRONG_12
def _is_playable(n): return n in PLAYABLE_21


# Postflop tiers — same as v2
HS_STRONG, HS_TOP_PAIR, HS_WEAK_PAIR, HS_STRONG_DRAW, HS_AIR = 0, 1, 2, 3, 4


def _eval_postflop(hole, board):
    if not _treys_available or len(board) < 3:
        return HS_AIR
    try:
        hole_t = [TreysCard.new(c) for c in hole]
        board_t = [TreysCard.new(c) for c in board[:5]]
        score = _evaluator.evaluate(board_t, hole_t)
        rc = _evaluator.get_rank_class(score)
        if rc <= 7:
            return HS_STRONG
        if rc == 8:
            return _classify_pair(hole, board[:5])
        if _has_flush_draw(hole, board) or _has_oesd(hole, board):
            return HS_STRONG_DRAW
        return HS_AIR
    except Exception:
        return HS_AIR


def _classify_pair(hole, board):
    if not board:
        return HS_WEAK_PAIR
    board_ranks = sorted([RANK_IDX[c[0]] for c in board], reverse=True)
    top_board = board_ranks[0]
    h1, h2 = RANK_IDX[hole[0][0]], RANK_IDX[hole[1][0]]
    if h1 == h2:
        return HS_TOP_PAIR if h1 > top_board else HS_WEAK_PAIR
    if h1 == top_board or h2 == top_board:
        return HS_TOP_PAIR
    return HS_WEAK_PAIR


def _has_flush_draw(hole, board):
    from collections import Counter
    sc = Counter(c[1] for c in (hole + board) if c)
    return any(v == 4 for v in sc.values())


def _has_oesd(hole, board):
    ranks = sorted({RANK_IDX[c[0]] for c in (hole + board) if c}, reverse=True)
    for i in range(len(ranks) - 3):
        if ranks[i] - ranks[i + 3] == 3:
            return True
    return False


def choose_action(hole_cards, board, state, client_pos, legal_mask):
    st = state['st']
    to_call = state.get('to_call', 0)
    is_hero_sb = (client_pos == 1)  # Slumbot convention: 1=SB (first preflop), 0=BB
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
            # SB always faces to_call=50 (BB blind) preflop, so this branch
            # handles BOTH "open" and "facing BB 3-bet".
            # Strategy (copies v2 actual behavior that produced -28.4 as SB):
            #   PREMIUM_3 → raise small (slot 5/7, never jam 8)
            #   STRONG_12 → call (limp, slot 1)
            #   else → fold
            if _is_premium(n):
                return pick([5, 7, 1, 0])      # small raise; explicitly NO slot 8 jam
            if _is_strong(n):
                return pick([1, 0])             # limp
            return pick([0, 1])                 # fold

        # Hero is BB
        if not facing_bet:
            # SB limped — see flop cheap
            return pick([1, 2, 0])

        # BB facing SB raise — POLARIZED Path B-style (no flat call!)
        # PLAYABLE_21 → 3-bet/jam (~ Path B's 17.9% observed rate)
        # else → fold
        if _is_playable(n):
            return pick([7, 5, 8, 0])           # 3-bet large; allow jam fallback; no call/check
        return pick([0, 1])                     # fold

    # ── POSTFLOP — same as v2 (Path B has 0% call/check postflop too, so
    # for now use a value-betting tight-passive postflop) ──
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


class HeuristicV3Policy(nn.Module):
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
