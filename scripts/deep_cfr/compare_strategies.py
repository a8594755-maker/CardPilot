"""
Compare SD-CFR neural strategies vs tabular CFR reference strategies on Leduc Hold'em.

Computes per-info-set KL divergence and overall strategy accuracy.

Usage:
  python -m scripts.deep_cfr.compare_strategies \
    --checkpoint checkpoints/sdcfr_leduc_v4/sdcfr_iter50.pt \
    --tabular-iters 200
"""

from __future__ import annotations

import argparse
import itertools
from collections import defaultdict

import numpy as np

from .eval_agent import SDCFRAgent, load_agent
from .game_state import LeducGameState
from .tabular_cfr_leduc import TabularCFR


def collect_info_sets(tabular: TabularCFR) -> dict[str, dict]:
    """
    Enumerate ALL reachable info sets and collect tabular average strategies.
    Returns: info_key → {'actions': list[str], 'tabular_strategy': np.array, 'player': int}
    """
    cards = list(range(6))
    deals = list(itertools.permutations(cards, 3))
    info_sets: dict[str, dict] = {}

    for p0_card, p1_card, board_card in deals:
        state = TabularCFR._make_state(p0_card, p1_card, board_card, cards)
        _collect_info_sets_recurse(state, tabular, info_sets)

    return info_sets


def _collect_info_sets_recurse(state: LeducGameState, tabular: TabularCFR,
                                info_sets: dict[str, dict]) -> None:
    if state.is_terminal():
        return

    actions = state.legal_actions()
    if not actions:
        return

    info_key = state.to_info_key()
    if info_key not in info_sets:
        avg_strategy = tabular.get_average_strategy(info_key)
        n = tabular.n_actions.get(info_key, len(actions))
        info_sets[info_key] = {
            'actions': actions[:n],
            'tabular_strategy': avg_strategy[:n].copy(),
            'player': state.current_player,
            'state_example': state,  # keep one example state for NN eval
        }

    for action in actions:
        child = state.apply(action)
        _collect_info_sets_recurse(child, tabular, info_sets)


def get_nn_strategy(agent: SDCFRAgent, state: LeducGameState) -> np.ndarray:
    """Get the NN strategy as probabilities over legal actions."""
    actions, probs = agent.get_strategy(state)
    return probs


def kl_divergence(p: np.ndarray, q: np.ndarray, eps: float = 1e-8) -> float:
    """KL(p || q) — how much q diverges from reference p."""
    p = np.clip(p, eps, 1.0)
    q = np.clip(q, eps, 1.0)
    # Renormalize after clipping
    p = p / p.sum()
    q = q / q.sum()
    return float(np.sum(p * np.log(p / q)))


def compare(tabular: TabularCFR, agents: list[SDCFRAgent]) -> dict:
    """
    Compare tabular vs NN strategies on all info sets.
    Returns summary statistics.
    """
    info_sets = collect_info_sets(tabular)
    print(f"Collected {len(info_sets)} info sets")

    kl_values = []
    top1_matches = 0
    total_info_sets = 0
    per_street = defaultdict(list)

    for info_key, info in info_sets.items():
        tab_strat = info['tabular_strategy']
        player = info['player']
        state = info['state_example']
        actions = info['actions']

        # Skip if tabular hasn't visited this info set enough
        if tab_strat.sum() < 1e-6:
            continue

        agent = agents[player]
        nn_strat = get_nn_strategy(agent, state)

        # Ensure same length
        n = min(len(tab_strat), len(nn_strat))
        tab_strat = tab_strat[:n]
        nn_strat = nn_strat[:n]

        # KL divergence
        kl = kl_divergence(tab_strat, nn_strat)
        kl_values.append(kl)

        # Top-1 accuracy (do they agree on the best action?)
        if np.argmax(tab_strat) == np.argmax(nn_strat):
            top1_matches += 1
        total_info_sets += 1

        # Per-street breakdown
        street = 'preflop' if state.street == 0 else 'flop'
        per_street[street].append(kl)

    mean_kl = np.mean(kl_values) if kl_values else 0.0
    median_kl = np.median(kl_values) if kl_values else 0.0
    max_kl = np.max(kl_values) if kl_values else 0.0
    top1_acc = top1_matches / max(total_info_sets, 1)

    results = {
        'mean_kl': mean_kl,
        'median_kl': median_kl,
        'max_kl': max_kl,
        'top1_accuracy': top1_acc,
        'n_info_sets': total_info_sets,
        'per_street': {
            street: {
                'mean_kl': float(np.mean(vals)),
                'median_kl': float(np.median(vals)),
                'count': len(vals),
            }
            for street, vals in per_street.items()
        },
    }

    return results


