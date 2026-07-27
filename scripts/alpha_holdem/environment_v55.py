"""
HUNL environment V5.5 — fixes structural bugs found in V4/V5.0 environment.py.

Bugs fixed (vs environment.py):
1. raise_cap_per_street: was 1 in GameConfig.full_200bb(), bumped to UNLIMITED here.
   The old cap allowed only one bet per postflop street, killing check-raise / 3-bet /
   4-bet dynamics. With unlimited cap, all-in naturally bounds the bet war.

2. encode_action_history: previously called a stub _get_street_for_action() that
   always returned 0, then re-tried with a heuristic that miscounted street
   transitions. Now uses HUNLGameState.get_actions_by_street() — correct replay of
   engine street-advance rules.

3. Action table cache: V5.0 promised this in v5_optimization_plan.md but never
   implemented it. Implemented here. _get_obs() builds (mask, slot_to_action) once,
   step() reuses the table — drops one state.legal_actions() call per decision.

Honest residual issues (NOT fixed in this file — flagged in v5_5_synthesis.md):
- MAX_ACTIONS_PER_STREET=6: unlimited raise_cap can in extreme cases produce >6
  actions on a single street (rare in 200bb). Overflow actions silently dropped.
  Lifting this changes net architecture (action_info shape) → V6.
- Preflop position semantics: engine has SB/BB position handling that may diverge
  from real-world HU NLHE rules (BB option after SB completion). Not addressed.

V4 environment.py is preserved untouched. To roll back, just import from
environment instead of environment_v55.
"""

from __future__ import annotations

import random
import numpy as np
from typing import Optional
from copy import deepcopy

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from deep_cfr.game_state import (
    HUNLGameState, Street, ActionType, Action, BetSizeConfig,
    EXPANDED_BET_FRACTIONS, GameConfig,
)
from deep_cfr.hand_eval import compare_hands
from alpha_holdem.environment import encode_action_history as encode_action_history_v4

# ===========================================================
# Constants (unchanged from environment.py — V4 net relies on these shapes)
# ===========================================================

NUM_ACTIONS = 9
RAISE_FRACTIONS = [0.33, 0.50, 0.67, 0.75, 1.00, 1.50]

NUM_SUITS = 4
NUM_RANKS = 13
NUM_CARD_CHANNELS = 6

MAX_ACTIONS_PER_STREET = 6
NUM_STREETS = 4
ACTION_HISTORY_CHANNELS = MAX_ACTIONS_PER_STREET * NUM_STREETS + 1  # 25

# V5.5 fix: bump raise cap to effectively unlimited (all-in naturally caps the bet war)
RAISE_CAP_UNLIMITED = 999


# ===========================================================
# Card encoding (unchanged from environment.py)
# ===========================================================

def card_to_suit_rank(card_idx: int) -> tuple[int, int]:
    return card_idx % 4, card_idx // 4


def encode_cards(state: HUNLGameState, player: int) -> np.ndarray:
    """Encode cards as (6, 4, 13) binary tensor. Channels: hole / flop / turn / river / public / visible."""
    tensor = np.zeros((NUM_CARD_CHANNELS, NUM_SUITS, NUM_RANKS), dtype=np.float32)

    def set_card(channel: int, card_idx: int):
        suit, rank = card_to_suit_rank(card_idx)
        tensor[channel, suit, rank] = 1.0

    hole = state.hole_cards[player]
    for c in hole:
        set_card(0, c)

    board = state.board
    if len(board) >= 3:
        for c in board[:3]:
            set_card(1, c)
    if len(board) >= 4:
        set_card(2, board[3])
    if len(board) >= 5:
        set_card(3, board[4])

    for c in board:
        set_card(4, c)

    for c in hole:
        set_card(5, c)
    for c in board:
        set_card(5, c)

    return tensor


# ===========================================================
# V5.5 FIX: encode_action_history using engine-correct street groups
# ===========================================================

