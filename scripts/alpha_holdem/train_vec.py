#!/usr/bin/env python3
"""Vectorized AlphaHoldem trainer — N parallel games in single process, batched inference.

Replaces train_mp3.py's 28-worker multiprocessing architecture. The point is to
keep inference batches large (batch=N instead of inf_bs ~5) by stepping all
parallel games in lockstep.

Single-process, single-GPU. Loop structure:
  1. For all alive games: encode obs (N samples)
  2. Batched inference for all N (one GPU forward pass)
  3. Apply actions to all N games (vectorized step)
  4. Collect terminal payoffs, reset finished games
  5. PPO update when iter_hands >= hands_per_iter

NOTE: encoding currently uses a Python loop calling the existing per-game
encode_cards / encode_action_history / etc. This is simple but suboptimal —
will optimize after end-to-end speedup confirmed.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from alpha_holdem.network import AlphaHoldemNet, count_parameters
from alpha_holdem.environment import NUM_ACTIONS  # 9

from vec_game_state import (
    VecHUNLState, MAX_HIST, RAISE_FRACTIONS, PREFLOP_RAISE_FRACTIONS,
    S_PRE, S_FLOP, S_TURN, S_RIVER,
    A_FOLD, A_CHECK, A_CALL, A_BET, A_RAISE, A_ALLIN,
)


# ─── Batched observation encoding (cards / action history / extra) ──────────
NUM_SUITS = 4
NUM_RANKS = 13
NUM_CARD_CHANNELS = 6
MAX_ACTIONS_PER_STREET = 6
NUM_STREETS = 4
ACTION_HISTORY_CHANNELS = MAX_ACTIONS_PER_STREET * NUM_STREETS + 1  # = 25


def encode_obs_batched(state: VecHUNLState) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Encode all N parallel game observations from the current player's perspective.

    Returns:
      card_t   (N, 6, 4, 13) float32
      action_t (N, 25, 4, 5) float32
      extra_t  (N, 2)        float32
      mask_t   (N, 9)        float32 (legal action mask)
    """
    N = state.N
    cp = state.current_player.astype(np.int64)

    # ── Cards (N, 6, 4, 13) ────────────────────────────────────────────────
    card_t = np.zeros((N, NUM_CARD_CHANNELS, NUM_SUITS, NUM_RANKS), dtype=np.float32)
    # Use vectorized fancy indexing. For each game, hole=state.holes[i, cp[i], :]
    rows = np.arange(N)
    hole = state.holes[rows, cp]  # (N, 2) card indices, possibly -1 if not dealt
    # Set hero hole channel 0
    for k in range(2):
        c = hole[:, k]
        valid = c >= 0
        if valid.any():
            r = c[valid] // 4
            s = c[valid] % 4
            card_t[valid, 0, s, r] = 1.0
            card_t[valid, 5, s, r] = 1.0  # also channel 5 (all visible)

    # Board channels: 1=flop, 2=turn, 3=river, 4=all public, 5=all visible
    for j in range(5):
        c = state.board[:, j]
        valid = c >= 0
        if not valid.any():
            continue
        rr = c[valid] // 4
        ss = c[valid] % 4
        if j < 3:
            card_t[valid, 1, ss, rr] = 1.0
        elif j == 3:
            card_t[valid, 2, ss, rr] = 1.0
        else:
            card_t[valid, 3, ss, rr] = 1.0
        card_t[valid, 4, ss, rr] = 1.0
        card_t[valid, 5, ss, rr] = 1.0

    # ── Action history (N, 25, 4, 5) ───────────────────────────────────────
    # Match the Python encoder exactly: action amounts are normalized by the
    # CURRENT (post-action-history) state.pot, not by per-action pot snapshots.
    action_t = np.zeros((N, ACTION_HISTORY_CHANNELS, NUM_STREETS, 5), dtype=np.float32)
    pot_now = state.pot
    for i in range(N):
        L = int(state.hist_len[i])
        cur_pot = max(float(pot_now[i]), 1e-6)
        if L > 0:
            slot_count_per_street = [0, 0, 0, 0]
            cur_street = 0
            for j in range(L):
                who = int(state.action_hist[i, j, 0])
                atype = int(state.action_hist[i, j, 1])
                amount = float(state.action_hist[i, j, 2]) / 100.0
                if cur_street >= NUM_STREETS:
                    break
                slot = slot_count_per_street[cur_street]
                if slot >= MAX_ACTIONS_PER_STREET:
                    continue
                channel = cur_street * MAX_ACTIONS_PER_STREET + slot
                action_t[i, channel, 0, 0] = 1.0 if who == cp[i] else 0.0
                action_t[i, channel, 1, min(atype, 4)] = 1.0
                if amount > 0:
                    action_t[i, channel, 2, 0] = min(amount / cur_pot, 2.0) / 2.0
                action_t[i, channel, 3, 0] = 1.0
                slot_count_per_street[cur_street] += 1
                # Mirror Python's street-advance heuristic
                if atype in (A_CHECK, A_CALL) and slot_count_per_street[cur_street] >= 2:
                    cur_street += 1
        # Current player indicator (channel 24)
        action_t[i, 24, 0, 0] = 1.0 if state.current_player[i] == cp[i] else 0.0

    # ── Extra (N, 2): normalized stacks ────────────────────────────────────
    extra_t = np.zeros((N, 2), dtype=np.float32)
    extra_t[:, 0] = state.stacks[rows, cp] / state.eff_stack
    extra_t[:, 1] = state.stacks[rows, 1 - cp] / state.eff_stack

    # ── Legal mask (N, 9) ──────────────────────────────────────────────────
    mask_t = state.legal_mask().astype(np.float32)

    return card_t, action_t, extra_t, mask_t


