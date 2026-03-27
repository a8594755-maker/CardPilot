"""
Experiment: SD-CFR with lookup table instead of neural network.

Key findings:
- Current strategy oscillates (normal for CFR)
- AVERAGE strategy converges to Nash
- Must record strategy BEFORE regret update (what was actually played)

This confirms the neural net SD-CFR problem is in the StrategyBuffer/ensemble mechanism.
"""
import random
import time
from collections import defaultdict

import numpy as np

from scripts.deep_cfr.game_state import LeducGameState
from scripts.deep_cfr.eval_agent import compute_exploitability_leduc


# ---------- Regret matching ----------

def regret_match(advantages: np.ndarray, legal_mask: np.ndarray) -> np.ndarray:
    positive = np.maximum(advantages, 0) * legal_mask
    total = positive.sum()
    if total > 0:
        return positive / total
    masked = np.where(legal_mask > 0, advantages, -np.inf)
    best = np.argmax(masked)
    result = np.zeros_like(advantages)
    result[best] = 1.0
    return result


def legal_mask_for_state(state: LeducGameState, max_actions: int = 4) -> np.ndarray:
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


ACTION_SLOT_MAP = {'fold': 0, 'check': 1, 'call': 1, 'bet': 2, 'raise': 3}
MAX_ACTIONS = 4


# ---------- Tables ----------

class CumulativeRegretTable:
    def __init__(self):
        self.cumulative: dict[str, np.ndarray] = defaultdict(
            lambda: np.zeros(MAX_ACTIONS, dtype=np.float64)
        )

    def add(self, info_key: str, inst_regret: np.ndarray, weight: float = 1.0):
        self.cumulative[info_key] += weight * inst_regret.astype(np.float64)

    def get_strategy(self, info_key: str, legal_mask: np.ndarray) -> np.ndarray:
        advantages = self.cumulative[info_key].astype(np.float32)
        return regret_match(advantages, legal_mask)


class AverageStrategyTable:
    def __init__(self):
        self.weighted_sum: dict[str, np.ndarray] = defaultdict(
            lambda: np.zeros(MAX_ACTIONS, dtype=np.float64)
        )
        self.weight_total: dict[str, float] = defaultdict(float)

    def add(self, info_key: str, strategy: np.ndarray, weight: float):
        self.weighted_sum[info_key] += weight * strategy.astype(np.float64)
        self.weight_total[info_key] += weight

    def get_strategy(self, info_key: str, legal_mask: np.ndarray) -> np.ndarray:
        if info_key not in self.weighted_sum or self.weight_total[info_key] == 0:
            n = legal_mask.sum()
            return (legal_mask / max(n, 1)).astype(np.float32)
        avg = (self.weighted_sum[info_key] / self.weight_total[info_key]).astype(np.float32)
        total = (avg * legal_mask).sum()
        if total > 0:
            return (avg * legal_mask / total).astype(np.float32)
        n = legal_mask.sum()
        return (legal_mask / max(n, 1)).astype(np.float32)


# ---------- Traversal ----------

def traverse(state, traverser, regret_tables, samples_out):
    if state.is_terminal():
        return state.payoff(traverser)
    actions = state.legal_actions()
    if not actions:
        return 0.0

    info_key = state.to_info_key()
    legal_mask = legal_mask_for_state(state)
    strategy = regret_tables[state.current_player].get_strategy(info_key, legal_mask)
    action_slots = [ACTION_SLOT_MAP[a] for a in actions]

    if state.current_player == traverser:
        values = np.zeros(MAX_ACTIONS, dtype=np.float32)
        for i, action in enumerate(actions):
            child = state.apply(action)
            values[action_slots[i]] = traverse(child, traverser, regret_tables, samples_out)
        ev = np.sum(strategy * values)
        inst_regret = (values - ev) * legal_mask
        samples_out.append((info_key, inst_regret, legal_mask, strategy.copy()))
        return ev
    else:
        slot_probs = np.array([strategy[action_slots[i]] for i in range(len(actions))])
        slot_probs = slot_probs / max(slot_probs.sum(), 1e-8)
        action_idx = np.random.choice(len(actions), p=slot_probs)
        child = state.apply(actions[action_idx])
        return traverse(child, traverser, regret_tables, samples_out)


# ---------- Agent wrappers ----------

class StrategyAgent:
    def __init__(self, table, method='get_strategy'):
        self.table = table
        self._method = method
    def get_strategy(self, state):
        actions = state.legal_actions()
        if not actions:
            return [], np.array([])
        info_key = state.to_info_key()
        legal_mask = legal_mask_for_state(state)
        strategy = self.table.get_strategy(info_key, legal_mask)
        action_probs = np.array([strategy[ACTION_SLOT_MAP[a]] for a in actions])
        total = action_probs.sum()
        if total > 0:
            action_probs /= total
        else:
            action_probs = np.ones(len(actions)) / len(actions)
        return actions, action_probs.astype(np.float32)


# ---------- Main ----------

ITERS = 300
TRAVERSALS = 5000

print(f"Tabular SD-CFR: {ITERS} iters, {TRAVERSALS} trav/iter", flush=True)
print(f"Records strategy BEFORE regret update (what was actually played).\n", flush=True)

regret_tables = [CumulativeRegretTable(), CumulativeRegretTable()]
avg_tables = [AverageStrategyTable(), AverageStrategyTable()]

t_start = time.time()

for t in range(ITERS):
    weight = t + 1  # Linear CFR weighting

    for p in range(2):
        # 1. Record the current strategy for all known info sets BEFORE traversal
        #    (this is the strategy that will be used during traversal)
        for info_key in list(regret_tables[p].cumulative.keys()):
            legal_mask_cached = np.ones(MAX_ACTIONS, dtype=np.float32)  # placeholder
            # We need the actual legal mask — we'll collect it during traversal instead
            pass

        # 2. Traverse and collect samples
        samples: list = []
        for _ in range(TRAVERSALS):
            state = LeducGameState().deal_new_hand()
            traverse(state, p, regret_tables, samples)

        # 3. Record the strategy USED during traversal (before regret update)
        #    Each info_key's strategy was computed from regret_tables BEFORE this update
        visited = set()
        for info_key, _, legal_mask, strategy_used in samples:
            if info_key not in visited:
                visited.add(info_key)
                avg_tables[p].add(info_key, strategy_used, weight)

        # 4. Update cumulative regrets
        for info_key, inst_regret, _, _ in samples:
            regret_tables[p].add(info_key, inst_regret, weight)

    if (t + 1) % 10 == 0:
        elapsed = time.time() - t_start

        a0_cur = StrategyAgent(regret_tables[0])
        a1_cur = StrategyAgent(regret_tables[1])
        exploit_cur = compute_exploitability_leduc([a0_cur, a1_cur])

        a0_avg = StrategyAgent(avg_tables[0])
        a1_avg = StrategyAgent(avg_tables[1])
        exploit_avg = compute_exploitability_leduc([a0_avg, a1_avg])

        print(
            f"  Iter {t+1:4d}: "
            f"current={exploit_cur:8.1f} | "
            f"average={exploit_avg:8.1f} mbb/g | "
            f"elapsed={elapsed:.0f}s",
            flush=True,
        )

print("\nDone!", flush=True)
