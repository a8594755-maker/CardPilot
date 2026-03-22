"""
Tabular CFR for Leduc Hold'em — reference implementation to validate game logic.

If this converges to <50 mbb/g, the game logic is correct and the issue is
in the neural network training. If it doesn't converge, the game logic has a bug.

Usage:
  python -m scripts.deep_cfr.tabular_cfr_leduc --iterations 1000
"""

from __future__ import annotations

import argparse
import itertools
import random
from collections import defaultdict

import numpy as np

from .game_state import LeducGameState


class TabularCFR:
    """Vanilla CFR for Leduc Hold'em with exact game tree traversal."""

    def __init__(self):
        # Cumulative regrets: info_set_key → np.array of regrets per action
        self.regret_sum: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(10))
        # Cumulative strategy (for average strategy): info_set_key → np.array
        self.strategy_sum: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(10))
        # Number of legal actions per info set
        self.n_actions: dict[str, int] = {}

    def get_strategy(self, info_key: str, n_actions: int) -> np.ndarray:
        """Get current strategy via regret matching."""
        regrets = self.regret_sum[info_key][:n_actions]
        positive = np.maximum(regrets, 0)
        total = positive.sum()
        if total > 0:
            return positive / total
        return np.ones(n_actions) / n_actions

    def get_average_strategy(self, info_key: str) -> np.ndarray:
        """Get the average strategy (converges to Nash)."""
        n = self.n_actions.get(info_key, 1)
        strategy = self.strategy_sum[info_key][:n]
        total = strategy.sum()
        if total > 0:
            return strategy / total
        return np.ones(n) / n

    def cfr(self, state: LeducGameState, reach_probs: np.ndarray, iteration: int) -> np.ndarray:
        """
        Run CFR traversal. Returns utility for each player as np.array([u0, u1]).
        Uses chance sampling for the deal.
        """
        if state.is_terminal():
            return np.array([state.payoff(0), state.payoff(1)])

        player = state.current_player
        actions = state.legal_actions()
        n_actions = len(actions)
        info_key = state.to_info_key()
        self.n_actions[info_key] = n_actions

        # Get current strategy
        strategy = self.get_strategy(info_key, n_actions)

        # Accumulate strategy (weighted by reach probability of this player)
        self.strategy_sum[info_key][:n_actions] += reach_probs[player] * strategy

        # Compute utility for each action
        action_utils = np.zeros((n_actions, 2))
        for i, action in enumerate(actions):
            child = state.apply(action)
            new_reach = reach_probs.copy()
            new_reach[player] *= strategy[i]
            action_utils[i] = self.cfr(child, new_reach, iteration)

        # Expected utility under current strategy
        node_util = np.zeros(2)
        for i in range(n_actions):
            node_util += strategy[i] * action_utils[i]

        # Compute and accumulate regrets for the current player
        opp = 1 - player
        for i in range(n_actions):
            regret = action_utils[i][player] - node_util[player]
            self.regret_sum[info_key][i] += reach_probs[opp] * regret

        return node_util

    def train(self, iterations: int) -> None:
        """Run CFR for the specified number of iterations."""
        cards = list(range(6))
        deals = list(itertools.permutations(cards, 3))  # (p0_card, p1_card, board_card)

        for t in range(iterations):
            total_util = np.zeros(2)
            for p0_card, p1_card, board_card in deals:
                state = self._make_state(p0_card, p1_card, board_card, cards)
                reach = np.ones(2) / len(deals)  # weight by deal probability
                util = self.cfr(state, reach, t)
                total_util += util

            if (t + 1) % 100 == 0 or t == 0:
                exploit = self.compute_exploitability()
                print(f"Iter {t+1}: EV=[{total_util[0]:.4f}, {total_util[1]:.4f}] "
                      f"exploit={exploit:.2f} mbb/g | info_sets={len(self.regret_sum)}")

    def compute_exploitability(self) -> float:
        """
        Compute exact exploitability with proper non-cheating best response.
        The BR player chooses ONE action per info set (can't condition on opponent's cards).

        Uses iterative approach: collect weighted action values per info set,
        pick best action, repeat until policy stabilizes (converges in 2-3 iterations
        for Leduc's 2-street structure).
        """
        cards = list(range(6))
        deals = list(itertools.permutations(cards, 3))
        deal_prob = 1.0 / len(deals)

        total_br_ev = [0.0, 0.0]
        for br_player in range(2):
            br_policy: dict[str, int] = {}  # info_key → best action index

            # Iterate until BR policy stabilizes
            for _ in range(10):
                info_action_values: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))

                for p0_card, p1_card, board_card in deals:
                    state = self._make_state(p0_card, p1_card, board_card, cards)
                    self._collect_br_action_values(
                        state, br_player, deal_prob, br_policy, info_action_values,
                    )

                # Update policy: pick best action per info set
                new_policy: dict[str, int] = {}
                for info_key, av in info_action_values.items():
                    new_policy[info_key] = max(av, key=av.get)

                if new_policy == br_policy:
                    break
                br_policy = new_policy

            # Final evaluation with non-cheating policy
            br_ev = 0.0
            for p0_card, p1_card, board_card in deals:
                state = self._make_state(p0_card, p1_card, board_card, cards)
                br_ev += self._eval_br_policy(state, br_player, deal_prob, br_policy)
            total_br_ev[br_player] = br_ev

        exploit = (total_br_ev[0] + total_br_ev[1]) / 2.0
        return exploit * 1000  # mbb/g

    @staticmethod
    def _make_state(p0_card: int, p1_card: int, board_card: int, cards: list[int]) -> LeducGameState:
        """Set up a LeducGameState with specific cards. Board card at deck index 2."""
        state = LeducGameState()
        state.hole_cards = [p0_card, p1_card]
        remaining = [c for c in cards if c not in (p0_card, p1_card, board_card)]
        state.deck = remaining[:2] + [board_card] + remaining[2:]
        return state

    def _collect_br_action_values(
        self,
        state: LeducGameState,
        br_player: int,
        opp_reach: float,
        br_policy: dict[str, int],
        info_action_values: dict[str, dict[int, float]],
    ) -> float:
        """
        Traverse game tree collecting weighted action values at BR info sets.

        Args:
            opp_reach: deal_prob × product of opponent strategy probs along the path.
        Returns:
            Raw expected payoff for br_player (NOT weighted by opp_reach).

        At BR nodes: explore ALL actions, accumulate opp_reach-weighted values per info set.
        At opponent nodes: multiply opp_reach by avg strategy prob and recurse.
        """
        if state.is_terminal():
            return state.payoff(br_player)

        actions = state.legal_actions()
        if not actions:
            return 0.0

        if state.current_player == br_player:
            info_key = state.to_info_key()
            action_evs = []
            for i, action in enumerate(actions):
                child = state.apply(action)
                ev = self._collect_br_action_values(
                    child, br_player, opp_reach, br_policy, info_action_values,
                )
                info_action_values[info_key][i] += opp_reach * ev
                action_evs.append(ev)

            # Return value for parent computation
            if info_key in br_policy:
                idx = br_policy[info_key]
                return action_evs[idx] if idx < len(action_evs) else max(action_evs)
            return max(action_evs)  # cheating fallback for first iteration
        else:
            info_key = state.to_info_key()
            avg_strategy = self.get_average_strategy(info_key)
            ev = 0.0
            for i, action in enumerate(actions):
                child = state.apply(action)
                child_ev = self._collect_br_action_values(
                    child, br_player, opp_reach * avg_strategy[i], br_policy, info_action_values,
                )
                ev += avg_strategy[i] * child_ev
            return ev

    def _eval_br_policy(
        self,
        state: LeducGameState,
        br_player: int,
        weight: float,
        br_policy: dict[str, int],
    ) -> float:
        """Evaluate the BR player's EV using the non-cheating policy."""
        if state.is_terminal():
            return weight * state.payoff(br_player)

        actions = state.legal_actions()
        if not actions:
            return 0.0

        if state.current_player == br_player:
            info_key = state.to_info_key()
            idx = br_policy.get(info_key, 0)
            idx = min(idx, len(actions) - 1)
            child = state.apply(actions[idx])
            return self._eval_br_policy(child, br_player, weight, br_policy)
        else:
            info_key = state.to_info_key()
            avg_strategy = self.get_average_strategy(info_key)
            ev = 0.0
            for i, action in enumerate(actions):
                child = state.apply(action)
                ev += self._eval_br_policy(child, br_player, weight * avg_strategy[i], br_policy)
            return ev


def main():
    parser = argparse.ArgumentParser(description='Tabular CFR for Leduc Hold\'em')
    parser.add_argument('--iterations', type=int, default=1000)
    args = parser.parse_args()

    cfr = TabularCFR()
    cfr.train(args.iterations)

    print(f"\nFinal info sets: {len(cfr.regret_sum)}")
    print("\nSample average strategies:")
    for key in sorted(cfr.n_actions.keys())[:20]:
        avg = cfr.get_average_strategy(key)
        n = cfr.n_actions[key]
        print(f"  {key}: {avg[:n]}")


if __name__ == '__main__':
    main()
