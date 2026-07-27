"""Scripted opponent policies for the internal opponent suite.

Each policy is a callable: policy_fn(hole_cards, board, state, client_pos, legal_mask) -> int (slot 0..8).

  always_fold       — slot 0 if legal else slot 1 (check fallback)
  always_call       — slot 1 always (becomes "limp" preflop, "call" facing bet)
  uniform_random    — random LEGAL slot per call
  scripted_aggro    — always raise when can_raise, c-bet flop, barrel turn
  scripted_station  — call any bet ≤ 0.6 pot, fold to larger
  scripted_jammer   — 50% jam top-30% hands preflop, fold trash; postflop: tight call

Slot map: 0=fold 1=check/call 2=raise 0.33x 3=raise 0.5x 4=raise 0.67x
          5=raise 0.75/1.0x 6=raise 1.0x 7=raise 1.5x 8=allin
"""
from __future__ import annotations
import numpy as np
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR.parent))  # scripts/alpha_holdem/

from heuristic_policy_v3 import (
    _hand_notation, _is_premium, _is_strong, _is_playable,
    _eval_postflop, HS_STRONG, HS_TOP_PAIR, HS_WEAK_PAIR, HS_STRONG_DRAW, HS_AIR,
)


def _pick(legal_mask, preferred):
    """First legal slot in preferred order; fallback to first legal overall."""
    for s in preferred:
        if 0 <= s < 9 and legal_mask[s]:
            return s
    for s in range(9):
        if legal_mask[s]:
            return s
    return 0


# ─── Fixed-strategy baselines ────────────────────────────────────────────
def always_fold(hole, board, state, client_pos, legal_mask) -> int:
    return _pick(legal_mask, [0, 1])


def always_call(hole, board, state, client_pos, legal_mask) -> int:
    return _pick(legal_mask, [1])


_rng = np.random.default_rng(seed=0)


def uniform_random(hole, board, state, client_pos, legal_mask) -> int:
    legal_idx = [s for s in range(9) if legal_mask[s]]
    if not legal_idx:
        return 0
    return int(_rng.choice(legal_idx))


# ─── Scripted styles ─────────────────────────────────────────────────────
def scripted_aggro(hole, board, state, client_pos, legal_mask) -> int:
    """Always raise when can_raise; c-bet flop; barrel turn; check-or-call-with-something river.

    Approximation: prefer raise slots; size escalates by street. Never fold.
    """
    st = state['st']
    to_call = state.get('to_call', 0)
    facing_bet = to_call > 0

    if st == 0:  # preflop
        if facing_bet:
            # Facing a raise: aggressive 3-bet
            return _pick(legal_mask, [7, 5, 8, 1, 0])
        return _pick(legal_mask, [5, 7, 2, 1])

    if st == 1:  # flop
        if facing_bet:
            return _pick(legal_mask, [1, 5, 0])  # call most bets, occasionally raise
        return _pick(legal_mask, [3, 4, 2, 1])  # c-bet ~half pot

    if st == 2:  # turn
        if facing_bet:
            return _pick(legal_mask, [1, 0])  # call
        return _pick(legal_mask, [3, 4, 1])  # barrel half-pot

    # river
    if facing_bet:
        # Aggressive bot calls down with anything
        return _pick(legal_mask, [1, 0])
    return _pick(legal_mask, [1, 2])  # check-back or thin value


def scripted_station(hole, board, state, client_pos, legal_mask) -> int:
    """Calling station: call any bet ≤ 0.6 pot, fold to larger. Never raises.

    Always check when option, always call small bets.
    """
    to_call = state.get('to_call', 0)
    pot_before = max(state.get('pot_before', 100), 1)
    facing_bet = to_call > 0

    if not facing_bet:
        return _pick(legal_mask, [1, 0])

    # Facing bet — call if ≤ 0.6 pot, else fold
    if to_call <= 0.6 * pot_before:
        return _pick(legal_mask, [1, 0])
    return _pick(legal_mask, [0, 1])


def scripted_polarized_jam(hole, board, state, client_pos, legal_mask) -> int:
    """Polarized: with strong hands jam preflop, otherwise fold. Postflop: tight call."""
    st = state['st']
    if st == 0:
        n = _hand_notation(hole)
        if _is_strong(n):
            # Jam top 12% preflop
            return _pick(legal_mask, [8, 7, 5, 1, 0])
        return _pick(legal_mask, [0, 1])

    # Postflop: tight call with pair+, fold air
    hs = _eval_postflop(hole, board)
    facing_bet = state.get('to_call', 0) > 0
    if hs in (HS_STRONG, HS_TOP_PAIR):
        if facing_bet:
            return _pick(legal_mask, [1, 7, 8, 0])
        return _pick(legal_mask, [3, 4, 1])
    return _pick(legal_mask, [0, 1] if facing_bet else [1, 0])


# ─── Registry ────────────────────────────────────────────────────────────
STRATEGY_REGISTRY = {
    'fold': always_fold,
    'call': always_call,
    'random': uniform_random,
    'scripted_aggro': scripted_aggro,
    'scripted_station': scripted_station,
    'scripted_jammer': scripted_polarized_jam,
}


def get_policy(name: str):
    """Resolve a strategy name to a callable.

    Supported:
      - Fixed baselines: fold / call / random
      - Scripted: scripted_aggro / scripted_station / scripted_jammer
      - Heuristic: heuristic / heuristic_v2 / heuristic_v3 / heuristic_v3_1
      - Frozen neural anchor: anchor:<path-to-.pt>   (loads via frozen_anchor.py)
      - Slumbot proxy:        proxy:<path-to-.pt>    (loads via proxy_callable.py;
                                                       public-state-only, no hole)
      - Named convenience aliases for known frozen anchors:
        pathb10m / pathb50m / v4_final
    """
    if name in STRATEGY_REGISTRY:
        return STRATEGY_REGISTRY[name]

    if name.startswith('anchor:'):
        from frozen_anchor import load_frozen_anchor_callable
        return load_frozen_anchor_callable(name.split(':', 1)[1])
    if name.startswith('proxy:'):
        from proxy_callable import load_proxy_callable
        return load_proxy_callable(name.split(':', 1)[1])

    # Named heuristic
    if name == 'heuristic_v3':
        from heuristic_policy_v3 import choose_action
        return choose_action
    if name == 'heuristic_v3_1':
        from heuristic_policy_v3_1 import choose_action
        return choose_action
    if name == 'heuristic_v2':
        from heuristic_policy_v2 import choose_action
        return choose_action
    if name == 'heuristic':
        from heuristic_policy import choose_action
        return choose_action

    # Named convenience aliases for frozen anchors
    NAMED_ANCHORS = {
        'pathb10m':   'scripts/alpha_holdem/models/path_b_smoke_10M.pt',
        'pathb50m':   'scripts/alpha_holdem/models/path_b_smoke_50M.pt',
        'v4_final':   'models/alpha_holdem_v4_final.pt',
        'path_b_smoke_5M': 'scripts/alpha_holdem/models/path_b_smoke_5M.pt',
    }
    if name in NAMED_ANCHORS:
        from frozen_anchor import load_frozen_anchor_callable
        from pathlib import Path as _P
        repo_root = _P(__file__).resolve().parents[3]
        return load_frozen_anchor_callable(str(repo_root / NAMED_ANCHORS[name]))

    raise ValueError(f'Unknown strategy: {name}')
