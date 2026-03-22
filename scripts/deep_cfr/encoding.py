"""
State → tensor encoding for SD-CFR advantage networks.

Two encoders:
1. HUNLEncoder: Full NLHE encoding (~150D) with combo embeddings
2. LeducEncoder: Simple Leduc Hold'em encoding (~30D) for smoke testing
"""

from __future__ import annotations

import numpy as np

from .game_state import (
    HUNLGameState, LeducGameState, Street, ActionType, Action,
)
from .hand_eval import combo_index

# ---------- HUNL Encoder ----------

# Max actions we track in history encoding
MAX_HISTORY_ACTIONS = 12
# Action types encoded as ints for history
ACTION_ENCODING = {
    ActionType.FOLD: 0,
    ActionType.CHECK: 1,
    ActionType.CALL: 2,
    ActionType.BET: 3,
    ActionType.RAISE: 4,
    ActionType.ALLIN: 5,
}
NUM_ACTION_TYPES = 6

# Feature dimensions
COMBO_INDEX_DIM = 1      # combo index (int for embedding lookup)
BOARD_CARD_DIM = 5       # up to 5 board cards (int indices, -1 for absent)
STREET_DIM = 4           # one-hot: preflop/flop/turn/river
POSITION_DIM = 2         # one-hot: OOP/IP
POT_GEOMETRY_DIM = 4     # pot, toCall, SPR, potOdds (normalized)
STACK_DIM = 2            # hero stack, villain stack (normalized)
HISTORY_DIM = MAX_HISTORY_ACTIONS * 3  # (who, action_type, amount) per action
RAISE_INFO_DIM = 2       # raise_count, raise_cap_remaining

# Total float features (excluding combo/board indices which use embeddings)
FLOAT_FEATURE_DIM = STREET_DIM + POSITION_DIM + POT_GEOMETRY_DIM + STACK_DIM + HISTORY_DIM + RAISE_INFO_DIM
# = 4 + 2 + 4 + 2 + 36 + 2 = 50

# For the network input, we'll concatenate:
# combo_embed(64) + board_embed(16) + float_features(50) = 130D
# But the raw encoding just stores the indices + float features


class HUNLEncoder:
    """Encode HUNL game state into a flat feature vector for the advantage network."""

    # Raw encoding: [combo_idx(1), board_cards(5), float_features(50)] = 56 floats
    RAW_DIM = 1 + 5 + FLOAT_FEATURE_DIM  # 56

    @staticmethod
    def encode(state: HUNLGameState) -> np.ndarray:
        """
        Encode the current state from the perspective of the current player.
        Returns a float32 array of shape (RAW_DIM,).
        """
        features = np.zeros(HUNLEncoder.RAW_DIM, dtype=np.float32)
        p = state.current_player
        opp = 1 - p

        # --- Combo index (for embedding lookup) ---
        hole = state.hole_cards[p]
        if hole is not None:
            features[0] = float(combo_index(hole[0], hole[1]))
        else:
            features[0] = -1.0

        # --- Board cards (for embedding lookup, -1 = absent) ---
        for i in range(5):
            if i < len(state.board):
                features[1 + i] = float(state.board[i])
            else:
                features[1 + i] = -1.0

        offset = 6  # after combo(1) + board(5)

        # --- Street one-hot ---
        street_idx = min(int(state.street), 3)
        features[offset + street_idx] = 1.0
        offset += STREET_DIM

        # --- Position one-hot ---
        features[offset + p] = 1.0
        offset += POSITION_DIM

        # --- Pot geometry (normalized by starting stack * 2) ---
        total_chips = state.config.effective_stack * 2 + state.config.starting_pot
        to_call = max(0.0, state.street_committed[opp] - state.street_committed[p])
        spr = state.stacks[p] / max(state.pot, 0.01)
        pot_odds = to_call / max(state.pot + to_call, 0.01)

        features[offset + 0] = state.pot / total_chips
        features[offset + 1] = to_call / total_chips
        features[offset + 2] = min(spr, 10.0) / 10.0  # cap SPR at 10
        features[offset + 3] = pot_odds
        offset += POT_GEOMETRY_DIM

        # --- Stack info (normalized) ---
        features[offset + 0] = state.stacks[p] / state.config.effective_stack
        features[offset + 1] = state.stacks[opp] / state.config.effective_stack
        offset += STACK_DIM

        # --- Action history (last MAX_HISTORY_ACTIONS actions) ---
        history = state.actions_history[-MAX_HISTORY_ACTIONS:]
        for i, (actor, action) in enumerate(history):
            base = offset + i * 3
            # Normalize actor relative to hero: 0 = hero, 1 = villain
            features[base + 0] = 0.0 if actor == p else 1.0
            features[base + 1] = ACTION_ENCODING.get(action.type, 0) / (NUM_ACTION_TYPES - 1)
            features[base + 2] = action.amount / total_chips
        offset += HISTORY_DIM

        # --- Raise info ---
        features[offset + 0] = state.raise_count / max(state.config.raise_cap_per_street, 1)
        features[offset + 1] = max(0, state.config.raise_cap_per_street - state.raise_count)
        offset += RAISE_INFO_DIM

        return features

    @staticmethod
    def encode_legal_mask(state: HUNLGameState, max_actions: int = 6) -> np.ndarray:
        """
        Encode legal actions as a binary mask of size max_actions.
        Canonical action slots:
          0: fold, 1: check/call, 2: bet_small/raise_small, 3: bet_large/raise_large,
          4: (reserved for additional sizes), 5: allin
        """
        mask = np.zeros(max_actions, dtype=np.float32)
        actions = state.legal_actions()
        for action in actions:
            slot = _action_to_slot(action)
            if 0 <= slot < max_actions:
                mask[slot] = 1.0
        return mask


