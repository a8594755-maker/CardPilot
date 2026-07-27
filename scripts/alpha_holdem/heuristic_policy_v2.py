"""Heuristic v2 — stronger HUNL baseline with flat-call ranges + size-aware postflop.

Goal: test whether the -50 bb/100 ceiling reflects Slumbot/abstraction limits
or just weak structure. v1 maxed at -51 with tight-passive + no flat-call.
v2 adds:

  preflop SB open : open top ~40% (was ~50%), never open-jam
  preflop SB facing 3-bet : 4-bet top 8%, call top 25%, fold rest
  preflop BB facing raise : 3-bet top 8%, CALL top 35% (flat range), fold rest
  postflop : finer hand-strength tiers (STRONG / TOP_PAIR / WEAK_PAIR / DRAW / AIR)
             — bet sizes scale with strength; never river-jam; cap sizing at half-pot

Slot map (vec_game_state.py):
  0=fold, 1=check/call, 2=raise 0.33pot, 3=raise 0.50, 4=raise 0.67,
  5=raise 0.75/1.0pot, 6=raise 1.0, 7=raise 1.5pot, 8=allin
Preflop legal raises are a subset.
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


# v2 tighter ranges (in HUNL these are wider than 9-handed; numbers are %)
PREMIUM_8 = {  # ~top 8% — 4-bet / 3-bet for value
    'AA','KK','QQ','JJ','AKs','AKo',
}
STRONG_25 = PREMIUM_8 | {  # ~top 25% — call vs 3-bet
    'TT','99','88','77',
    'AQs','AQo','AJs','AJo','KQs','KQo','KJs','QJs','JTs',
    'ATs','A9s','A8s','A7s','A6s','A5s','A4s','A3s','A2s',
}
PLAYABLE_40 = STRONG_25 | {  # ~top 40% — open from SB
    '66','55','44','33','22',
    'ATo','KTs','KJo','QTs','JTo','T9s','98s','87s',
    'K9s','K8s','K7s','Q9s','J9s','76s','65s','54s',
}
FLAT_BB_35 = STRONG_25 | {  # ~top 35% — BB flat-call vs SB raise
    '66','55','44','33','22',
    'ATo','KTs','QTs','JTo','T9s','98s','87s',
    'K9s','Q9s','J9s','76s','65s',
}


def _is_premium(n): return n in PREMIUM_8
def _is_strong(n): return n in STRONG_25
def _is_playable(n): return n in PLAYABLE_40
def _is_flat_bb(n): return n in FLAT_BB_35


# Postflop hand-strength tiers (more granular than v1)
HS_STRONG = 0      # two pair+ (set/straight/flush/full/quads/etc.)
HS_TOP_PAIR = 1    # pair with top kicker (top board pair OR pocket pair > top board)
HS_WEAK_PAIR = 2   # any other pair (mid/bottom pair, weak overpair)
HS_STRONG_DRAW = 3 # flush draw, OESD, or strong combo
HS_AIR = 4


def _eval_postflop(hole, board):
    if not _treys_available or len(board) < 3:
        return HS_AIR
    try:
        hole_t = [TreysCard.new(c) for c in hole]
        board_t = [TreysCard.new(c) for c in board[:5]]
        score = _evaluator.evaluate(board_t, hole_t)
        rc = _evaluator.get_rank_class(score)
        # rc: 1=SF, 2=Quads, 3=Boat, 4=Flush, 5=Straight, 6=Trips, 7=TwoPair, 8=Pair, 9=High
        if rc <= 7:
            return HS_STRONG
        if rc == 8:
            return _classify_pair(hole, board[:5])
        # No made hand
        if _has_flush_draw(hole, board) or _has_oesd(hole, board):
            return HS_STRONG_DRAW
        return HS_AIR
    except Exception:
        return HS_AIR


def _classify_pair(hole, board):
    """Distinguish top pair (one hole card matches top board card, or pocket pair
    > top board card) from weak pair."""
    if not board:
        return HS_WEAK_PAIR
    board_ranks = sorted([RANK_IDX[c[0]] for c in board], reverse=True)
    top_board = board_ranks[0]
    h1, h2 = RANK_IDX[hole[0][0]], RANK_IDX[hole[1][0]]
    # Pocket pair
    if h1 == h2:
        # Overpair (PP > top board) treated as TOP_PAIR for sizing
        if h1 > top_board:
            return HS_TOP_PAIR
        return HS_WEAK_PAIR
    # Non-pair hole: did one card pair the top board?
    if h1 == top_board or h2 == top_board:
        return HS_TOP_PAIR
    return HS_WEAK_PAIR


def _has_flush_draw(hole, board):
    from collections import Counter
    cards = hole + board
    sc = Counter(c[1] for c in cards if c)
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
    is_hero_sb = (client_pos == 1)  # Slumbot client_pos=1 → hero is SB (first preflop)
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

        if is_hero_sb and not facing_bet:
            # SB opening preflop. Open top 40%, fold rest. Never open-jam.
            if _is_playable(n):
                return pick([2, 5, 7, 1])  # small open (slot 2 = 0.33-ish), never slot 8
            return pick([0, 1])

        if is_hero_sb and facing_bet:
            # SB facing BB 3-bet (after our open).
            if _is_premium(n):
                return pick([5, 7, 1, 0])  # 4-bet small or call
            if _is_strong(n):
                return pick([1, 0])         # call
            return pick([0, 1])             # fold

        # Hero is BB
        if not facing_bet:
            # SB limped → check option
            return pick([1, 2, 0])

        # BB facing SB raise — KEY ADDITION: flat-call range
        if _is_premium(n):
            return pick([5, 1, 0])           # 3-bet for value (small)
        if _is_flat_bb(n):
            return pick([1, 0])               # FLAT CALL (this is new in v2!)
        return pick([0, 1])                  # fold

    # ── POSTFLOP ──
    hs = _eval_postflop(hole_cards, board)

    if not facing_bet:
        # We have the option. Value bet strength tiers; check air.
        if hs == HS_STRONG:
            return pick([3, 4, 2, 1])         # 0.5x pot value (cap; never jam)
        if hs == HS_TOP_PAIR:
            return pick([2, 3, 1])            # 0.33x pot small value
        if hs == HS_WEAK_PAIR:
            return pick([1, 2])               # check (pot control)
        if hs == HS_STRONG_DRAW:
            # Semi-bluff small only when in position pre-river to avoid bloating pot
            if st < 3:                        # not river
                return pick([2, 1])
            return pick([1, 0])               # river: don't bluff with miss-draw
        return pick([1, 0])                   # air checks

    # Facing bet postflop
    if hs == HS_STRONG:
        return pick([1, 5, 2, 0])             # call (mostly); rare value-raise
    if hs == HS_TOP_PAIR:
        return pick([1, 0])                   # call
    if hs == HS_WEAK_PAIR:
        # Call only if bet is small-ish (<=0.5 pot proxy via to_call < 0.5 * pot_before)
        pot = max(state.get('pot_before', state.get('pot', 100)), 1)
        if to_call * 2 <= pot:                # call small bet
            return pick([1, 0])
        return pick([0, 1])                   # fold to large bet
    if hs == HS_STRONG_DRAW:
        # Continue if pot-odds reasonable (treat ~3:1 as auto-call proxy)
        return pick([1, 0])
    return pick([0, 1])                        # air folds


class HeuristicV2Policy(nn.Module):
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