def print_worst_info_sets(tabular: TabularCFR, agents: list[SDCFRAgent], top_n: int = 10):
    """Print the info sets with the highest KL divergence."""
    info_sets = collect_info_sets(tabular)

    divergences = []
    for info_key, info in info_sets.items():
        tab_strat = info['tabular_strategy']
        if tab_strat.sum() < 1e-6:
            continue
        player = info['player']
        state = info['state_example']
        agent = agents[player]
        nn_strat = get_nn_strategy(agent, state)
        n = min(len(tab_strat), len(nn_strat))
        kl = kl_divergence(tab_strat[:n], nn_strat[:n])
        divergences.append((kl, info_key, tab_strat[:n], nn_strat[:n], info['actions'][:n]))

    divergences.sort(reverse=True)

    print(f"\nTop {top_n} worst info sets (highest KL divergence):")
    print(f"{'Info Set':<60} {'KL':>8} {'Tab Strategy':>35} {'NN Strategy':>35}")
    print("-" * 145)
    for kl, key, tab, nn, actions in divergences[:top_n]:
        tab_str = ' '.join(f"{a}={v:.3f}" for a, v in zip(actions, tab))
        nn_str = ' '.join(f"{a}={v:.3f}" for a, v in zip(actions, nn))
        print(f"  {key:<58} {kl:8.4f} {tab_str:>35} {nn_str:>35}")


def main():
    parser = argparse.ArgumentParser(description='Compare SD-CFR vs Tabular strategies')
    parser.add_argument('--checkpoint', type=str, required=True)
    parser.add_argument('--tabular-iters', type=int, default=200)
    parser.add_argument('--device', type=str, default='cpu')
    parser.add_argument('--worst', type=int, default=10,
                       help='Print N worst info sets by KL divergence')

    args = parser.parse_args()

    # Train tabular CFR
    print(f"Training tabular CFR for {args.tabular_iters} iterations...")
    tabular = TabularCFR()
    tabular.train(args.tabular_iters)

    # Load SD-CFR agents (ensemble mode for average strategy)
    print(f"\nLoading SD-CFR checkpoint: {args.checkpoint}")
    agent0 = load_agent(args.checkpoint, player=0, device=args.device, mode='ensemble')
    agent1 = load_agent(args.checkpoint, player=1, device=args.device, mode='ensemble')
    agents = [agent0, agent1]

    # Compare
    print("\nComparing strategies...")
    results = compare(tabular, agents)

    print(f"\n{'='*60}")
    print(f"SD-CFR vs Tabular CFR ({args.tabular_iters} iter) Comparison")
    print(f"{'='*60}")
    print(f"  Info sets compared: {results['n_info_sets']}")
    print(f"  Mean KL divergence:   {results['mean_kl']:.4f}")
    print(f"  Median KL divergence: {results['median_kl']:.4f}")
    print(f"  Max KL divergence:    {results['max_kl']:.4f}")
    print(f"  Top-1 accuracy:       {results['top1_accuracy']:.1%}")

    for street, stats in results['per_street'].items():
        print(f"  {street}: mean_kl={stats['mean_kl']:.4f}, "
              f"median={stats['median_kl']:.4f}, count={stats['count']}")

    # Print worst info sets
    if args.worst > 0:
        print_worst_info_sets(tabular, agents, args.worst)


if __name__ == '__main__':
    main()