def _action_to_slot(action: Action) -> int:
    """Map an Action to a canonical slot index."""
    if action.type == ActionType.FOLD:
        return 0
    elif action.type in (ActionType.CHECK, ActionType.CALL):
        return 1
    elif action.type == ActionType.BET:
        return 2  # first bet size → slot 2, second → slot 3
    elif action.type == ActionType.RAISE:
        return 2  # first raise size → slot 2, second → slot 3
    elif action.type == ActionType.ALLIN:
        return 5
    return -1


def actions_to_slots(actions: list[Action]) -> list[int]:
    """Map a list of legal actions to their canonical slot indices, handling duplicates."""
    slots = []
    bet_raise_count = 0
    for action in actions:
        if action.type == ActionType.FOLD:
            slots.append(0)
        elif action.type in (ActionType.CHECK, ActionType.CALL):
            slots.append(1)
        elif action.type in (ActionType.BET, ActionType.RAISE):
            slot = 2 + bet_raise_count
            bet_raise_count += 1
            slots.append(min(slot, 4))  # cap at slot 4
        elif action.type == ActionType.ALLIN:
            slots.append(5)
        else:
            slots.append(-1)
    return slots


def encode_legal_mask_from_actions(actions: list[Action], max_actions: int = 6) -> np.ndarray:
    """Encode legal actions as a binary mask using proper slot assignment."""
    mask = np.zeros(max_actions, dtype=np.float32)
    for slot in actions_to_slots(actions):
        if 0 <= slot < max_actions:
            mask[slot] = 1.0
    return mask


# ---------- Leduc Encoder ----------

class LeducEncoder:
    """Simple encoder for Leduc Hold'em."""

    # card_rank(3) + board_rank(3) + street(2) + position(2) + pot(1) + committed(2) + history(12) = 25
    RAW_DIM = 25

    @staticmethod
    def encode(state: LeducGameState) -> np.ndarray:
        features = np.zeros(LeducEncoder.RAW_DIM, dtype=np.float32)
        p = state.current_player

        # Card rank one-hot (J=0, Q=1, K=2)
        rank = state.hole_cards[p] // 2
        features[rank] = 1.0

        # Board rank one-hot
        if state.board >= 0:
            board_rank = state.board // 2
            features[3 + board_rank] = 1.0

        # Street
        features[6 + state.street] = 1.0

        # Position
        features[8 + p] = 1.0

        # Pot (normalized)
        features[10] = state.pot / 26.0

        # Committed this street
        features[11] = state.street_committed[p] / 13.0
        features[12] = state.street_committed[1 - p] / 13.0

        # Action history (last 6 actions × 2 features each)
        history = state.actions_history[-6:]
        action_map = {'fold': 0, 'check': 0.25, 'call': 0.5, 'bet': 0.75, 'raise': 1.0}
        for i, (actor, action_str) in enumerate(history):
            features[13 + i * 2] = 0.0 if actor == p else 1.0
            features[13 + i * 2 + 1] = action_map.get(action_str, 0)

        return features

    @staticmethod
    def encode_legal_mask(state: LeducGameState, max_actions: int = 4) -> np.ndarray:
        """Leduc actions: 0=fold, 1=check/call, 2=bet, 3=raise"""
        mask = np.zeros(max_actions, dtype=np.float32)
        for a in state.legal_actions():
            if a == 'fold':
                mask[0] = 1.0
            elif a in ('check', 'call'):
                mask[1] = 1.0
            elif a == 'bet':
                mask[2] = 1.0
            elif a == 'raise':
                mask[3] = 1.0
        return mask