def encode_action_history(state: HUNLGameState, player: int) -> np.ndarray:
    """
    Encode action history as (25, 4, 5) tensor.

    Channel layout:
      Channels 0..23: 6 action slots × 4 streets, each plane (4, 5).
        Plane axis 0: position-info (5 features below at index [0..4])
        Plane row encoding (axis 1, len 5):
          row 0 col 0: is_hero (1.0 if action made by `player`)
          row 1 cols [0..4]: one-hot action type (clamped to 0-4)
          row 2 col 0: amount as fraction of pot (capped, normalized to [0,1])
          row 3 col 0: slot-filled flag
          row 4: reserved
      Channel 24: current player indicator at [0,0]

    V5.5 change: groups by *engine-true* street via state.get_actions_by_street(),
    instead of the broken stub + heuristic in environment.py.
    """
    tensor = np.zeros((ACTION_HISTORY_CHANNELS, NUM_STREETS, 5), dtype=np.float32)

    by_street = state.get_actions_by_street()

    for street_idx in range(NUM_STREETS):
        actions_on_street = by_street[street_idx]
        for slot, (who, action) in enumerate(actions_on_street):
            if slot >= MAX_ACTIONS_PER_STREET:
                # Rare overflow: extreme bet war exceeds 6 actions on one street.
                # Documented limitation — see file header.
                break

            channel = street_idx * MAX_ACTIONS_PER_STREET + slot

            # is_hero
            tensor[channel, 0, 0] = 1.0 if who == player else 0.0
            # action type one-hot (clamped to 0-4 since plane width is 5)
            tensor[channel, 1, min(int(action.type), 4)] = 1.0
            # amount as pot-fraction (cap at 2.0, normalize to [0, 1])
            if action.amount > 0 and state.pot > 0:
                tensor[channel, 2, 0] = min(action.amount / max(state.pot, 1.0), 2.0) / 2.0
            # slot filled flag
            tensor[channel, 3, 0] = 1.0

    # Channel 24: current player indicator
    tensor[ACTION_HISTORY_CHANNELS - 1, 0, 0] = 1.0 if state.current_player == player else 0.0

    return tensor


def encode_extra(state: HUNLGameState, player: int) -> np.ndarray:
    """Encode normalized stacks."""
    start_stack = state.config.effective_stack
    hero_stack = state.stacks[player] / start_stack if start_stack > 0 else 0
    villain_stack = state.stacks[1 - player] / start_stack if start_stack > 0 else 0
    return np.array([hero_stack, villain_stack], dtype=np.float32)


# ===========================================================
# Action mapping (unchanged from environment.py except action cache integration)
# ===========================================================

def _closest_raise_slot(pot_frac: float) -> int:
    """Map a pot fraction to the closest raise slot (2-7)."""
    best_idx = 0
    best_dist = float('inf')
    for i, f in enumerate(RAISE_FRACTIONS):
        dist = abs(pot_frac - f)
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx + 2


def _find_passive(legal: list[Action]) -> Action:
    for a in legal:
        if a.type in (ActionType.CHECK, ActionType.CALL):
            return a
    return legal[0]


def _find_largest_raise(legal: list[Action]) -> Action:
    best = None
    for a in legal:
        if a.type in (ActionType.BET, ActionType.RAISE, ActionType.ALLIN):
            if best is None or a.amount > best.amount:
                best = a
    return best or legal[0]


def _find_closest_raise(legal: list[Action], target_frac: float, pot: float) -> Action:
    target_amount = target_frac * pot
    best = None
    best_dist = float('inf')
    for a in legal:
        if a.type in (ActionType.BET, ActionType.RAISE, ActionType.ALLIN):
            dist = abs(a.amount - target_amount)
            if dist < best_dist:
                best_dist = dist
                best = a
    if best is None:
        return _find_passive(legal)
    return best


# ===========================================================
# V5.5 FIX: action table cache — build mask + slot table together, eliminate
# the second state.legal_actions() call in step().
# ===========================================================

def _raise_over_pot_fraction(state: HUNLGameState, action: Action) -> float:
    """Recover the engine bet-size fraction from a BET/RAISE action."""
    player = int(state.current_player)
    committed = float(state.street_committed[player])
    opponent_committed = float(state.street_committed[1 - player])
    to_call = max(opponent_committed - committed, 0.0)
    additional = max(float(action.amount) - committed, 0.0)
    if to_call <= 0.0:
        return additional / max(float(state.pot), 1e-9)
    raise_over = max(additional - to_call, 0.0)
    return raise_over / max(float(state.pot) + to_call, 1e-9)


