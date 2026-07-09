"""Wrappers that expose a frozen AlphaHoldemNet checkpoint as a policy callable.

Used for:
  - Frozen BC anchor (the SL teacher snapshot)
  - Path B 10M / 50M
  - V4 final
  - Future SL/RL snapshots

Eval mode, no optimizer, no gradient. Inference is one row at a time when
called from internal_bench's per-game dispatch — slow but correct. For
real Day 1+ population PPO, batched inference is done in train_population_ppo.
This wrapper is for the eval-suite path.

API matches scripted_policies.get_policy() callables:
  fn(hole, board, state, client_pos, legal_mask) -> int

Card / action / extra encoders mirror train_vec.encode_obs_batched for ONE row.

Usage:
  from frozen_anchor import load_frozen_anchor_callable
  pathb_fn = load_frozen_anchor_callable('scripts/alpha_holdem/models/path_b_smoke_10M.pt')
  slot = pathb_fn(hole, board, state, client_pos, legal_mask)
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
sys.path.insert(0, str(REPO_ROOT / 'scripts' / 'alpha_holdem'))

from alpha_holdem.network import AlphaHoldemNet

NUM_ACTIONS = 9
NUM_SUITS = 4
NUM_RANKS = 13
NUM_CARD_CHANNELS = 6
MAX_ACTIONS_PER_STREET = 6
NUM_STREETS = 4
ACTION_HISTORY_CHANNELS = MAX_ACTIONS_PER_STREET * NUM_STREETS + 1  # 25


_RANK_IDX = {r: i for i, r in enumerate('23456789TJQKA')}
_SUIT_IDX = {s: i for i, s in enumerate('shdc')}


def _card_str_to_idx(c: str) -> tuple[int, int]:
    """Returns (rank_idx, suit_idx) for a card string like 'As'."""
    return _RANK_IDX[c[0]], _SUIT_IDX[c[1]]


def encode_single_state(hole, board, state, client_pos, legal_mask) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build (card_t, action_t, extra_t, mask_t) for ONE game state.

    Approximation note: action_history is reconstructed minimally from state info
    (we don't have full hand history available here). The frozen model was
    trained on full encoding — at inference time, an empty action_history is
    a degraded but reasonable approximation that still gives meaningful logits
    from the card branch. Day 1+ should plumb proper action history.
    """
    card_t = np.zeros((NUM_CARD_CHANNELS, NUM_SUITS, NUM_RANKS), dtype=np.float32)
    # Hero hole → channel 0 + channel 5
    for c in hole:
        if not c:
            continue
        r, s = _card_str_to_idx(c)
        card_t[0, s, r] = 1.0
        card_t[5, s, r] = 1.0
    # Board: channels 1=flop, 2=turn, 3=river, 4=all public, 5=all visible
    for i, c in enumerate(board or []):
        if not c:
            continue
        r, s = _card_str_to_idx(c)
        if i < 3:
            card_t[1, s, r] = 1.0
        elif i == 3:
            card_t[2, s, r] = 1.0
        elif i == 4:
            card_t[3, s, r] = 1.0
        card_t[4, s, r] = 1.0
        card_t[5, s, r] = 1.0

    # Action history (minimal placeholder — current player indicator only)
    action_t = np.zeros((ACTION_HISTORY_CHANNELS, NUM_STREETS, 5), dtype=np.float32)
    action_t[24, 0, 0] = 1.0  # current player flag

    # Extra: normalized stacks (approximation; full stack tracking needs proper state)
    extra_t = np.zeros(2, dtype=np.float32)
    stack_norm = state.get('stack_remaining', 19000) / 20000.0
    extra_t[0] = stack_norm  # current player's stack
    extra_t[1] = stack_norm  # opp's (approximate as same — not great, but functional)

    mask_t = np.array(legal_mask, dtype=np.float32)
    return card_t, action_t, extra_t, mask_t


def load_frozen_anchor_callable(ckpt_path: str, device: str = 'cpu',
                                 *, greedy: bool = True, seed: int = 0):
    """Load any AlphaHoldemNet checkpoint as a frozen policy callable.

    Returns fn(hole, board, state, client_pos, legal_mask) -> int.
    """
    ckpt_path = str(ckpt_path)
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    norm = ck.get('norm_layer', 'bn')
    model = AlphaHoldemNet(num_actions=NUM_ACTIONS, norm_layer=norm).to(device)
    model.eval()
    # Lazy trunk init
    model(torch.zeros(2, NUM_CARD_CHANNELS, NUM_SUITS, NUM_RANKS, device=device),
          torch.zeros(2, ACTION_HISTORY_CHANNELS, NUM_STREETS, 5, device=device),
          torch.zeros(2, 2, device=device))
    model.load_state_dict(ck['model'])
    model.eval()
    for p in model.parameters():
        p.requires_grad_(False)
    rng = np.random.default_rng(seed)

    def anchor_policy(hole, board, state, client_pos, legal_mask) -> int:
        card_t, action_t, extra_t, mask_t = encode_single_state(
            hole, board, state, client_pos, legal_mask)
        c = torch.from_numpy(card_t).unsqueeze(0).to(device)
        a = torch.from_numpy(action_t).unsqueeze(0).to(device)
        e = torch.from_numpy(extra_t).unsqueeze(0).to(device)
        m = torch.from_numpy(mask_t).unsqueeze(0).to(device)
        with torch.no_grad():
            logits, _ = model(c, a, e, m)
        if greedy:
            slot = int(logits.argmax(-1).item())
        else:
            probs = F.softmax(logits, dim=-1)[0].cpu().numpy()
            slot = int(rng.choice(NUM_ACTIONS, p=probs))
        # Safety: enforce legal mask
        if not legal_mask[slot]:
            for s in range(NUM_ACTIONS):
                if legal_mask[s]:
                    return s
            return 0
        return slot

    return anchor_policy
