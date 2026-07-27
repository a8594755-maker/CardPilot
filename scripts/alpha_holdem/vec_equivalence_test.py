"""Deterministic equivalence test: vec_game_state vs deep_cfr.HUNLGameState.

Runs specific scripted action sequences through both simulators and verifies
state after each step. This is a stricter test than vec_validate.py's
random-policy statistical comparison.

Output: per-scenario PASS/FAIL with concrete divergence at the first mismatch.
"""
from __future__ import annotations

import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from vec_game_state import (
    VecHUNLState,
    A_FOLD, A_CHECK, A_CALL, A_BET, A_RAISE, A_ALLIN,
    S_PRE, S_FLOP, S_TURN, S_RIVER, S_SHOWDOWN,
)
from deep_cfr.game_state import (
    HUNLGameState, GameConfig, ActionType, Action, Street,
)
from alpha_holdem.environment import RAISE_FRACTIONS


# Slot → index into deep_cfr legal_actions raise list.
# Preflop: environment.py's _closest_raise_slot collapses all preflop raises
#   to slot 7. action_index_to_game_action(7) picks the raise with amount/pot
#   CLOSEST to RAISE_FRACTIONS[5]=1.50 — at any preflop pot the smallest raise
#   wins (ratios 1.33, 2.0, 2.67 → 1.33 closest to 1.50). So slot 7 → index 0.
# Postflop: 6 fractions 1-to-1 with slots 2..7.
SLOT_TO_PREFLOP_INDEX = {7: 0}
SLOT_TO_POSTFLOP_INDEX = {2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}


def slot_to_python_action(slot: int, py_state: HUNLGameState) -> Action:
    """Map a 9-slot action to a deep_cfr Action against the current state.

    Vec maps slots to fractions of pot_after_call; Python's legal_actions
    generates raise actions in the same order from the BetSizeConfig list.
    We index INTO that ordered list rather than fuzzy-matching by amount,
    because Python's `action.amount` is "total committed" not "fraction",
    so amount/pot doesn't equal the input fraction.
    """
    legal = py_state.legal_actions()
    if slot == 0:
        for a in legal:
            if a.type == ActionType.FOLD:
                return a
        raise RuntimeError(f"FOLD not legal in py_state")
    if slot == 1:
        for a in legal:
            if a.type in (ActionType.CALL, ActionType.CHECK):
                return a
        raise RuntimeError(f"CALL/CHECK not legal")
    if slot == 8:
        for a in legal:
            if a.type == ActionType.ALLIN:
                return a
        raise RuntimeError(f"ALLIN not legal")
    # Raise slot — pick by index into legal raise actions
    is_pre = (py_state.street == Street.PREFLOP)
    table = SLOT_TO_PREFLOP_INDEX if is_pre else SLOT_TO_POSTFLOP_INDEX
    if slot not in table:
        raise RuntimeError(f"Slot {slot} not a valid {'preflop' if is_pre else 'postflop'} raise")
    target_idx = table[slot]
    raise_actions = [a for a in legal if a.type in (ActionType.BET, ActionType.RAISE)]
    if not raise_actions:
        raise RuntimeError(f"No raise legal in py_state")
    if target_idx >= len(raise_actions):
        raise RuntimeError(f"target_idx {target_idx} out of range (have {len(raise_actions)} raise actions)")
    return raise_actions[target_idx]


def vec_state_dict(vs: VecHUNLState, i: int) -> dict:
    return {
        'pot': float(vs.pot[i]),
        'stacks': (float(vs.stacks[i, 0]), float(vs.stacks[i, 1])),
        'street': int(vs.street[i]),
        'current_player': int(vs.current_player[i]),
        'street_committed': (float(vs.street_committed[i, 0]), float(vs.street_committed[i, 1])),
        'is_done': bool(vs.is_done[i]),
        'folded_player': int(vs.folded_player[i]),
        'num_actions': int(vs.num_actions[i]),
        'raise_count': int(vs.raise_count[i]),
    }


_PY_STREET_TO_INT = {
    Street.PREFLOP: S_PRE,
    Street.FLOP: S_FLOP,
    Street.TURN: S_TURN,
    Street.RIVER: S_RIVER,
    Street.SHOWDOWN: S_SHOWDOWN,
}


def py_state_dict(ps: HUNLGameState) -> dict:
    return {
        'pot': float(ps.pot),
        'stacks': (float(ps.stacks[0]), float(ps.stacks[1])),
        'street': _PY_STREET_TO_INT[ps.street],
        'current_player': int(ps.current_player),
        'street_committed': (float(ps.street_committed[0]), float(ps.street_committed[1])),
        'is_done': bool(ps.is_terminal()),
        'folded_player': int(ps.folded_player) if ps.folded_player is not None else -1,
        'num_actions': int(ps.num_actions_this_street),
        'raise_count': int(ps.raise_count),
    }


