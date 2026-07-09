"""T2: ckpt roundtrip sanity test.

Load V4 final → save with patched-trainer metadata → no training step.
Bench the result. If output != V4 baseline, save/load itself is the issue.
"""
import os
import sys
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

src = 'models/alpha_holdem_v4_final.pt'
dst = 'models/alpha_holdem_T2_roundtrip.pt'

print(f'Loading {src}...')
ckpt = torch.load(src, map_location='cpu', weights_only=False)
print(f'Keys: {list(ckpt.keys())}')
print(f'Model state_dict keys: {len(ckpt["model"])} entries')

# Re-save with the same metadata the patched trainer adds (so play_slumbot eval
# path is identical to vec_clean / mp3_patched / T4 benches).
out = {
    'model': ckpt['model'],
    'optimizer': ckpt.get('optimizer', {}),
    'total_hands': ckpt.get('total_hands', 0),
    'iteration': ckpt.get('iteration', 0),
    'pool_snapshots': ckpt.get('pool_snapshots', []),
    'env_version': 'v4',
    'obs_version': 'v4',
    'action_space_version': '9slot_v4',
    'starting_stack_bb': 200.0,
}
print(f'Saving to {dst}...')
torch.save(out, dst)

# Verify roundtrip preserves model weights exactly
ck2 = torch.load(dst, map_location='cpu', weights_only=False)
for k in ckpt['model']:
    a = ckpt['model'][k]
    b = ck2['model'][k]
    if not torch.equal(a, b):
        print(f'MISMATCH at {k}!')
        sys.exit(1)
print(f'Roundtrip OK: {len(ckpt["model"])} tensors identical')
print(f'Output: {dst}')
