"""Wrapper that exposes a trained Slumbot proxy as a policy callable.

CRITICAL CONTRACT: the proxy sees PUBLIC STATE ONLY. Hero hole cards are NEVER
passed to the proxy. This wrapper enforces that — the `hole` arg from the
policy_callable interface is accepted (for API compatibility) but explicitly
unused.

API matches scripted_policies.get_policy() callables:
  fn(hole_cards, board, state, client_pos, legal_mask) -> int (slot 0..8)

Usage:
  from proxy_callable import load_proxy_callable
  proxy_fn = load_proxy_callable('models/proxy/slumbot_smoke/best.pt', device='cuda')
  slot = proxy_fn(hero_hole_IGNORED, board, state, client_pos, legal_mask)
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))
from train_slumbot_proxy import ProxyMLP, FEAT_DIM, slot_to_family_size
# v2 architecture (board-aware) — newer trained proxies use this
from train_slumbot_proxy_v2 import (
    ProxyV2, SCALAR_DIM as V2_SCALAR_DIM, BOARD_SLOTS as V2_BOARD_SLOTS,
    encode_scalar_features as v2_encode_scalar,
    encode_board as v2_encode_board,
)


# Inverse map: (family, size_bucket) -> slot
# size_bucket 0=small, 1=medium, 2=large, 3=jam
SIZE_TO_SLOT = {0: 3, 1: 5, 2: 7, 3: 8}  # see train_slumbot_proxy.slot_to_family_size


def public_state_features(board: list, state: dict, client_pos: int,
                          legal_mask) -> np.ndarray:
    """Build the 16-dim feature vector used at proxy training time.

    Inputs come from vec_game_state internals (street, to_call, pot_before, etc.)
    plus public board. NO hero hole cards used.

    NOTE: action_str_before features (n_bets/calls/checks) are unavailable at
    this call site; we approximate from state.to_call (presence implies a bet).
    Day 1+ should plumb action history into the state dict.
    """
    street = state.get('st', 0)
    mover_pos = client_pos                  # 0=BB, 1=SB (Slumbot convention)
    pot_before = state.get('pot_before', 0)
    to_call = state.get('to_call', 0)
    stack = state.get('stack_remaining', 19000)  # default ~200bb
    last_bet = state.get('last_bet_size', to_call)
    street_last_bet_to = state.get('street_last_bet_to', to_call)
    total_last_bet_to = state.get('total_last_bet_to', to_call)
    n_board = len(board) if board else 0
    n_bets = 1 if to_call > 0 else 0  # approximation
    n_calls = 0
    n_checks = 0

    feats = np.array([
        street,
        mover_pos,
        pot_before / 1000.0,
        to_call / 1000.0,
        stack / 20000.0,
        last_bet / 1000.0,
        street_last_bet_to / 1000.0,
        total_last_bet_to / 1000.0,
        n_board,
        n_bets, n_calls, n_checks,
        1.0 if to_call > 0 else 0.0,
        np.log1p(pot_before) / 8.0,
        np.log1p(to_call) / 8.0,
        np.log1p(stack) / 10.0,
    ], dtype=np.float32)
    assert feats.shape[0] == FEAT_DIM, f'feature dim mismatch: {feats.shape[0]} vs {FEAT_DIM}'
    return feats


def load_proxy_callable(ckpt_path: str, device: str = 'cpu', *, greedy: bool = True,
                        seed: int = 0):
    """Load a trained proxy NN and return a policy callable.

    Auto-detects v1 (ProxyMLP, scalars only) vs v2 (ProxyV2, board-aware) via the
    `arch` key in the checkpoint. v1 falls back to feature builder; v2 uses the
    v2 scalar+board encoders.

    Returns a function with signature:
        fn(hole, board, state, client_pos, legal_mask) -> int

    The `hole` parameter is accepted for interface compatibility but ignored —
    the proxy must not see hero hole cards.
    """
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    arch = ck.get('arch', 'proxy_v1_scalar')
    hidden = ck.get('hidden', 256)
    layers = ck.get('layers', 4)

    if arch == 'proxy_v2_board_embed':
        model = ProxyV2(scalar_dim=V2_SCALAR_DIM, hidden=hidden, layers=layers).to(device)
    else:
        model = ProxyMLP(feat_dim=FEAT_DIM, hidden=hidden, layers=layers).to(device)
    model.load_state_dict(ck['model'])
    model.eval()
    for p in model.parameters():
        p.requires_grad_(False)
    rng = np.random.default_rng(seed)
    is_v2 = (arch == 'proxy_v2_board_embed')

    def proxy_policy(hole, board, state, client_pos, legal_mask) -> int:
        # NOTE: `hole` parameter is intentionally ignored.
        _ = hole  # explicit silence
        if is_v2:
            # v2 builder. State dict needs the fields the dump record provides
            # — build a synthetic record from the runtime call args.
            rec = {
                'street': state.get('st', 0),
                'mover_pos': client_pos,
                'pot_before': state.get('pot_before', 0),
                'to_call': state.get('to_call', 0),
                'stack_remaining': state.get('stack_remaining', 19000),
                'last_bet_size': state.get('last_bet_size', state.get('to_call', 0)),
                'street_last_bet_to': state.get('street_last_bet_to', state.get('to_call', 0)),
                'total_last_bet_to': state.get('total_last_bet_to', state.get('to_call', 0)),
                'public_board': board or [],
                'action_str_before': state.get('action_str_before', ''),
            }
            scalars = v2_encode_scalar(rec)
            boards_np = v2_encode_board(rec['public_board'])
            x_scalars = torch.from_numpy(scalars).unsqueeze(0).to(device)
            x_boards = torch.from_numpy(boards_np).unsqueeze(0).to(device)
            with torch.no_grad():
                fam_logits, sz_logits = model(x_scalars, x_boards)
        else:
            feats = public_state_features(board, state, client_pos, legal_mask)
            x = torch.from_numpy(feats).unsqueeze(0).to(device)
            with torch.no_grad():
                fam_logits, sz_logits = model(x)
        if greedy:
            fam = int(fam_logits.argmax(-1).item())
        else:
            fam_p = F.softmax(fam_logits, dim=-1)[0].cpu().numpy()
            fam = int(rng.choice(3, p=fam_p))

        # Map family + (size if raise) -> slot, then filter by legal_mask
        if fam == 0:
            chosen = 0  # fold
        elif fam == 1:
            chosen = 1  # check/call
        else:
            if greedy:
                sz = int(sz_logits.argmax(-1).item())
            else:
                sz_p = F.softmax(sz_logits, dim=-1)[0].cpu().numpy()
                sz = int(rng.choice(4, p=sz_p))
            chosen = SIZE_TO_SLOT[sz]

        # Enforce legal mask: if chosen is illegal, fallback to nearest legal action
        if legal_mask[chosen]:
            return chosen
        # Fallback ordering: try call/check (1), then fold (0), then any other legal slot
        for s in (1, 0, 7, 5, 3, 8, 6, 4, 2):
            if legal_mask[s]:
                return s
        return 0

    return proxy_policy