def build_action_table(
    state: HUNLGameState,
    raise_action_mapping: str = "legacy_total_over_pot",
) -> tuple[np.ndarray, list]:
    """
    Build legal-action mask AND slot-to-Action table in a single pass.

    Returns:
      mask: (NUM_ACTIONS,) float32, 1.0 where slot is legal
      slot_to_action: list[Optional[Action]] of length NUM_ACTIONS
    """
    mask = np.zeros(NUM_ACTIONS, dtype=np.float32)
    slot_to_action: list = [None] * NUM_ACTIONS

    legal = state.legal_actions()
    if not legal:
        return mask, slot_to_action

    if raise_action_mapping not in {
        "legacy_total_over_pot",
        "preflop_pot_fraction_v2",
        "pot_fraction_v2",
    }:
        raise ValueError(f"unknown raise action mapping: {raise_action_mapping}")

    slot_distance = [float("inf")] * NUM_ACTIONS
    for action in legal:
        if action.type == ActionType.FOLD:
            mask[0] = 1.0
            if slot_to_action[0] is None:
                slot_to_action[0] = action
        elif action.type in (ActionType.CHECK, ActionType.CALL):
            mask[1] = 1.0
            # Prefer CALL over CHECK if both exist (rare)
            if slot_to_action[1] is None or slot_to_action[1].type == ActionType.CHECK:
                slot_to_action[1] = action
        elif action.type == ActionType.ALLIN:
            mask[8] = 1.0
            slot_to_action[8] = action
        elif action.type in (ActionType.BET, ActionType.RAISE):
            pot = state.pot
            if pot > 0:
                use_corrected_fraction = (
                    raise_action_mapping == "pot_fraction_v2"
                    or (
                        raise_action_mapping == "preflop_pot_fraction_v2"
                        and state.street == Street.PREFLOP
                    )
                )
                if use_corrected_fraction:
                    frac = _raise_over_pot_fraction(state, action)
                else:
                    frac = action.amount / pot
                slot = _closest_raise_slot(frac)
            else:
                slot = 2  # default smallest
            mask[slot] = 1.0
            # Prefer the closest match if multiple raises map to same slot
            distance = abs(float(frac) - RAISE_FRACTIONS[slot - 2])
            if slot_to_action[slot] is None or distance < slot_distance[slot]:
                slot_to_action[slot] = action
                slot_distance[slot] = distance

    # Fallback: if nothing legal somehow, allow check/call as no-op
    if mask.sum() == 0:
        mask[1] = 1.0

    return mask, slot_to_action


def get_legal_mask(state: HUNLGameState) -> np.ndarray:
    """Backwards-compatible wrapper — drop slot table."""
    mask, _ = build_action_table(state)
    return mask


# ===========================================================
# Environment Wrapper V5.5
# ===========================================================