# ─── PPO + GAE ──────────────────────────────────────────────────────────────
def compute_gae(rewards, values, dones, gamma=0.999, lam=0.95):
    advantages = np.zeros_like(rewards)
    last_gae = 0.0
    n = len(rewards)
    for t in reversed(range(n)):
        next_value = 0.0 if t == n - 1 else values[t + 1]
        delta = rewards[t] + gamma * next_value * (1 - dones[t]) - values[t]
        advantages[t] = last_gae = delta + gamma * lam * (1 - dones[t]) * last_gae
    returns = advantages + values
    return advantages, returns


# ─── BatchNorm helpers (Path B preflight) ──────────────────────────────────
_BN_TYPES = (nn.BatchNorm1d, nn.BatchNorm2d, nn.BatchNorm3d)


def _has_bn(model: nn.Module) -> bool:
    return any(isinstance(m, _BN_TYPES) for m in model.modules())


def _set_bn_eval(model: nn.Module) -> None:
    """Force every BN module to eval mode (freezes running stats, uses them for forward)."""
    for m in model.modules():
        if isinstance(m, _BN_TYPES):
            m.eval()


def snapshot_bn_stats(model: nn.Module) -> dict:
    snap = {}
    for name, m in model.named_modules():
        if isinstance(m, _BN_TYPES):
            snap[name + '.running_mean'] = m.running_mean.detach().clone()
            snap[name + '.running_var'] = m.running_var.detach().clone()
    return snap


def bn_stats_delta(model: nn.Module, prev_snap: dict) -> tuple[float, float]:
    """Returns (max_abs_delta_mean, max_abs_delta_var) since prev_snap."""
    if not prev_snap:
        return 0.0, 0.0
    max_dm = 0.0
    max_dv = 0.0
    for name, m in model.named_modules():
        if isinstance(m, _BN_TYPES):
            km = name + '.running_mean'
            kv = name + '.running_var'
            if km in prev_snap:
                dm = (m.running_mean - prev_snap[km]).abs().max().item()
                if dm > max_dm:
                    max_dm = dm
            if kv in prev_snap:
                dv = (m.running_var - prev_snap[kv]).abs().max().item()
                if dv > max_dv:
                    max_dv = dv
    return max_dm, max_dv


