"""Simple HUNL heuristic baseline — tight-passive style.

Designed to test the hypothesis: 'RL hasn't learned poker structure'.
If this hand-crafted policy outperforms V4/PathB Slumbot benches, that's
evidence the RL pipeline is not extracting basic poker structure from
self-play, and the answer isn't more compute (or pool).

Strategy summary:
  preflop SB (open):
    top 5% hands (AA-TT, AK, AKs)            -> raise small (slot 2 = 0.33x pot)
    next 15% (top 20%)                       -> raise small (slot 2)
    50% (top 50%)                            -> raise small (slot 2)
    bottom 50%                               -> fold
    NEVER open-jam 200bb
  preflop BB facing SB limp (no raise):
    always check                              -> slot 1
  preflop BB facing SB raise (small):
    top 5%                                   -> 3-bet small (slot 5 ~ 1.0x pot)
    top 5..20%                               -> call (slot 1)
    bottom 80%                               -> fold
  preflop facing 3-bet or 4-bet:
    top 5% (QQ+, AK)                         -> call (or rarely 4-bet small)
    rest                                     -> fold
  postflop:
    pair+ on board OR strong draw (FD/OESD)  -> bet small (slot 2) when checked to
                                              call when facing bet
    overpair (PP > top board)                -> bet small
    air (no pair / no draw)                  -> check (slot 1) / fold to bet (slot 0)

Slot map (vec_game_state.py):
  0=fold, 1=check/call, 2=raise 0.33pot, 3=raise 0.50, 4=raise 0.67,
  5=raise 0.75/1.0pot, 6=raise 1.0, 7=raise 1.5pot, 8=allin
Preflop legal raises are subset of {2,5,7} per PREFLOP_LEGAL_RAISE_SLOTS.
"""
from __future__ import annotations
import torch
import torch.nn as nn


# Treys for postflop hand evaluation
try:
    from treys import Card as TreysCard, Evaluator as TreysEvaluator
    _treys_available = True
    _evaluator = TreysEvaluator()
except ImportError:
    _treys_available = False
    _evaluator = None


# ─── Preflop chart (169 starting hand classes) ──────────────────────────────
# Rank order, used for canonicalisation. '2' is weakest, 'A' strongest.
RANK_ORDER = '23456789TJQKA'
RANK_IDX = {r: i for i, r in enumerate(RANK_ORDER)}


def _hand_notation(hole_cards: list[str]) -> str:
    """Convert ['As','Kd'] -> 'AKo' (offsuit) or ['As','Ks'] -> 'AKs' (suited).
    Pairs return 'AA', 'KK', etc."""
    r1, s1 = hole_cards[0][0], hole_cards[0][1]
    r2, s2 = hole_cards[1][0], hole_cards[1][1]
    if RANK_IDX[r1] < RANK_IDX[r2]:
        r1, r2 = r2, r1
        s1, s2 = s2, s1
    if r1 == r2:
        return r1 + r2
    return r1 + r2 + ('s' if s1 == s2 else 'o')


# Approximate preflop equity rank (top X%) for HUNL (single opponent).
# Source: combination of poker tracking software defaults + intuition;
# numbers are conservative for HUNL where ranges are wider.
PREMIUM = {  # top ~5%: very strong, never fold preflop
    'AA','KK','QQ','JJ','TT','AKs','AKo',
}
STRONG = PREMIUM | {  # top ~20%: open-raise, call vs 3-bet
    '99','88','77','AQs','AQo','AJs','AJo','KQs','KQo',
    'ATs','KJs','KTs','QJs','QTs','JTs',
    'A9s','A8s','A7s','A6s','A5s','A4s','A3s','A2s',
}
PLAYABLE = STRONG | {  # top ~50%: open-raise on button, fold to big aggression
    '66','55','44','33','22',
    'KJo','KTo','QJo','QTo','JTo','J9s','T9s','98s','87s','76s',
    'ATo','A9o','A8o','A7o','A6o','A5o','A4o','A3o','A2o',
    'K9s','K8s','K7s','K6s','K5s','K4s','K3s','K2s',
    'Q9s','Q8s','Q7s','J8s','T8s','97s','86s','75s','65s','54s',
}


def _is_premium(notation: str) -> bool:
    return notation in PREMIUM


def _is_strong(notation: str) -> bool:
    return notation in STRONG


def _is_playable(notation: str) -> bool:
    return notation in PLAYABLE


# ─── Postflop hand strength categories ──────────────────────────────────────
HAND_STRENGTH_STRONG = 0   # two pair+ (set, straight, flush, full, quads, etc.)
HAND_STRENGTH_PAIR = 1     # any pair (top pair / mid pair / bottom / pocket pair)
HAND_STRENGTH_DRAW = 2     # flush draw or open-ended straight draw (no pair)
HAND_STRENGTH_AIR = 3      # nothing


def _evaluate_postflop(hole: list[str], board: list[str]) -> int:
    """Classify hero's hand on flop/turn/river. Uses treys if available."""
    if not _treys_available or len(board) < 3:
        return HAND_STRENGTH_AIR
    try:
        hole_t = [TreysCard.new(c) for c in hole]
        board_t = [TreysCard.new(c) for c in board[:5]]
        score = _evaluator.evaluate(board_t, hole_t)  # lower = stronger
        # treys rank classes: 0=straight flush down to 8=high card; lower = stronger
        rank_class = _evaluator.get_rank_class(score)
        # rank_class: 1=Royal/SF, 2=Quads, 3=Boat, 4=Flush, 5=Straight, 6=Trips, 7=TwoPair, 8=Pair, 9=High Card
        if rank_class <= 7:
            return HAND_STRENGTH_STRONG
        if rank_class == 8:
            return HAND_STRENGTH_PAIR
        # No made hand — check for draws
        if _has_flush_draw(hole, board) or _has_oesd(hole, board):
            return HAND_STRENGTH_DRAW
        return HAND_STRENGTH_AIR
    except Exception:
        return HAND_STRENGTH_AIR


