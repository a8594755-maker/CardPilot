"""
SD-CFR inference agent.

Given a trained SD-CFR checkpoint, produce a strategy for any game state:
1. Sample a network from the StrategyBuffer (weighted by iteration)
2. Forward pass to get advantages
3. Regret matching → strategy (probability distribution over actions)

Usage:
  python -m scripts.deep_cfr.eval_agent --checkpoint checkpoints/sdcfr/sdcfr_iter200.pt --game hunl
"""

from __future__ import annotations

import argparse
import random
from collections import OrderedDict

import numpy as np
import torch
import torch.nn as nn

from .encoding import (
    HUNLEncoder, LeducEncoder, encode_legal_mask_from_actions, actions_to_slots,
)
from .game_state import (
    HUNLGameState, LeducGameState, GameConfig, Action, ActionType,
)
from .networks import AdvantageNetwork, LeducAdvantageNetwork, StrategyBuffer


class SDCFRAgent:
    """
    Inference agent using a trained SD-CFR strategy buffer.

    Supports three modes:
    - 'sample': randomly pick a network from the buffer (stochastic, theoretically correct)
    - 'average': use the weighted-average network (deterministic, approximate)
    - 'ensemble': average the regret-matched strategies from ALL networks (deterministic, exact)
    """

    def __init__(
        self,
        strategy_buffer: StrategyBuffer,
        network_template: nn.Module,
        device: torch.device = torch.device('cpu'),
        mode: str = 'sample',
    ):
        self.strategy_buffer = strategy_buffer
        self.network = network_template.to(device)
        self.device = device
        self.mode = mode
        self.is_leduc = isinstance(network_template, LeducAdvantageNetwork)
        self.max_actions = network_template.max_actions

        if mode == 'average':
            avg_dict = strategy_buffer.average_strategy(network_template)
            self.network.load_state_dict(avg_dict)
            self.network.eval()

    def get_strategy(self, state) -> tuple[list, np.ndarray]:
        """
        Get action probabilities for the current state.

        Returns:
            (actions, strategy): list of actions and their probabilities
        """
        if self.mode == 'sample':
            sd = self.strategy_buffer.sample_strategy()
            self.network.load_state_dict(sd)
            self.network.to(self.device)
            self.network.eval()

        if self.mode == 'ensemble':
            if self.is_leduc:
                return self._get_strategy_ensemble_leduc(state)
            else:
                return self._get_strategy_ensemble_hunl(state)

        if self.is_leduc:
            return self._get_strategy_leduc(state)
        else:
            return self._get_strategy_hunl(state)

    def _get_strategy_ensemble_leduc(self, state: LeducGameState) -> tuple[list[str], np.ndarray]:
        """Compute exact average strategy by averaging regret-matched outputs from ALL buffer networks."""
        actions = state.legal_actions()
        if not actions:
            return [], np.array([])

        raw = LeducEncoder.encode(state)
        legal_mask = LeducEncoder.encode_legal_mask(state, self.max_actions)
        raw_t = torch.from_numpy(raw).unsqueeze(0).to(self.device)
        mask_t = torch.from_numpy(legal_mask).unsqueeze(0).to(self.device)

        total_weight = 0.0
        avg_strategy = np.zeros(self.max_actions, dtype=np.float64)

        with torch.no_grad():
            for sd, weight in self.strategy_buffer.networks:
                self.network.load_state_dict(sd)
                self.network.to(self.device)
                self.network.eval()
                advantages = self.network(raw_t, mask_t).squeeze(0).cpu().numpy()
                strategy = _regret_match(advantages, legal_mask)
                avg_strategy += strategy * weight
                total_weight += weight

        if total_weight > 0:
            avg_strategy /= total_weight

        action_slot_map = {'fold': 0, 'check': 1, 'call': 1, 'bet': 2, 'raise': 3}
        action_probs = np.array([avg_strategy[action_slot_map[a]] for a in actions], dtype=np.float64)
        total = action_probs.sum()
        if total > 0:
            action_probs /= total
        else:
            action_probs = np.ones(len(actions)) / len(actions)

        return actions, action_probs.astype(np.float32)

    def _get_strategy_ensemble_hunl(self, state: HUNLGameState) -> tuple[list[Action], np.ndarray]:
        """Compute exact average strategy for HUNL by averaging regret-matched outputs."""
        actions = state.legal_actions()
        if not actions:
            return [], np.array([])

        raw = HUNLEncoder.encode(state)
        legal_mask = encode_legal_mask_from_actions(actions, self.max_actions)
        slots = actions_to_slots(actions)
        raw_t = torch.from_numpy(raw).unsqueeze(0).to(self.device)
        mask_t = torch.from_numpy(legal_mask).unsqueeze(0).to(self.device)

        total_weight = 0.0
        avg_strategy = np.zeros(self.max_actions, dtype=np.float64)

        with torch.no_grad():
            for sd, weight in self.strategy_buffer.networks:
                self.network.load_state_dict(sd)
                self.network.to(self.device)
                self.network.eval()
                advantages = self.network(raw_t, mask_t).squeeze(0).cpu().numpy()
                strategy = _regret_match(advantages, legal_mask)
                avg_strategy += strategy * weight
                total_weight += weight

        if total_weight > 0:
            avg_strategy /= total_weight

        action_probs = np.array([avg_strategy[slots[i]] for i in range(len(actions))], dtype=np.float64)
        total = action_probs.sum()
        if total > 0:
            action_probs /= total
        else:
            action_probs = np.ones(len(actions)) / len(actions)

        return actions, action_probs.astype(np.float32)

    def _get_strategy_hunl(self, state: HUNLGameState) -> tuple[list[Action], np.ndarray]:
        actions = state.legal_actions()
        if not actions:
            return [], np.array([])

        raw = HUNLEncoder.encode(state)
        legal_mask = encode_legal_mask_from_actions(actions, self.max_actions)
        slots = actions_to_slots(actions)

        with torch.no_grad():
            raw_t = torch.from_numpy(raw).unsqueeze(0).to(self.device)
            mask_t = torch.from_numpy(legal_mask).unsqueeze(0).to(self.device)
            advantages = self.network(raw_t, mask_t).squeeze(0).cpu().numpy()

        # Regret matching
        strategy = _regret_match(advantages, legal_mask)

        # Map back to per-action probabilities
        action_probs = np.array([strategy[slots[i]] for i in range(len(actions))])
        total = action_probs.sum()
        if total > 0:
            action_probs /= total
        else:
            action_probs = np.ones(len(actions)) / len(actions)

        return actions, action_probs

    def _get_strategy_leduc(self, state: LeducGameState) -> tuple[list[str], np.ndarray]:
        actions = state.legal_actions()
        if not actions:
            return [], np.array([])

        raw = LeducEncoder.encode(state)
        legal_mask = LeducEncoder.encode_legal_mask(state, self.max_actions)

        with torch.no_grad():
            raw_t = torch.from_numpy(raw).unsqueeze(0).to(self.device)
            mask_t = torch.from_numpy(legal_mask).unsqueeze(0).to(self.device)
            advantages = self.network(raw_t, mask_t).squeeze(0).cpu().numpy()

        strategy = _regret_match(advantages, legal_mask)

        action_slot_map = {'fold': 0, 'check': 1, 'call': 1, 'bet': 2, 'raise': 3}
        action_probs = np.array([strategy[action_slot_map[a]] for a in actions])
        total = action_probs.sum()
        if total > 0:
            action_probs /= total
        else:
            action_probs = np.ones(len(actions)) / len(actions)

        return actions, action_probs

    def choose_action(self, state) -> object:
        """Sample an action from the strategy."""
        actions, probs = self.get_strategy(state)
        if not actions:
            return None
        idx = np.random.choice(len(actions), p=probs)
        return actions[idx]