class HUNLEnvironmentV55:
    """
    Self-play environment for AlphaHoldem V5.5 training.

    Differences from HUNLEnvironment (V4/V5.0):
    1. raise_cap_per_street forced to UNLIMITED (999) — full bet war allowed,
       all-in caps naturally.
    2. action_info encoding via state.get_actions_by_street() — engine-correct
       street grouping (was broken stub + heuristic).
    3. Real action table cache via build_action_table() — step() uses
       self.last_action_table instead of re-running legal_actions().
    """

    def __init__(
        self,
        starting_stack: float = 200.0,
        small_blind: float = 0.5,
        big_blind: float = 1.0,
        bet_sizes: Optional[BetSizeConfig] = None,
        raise_cap_per_street: int = RAISE_CAP_UNLIMITED,
        action_history_style: str = "v55",
        raise_action_mapping: str = "legacy_total_over_pot",
    ):
        self.starting_stack = starting_stack
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.raise_cap_per_street = raise_cap_per_street
        if raise_action_mapping not in {
            "legacy_total_over_pot",
            "preflop_pot_fraction_v2",
            "pot_fraction_v2",
        }:
            raise ValueError(
                f"unknown raise action mapping: {raise_action_mapping}"
            )
        self.raise_action_mapping = raise_action_mapping
        self._override_bet_sizes = (
            bet_sizes is not None
            or raise_action_mapping in {
                "preflop_pot_fraction_v2",
                "pot_fraction_v2",
            }
        )
        self.bet_sizes = bet_sizes or BetSizeConfig(
            # 0.33 would produce an illegal sub-minimum opening raise from
            # the posted blinds. The remaining five fractions produce
            # 2.0/2.34/2.5/3.0/4.0 BB opens and map to distinct slots 3..7.
            preflop=(
                [0.50, 0.67, 0.75, 1.00, 1.50]
                if raise_action_mapping in {
                    "preflop_pot_fraction_v2",
                    "pot_fraction_v2",
                }
                else []
            ),
            flop=RAISE_FRACTIONS,
            turn=RAISE_FRACTIONS,
            river=RAISE_FRACTIONS,
        )
        if action_history_style not in ("v55", "v4"):
            raise ValueError(f"unknown action_history_style: {action_history_style}")
        self.action_history_style = action_history_style
        self.state: Optional[HUNLGameState] = None
        # V5.5: action table cache (set in _get_obs)
        self.last_action_table: list = [None] * NUM_ACTIONS
        # V5.5: legal_actions() call counter for diagnostic / verification
        self._legal_calls_this_hand = 0

    def _make_config(self) -> GameConfig:
        """Construct GameConfig with V5.5 raise_cap override."""
        if self.starting_stack <= 50:
            cfg = GameConfig.full_50bb()
        elif self.starting_stack <= 100:
            cfg = GameConfig.full_100bb()
        else:
            cfg = GameConfig.full_200bb()
        cfg.raise_cap_per_street = self.raise_cap_per_street
        if self._override_bet_sizes:
            cfg.bet_sizes = self.bet_sizes
        return cfg

    def reset(self) -> dict:
        """Start a new hand. Returns observation dict for the first player to act."""
        config = self._make_config()
        self.state = HUNLGameState(config=config)
        self.state = self.state.deal_new_hand()
        self._legal_calls_this_hand = 0
        return self._get_obs()

    def chips_committed(self, player: int) -> float:
        """Total chips committed by a player across all streets (BB units)."""
        if self.state is None:
            return 0.0
        return float(self.state.config.effective_stack - self.state.stacks[player])

    def step(self, action_idx: int) -> tuple[dict, float, bool]:
        """Apply action. Returns (next_obs, reward, done)."""
        if self.state is None or self.state.is_terminal():
            raise ValueError("Game is terminal, call reset()")

        player = self.state.current_player

        # V5.5: use cached action table from previous _get_obs(); fall back to
        # rebuild only if cache is invalid (e.g., illegal slot picked).
        action = self.last_action_table[action_idx]
        if action is None:
            # Fallback: cache miss (shouldn't happen if caller respects mask)
            mask, table = build_action_table(
                self.state,
                self.raise_action_mapping,
            )
            self._legal_calls_this_hand += 1
            action = table[action_idx]
            if action is None:
                # Truly illegal slot — pick passive fallback (matches V4 behavior)
                action = _find_passive(self.state.legal_actions())
                self._legal_calls_this_hand += 1

        self.state = self.state.apply(action)

        if self.state.is_terminal():
            reward = self.state.payoff(player)
            return self._terminal_obs(), reward / self.big_blind, True

        return self._get_obs(), 0.0, False

    def _get_obs(self) -> dict:
        """Build observation. V5.5: also stashes last_action_table for next step()."""
        player = self.state.current_player

        # V5.5: single legal_actions() call serves both mask and slot table
        mask, slot_to_action = build_action_table(
            self.state,
            self.raise_action_mapping,
        )
        self._legal_calls_this_hand += 1
        self.last_action_table = slot_to_action
        if self.action_history_style == "v4":
            action_info = encode_action_history_v4(self.state, player)
        else:
            action_info = encode_action_history(self.state, player)

        return {
            'card_info': encode_cards(self.state, player),
            'action_info': action_info,
            'extra_info': encode_extra(self.state, player),
            'legal_mask': mask,
            'player': player,
        }

    def _terminal_obs(self) -> dict:
        return {
            'card_info': np.zeros((NUM_CARD_CHANNELS, NUM_SUITS, NUM_RANKS), dtype=np.float32),
            'action_info': np.zeros((ACTION_HISTORY_CHANNELS, NUM_STREETS, 5), dtype=np.float32),
            'extra_info': np.zeros(2, dtype=np.float32),
            'legal_mask': np.zeros(NUM_ACTIONS, dtype=np.float32),
            'player': -1,
        }


# Back-compat alias so train_v55.py can `from alpha_holdem.environment_v55 import HUNLEnvironment`
HUNLEnvironment = HUNLEnvironmentV55


# ===========================================================
# Self-test
# ===========================================================

if __name__ == '__main__':
    env = HUNLEnvironmentV55(starting_stack=200.0)

    # Multi-hand smoke: verify legal_calls/decision <= 1 (V5.5 cache works)
    total_decisions = 0
    total_legal_calls = 0
    for hand_i in range(20):
        obs = env.reset()
        if hand_i == 0:
            print(f"Hand 0 obs shapes:")
            print(f"  card_info:   {obs['card_info'].shape}")
            print(f"  action_info: {obs['action_info'].shape}")
            print(f"  extra_info:  {obs['extra_info'].shape}")
            print(f"  legal_mask:  {obs['legal_mask'].shape}, legal slots: {np.where(obs['legal_mask']>0)[0].tolist()}")

        decisions = 0
        done = False
        while not done:
            legal = np.where(obs['legal_mask'] > 0)[0]
            action = random.choice(legal)
            obs, reward, done = env.step(int(action))
            decisions += 1

        total_decisions += decisions
        total_legal_calls += env._legal_calls_this_hand

    avg = total_legal_calls / max(total_decisions, 1)
    print(f"\nOver 20 hands: {total_decisions} decisions, "
          f"{total_legal_calls} legal_actions() calls, "
          f"avg = {avg:.3f} per decision (target: ~1.0, V4 was ~2.0)")
    assert avg < 1.5, f"action cache not effective: {avg} calls/decision"
    print("V5.5 action cache: PASS")
