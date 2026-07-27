"""Verification: ckpt metadata + weight distance for Path B 5M/10M/50M vs V4 family."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import torch
from alpha_holdem.network import AlphaHoldemNet, count_parameters


PATHS = {
    'path_b_5M':  'models/path_b_smoke_5M.pt',
    'path_b_10M': 'models/path_b_smoke_10M.pt',
    'path_b_50M': 'models/path_b_smoke_50M.pt',
}

## V4 family lives at repo root /models/, not scripts/alpha_holdem/models/
V4_CANDIDATES = [
    '../../models/alpha_holdem_v4_final.pt',
    '../../models/alpha_holdem_v4_rolling_987M.pt',
    '../../models/alpha_holdem_v4.pt',
    '../../models/alpha_holdem_v4_eval987M_floor03.pt',
]


def metadata(path):
    ck = torch.load(path, map_location='cpu', weights_only=False)
    info = {}
    for k in sorted(ck.keys()):
        if k == 'model':
            info['model_state_keys'] = len(ck['model'])
            info['bn_running_mean_keys'] = sum(1 for kk in ck['model'] if 'running_mean' in kk)
            info['gn_norm_only'] = info['bn_running_mean_keys'] == 0
        elif k == 'optimizer':
            try:
                info['optimizer_param_groups'] = len(ck['optimizer']['param_groups'])
                info['optimizer_state_entries'] = len(ck['optimizer']['state'])
                # First-param state keys to confirm Adam state exists
                if ck['optimizer']['state']:
                    first = next(iter(ck['optimizer']['state'].values()))
                    info['optimizer_first_state_keys'] = list(first.keys())
            except Exception as e:
                info['optimizer_err'] = str(e)
        elif k == 'pool_snapshots':
            info['pool_snapshots'] = f'list len={len(ck[k]) if isinstance(ck[k], list) else "?"}'
        else:
            v = ck[k]
            info[k] = repr(v) if not isinstance(v, (list, dict)) else f'{type(v).__name__} len={len(v)}'
    return ck, info


print('=' * 70)
print('CKPT METADATA')
print('=' * 70)
ckpts = {}
for name, path in PATHS.items():
    print(f'\n[{name}]  {path}')
    if not os.path.exists(path):
        print('  (file not found)')
        continue
    ck, info = metadata(path)
    ckpts[name] = ck
    for k, v in info.items():
        print(f'  {k}: {v}')


def state_dict_l2(sd_a, sd_b):
    """L2 distance between matching keys (excluding running stats)."""
    total = 0.0
    norm_a = 0.0
    norm_b = 0.0
    mismatch_keys = []
    matched = 0
    for k in sd_a:
        if k.endswith('.running_mean') or k.endswith('.running_var') or k.endswith('.num_batches_tracked'):
            continue
        if k not in sd_b:
            mismatch_keys.append(k)
            continue
        a = sd_a[k].float()
        b = sd_b[k].float()
        if a.shape != b.shape:
            mismatch_keys.append(f'{k}:shape{tuple(a.shape)}vs{tuple(b.shape)}')
            continue
        total += ((a - b) ** 2).sum().item()
        norm_a += (a ** 2).sum().item()
        norm_b += (b ** 2).sum().item()
        matched += 1
    return {
        'l2': total ** 0.5,
        'norm_a': norm_a ** 0.5,
        'norm_b': norm_b ** 0.5,
        'relative': (total ** 0.5) / max(norm_a ** 0.5, 1e-9),
        'matched_keys': matched,
        'mismatch': mismatch_keys[:5],
    }


# Generate a fresh random-init model with the same seed pattern to compare
print()
print('=' * 70)
print('WEIGHT DISTANCES (path_b state_dicts)')
print('=' * 70)

# Materialize a fresh GN model (random init)
torch.manual_seed(42)
fresh = AlphaHoldemNet(num_actions=9, norm_layer='gn')
fresh.eval()
fresh(torch.zeros(2, 6, 4, 13), torch.zeros(2, 25, 4, 5), torch.zeros(2, 2))
fresh_sd = fresh.state_dict()
print(f'\nFresh GN model (random init, seed=42): {count_parameters(fresh):,} params')

for name in PATHS:
    if name not in ckpts:
        continue
    print(f'\n  Fresh vs {name}:')
    d = state_dict_l2(fresh_sd, ckpts[name]['model'])
    for k, v in d.items():
        print(f'    {k}: {v}')

# Pairwise distances among Path B
print()
print('Pairwise Path B:')
names = list(ckpts.keys())
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        a, b = names[i], names[j]
        d = state_dict_l2(ckpts[a]['model'], ckpts[b]['model'])
        print(f'  {a} vs {b}: l2={d["l2"]:.2f}  rel={d["relative"]:.4f}  matched={d["matched_keys"]}')

# Check V4 candidates
print()
print('=' * 70)
print('V4 FAMILY COMPARISON (if available)')
print('=' * 70)
found_v4 = False
for v4_path in V4_CANDIDATES:
    if not os.path.exists(v4_path):
        continue
    found_v4 = True
    print(f'\n[{v4_path}]')
    v4_ck = torch.load(v4_path, map_location='cpu', weights_only=False)
    v4_sd = v4_ck['model']
    # V4 ckpt metadata
    print(f'  V4 ckpt top-level keys: {sorted(v4_ck.keys())}')
    if 'total_hands' in v4_ck:
        print(f'  V4 total_hands: {v4_ck["total_hands"]:,}')
    if 'iteration' in v4_ck:
        print(f'  V4 iteration: {v4_ck["iteration"]}')
    if 'pool_snapshots' in v4_ck:
        ps = v4_ck['pool_snapshots']
        print(f'  V4 pool_snapshots: list len={len(ps) if isinstance(ps, list) else "?"}')
    # First, identify V4 norm type
    v4_bn = sum(1 for k in v4_sd if 'running_mean' in k)
    print(f'  V4 bn_running_mean keys: {v4_bn}  (V4 is BN, path_b is GN — keys differ)')
    print(f'  V4 keys total: {len(v4_sd)}')
    # Build a BN model to load V4 then compare CONV WEIGHTS only (shared between BN/GN)
    v4_norm = v4_ck.get('norm_layer', 'bn')
    v4_model = AlphaHoldemNet(num_actions=9, norm_layer=v4_norm)
    v4_model.eval()
    v4_model(torch.zeros(2, 6, 4, 13), torch.zeros(2, 25, 4, 5), torch.zeros(2, 2))
    v4_model.load_state_dict(v4_sd)
    v4_sd_loaded = v4_model.state_dict()
    # Compare only weight keys that exist in BOTH BN and GN (conv weights, linear weights/biases)
    conv_linear_keys = [k for k in v4_sd_loaded if ('conv' in k or 'linear' in k or 'fc' in k or 'head' in k or 'trunk' in k)
                        and (k.endswith('.weight') or k.endswith('.bias'))]
    for name in ['path_b_10M', 'path_b_50M']:
        if name not in ckpts:
            continue
        pb_sd = ckpts[name]['model']
        # Distance restricted to keys present in BOTH
        common = [k for k in conv_linear_keys if k in pb_sd and v4_sd_loaded[k].shape == pb_sd[k].shape]
        if not common:
            print(f'    {name}: no common conv/linear keys with V4 (architecture mismatch?)')
            continue
        total = 0.0
        norm_v4 = 0.0
        norm_pb = 0.0
        for k in common:
            a = v4_sd_loaded[k].float()
            b = pb_sd[k].float()
            total += ((a - b) ** 2).sum().item()
            norm_v4 += (a ** 2).sum().item()
            norm_pb += (b ** 2).sum().item()
        l2 = total ** 0.5
        rel = l2 / max(norm_v4 ** 0.5, 1e-9)
        print(f'    {name} vs V4 (conv+linear only, n={len(common)} keys):')
        print(f'      l2={l2:.2f}  |V4|={norm_v4**0.5:.2f}  |pathB|={norm_pb**0.5:.2f}  rel={rel:.4f}')
    break
else:
    print('  No V4 ckpt found locally; weight-distance vs V4 SKIPPED.')