@torch.no_grad()
def measure_mode_divergence(model: nn.Module, cards, actions, extras, masks,
                            n_sample: int = 1024) -> dict | None:
    """Compare train-mode vs eval-mode forward on same inputs.
    Returns None for BN-free models (GN/LN have no train/eval distinction).

    Snapshots/restores BN running stats around the train-mode forward so the
    diagnostic itself does not pollute running_mean/running_var.
    """
    if not _has_bn(model):
        return None
    nsamp = min(n_sample, cards.shape[0])
    c = cards[:nsamp]
    a = actions[:nsamp]
    e = extras[:nsamp]
    mk = masks[:nsamp]
    was_training = model.training

    # Snapshot all BN running stats so we can restore after the train-mode forward.
    bn_save = {}
    for name, m in model.named_modules():
        if isinstance(m, _BN_TYPES):
            bn_save[name + '.rm'] = m.running_mean.detach().clone()
            bn_save[name + '.rv'] = m.running_var.detach().clone()
            if m.num_batches_tracked is not None:
                bn_save[name + '.nbt'] = m.num_batches_tracked.detach().clone()

    model.train()
    logits_train, _ = model(c, a, e, mk)
    probs_train = F.softmax(logits_train, dim=-1).clamp_min(1e-12)
    amax_train = logits_train.argmax(dim=-1)

    # Restore running stats (otherwise the diagnostic itself drifts them).
    for name, m in model.named_modules():
        if isinstance(m, _BN_TYPES):
            m.running_mean.copy_(bn_save[name + '.rm'])
            m.running_var.copy_(bn_save[name + '.rv'])
            if m.num_batches_tracked is not None:
                m.num_batches_tracked.copy_(bn_save[name + '.nbt'])

    model.eval()
    logits_eval, _ = model(c, a, e, mk)
    probs_eval = F.softmax(logits_eval, dim=-1).clamp_min(1e-12)
    amax_eval = logits_eval.argmax(dim=-1)

    if was_training:
        model.train()
    else:
        model.eval()

    log_diff = probs_eval.log() - probs_train.log()
    kl_eval_train = float((probs_eval * log_diff).sum(dim=-1).mean().item())
    greedy_flip_rate = float((amax_train != amax_eval).float().mean().item())
    return {'eval_kl': kl_eval_train, 'greedy_flip_rate': greedy_flip_rate}


