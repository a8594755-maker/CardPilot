"""Strict v6 training environment, with a read-only BB-unit legacy trainer view."""
from __future__ import annotations

import operator
from types import SimpleNamespace
import numpy as np

from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.policy_contract_v6 import METADATA, action_table, apply_incr, observation
from deep_cfr.game_state import Action, ActionType, Street


def legacy_action(state, incr):
    if incr is None:
        return None
    if incr[0] != "b":
        return Action({"f": ActionType.FOLD, "k": ActionType.CHECK, "c": ActionType.CALL}[incr])
    return Action(ActionType.RAISE if max(state.bets) else ActionType.BET, int(incr[1:])/100)


class BBStateView:
    """Adapter only: all mutable monetary logic stays in immutable ChipState."""
    def __init__(self, core):
        self.core = core
        self.config = SimpleNamespace(effective_stack=core.initial[0]/100, include_preflop=True)

    @property
    def stacks(self): return [x/100 for x in self.core.stacks]
    @property
    def street_committed(self): return [x/100 for x in self.core.bets]
    @property
    def pot(self): return self.core.pot/100
    @property
    def current_player(self): return self.core.actor
    @property
    def street(self): return Street(self.core.street)
    @property
    def board(self): return list(self.core.board)
    @property
    def deck(self): return list(self.core.deck)
    @property
    def hole_cards(self): return list(self.core.holes)
    @property
    def last_bet_size(self): return self.core.last_full_raise/100
    @property
    def folded_player(self): return self.core.folded
    @property
    def is_done(self): return self.core.terminal
    @property
    def num_actions_this_street(self): return sum(e.street == self.core.street for e in self.core.history)
    @property
    def raise_count(self): return sum(e.street == self.core.street and e.kind == "b" for e in self.core.history)
    @property
    def actions_history(self):
        return [(event.player, Action((ActionType.RAISE if event.is_raise else ActionType.BET)
                      if event.kind == "b" else {"f": ActionType.FOLD, "k": ActionType.CHECK, "c": ActionType.CALL}[event.kind],
                      event.amount/100)) for event in self.core.history]

    def get_actions_by_street(self):
        groups = [[] for _ in range(4)]
        for event, action in zip(self.core.history, self.actions_history):
            groups[event.street].append(action)
        return groups

    def is_terminal(self): return self.core.terminal
    def payoff(self, player): return self.core.payoffs()[player]/100
    def clone(self): return BBStateView(self.core)

    def legal_actions(self):
        return [legacy_action(self.core, incr) for incr in action_table(self.core)[1] if incr is not None]

    def apply(self, action):
        if action.type in (ActionType.BET, ActionType.RAISE, ActionType.ALLIN):
            chips = round(action.amount*100)
            if abs(chips-action.amount*100) > 1e-7:
                raise ValueError("Action not representable in integer chips")
            incr = f"b{chips}"
        else:
            incr = {ActionType.FOLD: "f", ActionType.CHECK: "k", ActionType.CALL: "c"}[action.type]
        return BBStateView(apply_incr(self.core, incr))


class HUNLEnvironmentV6:
    metadata = METADATA

    def __init__(self, starting_stack=200.0):
        if starting_stack != 200:
            raise ValueError("This versioned production environment requires exactly200bb")
        self.starting_stack = 200.0
        self.big_blind = 1.0
        self.state = None
        self.last_action_table = [None]*9
        self._legal_calls_this_hand = 0

    def reset(self):
        return self.reset_with_deck(None)

    def reset_with_deck(self, deck):
        self.state = BBStateView(ChipState.new(deck))
        self._legal_calls_this_hand = 0
        return self._get_obs()

    def _get_obs(self):
        obs, table = observation(self.state.core)
        self.last_action_table = [legacy_action(self.state.core, incr) for incr in table]
        self._legal_calls_this_hand += 1
        return obs

    def chips_committed(self, player):
        return (self.state.core.initial[player]-self.state.core.stacks[player])/100 if self.state else 0.0

    def step(self, action_idx):
        index = operator.index(action_idx)
        if self.state is None or self.state.is_terminal():
            raise ValueError("Call reset before step")
        if not 0 <= index < 9 or self.last_action_table[index] is None:
            raise ValueError("Illegal action slot; no passive fallback in v6")
        player = self.state.current_player
        self.state = self.state.apply(self.last_action_table[index])
        if self.state.is_terminal():
            return dict(card_info=np.zeros((6, 4, 13), np.float32),
                        action_info=np.zeros((25, 4, 5), np.float32),
                        extra_info=np.zeros(2, np.float32), legal_mask=np.zeros(9, np.float32),
                        player=-1), self.state.payoff(player), True
        return self._get_obs(), 0.0, False


HUNLEnvironment = HUNLEnvironmentV6
