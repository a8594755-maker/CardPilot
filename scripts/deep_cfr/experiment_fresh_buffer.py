"""Quick experiment: SD-CFR with fresh buffer each iteration (no historical contamination)."""
import torch
from scripts.deep_cfr.game_state import LeducGameState
from scripts.deep_cfr.networks import LeducAdvantageNetwork, StrategyBuffer
from scripts.deep_cfr.reservoir import ReservoirBuffer
from scripts.deep_cfr.train import traverse_leduc, train_advantage_net
from scripts.deep_cfr.eval_agent import compute_exploitability_leduc, SDCFRAgent

device = torch.device('cuda')
max_actions = 4
ITERS = 100
TRAVERSALS = 10000
TRAIN_STEPS = 4000
BATCH = 2048
LR = 0.001

nets = [LeducAdvantageNetwork(max_actions=max_actions).to(device) for _ in range(2)]
strategy_buffers = [StrategyBuffer(), StrategyBuffer()]

import sys
# Force unbuffered output
print(f'Fresh-buffer SD-CFR: {ITERS} iters, {TRAVERSALS} trav, {TRAIN_STEPS} steps, batch {BATCH}', flush=True)

for t in range(ITERS):
    for p in range(2):
        # FRESH BUFFER each iteration
        buf = ReservoirBuffer(max_size=2_000_000)
        for _ in range(TRAVERSALS):
            state = LeducGameState().deal_new_hand()
            traverse_leduc(state, p, nets, buf, t, device, max_actions)

        actual_steps = min(TRAIN_STEPS, len(buf) // max(BATCH // 4, 1))
        actual_steps = max(actual_steps, 100)
        loss = train_advantage_net(
            nets[p], buf, device, max_iteration=t + 1,
            steps=actual_steps, batch_size=BATCH, lr=LR,
        )
        strategy_buffers[p].add(nets[p], t)

    if (t + 1) % 25 == 0:
        sb0, sb1 = StrategyBuffer(), StrategyBuffer()
        sb0.networks = list(strategy_buffers[0].networks)
        sb1.networks = list(strategy_buffers[1].networks)
        a0 = SDCFRAgent(sb0, LeducAdvantageNetwork(max_actions=4), torch.device('cpu'), mode='ensemble')
        a1 = SDCFRAgent(sb1, LeducAdvantageNetwork(max_actions=4), torch.device('cpu'), mode='ensemble')
        exploit = compute_exploitability_leduc([a0, a1])
        print(f'  Iter {t+1}: exploit={exploit:.1f} mbb/g, loss={loss:.4f}, buf={len(buf)}', flush=True)

print('Done!')
