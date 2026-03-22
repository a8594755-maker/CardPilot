"""
Hand evaluation for SD-CFR.
Uses the `treys` library (pip install treys) for fast 5/6/7-card evaluation.
Card encoding: 0..51 where card = rank*4 + suit (rank: 0=2..12=A, suit: 0=c 1=d 2=h 3=s).
"""

from __future__ import annotations

from functools import lru_cache

from treys import Card as TreysCard, Evaluator as TreysEvaluator

_evaluator = TreysEvaluator()

# ---------- Card conversion: our int encoding <-> treys encoding ----------

_RANK_CHARS = "23456789TJQKA"
_SUIT_CHARS = "cdhs"

def card_to_treys(c: int) -> int:
    """Convert our 0-51 card int to treys int."""
    rank = c // 4        # 0=2 .. 12=A
    suit = c % 4         # 0=c, 1=d, 2=h, 3=s
    return TreysCard.new(_RANK_CHARS[rank] + _SUIT_CHARS[suit])


def card_from_str(s: str) -> int:
    """Convert 'As', '2c' style string to 0-51 int."""
    rank = _RANK_CHARS.index(s[0].upper())
    suit = _SUIT_CHARS.index(s[1].lower())
    return rank * 4 + suit


def card_to_str(c: int) -> str:
    """Convert 0-51 int to 'As' style string."""
    return _RANK_CHARS[c // 4] + _SUIT_CHARS[c % 4]


# ---------- Combo index (triangular mapping) ----------

def combo_index(c1: int, c2: int) -> int:
    """Map two cards (0-51) to a unique combo index 0..1325."""
    lo, hi = (c1, c2) if c1 < c2 else (c2, c1)
    return hi * (hi - 1) // 2 + lo


# ---------- Hand evaluation ----------

def evaluate(hole: tuple[int, int], board: list[int]) -> int:
    """
    Evaluate a hand. Returns a rank where LOWER is BETTER (treys convention).
    Range: 1 (Royal Flush) to 7462 (worst high card).
    """
    t_hole = [card_to_treys(hole[0]), card_to_treys(hole[1])]
    t_board = [card_to_treys(c) for c in board]
    return _evaluator.evaluate(t_board, t_hole)


def compare_hands(hole1: tuple[int, int], hole2: tuple[int, int], board: list[int]) -> int:
    """
    Compare two hands on a given board.
    Returns: >0 if hole1 wins, <0 if hole2 wins, 0 if tie.
    (Inverted from treys where lower = better.)
    """
    r1 = evaluate(hole1, board)
    r2 = evaluate(hole2, board)
    # Lower treys rank = better hand, so invert
    return r2 - r1