def _regret_match(advantages: np.ndarray, legal_mask: np.ndarray) -> np.ndarray:
    """When all advantages <= 0, select highest (least negative) action per Brown et al. (2019)."""
    positive = np.maximum(advantages, 0) * legal_mask
    total = positive.sum()
    if total > 0:
        return positive / total
    masked = np.where(legal_mask > 0, advantages, -np.inf)
    best = np.argmax(masked)
    result = np.zeros_like(advantages)
    result[best] = 1.0
    return result


# ---------- Exploitability computation (Leduc only) ----------

def compute_exploitability_leduc(
    agents: list[SDCFRAgent] | SDCFRAgent,
) -> float:
    """
    Compute exact exploitability of Leduc agents via proper non-cheating best response.
    Enumerates all 120 deals and uses iterative BR that picks one action per info set.
    Returns exploitability in mbb/g (milli big blinds per game).

    Args:
        agents: list of [agent_p0, agent_p1] or single agent (used for both).
    """
    import itertools
    from collections import defaultdict

    if isinstance(agents, SDCFRAgent):
        agents = [agents, agents]

    cards = list(range(6))
    deals = list(itertools.permutations(cards, 3))  # (p0, p1, board)
    deal_prob = 1.0 / len(deals)

    total_br_ev = [0.0, 0.0]

    for br_player in range(2):
        br_policy: dict[str, int] = {}

        # Iterate until BR policy stabilizes
        for _ in range(10):
            info_action_values: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))

            for p0_card, p1_card, board_card in deals:
                state = _make_leduc_state(p0_card, p1_card, board_card, cards)
                _collect_br_values_nn(
                    state, br_player, deal_prob, br_policy,
                    agents, info_action_values,
                )

            new_policy: dict[str, int] = {}
            for info_key, av in info_action_values.items():
                new_policy[info_key] = max(av, key=av.get)

            if new_policy == br_policy:
                break
            br_policy = new_policy

        # Final evaluation with non-cheating policy
        br_ev = 0.0
        for p0_card, p1_card, board_card in deals:
            state = _make_leduc_state(p0_card, p1_card, board_card, cards)
            br_ev += _eval_br_policy_nn(state, br_player, deal_prob, br_policy, agents)
        total_br_ev[br_player] = br_ev

    exploit = (total_br_ev[0] + total_br_ev[1]) / 2.0
    return exploit * 1000  # mbb/g


