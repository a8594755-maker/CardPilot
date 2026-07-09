"""
HUNL environment for AlphaHoldem self-play.

Wraps our existing HUNLGameState with AlphaHoldem-style tensor encoding:
  card_info:   (6, 4, 13) — binary card presence planes
  action_info: (25, 4, 5) — action history per street
  extra_info:  (2,)       — normalized stacks
  legal_mask:  (9,)       — which actions are legal

Action space (9 discrete):
  0: fold
  1: check/call
  2-7: raise to X% pot (33%, 50%, 67%, 75%, 100%, 150%)
  8: all-in
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
    EXPANDED_BET_FRACTIONS,
)
from deep_cfr.hand_eval import compare_hands

# ═══════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════

NUM_ACTIONS = 9  # fold, check/call, 6 raise sizes, allin
RAISE_FRACTIONS = [0.33, 0.50, 0.67, 0.75, 1.00, 1.50]

# Card encoding
NUM_SUITS = 4
NUM_RANKS = 13
NUM_CARD_CHANNELS = 6  # hole, flop, turn, river, all_public, all_visible

# Action history
MAX_ACTIONS_PER_STREET = 6  # max actions to track per street
NUM_STREETS = 4  # preflop, flop, turn, river
ACTION_HISTORY_CHANNELS = MAX_ACTIONS_PER_STREET * NUM_STREETS + 1  # = 25 (24 + 1 for current player)

# ═══════════════════════════════════════════════════════════
# State Encoding
# ═══════════════════════════════════════════════════════════

def card_to_suit_rank(card_idx: int) -> tuple[int, int]:
    """Convert card index (0-51) to (suit, rank). card = rank*4 + suit."""
    return card_idx % 4, card_idx // 4


def encode_cards(state: HUNLGameState, player: int) -> np.ndarray:
    """
    Encode cards as (6, 4, 13) binary tensor.

    Channels:
      0: hero's hole cards
      1: flop cards
      2: turn card
      3: river card
      4: all public cards (flop+turn+river)
      5: all visible cards (hole + public)
    """
    tensor = np.zeros((NUM_CARD_CHANNELS, NUM_SUITS, NUM_RANKS), dtype=np.float32)

    def set_card(channel: int, card_idx: int):
        suit, rank = card_to_suit_rank(card_idx)
        tensor[channel, suit, rank] = 1.0

    # Channel 0: hero's hole cards
    hole = state.hole_cards[player]
    for c in hole:
        set_card(0, c)

    # Channel 1: flop
    board = state.board
    for i, c in enumerate(board):
        if i < 3:
            set_card(1, c)  # flop
        elif i == 3:
            set_card(2, c)  # turn
        elif i == 4:
            set_card(3, c)  # river

    # Channel 4: all public
    for c in board:
        set_card(4, c)

    # Channel 5: all visible (hole + public)
    for c in hole:
        set_card(5, c)
    for c in board:
        set_card(5, c)

    return tensor


def encode_action_history(state: HUNLGameState, player: int) -> np.ndarray:
    """
    Encode action history as (25, 4, 5) tensor.

    For each street (4) × up to 6 actions:
      - One plane per action slot (24 planes total)
      - Each plane is (4, 5): [who_acted, action_type, amount_frac, is_hero, is_legal]
    Plus 1 channel for current player indicator.
    """
    tensor = np.zeros((ACTION_HISTORY_CHANNELS, NUM_STREETS, 5), dtype=np.float32)

    # Group history by street
    street_actions: list[list[tuple[int, Action]]] = [[] for _ in range(NUM_STREETS)]
    for who, action in state.actions_history:
        street_idx = _get_street_for_action(state, who, action, street_actions)
        if street_idx < NUM_STREETS:
            street_actions[street_idx].append((who, action))

    # Actually, simpler: iterate history and track street transitions
    # The history is chronological, streets advance after certain patterns
    action_idx = 0
    current_street = 0
    street_counts = [0] * NUM_STREETS

    for who, action in state.actions_history:
        if current_street >= NUM_STREETS:
            break
        slot = street_counts[current_street]
        if slot >= MAX_ACTIONS_PER_STREET:
            continue

        channel = current_street * MAX_ACTIONS_PER_STREET + slot
        # Encode into (4, 5) plane at this channel
        tensor[channel, 0, 0] = 1.0 if who == player else 0.0  # is_hero
        tensor[channel, 1, min(int(action.type), 4)] = 1.0  # action type (clamped to 0-4)
        # Amount as fraction of pot (capped at 2.0)
        if action.amount > 0 and state.pot > 0:
            tensor[channel, 2, 0] = min(action.amount / max(state.pot, 1), 2.0) / 2.0
        tensor[channel, 3, 0] = 1.0  # slot is filled

        street_counts[current_street] += 1

        # Check if street should advance (both players acted and action closed)
        if action.type in (ActionType.CALL, ActionType.CHECK):
            # Simplified: if both players have acted at least once, street might advance
            if street_counts[current_street] >= 2:
                current_street += 1

    # Channel 24: current player indicator
    tensor[24, 0, 0] = 1.0 if state.current_player == player else 0.0

    return tensor


def _get_street_for_action(state, who, action, street_actions):
    """Helper — not used in simplified encoding above."""
    return 0


def encode_extra(state: HUNLGameState, player: int) -> np.ndarray:
    """Encode extra info: normalized stacks."""
    start_stack = state.config.effective_stack
    hero_stack = state.stacks[player] / start_stack if start_stack > 0 else 0
    villain_stack = state.stacks[1 - player] / start_stack if start_stack > 0 else 0
    return np.array([hero_stack, villain_stack], dtype=np.float32)


def get_legal_mask(state: HUNLGameState) -> np.ndarray:
    """
    Get legal action mask (9,).
    Maps game actions to our 9-slot discrete space.
    """
    mask = np.zeros(NUM_ACTIONS, dtype=np.float32)
    legal = state.legal_actions()

    for action in legal:
        if action.type == ActionType.FOLD:
            mask[0] = 1.0
        elif action.type in (ActionType.CHECK, ActionType.CALL):
            mask[1] = 1.0
        elif action.type == ActionType.ALLIN:
            mask[8] = 1.0
        elif action.type in (ActionType.BET, ActionType.RAISE):
            # Map to closest raise fraction slot
            pot = state.pot
            if pot > 0:
                frac = action.amount / pot
                best_slot = _closest_raise_slot(frac)
                mask[best_slot] = 1.0
            else:
                mask[2] = 1.0  # default to smallest raise

    # Always allow at least fold if it's in legal actions
    if mask.sum() == 0:
        # Shouldn't happen, but fallback
        mask[1] = 1.0  # check/call as fallback

    return mask


def _closest_raise_slot(pot_frac: float) -> int:
    """Map a pot fraction to the closest raise slot (2-7)."""
    best_idx = 0
    best_dist = float('inf')
    for i, f in enumerate(RAISE_FRACTIONS):
        dist = abs(pot_frac - f)
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx + 2  # slots 2-7


def action_index_to_game_action(action_idx: int, state: HUNLGameState) -> Action:
    """Convert discrete action index (0-8) to game Action."""
    legal = state.legal_actions()

    if action_idx == 0:
        # Fold
        for a in legal:
            if a.type == ActionType.FOLD:
                return a
        # Fold not legal — fall back to check/call
        return _find_passive(legal)

    elif action_idx == 1:
        # Check/Call
        return _find_passive(legal)

    elif action_idx == 8:
        # All-in
        for a in legal:
            if a.type == ActionType.ALLIN:
                return a
        # No allin — find largest raise
        return _find_largest_raise(legal)

    else:
        # Raise slots 2-7 → fractions
        target_frac = RAISE_FRACTIONS[action_idx - 2]
        return _find_closest_raise(legal, target_frac, state.pot)


def _find_passive(legal: list[Action]) -> Action:
    for a in legal:
        if a.type in (ActionType.CHECK, ActionType.CALL):
            return a
    return legal[0]  # fallback


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


# ═══════════════════════════════════════════════════════════
# Environment Wrapper
# ═══════════════════════════════════════════════════════════

class HUNLEnvironment:
    """
    Self-play environment for AlphaHoldem training.

    Each step:
      1. Observe state from current player's perspective
      2. Select action (9-slot discrete)
      3. Apply action to game state
      4. Return next observation (opponent's perspective) or terminal reward
    """

    def __init__(
        self,
        starting_stack: float = 50.0,
        small_blind: float = 0.5,
        big_blind: float = 1.0,
        bet_sizes: Optional[BetSizeConfig] = None,
    ):
        self.starting_stack = starting_stack
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.bet_sizes = bet_sizes or BetSizeConfig(
            preflop=[],
            flop=RAISE_FRACTIONS,
            turn=RAISE_FRACTIONS,
            river=RAISE_FRACTIONS,
        )
        self.state: Optional[HUNLGameState] = None

    def reset(self) -> dict:
        """Start a new hand. Returns observation dict for the first player to act."""
        from deep_cfr.game_state import GameConfig
        if self.starting_stack <= 50:
            config = GameConfig.full_50bb()
        elif self.starting_stack <= 100:
            config = GameConfig.full_100bb()
        else:
            config = GameConfig.full_200bb()
        self.state = HUNLGameState(config=config)
        self.state = self.state.deal_new_hand()
        return self._get_obs()

    def chips_committed(self, player: int) -> float:
        """Total chips committed by a player across all streets (in BB units)."""
        if self.state is None:
            return 0.0
        # Starting stack minus remaining stack = total committed
        return float(self.state.config.effective_stack - self.state.stacks[player])

    def step(self, action_idx: int) -> tuple[dict, float, bool]:
        """
        Apply action and return (next_obs, reward, done).

        reward is from the perspective of the player who just acted.
        When done=True, reward is the final payoff.
        """
        if self.state is None or self.state.is_terminal():
            raise ValueError("Game is terminal, call reset()")

        player = self.state.current_player
        action = action_index_to_game_action(action_idx, self.state)
        self.state = self.state.apply(action)

        if self.state.is_terminal():
            # Game over — return reward for the player who acted
            reward = self.state.payoff(player)
            return self._terminal_obs(), reward / self.big_blind, True

        return self._get_obs(), 0.0, False

    def _get_obs(self) -> dict:
        """Get observation dict for current player."""
        player = self.state.current_player
        return {
            'card_info': encode_cards(self.state, player),
            'action_info': encode_action_history(self.state, player),
            'extra_info': encode_extra(self.state, player),
            'legal_mask': get_legal_mask(self.state),
            'player': player,
        }

    def _terminal_obs(self) -> dict:
        """Dummy observation for terminal state."""
        return {
            'card_info': np.zeros((NUM_CARD_CHANNELS, NUM_SUITS, NUM_RANKS), dtype=np.float32),
            'action_info': np.zeros((ACTION_HISTORY_CHANNELS, NUM_STREETS, 5), dtype=np.float32),
            'extra_info': np.zeros(2, dtype=np.float32),
            'legal_mask': np.zeros(NUM_ACTIONS, dtype=np.float32),
            'player': -1,
        }


# ═══════════════════════════════════════════════════════════
# Test
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    env = HUNLEnvironment(starting_stack=50.0)

    # Play a random hand
    obs = env.reset()
    print(f"Card info shape: {obs['card_info'].shape}")
    print(f"Action info shape: {obs['action_info'].shape}")
    print(f"Extra info shape: {obs['extra_info'].shape}")
    print(f"Legal mask: {obs['legal_mask']}")
    print(f"Player: {obs['player']}")

    done = False
    steps = 0
    while not done:
        legal = np.where(obs['legal_mask'] > 0)[0]
        action = random.choice(legal)
        obs, reward, done = env.step(action)
        steps += 1

    print(f"\nHand finished in {steps} steps, reward: {reward:.2f} BB")