def trinal_clip_ppo_update(model, optimizer, transitions, device,
                            epochs=4, mini_batch_size=2048,
                            eps=0.2, delta1=3.0, value_coef=0.5,
                            entropy_coef=0.05, entropy_floor=0.3,
                            max_grad_norm=0.5, gamma=0.999,
                            freeze_bn_stats: bool = False,
                            target_kl: float = 0.0) -> dict:
    model.train()
    if freeze_bn_stats:
        _set_bn_eval(model)
    n = len(transitions)
    if n == 0:
        return {'policy_loss': 0, 'value_loss': 0, 'entropy': 0}

    card_arr = np.stack([t[0] for t in transitions])
    action_arr = np.stack([t[1] for t in transitions])
    extra_arr = np.stack([t[2] for t in transitions])
    mask_arr = np.stack([t[3] for t in transitions])
    act_arr = np.array([t[4] for t in transitions], dtype=np.int64)
    lp_arr = np.array([t[5] for t in transitions], dtype=np.float32)
    rew_arr = np.array([t[6] for t in transitions], dtype=np.float32)
    val_arr = np.array([t[7] for t in transitions], dtype=np.float32)
    done_arr = np.array([t[8] for t in transitions], dtype=np.float32)
    hero_chips = np.array([t[9] for t in transitions], dtype=np.float32)
    villain_chips = np.array([t[10] for t in transitions], dtype=np.float32)

    advantages, returns = compute_gae(rew_arr, val_arr, done_arr, gamma=gamma)

    cards_t = torch.tensor(card_arr, device=device)
    actions_t = torch.tensor(action_arr, device=device)
    extras_t = torch.tensor(extra_arr, device=device)
    masks_t = torch.tensor(mask_arr, device=device)
    acts_t = torch.tensor(act_arr, device=device)
    old_lp_t = torch.tensor(lp_arr, device=device)
    adv_t = torch.tensor(advantages, device=device)
    ret_t = torch.tensor(returns, device=device)
    d2_t = torch.tensor(hero_chips, device=device)
    d3_t = torch.tensor(villain_chips, device=device)

    if n > 1:
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

    # GPU-resident scalar accumulators (avoid GPU↔CPU sync per minibatch).
    tp_t = torch.zeros((), device=device)
    tv_t = torch.zeros((), device=device)
    te_t = torch.zeros((), device=device)
    tkl_t = torch.zeros((), device=device)
    tcf_t = torch.zeros((), device=device)
    tdb_t = torch.zeros((), device=device)
    ratio_samples = []
    nu = 0

    # GPU-resident constants for tensor-conditional entropy boost.
    entropy_floor_t = torch.tensor(entropy_floor, device=device)
    boost_factor_t = torch.tensor(5.0, device=device)
    no_boost_t = torch.tensor(1.0, device=device)

    epochs_done = 0
    early_stopped = False
    for _ in range(epochs):
        idx = torch.randperm(n, device=device)
        epoch_kl_t = torch.zeros((), device=device)
        epoch_steps = 0
        for start in range(0, n, mini_batch_size):
            mb = idx[start:start + mini_batch_size]
            logits, values = model(cards_t[mb], actions_t[mb], extras_t[mb], masks_t[mb])
            probs = F.softmax(logits, dim=-1)
            dist = Categorical(probs)
            new_lp = dist.log_prob(acts_t[mb])
            entropy = dist.entropy().mean()

            # ratio = pi_new(a|s) / b_old(a|s)  (off-policy correction — b_old
            # is the behavior policy, includes epsilon mixing at sample time).
            ratio = torch.exp(new_lp - old_lp_t[mb])
            adv_b = adv_t[mb]

            ratio_clipped = torch.clamp(ratio, 1 - eps, 1 + eps)

            # Trinal-Clip extra cap (paper Eq. 3): when A<0 the standard PPO
            # min(surr1, surr2) picks ratio*A which is unbounded as ratio→∞.
            # Cap ratio at delta1 in that case so worst-case is -delta1·|A|.
            ratio_for_unclipped = torch.where(
                adv_b < 0,
                torch.clamp(ratio, max=delta1),
                ratio,
            )
            surr1 = ratio_for_unclipped * adv_b
            surr2 = ratio_clipped * adv_b
            ploss = -torch.min(surr1, surr2).mean()

            with torch.no_grad():
                neg_mask = adv_b < 0
                neg_count = neg_mask.float().sum().clamp_min(1.0)
                delta1_bite_frac = ((ratio > delta1) & neg_mask).float().sum() / neg_count
                clip_frac = ((ratio < 1 - eps) | (ratio > 1 + eps)).float().mean()
                approx_kl = (old_lp_t[mb] - new_lp).mean()

            ret_b = ret_t[mb]
            d2_b = d2_t[mb]
            d3_b = d3_t[mb]
            ret_clipped = torch.max(torch.min(ret_b, d3_b), -d2_b)
            vloss = F.mse_loss(values.squeeze(-1), ret_clipped)

            # GPU-resident entropy boost (avoid per-minibatch .item() sync).
            ec_t = torch.where(entropy < entropy_floor_t, boost_factor_t, no_boost_t) * entropy_coef
            loss = ploss + value_coef * vloss - ec_t * entropy

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            optimizer.step()

            tp_t += ploss.detach()
            tv_t += vloss.detach()
            te_t += entropy.detach()
            tkl_t += approx_kl
            tcf_t += clip_frac
            tdb_t += delta1_bite_frac
            if len(ratio_samples) < 8:
                ratio_samples.append(ratio.detach())
            nu += 1
            epoch_kl_t += approx_kl
            epoch_steps += 1

        epochs_done += 1
        # Target-KL early stop (between epochs, not minibatches) — only if requested.
        if target_kl > 0.0 and epoch_steps > 0:
            mean_epoch_kl = float((epoch_kl_t / epoch_steps).item())
            if mean_epoch_kl > target_kl:
                early_stopped = True
                break

    # ONE GPU→CPU sync at end of all PPO epochs.
    if ratio_samples:
        all_ratios = torch.cat(ratio_samples)
        ratio_p50 = float(torch.quantile(all_ratios, 0.50).item())
        ratio_p95 = float(torch.quantile(all_ratios, 0.95).item())
        ratio_p99 = float(torch.quantile(all_ratios, 0.99).item())
        ratio_max = float(all_ratios.max().item())
    else:
        ratio_p50 = ratio_p95 = ratio_p99 = ratio_max = 0.0

    inv_nu = 1.0 / max(nu, 1)
    return {
        'policy_loss': float(tp_t.item()) * inv_nu,
        'value_loss': float(tv_t.item()) * inv_nu,
        'entropy': float(te_t.item()) * inv_nu,
        'approx_kl': float(tkl_t.item()) * inv_nu,
        'clip_frac': float(tcf_t.item()) * inv_nu,
        'delta1_bite_frac': float(tdb_t.item()) * inv_nu,
        'ratio_p50': ratio_p50,
        'ratio_p95': ratio_p95,
        'ratio_p99': ratio_p99,
        'ratio_max': ratio_max,
        'epochs_done': epochs_done,
        'early_stopped': early_stopped,
    }


