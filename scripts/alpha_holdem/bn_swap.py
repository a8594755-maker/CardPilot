"""BN swap surgery (Test 2 from round 4 review).

Hypothesis: T5 went from V4 -65 to -116 not because PPO weights drifted,
but because BatchNorm running_mean/running_var stats drifted across the
122 PPO updates while in model.train() mode. Slumbot bench runs eval mode
which uses those drifted stats.

Procedure:
  A. V4 weights + T5 BN buffers → bench. If bad → BN drift is the killer.
  B. T5 weights + V4 BN buffers → bench. If good → weights are fine, BN was the killer.

BN buffers in state_dict have keys ending in:
  running_mean
  running_var
  num_batches_tracked
"""
import os
import sys
import torch

V4_PATH = 'models/alpha_holdem_v4_final.pt'
T5_PATH = 'models/alpha_holdem_T5_conservative.pt'
OUT_A = 'models/alpha_holdem_TBNa_V4w_T5bn.pt'   # V4 weights + T5 BN
OUT_B = 'models/alpha_holdem_TBNb_T5w_V4bn.pt'   # T5 weights + V4 BN


def is_bn_buffer(key: str) -> bool:
    return (key.endswith('.running_mean')
            or key.endswith('.running_var')
            or key.endswith('.num_batches_tracked'))


def load(path):
    return torch.load(path, map_location='cpu', weights_only=False)


def show_bn_diff(a, b, label):
    diffs = []
    for k in a['model']:
        if not is_bn_buffer(k):
            continue
        ta = a['model'][k]
        tb = b['model'][k]
        if ta.shape != tb.shape:
            diffs.append(f'  {k}: shape mismatch {ta.shape} vs {tb.shape}')
            continue
        d = (ta - tb).abs().max().item()
        diffs.append(f'  {k}: max_abs_diff = {d:.6f}')
    print(f'BN buffer diffs ({label}):')
    for d in diffs:
        print(d)


def main():
    print(f'Loading {V4_PATH}...')
    v4 = load(V4_PATH)
    print(f'Loading {T5_PATH}...')
    t5 = load(T5_PATH)

    # Sanity: same key set?
    v4_keys = set(v4['model'].keys())
    t5_keys = set(t5['model'].keys())
    assert v4_keys == t5_keys, f'Key mismatch: only-V4 {v4_keys - t5_keys}, only-T5 {t5_keys - v4_keys}'
    bn_keys = [k for k in v4_keys if is_bn_buffer(k)]
    print(f'BN buffer keys ({len(bn_keys)}):')
    for k in bn_keys:
        print(f'  {k}')

    # Diff magnitudes
    show_bn_diff(v4, t5, 'V4 vs T5')

    # Build A: V4 weights + T5 BN
    model_a = dict(v4['model'])
    for k in bn_keys:
        model_a[k] = t5['model'][k].clone()

    out_a = {
        'model': model_a,
        'optimizer': v4.get('optimizer', {}),
        'total_hands': v4.get('total_hands', 0),
        'iteration': v4.get('iteration', 0),
        'pool_snapshots': v4.get('pool_snapshots', []),
        'env_version': 'v4',
        'obs_version': 'v4',
        'action_space_version': '9slot_v4',
        'starting_stack_bb': 200.0,
        'note': 'BN_SWAP_A: V4 non-BN weights + T5 BN running stats',
    }
    torch.save(out_a, OUT_A)
    print(f'Wrote {OUT_A}')

    # Build B: T5 weights + V4 BN
    model_b = dict(t5['model'])
    for k in bn_keys:
        model_b[k] = v4['model'][k].clone()

    out_b = {
        'model': model_b,
        'optimizer': t5.get('optimizer', {}),
        'total_hands': t5.get('total_hands', 0),
        'iteration': t5.get('iteration', 0),
        'pool_snapshots': t5.get('pool_snapshots', []),
        'env_version': 'v4',
        'obs_version': 'v4',
        'action_space_version': '9slot_v4',
        'starting_stack_bb': 200.0,
        'note': 'BN_SWAP_B: T5 non-BN weights + V4 BN running stats',
    }
    torch.save(out_b, OUT_B)
    print(f'Wrote {OUT_B}')


if __name__ == '__main__':
    main()