def _has_flush_draw(hole, board):
    """4-card flush draw (4 cards of the same suit between hole+board)."""
    cards = hole + board
    from collections import Counter
    suit_counts = Counter(c[1] for c in cards if c)
    return any(v >= 4 for v in suit_counts.values()) and not any(v >= 5 for v in suit_counts.values())


def _has_oesd(hole, board):
    """Open-ended straight draw — heuristic: 4 consecutive ranks present
    among hole+board with gaps <= 0."""
    ranks = sorted({RANK_IDX[c[0]] for c in (hole + board) if c}, reverse=True)
    # Look for any 4-in-a-row (n-2..n+1)
    for i in range(len(ranks) - 3):
        if ranks[i] - ranks[i + 3] == 3:
            return True
    return False


# ─── Action chooser given the high-level Slumbot state ──────────────────────
def choose_action(hole_cards: list[str], board: list[str], state: dict,
                  client_pos: int, legal_mask) -> int:
    """Return a 9-slot action index. Picks the FIRST-legal among the
    heuristic's preferred ordering, never falling outside legal_mask."""
    st = state['st']  # 0=preflop 1=flop 2=turn 3=river
    to_call = state.get('to_call', 0)
    is_hero_sb = (client_pos == 1)  # Slumbot convention (play_slumbot.py:12): client_pos=1 → hero SB (first preflop), =0 → BB
    # NOTE: this was originally inverted (client_pos==0); the original v1 bench reported -51.04 over 8k hands
    # but with the SB/BB branches swapped. v2 has the correct mapping from the start.
    facing_bet = to_call > 0

    # Slots present in legal_mask (boolean / float, 9 entries)
    legal = [bool(legal_mask[i]) for i in range(9)]

    def pick(preferred):
        """Return the first slot in preferred[] that is legal."""
        for s in preferred:
            if 0 <= s < 9 and legal[s]:
                return s
        # Fallback: any legal slot
        for s in range(9):
            if legal[s]:
                return s
        return 0  # impossible

    # ── PREFLOP ──────────────────────────────────────────────────────────
    if st == 0:
        notation = _hand_notation(hole_cards)

        if is_hero_sb and not facing_bet:
            # SB acts first preflop. Open-raise top 50%, fold rest.
            if _is_playable(notation):
                return pick([2, 5, 7, 1])   # min-raise; never open-jam
            return pick([0, 1])  # fold (or check if check is somehow legal)

        if is_hero_sb and facing_bet:
            # SB facing 3-bet (BB raised).
            if _is_premium(notation):
                return pick([5, 7, 1, 0])   # call or small 4-bet
            if _is_strong(notation):
                return pick([1, 0])         # call
            return pick([0, 1])             # fold

        # BB (acts second preflop)
        if not facing_bet:
            return pick([1, 2, 0])  # check, vs SB limp

        # BB facing SB raise
        if _is_premium(notation):
            return pick([5, 1, 0])          # 3-bet small or call
        if _is_strong(notation):
            return pick([1, 0])             # call
        return pick([0, 1])                 # fold

    # ── POSTFLOP ─────────────────────────────────────────────────────────
    hs = _evaluate_postflop(hole_cards, board)

    if not facing_bet:
        # Bet for value with pair+ ; check air / small draws
        if hs == HAND_STRENGTH_STRONG:
            return pick([2, 3, 5, 1])
        if hs == HAND_STRENGTH_PAIR:
            return pick([2, 1])              # small value bet
        if hs == HAND_STRENGTH_DRAW:
            return pick([1, 2])              # check (or rarely semi-bluff)
        return pick([1, 0])                  # check air

    # Facing bet postflop
    if hs == HAND_STRENGTH_STRONG:
        return pick([1, 5, 2, 0])           # call (or rarely raise)
    if hs == HAND_STRENGTH_PAIR:
        return pick([1, 0])                  # call top-pair-or-pocket-pair
    if hs == HAND_STRENGTH_DRAW:
        return pick([1, 0])                  # peel one
    return pick([0, 1])                      # fold air


# ─── nn.Module wrapper so play_slumbot.py existing harness works ────────────
class HeuristicPolicy(nn.Module):
    """Wraps choose_action() in the AlphaHoldemNet interface so play_slumbot.py
    can use it without architectural changes. The forward returns logits where
    the heuristic-chosen slot dominates — used after legal-masking + argmax."""
    def __init__(self, num_actions: int = 9):
        super().__init__()
        self.num_actions = num_actions
        self._last_choice = None  # set by decide() before forward

    def decide(self, hole_cards, board, state, client_pos, legal_mask) -> int:
        self._last_choice = choose_action(hole_cards, board, state, client_pos, legal_mask)
        return self._last_choice

    def forward(self, card, action_inp, extra, legal_mask=None):
        # Build a one-hot logits tensor at the precomputed choice.
        B = card.shape[0]
        logits = torch.zeros(B, self.num_actions, device=card.device)
        if self._last_choice is not None:
            logits[:, self._last_choice] = 1e6
        if legal_mask is not None:
            logits = logits + (1 - legal_mask) * (-1e9)
        value = torch.zeros(B, 1, device=card.device)
        return logits, value
