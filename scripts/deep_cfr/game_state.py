"""
HU No-Limit Hold'em game state for SD-CFR traversal.

Simplified but faithful model of heads-up NLHE:
- 2 players: OOP (0, BB) and IP (1, BTN/SB)
- Streets: PREFLOP → FLOP → TURN → RIVER → SHOWDOWN
- Configurable bet sizes, stack depths, raise caps
- Immutable-style: apply() returns a new state (for tree branching)

Card encoding: 0..51, card = rank*4 + suit  (rank: 0=2..12=A, suit: 0=c 1=d 2=h 3=s)
"""

from __future__ import annotations

import random
from copy import deepcopy
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

from .hand_eval import compare_hands

# ---------- Constants ----------

class Street(IntEnum):
    PREFLOP = 0
    FLOP = 1
    TURN = 2
    RIVER = 3
    SHOWDOWN = 4

STREET_NAMES = ['PREFLOP', 'FLOP', 'TURN', 'RIVER', 'SHOWDOWN']

class ActionType(IntEnum):
    FOLD = 0
    CHECK = 1
    CALL = 2
    BET = 3     # opening bet (when no bet yet on street)
    RAISE = 4   # raising an existing bet
    ALLIN = 5

@dataclass(frozen=True)
class Action:
    type: ActionType
    amount: float = 0.0   # total bet/raise TO amount (not additional chips)

    def __repr__(self) -> str:
        if self.type in (ActionType.FOLD, ActionType.CHECK, ActionType.CALL):
            return self.type.name.lower()
        if self.type == ActionType.ALLIN:
            return f"allin({self.amount:.1f})"
        return f"{self.type.name.lower()}({self.amount:.1f})"


# ---------- Bet sizing config ----------

@dataclass
class BetSizeConfig:
    """Bet sizes as fractions of the pot, per street."""
    flop: list[float] = field(default_factory=lambda: [0.33, 0.75])
    turn: list[float] = field(default_factory=lambda: [0.50, 1.00])
    river: list[float] = field(default_factory=lambda: [0.75, 1.50])

    def for_street(self, street: Street) -> list[float]:
        if street == Street.FLOP:
            return self.flop
        elif street == Street.TURN:
            return self.turn
        elif street == Street.RIVER:
            return self.river
        return []


DEFAULT_BET_SIZES = BetSizeConfig()


# ---------- Game config ----------

@dataclass
class GameConfig:
    """Configuration for a HU NLHE game."""
    starting_pot: float = 5.0       # pot after preflop action (in BB)
    effective_stack: float = 47.5   # remaining stack per player (in BB)
    bet_sizes: BetSizeConfig = field(default_factory=BetSizeConfig)
    raise_cap_per_street: int = 1   # max raises per street (0 = no raising after bet)
    include_preflop: bool = False   # if False, start from flop

    @staticmethod
    def srp_50bb() -> 'GameConfig':
        return GameConfig(starting_pot=5.0, effective_stack=47.5)

    @staticmethod
    def bet3_50bb() -> 'GameConfig':
        return GameConfig(starting_pot=17.5, effective_stack=41.25)

    @staticmethod
    def srp_100bb() -> 'GameConfig':
        return GameConfig(starting_pot=5.0, effective_stack=97.5)

    @staticmethod
    def bet3_100bb() -> 'GameConfig':
        return GameConfig(starting_pot=17.5, effective_stack=91.25)


# ---------- Game state ----------

