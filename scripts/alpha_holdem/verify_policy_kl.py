"""Behavioral verification: pairwise KL divergence between path_b 0M/10M/50M and V4.

Parameter-space L2 is meaningless across BN/GN architectures — same effective
policy can be parametrized differently. Instead, run all candidate models on the
SAME batch of states and compare the policy distributions directly.

Generates 1024 states from a vec game state under random play, then forwards
each model in eval mode (no_grad) and compares output policy distributions.

For each pair:
  - mean per-state KL(P || Q) on the legal-masked policy
  - greedy argmax disagreement rate
  - L1 distance between policies
"""
import os, sys, torch, torch.nn.functional as F
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from alpha_holdem.network import AlphaHoldemNet
from vec_game_state import VecHUNLState
from train_vec import encode_obs_batched


CKPTS = {
    '0M_random':  'models/path_b_smoke_0M.pt',
    '10M':        'models/path_b_smoke_10M.pt',
    '50M':        'models/path_b_smoke_50M.pt',
    'V4_final':   '../../models/alpha_holdem_v4_final.pt',
}


def load_model(path, device='cpu'):
    ck = torch.load(path, map_location=device, weights_only=False)
    norm = ck.get('norm_layer', 'bn')
    m = AlphaHoldemNet(num_actions=9, norm_layer=norm).to(device)
    m.eval()
    m(torch.zeros(2, 6, 4, 13, device=device),
      torch.zeros(2, 25, 4, 5, device=device),
      torch.zeros(2, 2, device=device))
    m.load_state_dict(ck['model'])
    m.eval()
    return m, norm, ck.get('total_hands', '?')


def collect_states(N=1024, n_steps=8, seed=137):
    """Roll N parallel games forward n_steps random actions; return one batch
    of encoded observations from the current player perspective at the end."""
    state = VecHUNLState(N=N, effective_stack=200.0, seed=seed)
    state.reset_all()
    rng = np.random.default_rng(seed)
    for _ in range(n_steps):
        mask = state.legal_mask()
        # Random legal action per game
        rand_logits = rng.random(mask.shape).astype(np.float32)
        masked = np.where(mask > 0.5, rand_logits, -1e9)
        action = masked.argmax(axis=-1).astype(np.int64)
        state.step(action)
        # Reset terminated rows so we keep N parallel
        if state.is_done.any():
            state.reset_done()
    card_np, action_np, extra_np, mask_np = encode_obs_batched(state)
    return (torch.from_numpy(card_np),
            torch.from_numpy(action_np),
            torch.from_numpy(extra_np),
            torch.from_numpy(mask_np))


@torch.no_grad()
def policy(model, cards, actions, extras, masks):
    logits, _ = model(cards, actions, extras, masks)
    probs = F.softmax(logits, dim=-1)
    # Mask out illegal actions (logits already +(1-mask)*-1e9 inside forward, but renormalize)
    probs = probs * masks
    probs = probs / probs.sum(dim=-1, keepdim=True).clamp_min(1e-12)
    return probs.clamp_min(1e-12)


def kl(p, q):
    """KL(P || Q) per-row, then mean."""
    return (p * (p.log() - q.log())).sum(dim=-1).mean().item()


def l1(p, q):
    return (p - q).abs().sum(dim=-1).mean().item() * 0.5  # total variation


def main():
    device = 'cpu'
    print('Loading models...')
    models = {}
    for name, path in CKPTS.items():
        if not os.path.exists(path):
            print(f'  [skip] {name}: {path} not found')
            continue
        m, norm, hands = load_model(path, device=device)
        models[name] = m
        print(f'  loaded {name}: norm={norm}, hands={hands}')

    print(f'\nGenerating 1024 states from random rollout...')
    cards, actions, extras, masks = collect_states(N=1024, n_steps=10)
    print(f'  cards={tuple(cards.shape)} actions={tuple(actions.shape)} '
          f'extras={tuple(extras.shape)} masks={tuple(masks.shape)}')
    legal_counts = masks.sum(dim=-1)
    print(f'  legal-action counts: mean={legal_counts.mean():.2f} '
          f'min={legal_counts.min():.0f} max={legal_counts.max():.0f}')

    print(f'\nForward each model...')
    policies = {}
    argmaxs = {}
    for name, m in models.items():
        p = policy(m, cards, actions, extras, masks)
        policies[name] = p
        argmaxs[name] = p.argmax(dim=-1)
        print(f'  {name}: policy entropy = {-(p * p.log()).sum(dim=-1).mean().item():.3f}')

    names = list(models.keys())
    print(f'\nPairwise behavioral KL / L1 / argmax-disagree:')
    print(f'  {"pair":<28s}  {"KL(P||Q)":>10s}  {"KL(Q||P)":>10s}  {"L1/2":>8s}  {"argmax!=":>8s}')
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            kl_ab = kl(policies[a], policies[b])
            kl_ba = kl(policies[b], policies[a])
            tv = l1(policies[a], policies[b])
            disagree = (argmaxs[a] != argmaxs[b]).float().mean().item()
            pair = f'{a} vs {b}'
            print(f'  {pair:<28s}  {kl_ab:>10.4f}  {kl_ba:>10.4f}  {tv:>8.4f}  {disagree:>8.3f}')

    # Per-action-slot mean prob comparison (action histograms across all 1024 states)
    print(f'\nPer-slot mean probability (action distribution per model):')
    print(f'  {"model":<12s}  ' + '  '.join(f'  slot{i}' for i in range(9)))
    for name, p in policies.items():
        slot_means = p.mean(dim=0).tolist()
        print(f'  {name:<12s}  ' + '  '.join(f'{x:>6.3f}' for x in slot_means))

    # Action histogram for the actually-most-likely action
    print(f'\nGreedy action distribution per model:')
    for name, am in argmaxs.items():
        counts = torch.bincount(am, minlength=9).float()
        freqs = (counts / counts.sum()).tolist()
        print(f'  {name:<12s}  ' + '  '.join(f'{x:>6.3f}' for x in freqs))


if __name__ == '__main__':
    main()
