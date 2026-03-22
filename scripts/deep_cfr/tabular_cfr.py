"""
Flaw 3 Fix: Tabular CFR solver for Leduc Hold'em.

Provides a ground-truth Nash equilibrium to validate SD-CFR convergence.
Leduc is small enough (~900 info sets) for exact tabular CFR.

Usage:
  # Solve Leduc to near-Nash
  python -m scripts.deep_cfr.tabular_cfr --iterations 10000

  # Compare against SD-CFR checkpoint
  python -m scripts.deep_cfr.tabular_cfr --iterations 10000 \
    --compare checkpoints/sdcfr_leduc_v3/sdcfr_iter150.pt
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import time
from collections import defaultdict

import numpy as np

from .game_state import LeducGameState


# ---------- Tabular CFR (Vanilla) ----------

class TabularCFR:
    """
    Vanilla CFR for Leduc Hold'em with tabular regret/strategy storage.
    Uses regret matching and accumulates average strategy with linear weighting.
    """

    def __init__(self):
        # regret_sum[info_key][action_index] = cumulative regret
        self.regret_sum: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(4, dtype=np.float64))
        # strategy_sum[info_key][action_index] = cumulative strategy (weighted)
        self.strategy_sum: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(4, dtype=np.float64))
        # action_slot_map for Leduc
        self.action_map = {'fold': 0, 'check': 1, 'call': 1, 'bet': 2, 'raise': 3}

    def get_strategy(self, info_key: str, legal_actions: list[str]) -> np.ndarray:
        """Get current strategy via regret matching."""
        regrets = self.regret_sum[info_key]
        strategy = np.zeros(4, dtype=np.float64)

        # Map legal actions to slots
        legal_slots = set()
        for a in legal_actions:
            legal_slots.add(self.action_map[a])

        # Regret matching over legal slots
        positive = np.maximum(regrets, 0)
        for slot in range(4):
            if slot not in legal_slots:
                positive[slot] = 0.0

        total = positive.sum()
        if total > 0:
            strategy = positive / total
        else:
            for slot in legal_slots:
                strategy[slot] = 1.0 / len(legal_slots)

        return strategy

    def get_average_strategy(self, info_key: str, legal_actions: list[str]) -> np.ndarray:
        """Get average strategy (Nash approximation)."""
        strat_sum = self.strategy_sum[info_key]
        legal_slots = set(self.action_map[a] for a in legal_actions)

        masked = strat_sum.copy()
        for slot in range(4):
            if slot not in legal_slots:
                masked[slot] = 0.0

        total = masked.sum()
        if total > 0:
            return masked / total
        return np.array([1.0 / len(legal_slots) if s in legal_slots else 0.0 for s in range(4)])

    def train(self, iterations: int = 10000) -> list[float]:
        """
        Run vanilla CFR for N iterations over all 120 Leduc deals.
        Returns exploitability per iteration (sampled every 100 iters).
        """
        cards = list(range(6))
        # All (p0_card, p1_card, board_card) permutations
        deals = list(itertools.permutations(cards, 3))
        deal_prob = 1.0 / len(deals)

        exploit_history = []
        t0 = time.time()

        for t in range(iterations):
            for p0_card, p1_card, board_card in deals:
                state = _make_state(p0_card, p1_card, board_card, cards)
                for traverser in range(2):
                    self._cfr(state, traverser, deal_prob, deal_prob, t + 1)

            if (t + 1) % 100 == 0 or t == 0:
                exploit = self.compute_exploitability()
                exploit_history.append(exploit)
                elapsed = time.time() - t0
                print(f"  Iter {t+1:>5}: exploitability = {exploit:>8.2f} mbb/g  ({elapsed:.1f}s)")

        return exploit_history

    def _cfr(
        self,
        state: LeducGameState,
        traverser: int,
        reach_0: float,
        reach_1: float,
        iteration: int,
    ) -> float:
        """
        Vanilla CFR traversal.
        Returns counterfactual value for traverser.
        """
        if state.is_terminal():
            return state.payoff(traverser)

        actions = state.legal_actions()
        if not actions:
            return 0.0

        p = state.current_player
        info_key = state.to_info_key()
        strategy = self.get_strategy(info_key, actions)

        # Accumulate average strategy with linear weighting
        reach_p = reach_0 if p == 0 else reach_1
        weight = iteration  # Linear CFR weighting
        for a in actions:
            slot = self.action_map[a]
            self.strategy_sum[info_key][slot] += reach_p * strategy[slot] * weight

        # Compute action values
        action_values = np.zeros(4, dtype=np.float64)
        for a in actions:
            slot = self.action_map[a]
            child = state.apply(a)
            if p == 0:
                action_values[slot] = self._cfr(child, traverser,
                                                 reach_0 * strategy[slot], reach_1, iteration)
            else:
                action_values[slot] = self._cfr(child, traverser,
                                                 reach_0, reach_1 * strategy[slot], iteration)

        # Expected value under current strategy
        ev = 0.0
        for a in actions:
            slot = self.action_map[a]
            ev += strategy[slot] * action_values[slot]

        # Update regrets (only for traverser)
        if p == traverser:
            opp_reach = reach_1 if p == 0 else reach_0
            for a in actions:
                slot = self.action_map[a]
                regret = action_values[slot] - ev
                self.regret_sum[info_key][slot] += opp_reach * regret

        return ev

    def compute_exploitability(self) -> float:
        """
        Compute exploitability in mbb/g via non-cheating best response.
        The BR player conditions only on their own info set (not opponent's cards).
        Uses iterative BR: accumulate per-info-set action values, pick argmax, repeat.
        """
        cards = list(range(6))
        deals = list(itertools.permutations(cards, 3))
        deal_prob = 1.0 / len(deals)

        total_br_ev = [0.0, 0.0]

        for br_player in range(2):
            br_policy: dict[str, int] = {}

            # Iterate until BR policy stabilizes
            for _ in range(20):
                info_action_values: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))

                for p0_card, p1_card, board_card in deals:
                    state = _make_state(p0_card, p1_card, board_card, cards)
                    self._collect_br_values(
                        state, br_player, deal_prob, br_policy, info_action_values,
                    )

                new_policy: dict[str, int] = {}
                for info_key, av in info_action_values.items():
                    new_policy[info_key] = max(av, key=av.get)

                if new_policy == br_policy:
                    break
                br_policy = new_policy

            # Final evaluation with the non-cheating BR policy
            br_ev = 0.0
            for p0_card, p1_card, board_card in deals:
                state = _make_state(p0_card, p1_card, board_card, cards)
                br_ev += self._eval_br_policy(state, br_player, deal_prob, br_policy)
            total_br_ev[br_player] = br_ev

        exploit = (total_br_ev[0] + total_br_ev[1]) / 2.0
        return exploit * 1000  # mbb/g

    def _collect_br_values(
        self,
        state: LeducGameState,
        br_player: int,
        opp_reach: float,
        br_policy: dict[str, int],
        info_action_values: dict[str, dict[int, float]],
    ) -> float:
        """Collect weighted action values at BR info sets. Returns raw EV for br_player."""
        if state.is_terminal():
            return state.payoff(br_player)

        actions = state.legal_actions()
        if not actions:
            return 0.0

        p = state.current_player
        info_key = state.to_info_key()

        if p == br_player:
            action_evs = []
            for i, a in enumerate(actions):
                child = state.apply(a)
                ev = self._collect_br_values(child, br_player, opp_reach,
                                              br_policy, info_action_values)
                info_action_values[info_key][i] += opp_reach * ev
                action_evs.append(ev)

            if info_key in br_policy:
                idx = br_policy[info_key]
                return action_evs[idx] if idx < len(action_evs) else max(action_evs)
            return max(action_evs)
        else:
            # Opponent plays average strategy
            avg_strategy = self.get_average_strategy(info_key, actions)
            ev = 0.0
            for i, a in enumerate(actions):
                slot = self.action_map[a]
                child = state.apply(a)
                child_ev = self._collect_br_values(
                    child, br_player, opp_reach * avg_strategy[slot],
                    br_policy, info_action_values,
                )
                ev += avg_strategy[slot] * child_ev
            return ev

    def _eval_br_policy(
        self,
        state: LeducGameState,
        br_player: int,
        weight: float,
        br_policy: dict[str, int],
    ) -> float:
        """Evaluate BR player's EV using the non-cheating info-set-level policy."""
        if state.is_terminal():
            return weight * state.payoff(br_player)

        actions = state.legal_actions()
        if not actions:
            return 0.0

        p = state.current_player
        info_key = state.to_info_key()

        if p == br_player:
            idx = br_policy.get(info_key, 0)
            idx = min(idx, len(actions) - 1)
            child = state.apply(actions[idx])
            return self._eval_br_policy(child, br_player, weight, br_policy)
        else:
            avg_strategy = self.get_average_strategy(info_key, actions)
            ev = 0.0
            for a in actions:
                slot = self.action_map[a]
                child = state.apply(a)
                ev += avg_strategy[slot] * self._eval_br_policy(
                    child, br_player, weight, br_policy)
            return ev

    def strategy_at_info_sets(self) -> dict[str, dict[str, float]]:
        """Export average strategy as {info_key: {slot_name: prob}}."""
        slot_names = {0: 'fold', 1: 'check/call', 2: 'bet', 3: 'raise'}
        result = {}
        for info_key in self.strategy_sum:
            strat = self.strategy_sum[info_key]
            total = strat.sum()
            if total > 0:
                probs = strat / total
            else:
                probs = np.zeros(4)
            result[info_key] = {slot_names[i]: float(probs[i]) for i in range(4) if probs[i] > 0.001}
        return result


# ---------- Compare SD-CFR vs Tabular ----------

def compare_strategies(
    tabular: TabularCFR,
    checkpoint_path: str,
    device: str = 'cpu',
) -> dict:
    """
    Compare SD-CFR ensemble strategy against tabular CFR ground truth.
    Returns per-info-set KL divergence and summary statistics.
    """
    from .eval_agent import load_agent, SDCFRAgent

    cards = list(range(6))
    deals = list(itertools.permutations(cards, 3))
    action_slot_map = {'fold': 0, 'check': 1, 'call': 1, 'bet': 2, 'raise': 3}

    # Load SD-CFR agents
    agents = [
        load_agent(checkpoint_path, player=p, device=device, mode='ensemble')
        for p in range(2)
    ]

    kl_divs = []
    l1_dists = []
    info_set_comparisons = []

    for p0_card, p1_card, board_card in deals:
        state = _make_state(p0_card, p1_card, board_card, cards)
        _compare_recursive(
            state, tabular, agents, action_slot_map,
            kl_divs, l1_dists, info_set_comparisons,
        )

    # Deduplicate info sets (same info_key seen from different deals)
    seen = set()
    unique_comparisons = []
    unique_kl = []
    unique_l1 = []
    for comp in info_set_comparisons:
        if comp['info_key'] not in seen:
            seen.add(comp['info_key'])
            unique_comparisons.append(comp)
            unique_kl.append(comp['kl'])
            unique_l1.append(comp['l1'])

    return {
        'n_info_sets': len(unique_comparisons),
        'mean_kl': float(np.mean(unique_kl)) if unique_kl else 0.0,
        'median_kl': float(np.median(unique_kl)) if unique_kl else 0.0,
        'max_kl': float(np.max(unique_kl)) if unique_kl else 0.0,
        'mean_l1': float(np.mean(unique_l1)) if unique_l1 else 0.0,
        'worst_info_sets': sorted(unique_comparisons, key=lambda x: -x['kl'])[:10],
    }


def _compare_recursive(
    state: LeducGameState,
    tabular: TabularCFR,
    agents: list,
    action_slot_map: dict,
    kl_divs: list,
    l1_dists: list,
    comparisons: list,
) -> None:
    """Walk the game tree, comparing strategies at each info set."""
    if state.is_terminal():
        return

    actions = state.legal_actions()
    if not actions:
        return

    p = state.current_player
    info_key = state.to_info_key()

    # Tabular average strategy
    tab_strat = tabular.get_average_strategy(info_key, actions)

    # SD-CFR ensemble strategy
    _, sdcfr_probs = agents[p].get_strategy(state)

    # Convert SD-CFR probs to slot format
    sdcfr_slots = np.zeros(4, dtype=np.float64)
    for i, a in enumerate(actions):
        sdcfr_slots[action_slot_map[a]] += sdcfr_probs[i]

    # KL divergence: tab || sdcfr
    kl = 0.0
    l1 = 0.0
    for slot in range(4):
        if tab_strat[slot] > 1e-8:
            kl += tab_strat[slot] * np.log(tab_strat[slot] / max(sdcfr_slots[slot], 1e-8))
        l1 += abs(tab_strat[slot] - sdcfr_slots[slot])

    kl_divs.append(kl)
    l1_dists.append(l1)
    comparisons.append({
        'info_key': info_key,
        'kl': kl,
        'l1': l1,
        'tabular': {i: float(tab_strat[i]) for i in range(4) if tab_strat[i] > 0.001},
        'sdcfr': {i: float(sdcfr_slots[i]) for i in range(4) if sdcfr_slots[i] > 0.001},
    })

    # Continue traversal (visit one random child for coverage)
    import random
    for a in actions:
        child = state.apply(a)
        _compare_recursive(child, tabular, agents, action_slot_map,
                           kl_divs, l1_dists, comparisons)


def _make_state(p0_card: int, p1_card: int, board_card: int, cards: list[int]) -> LeducGameState:
    """Create a Leduc state with specific cards."""
    state = LeducGameState()
    state.hole_cards = [p0_card, p1_card]
    remaining = [c for c in cards if c not in (p0_card, p1_card, board_card)]
    state.deck = remaining[:2] + [board_card] + remaining[2:]
    return state


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(description='Tabular CFR for Leduc Hold\'em')
    parser.add_argument('--iterations', type=int, default=10000,
                        help='Number of CFR iterations')
    parser.add_argument('--compare', type=str, default=None,
                        help='SD-CFR checkpoint to compare against')
    parser.add_argument('--device', type=str, default='cpu')
    parser.add_argument('--save-strategy', type=str, default=None,
                        help='Save tabular strategy as JSON')

    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"Tabular CFR for Leduc Hold'em")
    print(f"Iterations: {args.iterations}")
    print(f"{'='*60}\n")

    cfr = TabularCFR()
    t0 = time.time()
    exploit_history = cfr.train(args.iterations)
    elapsed = time.time() - t0

    print(f"\nFinal exploitability: {exploit_history[-1]:.2f} mbb/g")
    print(f"Info sets: {len(cfr.strategy_sum)}")
    print(f"Time: {elapsed:.1f}s")

    # Save strategy
    if args.save_strategy:
        strategy = cfr.strategy_at_info_sets()
        with open(args.save_strategy, 'w') as f:
            json.dump(strategy, f, indent=2)
        print(f"Saved strategy to {args.save_strategy}")

    # Compare against SD-CFR
    if args.compare:
        print(f"\n{'='*60}")
        print(f"Comparing against SD-CFR: {args.compare}")
        print(f"{'='*60}\n")

        result = compare_strategies(cfr, args.compare, device=args.device)

        print(f"Info sets compared: {result['n_info_sets']}")
        print(f"Mean KL divergence:   {result['mean_kl']:.6f}")
        print(f"Median KL divergence: {result['median_kl']:.6f}")
        print(f"Max KL divergence:    {result['max_kl']:.6f}")
        print(f"Mean L1 distance:     {result['mean_l1']:.4f}")

        print(f"\nWorst 10 info sets:")
        for comp in result['worst_info_sets']:
            print(f"  {comp['info_key']}")
            print(f"    Tabular: {comp['tabular']}")
            print(f"    SD-CFR:  {comp['sdcfr']}")
            print(f"    KL={comp['kl']:.4f}  L1={comp['l1']:.4f}")


if __name__ == '__main__':
    main()