class HUNLGameState:
    """
    Immutable-ish HU NL Hold'em game state.
    Call apply(action) to get a new state — does NOT mutate self.
    """

    __slots__ = (
        'config', 'deck', 'hole_cards', 'board', 'pot', 'stacks',
        'street', 'street_committed', 'current_player', 'actions_history',
        'raise_count', 'last_bet_size', 'is_done', 'folded_player',
        'num_actions_this_street',
    )

    def __init__(self, config: GameConfig | None = None):
        self.config = config or GameConfig()
        self.deck: list[int] = list(range(52))
        self.hole_cards: list[tuple[int, int] | None] = [None, None]
        self.board: list[int] = []
        self.pot: float = self.config.starting_pot
        self.stacks: list[float] = [self.config.effective_stack, self.config.effective_stack]
        self.street: Street = Street.FLOP if not self.config.include_preflop else Street.PREFLOP
        self.street_committed: list[float] = [0.0, 0.0]  # chips committed this street
        self.current_player: int = 0  # OOP acts first postflop
        self.actions_history: list[tuple[int, Action]] = []
        self.raise_count: int = 0
        self.last_bet_size: float = 0.0  # the current outstanding bet on this street
        self.is_done: bool = False
        self.folded_player: int = -1
        self.num_actions_this_street: int = 0

    def clone(self) -> 'HUNLGameState':
        """Deep copy for branching."""
        s = HUNLGameState.__new__(HUNLGameState)
        s.config = self.config
        s.deck = self.deck.copy()
        s.hole_cards = list(self.hole_cards)
        s.board = self.board.copy()
        s.pot = self.pot
        s.stacks = self.stacks.copy()
        s.street = self.street
        s.street_committed = self.street_committed.copy()
        s.current_player = self.current_player
        s.actions_history = self.actions_history.copy()
        s.raise_count = self.raise_count
        s.last_bet_size = self.last_bet_size
        s.is_done = self.is_done
        s.folded_player = self.folded_player
        s.num_actions_this_street = self.num_actions_this_street
        return s

    # ---------- Deal ----------

    def deal_new_hand(self) -> 'HUNLGameState':
        """Deal hole cards and flop (or just hole cards if include_preflop)."""
        s = self.clone()
        random.shuffle(s.deck)
        s.hole_cards = [
            (s.deck[0], s.deck[1]),
            (s.deck[2], s.deck[3]),
        ]
        if not s.config.include_preflop:
            # Deal flop
            s.board = [s.deck[4], s.deck[5], s.deck[6]]
        return s

    def deal_with_cards(self, hole0: tuple[int, int], hole1: tuple[int, int],
                        board: list[int]) -> 'HUNLGameState':
        """Set up with specific cards (for controlled traversals)."""
        s = self.clone()
        used = {hole0[0], hole0[1], hole1[0], hole1[1]} | set(board)
        s.deck = [c for c in range(52) if c not in used]
        random.shuffle(s.deck)
        s.hole_cards = [hole0, hole1]
        s.board = list(board)
        return s

    # ---------- Queries ----------

    def is_terminal(self) -> bool:
        return self.is_done

    def is_chance_node(self) -> bool:
        """True if we need to deal community cards before next action."""
        if self.is_done:
            return False
        # Street transition: both players acted and betting is closed
        return False  # Chance is handled inside _advance_street

    def payoff(self, player: int) -> float:
        """
        Terminal payoff for `player` in BB.
        Positive = won, negative = lost.
        """
        assert self.is_done, "Not a terminal state"

        if self.folded_player >= 0:
            # Someone folded — other player wins the pot
            if self.folded_player == player:
                return -(self.config.effective_stack - self.stacks[player])
            else:
                winner_profit = self.config.effective_stack - self.stacks[self.folded_player]
                return winner_profit if player != self.folded_player else -winner_profit

        # Showdown
        assert self.street == Street.SHOWDOWN
        assert len(self.board) == 5
        assert self.hole_cards[0] is not None and self.hole_cards[1] is not None

        cmp = compare_hands(self.hole_cards[0], self.hole_cards[1], self.board)
        total_invested_0 = self.config.effective_stack - self.stacks[0]
        total_invested_1 = self.config.effective_stack - self.stacks[1]

        if cmp > 0:
            # Player 0 wins
            return total_invested_1 if player == 0 else -total_invested_1
        elif cmp < 0:
            # Player 1 wins
            return total_invested_0 if player == 1 else -total_invested_0
        else:
            # Tie — no profit
            return 0.0

    # ---------- Legal actions ----------

    def legal_actions(self) -> list[Action]:
        """Enumerate legal actions for the current player."""
        if self.is_done:
            return []

        p = self.current_player
        stack = self.stacks[p]
        committed = self.street_committed[p]
        opp_committed = self.street_committed[1 - p]
        to_call = opp_committed - committed

        actions: list[Action] = []

        if to_call <= 0:
            # No outstanding bet — can check
            actions.append(Action(ActionType.CHECK))
        else:
            # Facing a bet — can fold or call
            actions.append(Action(ActionType.FOLD))
            if to_call >= stack:
                # Can only call (all-in)
                actions.append(Action(ActionType.CALL))
                return actions
            actions.append(Action(ActionType.CALL))

        # Can we raise/bet?
        can_raise = self.raise_count < self.config.raise_cap_per_street
        if to_call > 0 and self.raise_count >= self.config.raise_cap_per_street:
            can_raise = False

        if can_raise and stack > to_call:
            pot_after_call = self.pot + to_call
            fractions = self.config.bet_sizes.for_street(self.street)

            for frac in fractions:
                if to_call <= 0:
                    # Opening bet: amount = pot * fraction
                    bet_amount = round(self.pot * frac * 100) / 100
                    total = committed + bet_amount
                    if bet_amount > 0 and bet_amount < stack:
                        actions.append(Action(ActionType.BET, total))
                else:
                    # Raise: call + (pot_after_call * fraction)
                    raise_over = pot_after_call * frac
                    additional = to_call + raise_over
                    if additional < stack:
                        total = committed + additional
                        actions.append(Action(ActionType.RAISE, total))

            # Always include all-in
            allin_total = committed + stack
            actions.append(Action(ActionType.ALLIN, allin_total))

        elif stack > to_call and to_call <= 0:
            # Even with raise cap hit, if no bet yet we can still bet
            # (raise_cap only limits re-raises after a bet)
            pass  # Already handled above

        return actions

    # ---------- Apply action ----------

    def apply(self, action: Action) -> 'HUNLGameState':
        """Apply an action and return a new game state."""
        s = self.clone()
        p = s.current_player
        committed = s.street_committed[p]
        opp_committed = s.street_committed[1 - p]
        to_call = max(0.0, opp_committed - committed)

        if action.type == ActionType.FOLD:
            s.folded_player = p
            s.is_done = True
            s.actions_history.append((p, action))
            return s

        elif action.type == ActionType.CHECK:
            s.actions_history.append((p, action))
            s.num_actions_this_street += 1
            # Check if street is complete
            if s.num_actions_this_street >= 2:
                s._advance_street()
            else:
                s.current_player = 1 - p
            return s

        elif action.type == ActionType.CALL:
            call_amount = min(to_call, s.stacks[p])
            s.stacks[p] -= call_amount
            s.street_committed[p] += call_amount
            s.pot += call_amount
            s.actions_history.append((p, action))
            s.num_actions_this_street += 1

            # After a call, the street is complete (or all-in)
            if s.stacks[0] <= 0 or s.stacks[1] <= 0:
                # All-in — run out remaining streets
                s._run_out_board()
                s.is_done = True
                s.street = Street.SHOWDOWN
            else:
                s._advance_street()
            return s

        elif action.type in (ActionType.BET, ActionType.RAISE, ActionType.ALLIN):
            # Total chips committed after this action
            additional = action.amount - committed
            additional = min(additional, s.stacks[p])
            s.stacks[p] -= additional
            s.street_committed[p] = committed + additional
            s.pot += additional
            s.actions_history.append((p, action))
            s.num_actions_this_street += 1

            if action.type in (ActionType.BET, ActionType.RAISE):
                s.raise_count += 1
                s.last_bet_size = s.street_committed[p]

            if s.stacks[p] <= 0:
                # Player went all-in
                if action.type == ActionType.ALLIN:
                    s.raise_count += 1
                # Opponent gets to act
                s.current_player = 1 - p
                # But if opponent is also all-in, go to showdown
                if s.stacks[1 - p] <= 0:
                    s._run_out_board()
                    s.is_done = True
                    s.street = Street.SHOWDOWN
            else:
                s.current_player = 1 - p

            return s

        raise ValueError(f"Unknown action type: {action.type}")

    # ---------- Street advancement ----------

    def _advance_street(self) -> None:
        """Move to the next street (deal cards, reset betting)."""
        if self.street == Street.RIVER:
            # Showdown
            self.street = Street.SHOWDOWN
            self.is_done = True
            return

        if self.street == Street.PREFLOP:
            self.street = Street.FLOP
            self._deal_street(3)
        elif self.street == Street.FLOP:
            self.street = Street.TURN
            self._deal_street(1)
        elif self.street == Street.TURN:
            self.street = Street.RIVER
            self._deal_street(1)

        # Reset street-level state
        self.street_committed = [0.0, 0.0]
        self.raise_count = 0
        self.last_bet_size = 0.0
        self.current_player = 0  # OOP acts first
        self.num_actions_this_street = 0

    def _deal_street(self, n: int) -> None:
        """Deal n community cards from the deck."""
        for _ in range(n):
            if self.deck:
                self.board.append(self.deck.pop())

    def _run_out_board(self) -> None:
        """Deal remaining community cards for all-in showdown."""
        while len(self.board) < 5:
            if self.deck:
                self.board.append(self.deck.pop())

    # ---------- Info for encoding ----------

    def street_actions(self) -> list[tuple[int, Action]]:
        """Get actions for the current street only (for encoding)."""
        result = []
        # Walk backwards from end to find where current street started
        for player, action in self.actions_history:
            # This is approximate — we include all actions on the current street
            result.append((player, action))
        return result

    def to_info_key(self) -> str:
        """
        Information set key for the current player.
        Includes: hole cards, board, and action history.
        """
        p = self.current_player
        hole = self.hole_cards[p]
        hole_str = f"{hole[0]},{hole[1]}" if hole else "?"
        board_str = ",".join(str(c) for c in self.board)
        acts_str = "|".join(f"{pp}:{a}" for pp, a in self.actions_history)
        return f"P{p}:H[{hole_str}]:B[{board_str}]:A[{acts_str}]"

    def __repr__(self) -> str:
        return (
            f"HUNLGameState(street={STREET_NAMES[self.street]}, pot={self.pot:.1f}, "
            f"stacks={self.stacks}, player={self.current_player}, "
            f"board={self.board}, actions={len(self.actions_history)})"
        )


