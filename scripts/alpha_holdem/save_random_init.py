"""Save a fresh random-init GN model as a Path B ckpt for 0M baseline bench.

Uses the same network architecture and metadata schema as train_vec.py so
play_slumbot.py loads it identically to the 10M/50M ckpts.
"""
import os, sys, torch
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from alpha_holdem.network import AlphaHoldemNet

torch.manual_seed(42)
model = AlphaHoldemNet(num_actions=9, norm_layer='gn')
model.eval()
# Build trunk via lazy-init forward (B>=2 for any future BN compat)
model(torch.zeros(2, 6, 4, 13), torch.zeros(2, 25, 4, 5), torch.zeros(2, 2))

opt = torch.optim.Adam(model.parameters(), lr=1e-4)
out = {
    'model': model.state_dict(),
    'optimizer': opt.state_dict(),
    'total_hands': 0,
    'iteration': 0,
    'env_version': 'v4',
    'obs_version': 'v4',
    'action_space_version': '9slot_v4',
    'starting_stack_bb': 200.0,
    'trainer': 'random_init',
    'norm_layer': 'gn',
    'freeze_bn_stats': False,
    'seed': 42,
}
out_path = 'models/path_b_smoke_0M.pt'
torch.save(out, out_path)
print(f'Saved random-init GN ckpt → {out_path}')
n_params = sum(p.numel() for p in model.parameters())
print(f'Params: {n_params:,}  norm=gn  seed=42')