# ─── Main training loop ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--parallel-games', type=int, default=1024, help='N parallel games')
    parser.add_argument('--hands-per-iter', type=int, default=16384)
    parser.add_argument('--total-hands', type=int, default=1_000_000_000)
    parser.add_argument('--starting-stack', type=float, default=200.0)
    parser.add_argument('--lr', type=float, default=3e-4)
    parser.add_argument('--epsilon', type=float, default=0.05)
    parser.add_argument('--mini-batch-size', type=int, default=4096)
    parser.add_argument('--ppo-epochs', type=int, default=4)
    parser.add_argument('--gamma', type=float, default=0.999)
    parser.add_argument('--delta1', type=float, default=3.0)
    parser.add_argument('--entropy-coef', type=float, default=0.02)
    parser.add_argument('--entropy-floor', type=float, default=0.3)
    parser.add_argument('--save-interval', type=int, default=25)
    parser.add_argument('--out', default='models/alpha_holdem_vec.pt')
    parser.add_argument('--resume', default=None)
    parser.add_argument('--max-iters', type=int, default=100, help='Hard cap on iterations (for benchmark)')
    parser.add_argument('--max-additional-hands', type=int, default=0,
                        help='If >0, stop after this many ADDITIONAL hands past --resume checkpoint.')
    parser.add_argument('--disable-lr-decay', action='store_true',
                        help='Reserved; current trainer has no built-in decay anyway.')
    # Path B preflight: norm/BN management + target_kl early stop + diagnostics
    parser.add_argument('--norm-layer', choices=['bn', 'gn', 'ln'], default='bn',
                        help="Conv normalization. bn=BatchNorm (mode-dependent, default for V4 compat). "
                             "gn=GroupNorm (mode-independent, recommended for random-init long self-play). "
                             "ln=GroupNorm(num_groups=1).")
    parser.add_argument('--freeze-bn-stats', action='store_true',
                        help='Force BN modules into eval() during PPO update too (linear/head still train). '
                             'Eliminates BN train/eval policy mismatch when norm-layer=bn.')
    parser.add_argument('--target-kl', type=float, default=0.0,
                        help='If >0, stop PPO epochs early when mean approx_kl exceeds this. 0.03 is typical.')
    parser.add_argument('--bn-diag-every', type=int, default=10,
                        help='Iterations between BN train/eval divergence measurements (only if norm-layer=bn).')
    args = parser.parse_args()

    device = args.device
    print(f'Device: {device}')
    if device == 'cuda':
        print(f'GPU: {torch.cuda.get_device_name(0)}')
    print(f'Parallel games (N): {args.parallel_games}')

    model = AlphaHoldemNet(num_actions=NUM_ACTIONS, norm_layer=args.norm_layer).to(device)
    # GroupNorm trunk init needs a forward pass to lazy-init Linear sizes.
    # The first forward pass needs B>=2 for BN if norm_layer='bn' (BN crashes on B=1 in train mode);
    # but model defaults to .training=True here. Run lazy init in eval mode to be safe.
    model.eval()
    dc = torch.zeros(2, 6, 4, 13, device=device)
    da = torch.zeros(2, 25, 4, 5, device=device)
    de = torch.zeros(2, 2, device=device)
    model(dc, da, de)
    print(f'Parameters: {count_parameters(model):,}  norm={args.norm_layer}')
    # Path B preflight banner — explicit so reviewer can verify the trainer is configured correctly.
    print('[Init]')
    print(f'  norm_layer       = {args.norm_layer}')
    print(f'  collection_mode  = eval   (model.eval() before every batched-inference forward)')
    print(f'  update_mode      = train  (model.train() at PPO update; BN freeze: {args.freeze_bn_stats})')
    print(f'  freeze_bn_stats  = {args.freeze_bn_stats}')
    print(f'  target_kl        = {args.target_kl}  (0 = no early stop)')
    print(f'  bn_diag_every    = {args.bn_diag_every}  (only meaningful when norm_layer=bn)')
    print(f'  lr               = {args.lr}')
    print(f'  epsilon          = {args.epsilon}')
    print(f'  ppo_epochs       = {args.ppo_epochs}')
    print(f'  delta1           = {args.delta1}')
    print(f'  entropy_coef     = {args.entropy_coef}  floor={args.entropy_floor}')
    print(f'  bn_layers        = {sum(1 for m in model.modules() if isinstance(m, _BN_TYPES))}')
    if args.norm_layer == 'bn' and args.freeze_bn_stats:
        print('  [BN] --freeze-bn-stats: BN running stats frozen during PPO update.')
    elif args.norm_layer != 'bn':
        if args.freeze_bn_stats:
            print(f'  [BN] --freeze-bn-stats has no effect with norm-layer={args.norm_layer}.')
        print(f'  [Norm] {args.norm_layer} has no running stats — collection and PPO are mode-independent.')

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    total_hands = 0
    iteration = 0
    if args.resume and os.path.exists(args.resume):
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model'])
        if 'optimizer' in ckpt:
            try:
                optimizer.load_state_dict(ckpt['optimizer'])
            except Exception as e:
                print(f'Optimizer state mismatch ({e}); resetting Adam.')
        total_hands = ckpt.get('total_hands', 0)
        iteration = ckpt.get('iteration', 0)
        print(f'Resumed from {args.resume}: hands={total_hands:,}, iter={iteration}')

    # Initialize N parallel games
    N = args.parallel_games
    state = VecHUNLState(N=N, effective_stack=args.starting_stack, seed=42)
    state.reset_all()

    # Hero buffer (per-game): we collect transitions only when current player is hero.
    # When a hand terminates, we finalize the transitions with the final reward.
    per_game_buffer: list[list] = [[] for _ in range(N)]
    iter_transitions: list = []
    iter_hands = 0
    iter_reward_sum = 0.0
    reward_window: list[float] = []

    # Action histogram diagnostics (per iter, reset after PPO update).
    iter_hero_act_counts = np.zeros(9, dtype=np.int64)
    iter_pre_hero_act_counts = np.zeros(9, dtype=np.int64)
    # BN diag: snapshot running stats before each PPO update to measure drift.
    prev_bn_snap: dict = snapshot_bn_stats(model) if _has_bn(model) else {}

    log_path = args.out.replace('.pt', '.log')
    t0 = time.time()
    bench_t0 = time.time()
    bench_hands_start = total_hands
    iters_this_run = 0

    start_hands = total_hands
    additional_cap = args.max_additional_hands

    while total_hands < args.total_hands and iters_this_run < args.max_iters:
        if additional_cap > 0 and (total_hands - start_hands) >= additional_cap:
            print(f'[stop] hit --max-additional-hands cap ({additional_cap:,}); '
                  f'extended {total_hands - start_hands:,} hands from {start_hands:,}.')
            break
        # 1. Encode observations from current player's perspective
        card_np, action_np, extra_np, mask_np = encode_obs_batched(state)

        # 2. Batched inference. Epsilon exploration is folded into the BEHAVIOR
        # policy for hero-acting rows:
        #     b(a|s) = (1-eps) * pi(a|s) + eps * uniform_legal(a|s)
        # The stored log_prob is log b(a|s) so PPO can compute a correct
        # off-policy ratio pi_new(a|s) / b_old(a|s).
        cp_np = state.current_player.astype(np.int64)
        is_hero_now = (cp_np == state.hero_player.astype(np.int64))
        # Collection MUST be in eval mode: behavior policy must match the policy that
        # will be deployed against Slumbot (eval mode for BN). Without this, BN uses
        # batch stats during action sampling and stored old_logprob is inconsistent
        # with what eval-mode forward gives later (PPO ratio bias).
        model.eval()
        with torch.no_grad():
            cards_t = torch.from_numpy(card_np).to(device, non_blocking=True)
            actions_t = torch.from_numpy(action_np).to(device, non_blocking=True)
            extras_t = torch.from_numpy(extra_np).to(device, non_blocking=True)
            masks_t = torch.from_numpy(mask_np).to(device, non_blocking=True)
            logits, values = model(cards_t, actions_t, extras_t, masks_t)
            probs = F.softmax(logits, dim=-1)

            if args.epsilon > 0.0:
                is_hero_t = torch.from_numpy(is_hero_now).to(device).bool()
                legal_counts = masks_t.sum(dim=-1, keepdim=True).clamp_min(1.0)
                uniform_legal = masks_t / legal_counts
                behavior_probs = (1.0 - args.epsilon) * probs + args.epsilon * uniform_legal
                behavior_probs = behavior_probs.clamp_min(1e-12)
                behavior_probs = behavior_probs / behavior_probs.sum(dim=-1, keepdim=True)
                # Hero rows use behavior policy; non-hero rows use pure policy.
                effective_probs = torch.where(is_hero_t.unsqueeze(-1), behavior_probs, probs)
            else:
                effective_probs = probs

            dist = Categorical(effective_probs)
            sampled = dist.sample()
            log_probs = dist.log_prob(sampled)   # behavior logprob for hero, pure pi for opp
        action_np_out = sampled.cpu().numpy()
        log_probs_np = log_probs.cpu().numpy()
        values_np = values.squeeze(-1).cpu().numpy()
        # NOTE: action_np_out and log_probs_np are paired and consistent — no
        # post-hoc override of action (which would mismatch the stored log_prob).

        # 3. Stash hero transitions BEFORE step (so per_game_buffer has the pre-step obs)
        hero_rows = np.where(is_hero_now & ~state.is_done)[0]
        if hero_rows.size > 0:
            hero_acts = action_np_out[hero_rows]
            # Per-slot histogram (overall + preflop-only)
            slot_counts = np.bincount(hero_acts, minlength=9)
            iter_hero_act_counts += slot_counts
            pre_mask = state.street[hero_rows] == S_PRE
            if pre_mask.any():
                pre_slot_counts = np.bincount(hero_acts[pre_mask], minlength=9)
                iter_pre_hero_act_counts += pre_slot_counts
        for i in hero_rows:
            per_game_buffer[i].append((
                card_np[i].copy(), action_np[i].copy(), extra_np[i].copy(), mask_np[i].copy(),
                int(action_np_out[i]), float(log_probs_np[i]), float(values_np[i]),
            ))

        # 4. Step all games
        state.step(action_np_out)

        # 5. Finalize hands that terminated
        if state.is_done.any():
            rewards = state.terminal_rewards()
            for i in np.where(state.is_done)[0]:
                buf = per_game_buffer[i]
                hand_reward = float(rewards[i])
                # Count ALL completed hands in the metric (avoid skip-bias when
                # hero=BB and opponent folds preflop without hero ever acting).
                # PPO transitions still come ONLY from hands with hero actions —
                # there is nothing to learn from a state hero never saw.
                iter_reward_sum += hand_reward
                iter_hands += 1
                if buf:
                    invested = state.eff_stack - state.stacks[i]
                    hero = int(state.hero_player[i])
                    hero_invested = float(invested[hero])
                    villain_invested = float(invested[1 - hero])
                    for j, (ci, ai, ei, lm, act, lp, val) in enumerate(buf):
                        last = (j == len(buf) - 1)
                        iter_transitions.append((
                            ci, ai, ei, lm, act, lp,
                            hand_reward if last else 0.0,
                            val,
                            1.0 if last else 0.0,
                            hero_invested,
                            villain_invested,
                        ))
                per_game_buffer[i] = []

            state.reset_done()

        # 6. PPO update when enough hero hands
        if iter_hands >= args.hands_per_iter:
            iteration += 1
            iters_this_run += 1
            t_collect = time.time() - bench_t0

            # BN diag: measure train/eval forward divergence on the last collected batch
            # BEFORE the PPO update modifies running stats. Skipped for GN/LN.
            mode_div = None
            if _has_bn(model) and (iteration % max(1, args.bn_diag_every) == 0):
                mode_div = measure_mode_divergence(
                    model, cards_t, actions_t, extras_t, masks_t, n_sample=1024)

            t_train_0 = time.time()
            stats = trinal_clip_ppo_update(
                model, optimizer, iter_transitions, device,
                epochs=args.ppo_epochs, mini_batch_size=args.mini_batch_size,
                delta1=args.delta1, gamma=args.gamma,
                entropy_coef=args.entropy_coef, entropy_floor=args.entropy_floor,
                freeze_bn_stats=args.freeze_bn_stats,
                target_kl=args.target_kl,
            )
            t_train = time.time() - t_train_0
            total_hands += iter_hands

            # BN running-stat delta since previous iter (post-update)
            bn_dm, bn_dv = bn_stats_delta(model, prev_bn_snap) if _has_bn(model) else (0.0, 0.0)
            if _has_bn(model):
                prev_bn_snap = snapshot_bn_stats(model)

            avg_rew = iter_reward_sum / max(iter_hands, 1)
            reward_window.append(avg_rew)
            if len(reward_window) > 100:
                reward_window.pop(0)
            rew100 = np.mean(reward_window)

            # Action histograms (overall + preflop)
            total_acts = max(int(iter_hero_act_counts.sum()), 1)
            total_pre = max(int(iter_pre_hero_act_counts.sum()), 1)
            fold_r = iter_hero_act_counts[0] / total_acts
            cc_r = iter_hero_act_counts[1] / total_acts
            raise_r = iter_hero_act_counts[2:8].sum() / total_acts
            allin_r = iter_hero_act_counts[8] / total_acts
            pre_fold_r = iter_pre_hero_act_counts[0] / total_pre
            pre_cc_r = iter_pre_hero_act_counts[1] / total_pre
            pre_raise_r = iter_pre_hero_act_counts[2:8].sum() / total_pre
            pre_allin_r = iter_pre_hero_act_counts[8] / total_pre

            elapsed_iter = time.time() - bench_t0
            h_per_s = iter_hands / elapsed_iter
            log_line = (
                f"[{iteration:5d}] hands={total_hands:,} N={N} "
                f"rew={avg_rew:+.3f} rew100={rew100:+.3f} "
                f"ploss={stats['policy_loss']:.4f} vloss={stats['value_loss']:.4f} "
                f"ent={stats['entropy']:.4f} "
                f"kl={stats['approx_kl']:+.4f} clipfrac={stats['clip_frac']:.3f} "
                f"d1bite={stats['delta1_bite_frac']:.3f} "
                f"r50={stats['ratio_p50']:.2f}/r95={stats['ratio_p95']:.2f}/"
                f"r99={stats['ratio_p99']:.2f}/rmax={stats['ratio_max']:.2f} "
                f"eps={args.epsilon:.3f} "
                f"act[F={fold_r:.2f}/CC={cc_r:.2f}/R={raise_r:.2f}/A={allin_r:.2f}] "
                f"pre[F={pre_fold_r:.2f}/CC={pre_cc_r:.2f}/R={pre_raise_r:.2f}/A={pre_allin_r:.2f}] "
                f"ppoEp={stats['epochs_done']}{'*' if stats['early_stopped'] else ''} "
                f"trans={len(iter_transitions)} h/s={h_per_s:.0f} "
                f"col={t_collect:.1f} ppo={t_train:.1f} t={elapsed_iter:.1f}s"
            )
            if _has_bn(model):
                bn_extra = f" bnDm={bn_dm:.4f} bnDv={bn_dv:.4f}"
                if mode_div is not None:
                    bn_extra += f" evalKL={mode_div['eval_kl']:.4f} flipR={mode_div['greedy_flip_rate']:.3f}"
                log_line += bn_extra
            print(log_line)
            with open(log_path, 'a') as f:
                f.write(log_line + '\n')

            iter_transitions = []
            iter_hands = 0
            iter_reward_sum = 0.0
            iter_hero_act_counts[:] = 0
            iter_pre_hero_act_counts[:] = 0
            bench_t0 = time.time()

            # Save checkpoint
            if iteration % args.save_interval == 0:
                os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
                torch.save({
                    'model': model.state_dict(),
                    'optimizer': optimizer.state_dict(),
                    'total_hands': total_hands,
                    'iteration': iteration,
                    # Encoder metadata — so play_slumbot.py / evaluate.py never have to guess.
                    'env_version': 'v4',
                    'obs_version': 'v4',
                    'action_space_version': '9slot_v4',
                    'starting_stack_bb': args.starting_stack,
                    'trainer': 'train_vec',
                    'norm_layer': args.norm_layer,
                    'freeze_bn_stats': bool(args.freeze_bn_stats),
                }, args.out)
                print(f'  [Save] {args.out} ({total_hands:,} hands)')

    elapsed = max(time.time() - t0, 1e-6)
    overall_hands = total_hands - bench_hands_start
    print(f'\nDONE. {overall_hands:,} hands in {elapsed:.1f}s = {overall_hands/elapsed:.0f} h/s overall')


if __name__ == '__main__':
    main()