def diff_states(va: dict, pa: dict, tol: float = 1e-4) -> list[str]:
    diffs = []
    for k in va:
        v = va[k]
        p = pa[k]
        if isinstance(v, tuple):
            for j, (vv, pv) in enumerate(zip(v, p)):
                if abs(vv - pv) > tol:
                    diffs.append(f"  {k}[{j}]: vec={vv:.4f} py={pv:.4f}")
        elif isinstance(v, float):
            if abs(v - p) > tol:
                diffs.append(f"  {k}: vec={v:.4f} py={p:.4f}")
        else:
            if v != p:
                diffs.append(f"  {k}: vec={v} py={p}")
    return diffs


def run_scenario(name: str, actions: list[int], seed: int = 42) -> tuple[bool, list[str]]:
    """Run a scripted action sequence through both sims.

    Both sims are seeded identically. After each step we compare state. The
    first divergence is reported; later divergences may be downstream.
    """
    # Vec sim with N=1 to make tracking easy
    vs = VecHUNLState(N=1, effective_stack=200.0, seed=seed)
    vs.reset_all()
    # Force hero_player to 0 so reward signs are consistent (not used for state-equiv check, just hygiene)
    vs.hero_player[:] = 0

    # Python sim with the same config as 200bb env
    import random as _pyrand
    _pyrand.seed(seed)
    config = GameConfig.full_200bb()
    ps = HUNLGameState(config=config)
    ps = ps.deal_new_hand()

    # Override hole cards + board so the two sims share the same chance outcomes.
    # We DON'T compare board/cards because the deck shufflers differ; we compare
    # only betting state.
    log = []
    log.append(f"== {name} ==")
    log.append(f"  start: vec={vec_state_dict(vs, 0)}")
    log.append(f"         py ={py_state_dict(ps)}")

    for step, slot in enumerate(actions):
        # Check both still alive
        if vs.is_done[0] or ps.is_terminal():
            log.append(f"  step {step}: one sim already terminal — vec_done={bool(vs.is_done[0])} py_done={ps.is_terminal()}")
            if vs.is_done[0] != ps.is_terminal():
                return False, log
            break

        # Apply action to both
        try:
            py_action = slot_to_python_action(slot, ps)
        except RuntimeError as e:
            log.append(f"  step {step} slot={slot}: py rejected ({e})")
            return False, log

        # Apply to py
        ps = ps.apply(py_action)

        # For vec we need to map slot too — but vec accepts slot directly.
        # Need to check the slot is legal in vec.
        vec_mask = vs.legal_mask()[0]
        if vec_mask[slot] < 0.5:
            log.append(f"  step {step} slot={slot}: vec mask says illegal "
                       f"(legal={np.where(vec_mask > 0)[0].tolist()})")
            return False, log
        vs.step(np.array([slot], dtype=np.int64))

        # Compare states
        va = vec_state_dict(vs, 0)
        pa = py_state_dict(ps)
        diffs = diff_states(va, pa)
        log.append(f"  step {step} slot={slot} py_action_type={py_action.type.name}:")
        log.append(f"    vec={va}")
        log.append(f"    py ={pa}")
        if diffs:
            log.append("  DIVERGENCE:")
            log.extend(diffs)
            return False, log

    return True, log


SCENARIOS = [
    ("Preflop: SB fold", [0]),
    ("Preflop: SB call, BB check", [1, 1]),
    ("Preflop: SB raise (slot 7), BB fold", [7, 0]),
    ("Preflop: SB raise, BB call, both check flop x2 streets", [7, 1, 1, 1, 1, 1, 1, 1]),
    ("Preflop: SB all-in, BB fold", [8, 0]),
    ("Preflop: SB all-in, BB call (all-in showdown)", [8, 1]),
    ("Preflop: SB raise, BB re-raise (only slot 7 legal), SB all-in, BB fold", [7, 7, 8, 0]),
    ("Postflop: SB call, BB check, both check flop", [1, 1, 1, 1]),
    ("Postflop SBPF-call: SB call, BB check, flop bet-fold (slot 5)", [1, 1, 5, 0]),
]


def main():
    print("=" * 70)
    print("Deterministic equivalence test: vec_game_state vs deep_cfr ref")
    print("=" * 70)
    n_pass = 0
    n_fail = 0
    fail_logs = []
    for name, actions in SCENARIOS:
        passed, log = run_scenario(name, actions, seed=42)
        marker = "PASS" if passed else "FAIL"
        print(f"[{marker}] {name}")
        if not passed:
            n_fail += 1
            fail_logs.append('\n'.join(log))
        else:
            n_pass += 1

    print()
    print(f"Results: {n_pass} PASS, {n_fail} FAIL")
    if fail_logs:
        print("\n--- FAILURE DETAILS ---")
        for log_text in fail_logs:
            print(log_text)
            print()


if __name__ == "__main__":
    main()