# ---------- Leduc Hold'em (for smoke testing) ----------

class LeducGameState:
    """
    Leduc Hold'em: 6-card deck (J,Q,K × 2 suits), 1 hole card, 1 board card.
    Used for smoke-testing SD-CFR convergence before scaling to NLHE.

    Rules:
    - 2 players, each antes 1 chip
    - 1 hole card each, 2 betting rounds
    - Round 1: bet/check/fold (fixed bet size = 2)
    - Deal 1 board card
    - Round 2: bet/check/fold (fixed bet size = 4)
    - Showdown: pair beats non-pair, higher card wins
    - Raise cap: 2 raises per round
    """

    BET_SIZES = [2, 4]  # round 1, round 2
    RAISE_CAP = 2

    def __init__(self):
        self.deck: list[int] = list(range(6))  # J=0,1  Q=2,3  K=4,5
        self.hole_cards: list[int] = [-1, -1]
        self.board: int = -1
        self.pot: float = 2.0  # antes (1 each)
        self.stacks: list[float] = [12.0, 12.0]  # 13 - 1 ante each
        self.street: int = 0  # 0 = preflop, 1 = postflop
        self.current_player: int = 0
        self.street_committed: list[float] = [0.0, 0.0]
        self.actions_history: list[tuple[int, str]] = []
        self.raise_count: int = 0
        self.num_actions_this_street: int = 0
        self.is_done: bool = False
        self.folded_player: int = -1

    def clone(self) -> 'LeducGameState':
        s = LeducGameState.__new__(LeducGameState)
        s.deck = self.deck.copy()
        s.hole_cards = self.hole_cards.copy()
        s.board = self.board
        s.pot = self.pot
        s.stacks = self.stacks.copy()
        s.street = self.street
        s.current_player = self.current_player
        s.street_committed = self.street_committed.copy()
        s.actions_history = self.actions_history.copy()
        s.raise_count = self.raise_count
        s.num_actions_this_street = self.num_actions_this_street
        s.is_done = self.is_done
        s.folded_player = self.folded_player
        return s

    def deal_new_hand(self) -> 'LeducGameState':
        s = self.clone()
        random.shuffle(s.deck)
        s.hole_cards = [s.deck[0], s.deck[1]]
        return s

    def is_terminal(self) -> bool:
        return self.is_done

    def _card_rank(self, c: int) -> int:
        """J=0, Q=1, K=2"""
        return c // 2

    def payoff(self, player: int) -> float:
        assert self.is_done
        if self.folded_player >= 0:
            if self.folded_player == player:
                return -(13.0 - self.stacks[player])
            else:
                return 13.0 - self.stacks[self.folded_player]

        # Showdown
        r0 = self._card_rank(self.hole_cards[0])
        r1 = self._card_rank(self.hole_cards[1])
        pair0 = r0 == self._card_rank(self.board)
        pair1 = r1 == self._card_rank(self.board)

        if pair0 and not pair1:
            winner = 0
        elif pair1 and not pair0:
            winner = 1
        elif r0 > r1:
            winner = 0
        elif r1 > r0:
            winner = 1
        else:
            return 0.0  # tie

        invested = 13.0 - self.stacks[1 - winner]
        return invested if player == winner else -invested

    def legal_actions(self) -> list[str]:
        p = self.current_player
        to_call = self.street_committed[1 - p] - self.street_committed[p]
        actions = []

        if to_call <= 0:
            actions.append('check')
        else:
            actions.append('fold')
            actions.append('call')

        if self.raise_count < self.RAISE_CAP:
            bet_size = self.BET_SIZES[self.street]
            if self.stacks[p] > to_call:
                if to_call <= 0:
                    actions.append('bet')
                else:
                    actions.append('raise')

        return actions

    def apply(self, action: str) -> 'LeducGameState':
        s = self.clone()
        p = s.current_player
        to_call = s.street_committed[1 - p] - s.street_committed[p]
        bet_size = s.BET_SIZES[s.street]

        if action == 'fold':
            s.folded_player = p
            s.is_done = True
        elif action == 'check':
            s.num_actions_this_street += 1
            if s.num_actions_this_street >= 2:
                s._advance_street()
            else:
                s.current_player = 1 - p
        elif action == 'call':
            s.stacks[p] -= to_call
            s.street_committed[p] += to_call
            s.pot += to_call
            s.num_actions_this_street += 1
            s._advance_street()
        elif action in ('bet', 'raise'):
            additional = to_call + bet_size
            s.stacks[p] -= additional
            s.street_committed[p] += additional
            s.pot += additional
            s.raise_count += 1
            s.num_actions_this_street += 1
            s.current_player = 1 - p

        s.actions_history.append((p, action))
        return s

    def _advance_street(self) -> None:
        if self.street == 1:
            self.is_done = True
            return

        self.street = 1
        self.board = self.deck[2]  # deal one card
        self.street_committed = [0.0, 0.0]
        self.raise_count = 0
        self.num_actions_this_street = 0
        self.current_player = 0

    def to_info_key(self) -> str:
        p = self.current_player
        h = self._card_rank(self.hole_cards[p])
        b = self._card_rank(self.board) if self.board >= 0 else "?"
        acts = "|".join(f"{pp}:{a}" for pp, a in self.actions_history)
        return f"P{p}:H{h}:B{b}:{acts}"