def _make_leduc_state(p0_card: int, p1_card: int, board_card: int, cards: list[int]) -> LeducGameState:
    """Set up a LeducGameState with specific cards. Board card at deck index 2."""
    state = LeducGameState()
    state.hole_cards = [p0_card, p1_card]
    remaining = [c for c in cards if c not in (p0_card, p1_card, board_card)]
    state.deck = remaining[:2] + [board_card] + remaining[2:]
    return state


def _collect_br_values_nn(
    state: LeducGameState,
    br_player: int,
    opp_reach: float,
    br_policy: dict[str, int],
    agents: list[SDCFRAgent],
    info_action_values: dict[str, dict[int, float]],
) -> float:
    """
    Traverse game tree collecting weighted action values at BR info sets.
    Uses neural network agents for opponent strategy.

    Returns: raw expected payoff for br_player (NOT weighted by opp_reach).
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
            ev = _collect_br_values_nn(
                child, br_player, opp_reach, br_policy, agents, info_action_values,
            )
            info_action_values[info_key][i] += opp_reach * ev
            action_evs.append(ev)

        if info_key in br_policy:
            idx = br_policy[info_key]
            return action_evs[idx] if idx < len(action_evs) else max(action_evs)
        return max(action_evs)
    else:
        agent = agents[state.current_player]
        _, probs = agent.get_strategy(state)
        ev = 0.0
        for i, action in enumerate(actions):
            child = state.apply(action)
            child_ev = _collect_br_values_nn(
                child, br_player, opp_reach * probs[i], br_policy, agents, info_action_values,
            )
            ev += probs[i] * child_ev
        return ev


def _eval_br_policy_nn(
    state: LeducGameState,
    br_player: int,
    weight: float,
    br_policy: dict[str, int],
    agents: list[SDCFRAgent],
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
        return _eval_br_policy_nn(child, br_player, weight, br_policy, agents)
    else:
        agent = agents[state.current_player]
        _, probs = agent.get_strategy(state)
        ev = 0.0
        for i, action in enumerate(actions):
            child = state.apply(action)
            ev += _eval_br_policy_nn(child, br_player, weight * probs[i], br_policy, agents)
        return ev


# ---------- Arena: play two agents against each other ----------

def play_match(agent0: SDCFRAgent, agent1: SDCFRAgent, n_hands: int = 5000,
               is_leduc: bool = True, config: GameConfig | None = None) -> dict:
    """
    Play n_hands between two agents, alternating positions.
    Returns results dict with win rates and avg profit.
    """
    agents = [agent0, agent1]
    profits = [0.0, 0.0]

    for hand in range(n_hands):
        # Alternate who is P0 (OOP)
        swap = hand % 2 == 1
        p0_agent = agents[1 if swap else 0]
        p1_agent = agents[0 if swap else 1]

        if is_leduc:
            state = LeducGameState().deal_new_hand()
        else:
            state = HUNLGameState(config or GameConfig()).deal_new_hand()

        while not state.is_terminal():
            current_agent = p0_agent if state.current_player == 0 else p1_agent
            action = current_agent.choose_action(state)
            if action is None:
                break
            state = state.apply(action)

        if state.is_terminal():
            p0_profit = state.payoff(0)
            if swap:
                profits[1] += p0_profit
                profits[0] -= p0_profit
            else:
                profits[0] += p0_profit
                profits[1] -= p0_profit

    return {
        'n_hands': n_hands,
        'agent0_profit': profits[0],
        'agent1_profit': profits[1],
        'agent0_bb_per_hand': profits[0] / n_hands,
        'agent1_bb_per_hand': profits[1] / n_hands,
    }


# ---------- Load agent from checkpoint ----------

def load_agent(
    checkpoint_path: str,
    player: int = 0,
    device: str = 'cpu',
    mode: str = 'sample',
) -> SDCFRAgent:
    """Load an SD-CFR agent from a checkpoint file."""
    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    game = ckpt.get('game', 'leduc')
    is_leduc = game == 'leduc'

    if is_leduc:
        # Dynamically detect hidden layer count from checkpoint state_dict
        sample_sd = ckpt[f'strategy_buffer_{player}'][0][0]
        dims = []
        i = 0
        while f'trunk.{i}.weight' in sample_sd:
            dims.append(sample_sd[f'trunk.{i}.weight'].shape[0])
            i += 2  # skip ReLU layers (no parameters)
        net = LeducAdvantageNetwork(max_actions=4, hidden_dims=tuple(dims))
    else:
        net = AdvantageNetwork(max_actions=6)

    # Reconstruct strategy buffer
    sb = StrategyBuffer()
    sb.networks = list(ckpt[f'strategy_buffer_{player}'])

    return SDCFRAgent(
        strategy_buffer=sb,
        network_template=net,
        device=torch.device(device),
        mode=mode,
    )


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(description='SD-CFR Evaluation')
    parser.add_argument('--checkpoint', type=str, required=True)
    parser.add_argument('--game', type=str, default='leduc', choices=['leduc', 'hunl'])
    parser.add_argument('--mode', type=str, default='sample', choices=['sample', 'average', 'ensemble'])
    parser.add_argument('--exploitability', action='store_true', help='Compute exploitability (Leduc only)')
    # --exploit-samples kept for backwards compat but no longer used (exact enumeration)
    parser.add_argument('--device', type=str, default='cpu')

    args = parser.parse_args()

    print(f"Loading checkpoint: {args.checkpoint}")
    agent0 = load_agent(args.checkpoint, player=0, device=args.device, mode=args.mode)
    agent1 = load_agent(args.checkpoint, player=1, device=args.device, mode=args.mode)

    if args.exploitability and args.game == 'leduc':
        print("Computing exploitability (Leduc)...")
        # Use ensemble mode for correct SD-CFR average strategy
        agent0_ens = load_agent(args.checkpoint, player=0, device=args.device, mode='ensemble')
        agent1_ens = load_agent(args.checkpoint, player=1, device=args.device, mode='ensemble')
        exploit = compute_exploitability_leduc([agent0_ens, agent1_ens])
        print(f"Exploitability (ensemble): {exploit:.2f} mbb/g")
        # Also measure with average-weights mode for comparison
        agent0_avg = load_agent(args.checkpoint, player=0, device=args.device, mode='average')
        agent1_avg = load_agent(args.checkpoint, player=1, device=args.device, mode='average')
        exploit_avg = compute_exploitability_leduc([agent0_avg, agent1_avg])
        print(f"Exploitability (avg weights): {exploit_avg:.2f} mbb/g")

    # Self-play
    print(f"\nSelf-play ({args.game})...")
    results = play_match(agent0, agent1, n_hands=5000, is_leduc=(args.game == 'leduc'))
    print(f"P0 profit: {results['agent0_profit']:.2f} ({results['agent0_bb_per_hand']:+.4f} bb/hand)")
    print(f"P1 profit: {results['agent1_profit']:.2f} ({results['agent1_bb_per_hand']:+.4f} bb/hand)")


if __name__ == '__main__':
    main()
