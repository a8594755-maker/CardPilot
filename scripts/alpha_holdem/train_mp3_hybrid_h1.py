#!/usr/bin/env python3
"""
AlphaHoldem trainer V3 — with all paper fixes:

1. Trinal-Clip PPO (Zhao et al. 2022, Equations 3 & 4)
   - Policy loss:  L^tcp = clip(clip(r, 1-e, 1+e), delta1) * A
   - Value loss:   L^tcv = (clip(R, -delta2, +delta3) - V)^2
     where delta2 = hero chips committed, delta3 = villain chips committed
2. K-best opponent pool (ELO-ranked snapshots)
3. 200bb HUNL (matches Slumbot)
4. Gamma = 0.999 (paper value)
5. Per-trajectory chip tracking for dynamic value clipping

Usage:
  python scripts/alpha_holdem/train_mp3.py --device cuda --workers 28
"""

import argparse
import os
import sys
import time
import math
import random
import multiprocessing as mp
from multiprocessing import shared_memory
from collections import deque

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet, CRITIC_V1, CRITIC_V2, count_parameters
from alpha_holdem.environment import NUM_ACTIONS

# ═══════════════════════════════════════════════════════════
# Shared Memory Layout
# ═══════════════════════════════════════════════════════════

CARD_SIZE = 6 * 4 * 13       # 312
ACTION_SIZE = 25 * 4 * 5     # 500
EXTRA_SIZE = 2
MASK_SIZE = NUM_ACTIONS       # 9
OBS_SIZE = CARD_SIZE + ACTION_SIZE + EXTRA_SIZE + MASK_SIZE  # 823
RESULT_SIZE = 3  # action_idx, log_prob, value

# Plus opponent_id slot: each worker knows which opponent to use (main writes)
# 0 = self-play, 1..K = pool member index

IDLE = 0
WAITING = 1
READY = 2


# ═══════════════════════════════════════════════════════════
# Worker: now tracks chips committed for Trinal-Clip value bounds
# ═══════════════════════════════════════════════════════════

def worker_process(
    worker_id,
    obs_shm_name,
    result_shm_name,
    status_shm_name,
    assigned_opp_shm_name,    # main writes only: which opponent for this hand (read once at hand start)
    request_shm_name,         # worker writes only: which model to use for this decision (-1=hero, else pool idx)
    transition_pipe,
    stop_event,
    starting_stack,        # NEW: configurable
):
    """Persistent game worker with chip tracking."""
    import sys as _sys
    import os as _os
    import time as _time
    import random as _random
    import numpy as _np
    from multiprocessing import shared_memory as _shm

    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..'))
    from alpha_holdem.environment import HUNLEnvironment

    obs_shm = _shm.SharedMemory(name=obs_shm_name)
    result_shm = _shm.SharedMemory(name=result_shm_name)
    status_shm = _shm.SharedMemory(name=status_shm_name)
    assigned_shm = _shm.SharedMemory(name=assigned_opp_shm_name)
    request_shm = _shm.SharedMemory(name=request_shm_name)

    obs_buf = _np.ndarray(
        (OBS_SIZE,), dtype=_np.float32,
        buffer=obs_shm.buf[worker_id * OBS_SIZE * 4:(worker_id + 1) * OBS_SIZE * 4],
    )
    result_buf = _np.ndarray(
        (RESULT_SIZE,), dtype=_np.float32,
        buffer=result_shm.buf[worker_id * RESULT_SIZE * 4:(worker_id + 1) * RESULT_SIZE * 4],
    )
    status_buf = _np.ndarray(
        (1,), dtype=_np.int32,
        buffer=status_shm.buf[worker_id * 4:(worker_id + 1) * 4],
    )
    assigned_opp_buf = _np.ndarray(
        (1,), dtype=_np.int32,
        buffer=assigned_shm.buf[worker_id * 4:(worker_id + 1) * 4],
    )
    request_buf = _np.ndarray(
        (1,), dtype=_np.int32,
        buffer=request_shm.buf[worker_id * 4:(worker_id + 1) * 4],
    )

    env = HUNLEnvironment(starting_stack=starting_stack)
    hands_played = 0
    local_transitions = []

    try:
        while not stop_event.is_set():
            # Read opponent assignment ONCE at start of hand (main owns this buffer).
            current_opp_id = int(assigned_opp_buf[0])

            obs = env.reset()
            done = False
            hero_player = hands_played % 2
            hand_buffer = []
            hand_reward = 0.0

            while not done and not stop_event.is_set():
                player = obs['player']
                is_hero = (player == hero_player)

                ci = obs['card_info'].flatten()
                ai = obs['action_info'].flatten()
                ei = obs['extra_info']
                lm = obs['legal_mask']

                obs_buf[:CARD_SIZE] = ci
                obs_buf[CARD_SIZE:CARD_SIZE + ACTION_SIZE] = ai
                obs_buf[CARD_SIZE + ACTION_SIZE:CARD_SIZE + ACTION_SIZE + EXTRA_SIZE] = ei
                obs_buf[CARD_SIZE + ACTION_SIZE + EXTRA_SIZE:] = lm

                # Tell inference which model to use for THIS decision.
                # request_buf is worker-owned; main reads it for grouping but never writes.
                request_buf[0] = (current_opp_id if not is_hero else -1)
                status_buf[0] = WAITING

                while status_buf[0] != READY:
                    if stop_event.is_set():
                        break
                    _time.sleep(0.000001)

                if stop_event.is_set():
                    break

                action_idx = int(result_buf[0])
                log_prob = float(result_buf[1])   # behavior log-prob for hero, pure-policy log-prob for opponent
                value = float(result_buf[2])
                status_buf[0] = IDLE

                # NOTE: epsilon exploration is now performed by master inference as
                # part of the hero behavior policy. Worker no longer overrides action.

                if is_hero:
                    hand_buffer.append((
                        ci.copy(), ai.copy(), ei.copy(), lm.copy(),
                        action_idx, log_prob, value,
                    ))

                obs, reward, done = env.step(action_idx)

                if done:
                    hand_reward = reward if is_hero else -reward

            # At hand end: grab chips committed for Trinal-Clip bounds
            hero_chips = env.chips_committed(hero_player)
            villain_chips = env.chips_committed(1 - hero_player)

            # Build transitions with dynamic clip bounds
            for i, (ci_s, ai_s, ei_s, lm_s, act, lp, val) in enumerate(hand_buffer):
                is_last = (i == len(hand_buffer) - 1)
                local_transitions.append((
                    ci_s, ai_s, ei_s, lm_s, act, lp,
                    hand_reward if is_last else 0.0,
                    val,
                    1.0 if is_last else 0.0,
                    hero_chips,       # NEW: for delta2
                    villain_chips,    # NEW: for delta3
                ))

            hands_played += 1

            if hands_played % 50 == 0 and local_transitions:
                try:
                    transition_pipe.send(local_transitions)
                except BrokenPipeError:
                    break
                local_transitions = []

        if local_transitions:
            try:
                transition_pipe.send(local_transitions)
            except BrokenPipeError:
                pass

        try:
            transition_pipe.send(None)
        except BrokenPipeError:
            pass

    finally:
        obs_shm.close()
        result_shm.close()
        status_shm.close()
        assigned_shm.close()
        request_shm.close()


# ═══════════════════════════════════════════════════════════
# GPU Inference with K-best pool
# ═══════════════════════════════════════════════════════════

@torch.no_grad()
def run_inference_kbest(
    hero_model: AlphaHoldemNet,
    opp_models: list,        # list of AlphaHoldemNet (pool members)
    obs_np, result_np, status_np, request_model_id_np,
    num_workers: int,
    device: str,
    epsilon: float = 0.0,    # NEW: hero behavior-policy mixing weight (uniform-over-legal)
    opponent_temperature: float = 1.0,
    bf16: bool = False,
) -> int:
    """
    Group waiting workers by model (hero or pool opponent), run per-model batch inference.
    request_model_id_np[w] = -1 means use hero model; >= 0 means use opp_models[idx]

    Hero sampling distribution is the BEHAVIOR policy:
        b(a|s) = (1-eps) * pi(a|s) + eps * uniform_legal(a|s)
    The stored log_prob is log b(a|s) so that PPO can compute a correct off-policy
    ratio pi_new(a|s) / b_old(a|s). Opponents sample from their pure (pool) policy
    so the hero faces the strongest available opposition.

    opponent_temperature: applied to opp model logits before softmax (T>1 flattens, T<1 sharpens).
    Hero always uses T=1.0 so the policy gradient stays calibrated.
    """
    # Group workers by model
    groups = {}  # model_id (-1=hero, else pool idx) -> list of worker_ids
    for w in range(num_workers):
        if status_np[w] == WAITING:
            mid = int(request_model_id_np[w])
            groups.setdefault(mid, []).append(w)

    if not groups:
        return 0

    total = 0
    for mid, workers in groups.items():
        is_opp = mid != -1
        model = hero_model if not is_opp else opp_models[mid % len(opp_models)]

        cards_list, actions_list, extras_list, masks_list = [], [], [], []
        for w in workers:
            offset = w * OBS_SIZE
            obs = obs_np[offset:offset + OBS_SIZE]
            cards_list.append(obs[:CARD_SIZE].reshape(6, 4, 13))
            actions_list.append(obs[CARD_SIZE:CARD_SIZE + ACTION_SIZE].reshape(25, 4, 5))
            extras_list.append(obs[CARD_SIZE + ACTION_SIZE:CARD_SIZE + ACTION_SIZE + EXTRA_SIZE])
            masks_list.append(obs[CARD_SIZE + ACTION_SIZE + EXTRA_SIZE:])

        cards_t = torch.tensor(np.array(cards_list), dtype=torch.float32, device=device)
        actions_t = torch.tensor(np.array(actions_list), dtype=torch.float32, device=device)
        extras_t = torch.tensor(np.array(extras_list), dtype=torch.float32, device=device)
        masks_t = torch.tensor(np.array(masks_list), dtype=torch.float32, device=device)

        if bf16 and device == 'cuda':
            with torch.amp.autocast(device_type='cuda', dtype=torch.bfloat16):
                logits, values = model(cards_t, actions_t, extras_t, masks_t)
            logits = logits.float()
            values = values.float()
        else:
            logits, values = model(cards_t, actions_t, extras_t, masks_t)
        if is_opp and opponent_temperature != 1.0:
            logits = logits / max(opponent_temperature, 1e-3)
        probs = F.softmax(logits, dim=-1)

        if (not is_opp) and epsilon > 0.0:
            # Hero behavior policy: mix pure policy with uniform-over-legal.
            # masks_t has 1.0 on legal actions, 0.0 elsewhere. The network already
            # masks illegal actions in logits (additive -1e9), so probs is zero on
            # illegal actions; we just need to renormalize the uniform component.
            legal_counts = masks_t.sum(dim=-1, keepdim=True).clamp_min(1.0)
            uniform_legal = masks_t / legal_counts
            behavior_probs = (1.0 - epsilon) * probs + epsilon * uniform_legal
            behavior_probs = behavior_probs.clamp_min(1e-12)
            behavior_probs = behavior_probs / behavior_probs.sum(dim=-1, keepdim=True)
            dist = Categorical(behavior_probs)
        else:
            dist = Categorical(probs)
        sampled = dist.sample()
        log_probs = dist.log_prob(sampled)   # behavior logprob when epsilon>0; pure policy otherwise

        s_np = sampled.cpu().numpy()
        lp_np = log_probs.cpu().numpy()
        v_np = values.squeeze(-1).cpu().numpy()

        for i, w in enumerate(workers):
            r_off = w * RESULT_SIZE
            result_np[r_off] = s_np[i]
            result_np[r_off + 1] = lp_np[i]
            result_np[r_off + 2] = v_np[i]
            status_np[w] = READY

        total += len(workers)

    return total


# ═══════════════════════════════════════════════════════════
# GAE + Trinal-Clip PPO
# ═══════════════════════════════════════════════════════════

def compute_gae(rewards, values, dones, gamma=0.999, lam=0.95):
    """GAE with paper's gamma=0.999."""
    advantages = np.zeros_like(rewards)
    last_gae = 0.0
    n = len(rewards)
    for t in reversed(range(n)):
        next_value = 0.0 if t == n - 1 else values[t + 1]
        delta = rewards[t] + gamma * next_value * (1 - dones[t]) - values[t]
        advantages[t] = last_gae = delta + gamma * lam * (1 - dones[t]) * last_gae
    returns = advantages + values
    return advantages, returns


def prepare_h1_critic_arrays(rewards, old_values, hero_chips, villain_chips, *, critic_contract=CRITIC_V1, effective_stack_divisor=200.0):
    if critic_contract not in {CRITIC_V1, CRITIC_V2}:
        raise ValueError(f'unknown critic_contract: {critic_contract}')
    rew = np.asarray(rewards, dtype=np.float64).copy()
    val = np.asarray(old_values, dtype=np.float64).copy()
    d2 = np.asarray(hero_chips, dtype=np.float64).copy()
    d3 = np.asarray(villain_chips, dtype=np.float64).copy()
    scale = 1.0
    if critic_contract == CRITIC_V2:
        scale = float(effective_stack_divisor)
        if scale != 200.0:
            raise ValueError('H1 critic_v2 requires exact effective_stack_divisor=200')
        rew /= scale
        val /= scale
        d2 /= scale
        d3 /= scale
    return rew, val, d2, d3, scale


def prepare_h2_critic_returns(
    rewards,
    old_values,
    dones,
    critic_target_overrides,
    *,
    gamma=0.999,
    gae_lambda=0.95,
):
    """Keep actor GAE fixed while overriding only finite H2 critic targets."""
    advantages, baseline_returns = compute_gae(
        rewards,
        old_values,
        dones,
        gamma=gamma,
        lam=gae_lambda,
    )
    critic_returns = np.asarray(baseline_returns, dtype=np.float64).copy()
    overrides = np.asarray(critic_target_overrides, dtype=np.float64)
    if overrides.shape != critic_returns.shape:
        raise ValueError('H2 critic target override shape mismatch')
    override_mask = np.isfinite(overrides)
    critic_returns[override_mask] = overrides[override_mask]
    return advantages, baseline_returns, critic_returns, override_mask

def trinal_clip_ppo_update(
    model, optimizer, transitions, device,
    epochs=4, mini_batch_size=1024,
    eps=0.2,                # standard PPO clip
    delta1=3.0,             # policy outer clip bound (paper value)
    value_coef=0.5,
    entropy_coef=0.05,      # higher than paper default
    entropy_floor=0.3,      # adaptive boost when below this (lowered from 0.5 to test plateau breakthrough)
    max_grad_norm=0.5,
    gamma=0.999,
    gae_lambda=0.95,
    critic_contract=CRITIC_V1,
    effective_stack_divisor=200.0,
    bf16=False,
    action_prior_coef=0.0,
    action_prior_target=None,
    action_prior_postflop_only=True,
    preflop_action_prior_coef=0.0,
    preflop_action_prior_target=None,
    preflop_sb_open_action_prior_coef=0.0,
    preflop_sb_open_action_prior_target=None,
    preflop_bb_vs_open_action_prior_coef=0.0,
    preflop_bb_vs_open_action_prior_target=None,
    target_kl=0.0,
    reference_policy=None,
    reference_policy_kl_coef=0.0,
    policy_postflop_only=False,
    policy_position_only='all',
    preflop_teacher_coef=0.0,
    value_head_catchup=False,
    value_head_catchup_loss='mse',
    value_head_catchup_smooth_l1_beta=1.0,
    critic_head_only_gradient=False,
) -> dict:
    """Trinal-Clip PPO (Zhao et al. 2022 Equations 3-4)."""
    model.train()
    n = len(transitions)
    use_reference_policy_kl = (
        reference_policy is not None
        and float(reference_policy_kl_coef or 0.0) > 0.0
    )
    use_preflop_teacher = float(preflop_teacher_coef or 0.0) > 0.0
    if policy_position_only not in {'all', 'bb', 'sb'}:
        raise ValueError(
            "policy_position_only must be one of: all, bb, sb"
        )
    if policy_position_only != 'all' and not policy_postflop_only:
        raise ValueError(
            'position-selective PPO requires policy_postflop_only'
        )
    if use_preflop_teacher and not policy_postflop_only:
        raise ValueError(
            'preflop teacher requires policy_postflop_only so PPO ratios are '
            'used only for model-sampled postflop actions'
        )
    if use_reference_policy_kl:
        reference_policy.eval()
    if critic_head_only_gradient and not hasattr(model, 'value_head'):
        raise ValueError('critic head-only gradient requires model.value_head')

    # Unpack — now 11 elements per transition
    card_arr = np.array([t[0].reshape(6, 4, 13) for t in transitions])
    action_arr = np.array([t[1].reshape(25, 4, 5) for t in transitions])
    extra_arr = np.array([t[2] for t in transitions])
    mask_arr = np.array([t[3] for t in transitions])
    act_arr = np.array([t[4] for t in transitions])
    lp_arr = np.array([t[5] for t in transitions])
    rew_arr = np.array([t[6] for t in transitions])
    val_arr = np.array([t[7] for t in transitions])
    done_arr = np.array([t[8] for t in transitions])
    hero_chips_arr = np.array([t[9] for t in transitions])     # NEW
    villain_chips_arr = np.array([t[10] for t in transitions]) # NEW

    # Transitions retain raw-BB rewards, raw-equivalent old values and raw
    # committed-chip bounds. Convert every critic/GAE quantity together.
    rew_arr, val_arr, hero_chips_arr, villain_chips_arr, value_scale = prepare_h1_critic_arrays(
        rew_arr, val_arr, hero_chips_arr, villain_chips_arr,
        critic_contract=critic_contract, effective_stack_divisor=effective_stack_divisor,
    )

    # Optional transition field 12 is an H2 critic-only raw-BB target.  Actor
    # advantages always come from the unchanged sampled reward/GAE path.
    critic_target_overrides = np.array([
        float(t[12]) if len(t) > 12 else np.nan for t in transitions
    ], dtype=np.float64)
    # Optional transition field 13 records the engine seat. In this HUNL
    # implementation player 0 is BB/OOP and player 1 is BTN/SB/IP. Older
    # transition producers have no seat field and remain compatible with the
    # default all-position update.
    player_arr = np.array([
        int(t[13]) if len(t) > 13 else -1 for t in transitions
    ], dtype=np.int8)
    if value_scale != 1.0:
        finite = np.isfinite(critic_target_overrides)
        critic_target_overrides[finite] /= value_scale
    advantages, baseline_returns, returns, h2_override_mask = prepare_h2_critic_returns(
        rew_arr,
        val_arr,
        done_arr,
        critic_target_overrides,
        gamma=gamma,
        gae_lambda=gae_lambda,
    )

    # To tensors
    cards_t = torch.tensor(card_arr, dtype=torch.float32, device=device)
    actions_t = torch.tensor(action_arr, dtype=torch.float32, device=device)
    extras_t = torch.tensor(extra_arr, dtype=torch.float32, device=device)
    masks_t = torch.tensor(mask_arr, dtype=torch.float32, device=device)
    acts_t = torch.tensor(act_arr, dtype=torch.long, device=device)
    old_lp_t = torch.tensor(lp_arr, dtype=torch.float32, device=device)
    adv_t = torch.tensor(advantages, dtype=torch.float32, device=device)
    ret_t = torch.tensor(returns, dtype=torch.float32, device=device)
    # Trinal-Clip value bounds: -hero_chips (max loss) to +villain_chips (max win)
    delta2_t = torch.tensor(hero_chips_arr, dtype=torch.float32, device=device)
    delta3_t = torch.tensor(villain_chips_arr, dtype=torch.float32, device=device)

    use_postflop_action_prior = float(action_prior_coef or 0.0) > 0.0
    use_preflop_action_prior = float(preflop_action_prior_coef or 0.0) > 0.0
    use_preflop_sb_open_action_prior = float(preflop_sb_open_action_prior_coef or 0.0) > 0.0
    use_preflop_bb_vs_open_action_prior = float(preflop_bb_vs_open_action_prior_coef or 0.0) > 0.0
    use_action_prior = (
        use_postflop_action_prior
        or use_preflop_action_prior
        or use_preflop_sb_open_action_prior
        or use_preflop_bb_vs_open_action_prior
    )

    def make_action_prior_tensor(target, *, default):
        if target is None:
            target = default
        if len(target) != 4:
            raise ValueError("action_prior_target must have four class weights: fold,call,raise,allin")
        target_t = torch.tensor(target, dtype=torch.float32, device=device).clamp_min(0.0)
        if float(target_t.sum().item()) <= 0.0:
            raise ValueError("action_prior_target must contain at least one positive weight")
        return target_t

    if use_action_prior or policy_postflop_only or use_preflop_teacher:
        action_prior_t = (
            make_action_prior_tensor(action_prior_target, default=(0.0, 0.0, 1.0, 0.0))
            if use_postflop_action_prior
            else None
        )
        preflop_action_prior_t = (
            make_action_prior_tensor(preflop_action_prior_target, default=(0.30, 0.25, 0.43, 0.02))
            if use_preflop_action_prior
            else None
        )
        preflop_sb_open_action_prior_t = (
            make_action_prior_tensor(preflop_sb_open_action_prior_target, default=(0.15, 0.20, 0.63, 0.02))
            if use_preflop_sb_open_action_prior
            else None
        )
        preflop_bb_vs_open_action_prior_t = (
            make_action_prior_tensor(preflop_bb_vs_open_action_prior_target, default=(0.25, 0.55, 0.18, 0.02))
            if use_preflop_bb_vs_open_action_prior
            else None
        )
        postflop_arr = card_arr[:, 4].sum(axis=(1, 2)) > 1e-6
        postflop_t = torch.tensor(postflop_arr, dtype=torch.bool, device=device)
        player_t = torch.tensor(player_arr, dtype=torch.int8, device=device)
        if policy_position_only == 'bb':
            policy_selection_t = postflop_t & (player_t == 0)
        elif policy_position_only == 'sb':
            policy_selection_t = postflop_t & (player_t == 1)
        else:
            policy_selection_t = postflop_t
        preflop_slot_count_arr = action_arr[:, :6, 3, 0].sum(axis=1)
        first_action_type_arr = action_arr[:, 0, 1, :]
        first_action_is_opp_arr = action_arr[:, 0, 0, 0] <= 0.5
        first_action_aggressive_arr = (
            (first_action_type_arr[:, 3] > 0.5)
            | (first_action_type_arr[:, 4] > 0.5)
        )
        preflop_sb_open_t = torch.tensor(
            (~postflop_arr) & (preflop_slot_count_arr <= 0.5),
            dtype=torch.bool,
            device=device,
        )
        preflop_bb_vs_open_t = torch.tensor(
            (
                (~postflop_arr)
                & (preflop_slot_count_arr > 0.5)
                & (preflop_slot_count_arr <= 1.5)
                & first_action_is_opp_arr
                & first_action_aggressive_arr
            ),
            dtype=torch.bool,
            device=device,
        )
    else:
        action_prior_t = None
        preflop_action_prior_t = None
        preflop_sb_open_action_prior_t = None
        preflop_bb_vs_open_action_prior_t = None
        postflop_t = None
        policy_selection_t = None
        preflop_sb_open_t = None
        preflop_bb_vs_open_t = None

    if n > 1:
        if policy_postflop_only:
            selected_advantages = adv_t[policy_selection_t]
            if selected_advantages.numel() > 1:
                adv_t = (
                    adv_t - selected_advantages.mean()
                ) / (selected_advantages.std() + 1e-8)
        else:
            adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

    # GPU-resident scalar accumulators — avoid GPU↔CPU sync per minibatch.
    tp_t = torch.zeros((), device=device)
    tv_t = torch.zeros((), device=device)
    te_t = torch.zeros((), device=device)
    tkl_t = torch.zeros((), device=device)
    trkl_t = torch.zeros((), device=device)
    tpt_t = torch.zeros((), device=device)
    tcf_t = torch.zeros((), device=device)
    tdb_t = torch.zeros((), device=device)
    tap_t = torch.zeros((), device=device)
    tap_post_t = torch.zeros((), device=device)
    tap_pre_t = torch.zeros((), device=device)
    tap_pre_sb_open_t = torch.zeros((), device=device)
    tap_pre_bb_vs_open_t = torch.zeros((), device=device)
    tap_n = 0
    tap_post_n = 0
    tap_pre_n = 0
    tap_pre_sb_open_n = 0
    tap_pre_bb_vs_open_n = 0
    tpt_n = 0
    ratio_samples = []
    nu = 0
    epochs_completed = 0
    kl_early_stop_triggered = False
    kl_early_stop_epoch = 0
    value_head_catchup_epochs = 0
    value_head_catchup_minibatches = 0
    value_head_catchup_loss_t = torch.zeros((), device=device)
    value_head_catchup_actor_state_unchanged = True

    # GPU-resident constants for tensor-conditional entropy boost
    entropy_floor_t = torch.tensor(entropy_floor, device=device)
    boost_factor_t = torch.tensor(5.0, device=device)
    no_boost_t = torch.tensor(1.0, device=device)

    use_amp = bf16 and device == 'cuda'
    autocast_ctx = lambda: (torch.amp.autocast(device_type='cuda', dtype=torch.bfloat16)
                            if use_amp else torch.amp.autocast(device_type='cpu', enabled=False))

    for epoch_index in range(epochs):
        epoch_kl_t = torch.zeros((), device=device)
        epoch_updates = 0
        indices = torch.randperm(n, device=device)
        for start in range(0, n, mini_batch_size):
            end = min(start + mini_batch_size, n)
            idx = indices[start:end]

            with autocast_ctx():
                logits, values = model(cards_t[idx], actions_t[idx], extras_t[idx], masks_t[idx])
            # Promote to fp32 for numerically sensitive ops (softmax + log_prob + loss)
            if use_amp:
                logits = logits.float()
                values = values.float()
            probs = F.softmax(logits, dim=-1)
            dist = Categorical(probs)
            new_lp = dist.log_prob(acts_t[idx])
            entropy_rows = dist.entropy()
            policy_rows = (
                policy_selection_t[idx]
                if policy_postflop_only
                else torch.ones_like(acts_t[idx], dtype=torch.bool)
            )
            if bool(policy_rows.any().item()):
                entropy = entropy_rows[policy_rows].mean()
            else:
                entropy = logits.sum() * 0.0
            reference_policy_kl = torch.zeros((), device=device)
            if use_reference_policy_kl:
                with torch.no_grad():
                    with autocast_ctx():
                        reference_logits, _ = reference_policy(
                            cards_t[idx], actions_t[idx], extras_t[idx], masks_t[idx]
                        )
                    if use_amp:
                        reference_logits = reference_logits.float()
                    reference_probs = F.softmax(reference_logits, dim=-1)
                # Forward KL KL(pi_reference || pi_current) keeps a strong
                # supervised source policy from being destroyed by a noisy
                # first critic/actor update while still allowing improvement.
                reference_policy_kl_rows = (
                    reference_probs
                    * (
                        reference_probs.clamp_min(1e-8).log()
                        - probs.clamp_min(1e-8).log()
                    )
                ).sum(dim=-1)
                # For a seat-selective actor update, anchor both postflop seats
                # to the source policy. This lets BB/OOP improve without the
                # shared adapter freely destroying the already stronger SB/IP
                # behavior.
                reference_rows = (
                    postflop_t[idx]
                    if policy_postflop_only
                    else torch.ones_like(policy_rows)
                )
                reference_policy_kl = (
                    reference_policy_kl_rows[reference_rows].mean()
                    if bool(reference_rows.any().item())
                    else logits.sum() * 0.0
                )
            preflop_teacher_loss = torch.zeros((), device=device)
            preflop_teacher_used = False
            if use_preflop_teacher:
                teacher_rows = ~postflop_t[idx]
                if bool(teacher_rows.any().item()):
                    preflop_teacher_loss = -new_lp[teacher_rows].mean()
                    preflop_teacher_used = True
            action_prior_loss = torch.zeros((), device=device)
            postflop_action_prior_loss = torch.zeros((), device=device)
            preflop_action_prior_loss = torch.zeros((), device=device)
            preflop_sb_open_action_prior_loss = torch.zeros((), device=device)
            preflop_bb_vs_open_action_prior_loss = torch.zeros((), device=device)
            postflop_action_prior_used = False
            preflop_action_prior_used = False
            preflop_sb_open_action_prior_used = False
            preflop_bb_vs_open_action_prior_used = False
            if use_action_prior:
                class_mass = torch.stack(
                    (
                        probs[:, 0],
                        probs[:, 1],
                        probs[:, 2:8].sum(dim=-1),
                        probs[:, 8],
                    ),
                    dim=-1,
                )
                class_legal = torch.stack(
                    (
                        masks_t[idx, 0] > 0.0,
                        masks_t[idx, 1] > 0.0,
                        masks_t[idx, 2:8].sum(dim=-1) > 0.0,
                        masks_t[idx, 8] > 0.0,
                    ),
                    dim=-1,
                )

                def prior_loss_for(row_mask, target_t):
                    if target_t is None or not bool(row_mask.any().item()):
                        return torch.zeros((), device=device), False
                    target = target_t.unsqueeze(0) * class_legal.float()
                    target_sum = target.sum(dim=-1, keepdim=True)
                    valid = row_mask & (target_sum.squeeze(-1) > 1e-8)
                    if bool(valid.any().item()):
                        target = target[valid] / target_sum[valid].clamp_min(1e-8)
                        mass = class_mass[valid].clamp_min(1e-8)
                        return -(target * mass.log()).sum(dim=-1).mean(), True
                    return torch.zeros((), device=device), False

                if use_postflop_action_prior:
                    prior_rows = (
                        postflop_t[idx]
                        if action_prior_postflop_only
                        else torch.ones_like(acts_t[idx], dtype=torch.bool)
                    )
                    postflop_action_prior_loss, postflop_action_prior_used = prior_loss_for(prior_rows, action_prior_t)
                    action_prior_loss = action_prior_loss + postflop_action_prior_loss
                specific_preflop_rows = torch.zeros_like(acts_t[idx], dtype=torch.bool)
                if use_preflop_sb_open_action_prior:
                    sb_rows = preflop_sb_open_t[idx]
                    preflop_sb_open_action_prior_loss, preflop_sb_open_action_prior_used = prior_loss_for(
                        sb_rows,
                        preflop_sb_open_action_prior_t,
                    )
                    action_prior_loss = action_prior_loss + preflop_sb_open_action_prior_loss
                    specific_preflop_rows = specific_preflop_rows | sb_rows
                if use_preflop_bb_vs_open_action_prior:
                    bb_rows = preflop_bb_vs_open_t[idx]
                    preflop_bb_vs_open_action_prior_loss, preflop_bb_vs_open_action_prior_used = prior_loss_for(
                        bb_rows,
                        preflop_bb_vs_open_action_prior_t,
                    )
                    action_prior_loss = action_prior_loss + preflop_bb_vs_open_action_prior_loss
                    specific_preflop_rows = specific_preflop_rows | bb_rows
                if use_preflop_action_prior:
                    preflop_rows = (~postflop_t[idx]) & (~specific_preflop_rows)
                    preflop_action_prior_loss, preflop_action_prior_used = prior_loss_for(
                        preflop_rows,
                        preflop_action_prior_t,
                    )
                    action_prior_loss = action_prior_loss + preflop_action_prior_loss

            # ── Trinal-Clip Policy Loss (Eq. 3) ──
            # ratio = pi_new(a|s) / b_old(a|s)  (off-policy correction; b_old includes
            # epsilon mixing applied at sampling time, so the numerator stays pure pi).
            ratio = torch.exp(new_lp - old_lp_t[idx])
            ratio_policy = ratio[policy_rows]
            adv_batch = adv_t[idx][policy_rows]

            # Standard PPO inner clip [1-eps, 1+eps]
            ratio_clipped = torch.clamp(ratio_policy, 1 - eps, 1 + eps)

            # Trinal-Clip extra cap: when A<0 the standard PPO min(surr1, surr2)
            # picks surr1 = ratio*A, which is unbounded as ratio → ∞. Paper Eq. 3
            # caps ratio at delta1 in that case so the worst-case surrogate is
            # -delta1 * |A| instead of -∞.
            ratio_for_unclipped = torch.where(
                adv_batch < 0,
                torch.clamp(ratio_policy, max=delta1),
                ratio_policy,
            )
            surr1 = ratio_for_unclipped * adv_batch
            surr2 = ratio_clipped * adv_batch
            ploss = (
                -torch.min(surr1, surr2).mean()
                if bool(policy_rows.any().item())
                else logits.sum() * 0.0
            )

            # Diagnostics: how often delta1 actually bites, and standard clip frac.
            # All computed on GPU; no sync until end of update.
            with torch.no_grad():
                if bool(policy_rows.any().item()):
                    neg_mask = adv_batch < 0
                    neg_count = neg_mask.float().sum().clamp_min(1.0)
                    delta1_bite_frac = (
                        (ratio_policy > delta1) & neg_mask
                    ).float().sum() / neg_count
                    clip_frac = (
                        (ratio_policy < 1 - eps)
                        | (ratio_policy > 1 + eps)
                    ).float().mean()
                    approx_kl = (
                        old_lp_t[idx][policy_rows] - new_lp[policy_rows]
                    ).mean()
                else:
                    delta1_bite_frac = logits.sum() * 0.0
                    clip_frac = logits.sum() * 0.0
                    approx_kl = logits.sum() * 0.0

            # ── Trinal-Clip Value Loss (Eq. 4) ──
            # Clip returns per-trajectory: [-hero_chips, +villain_chips]
            ret_batch = ret_t[idx]
            d2 = delta2_t[idx]
            d3 = delta3_t[idx]
            ret_clipped = torch.max(torch.min(ret_batch, d3), -d2)
            vloss = F.mse_loss(values.squeeze(-1), ret_clipped)

            # Safety net: boost entropy coef if collapsing below floor.
            # GPU-resident conditional avoids a per-minibatch .item() sync.
            ec_t = torch.where(entropy < entropy_floor_t, boost_factor_t, no_boost_t) * entropy_coef
            actor_loss = ploss - ec_t * entropy
            if use_reference_policy_kl:
                actor_loss = actor_loss + float(reference_policy_kl_coef) * reference_policy_kl
            if use_preflop_teacher:
                actor_loss = actor_loss + float(preflop_teacher_coef) * preflop_teacher_loss
            if use_postflop_action_prior:
                actor_loss = actor_loss + float(action_prior_coef) * postflop_action_prior_loss
            if use_preflop_action_prior:
                actor_loss = actor_loss + float(preflop_action_prior_coef) * preflop_action_prior_loss
            if use_preflop_sb_open_action_prior:
                actor_loss = actor_loss + float(preflop_sb_open_action_prior_coef) * preflop_sb_open_action_prior_loss
            if use_preflop_bb_vs_open_action_prior:
                actor_loss = actor_loss + float(preflop_bb_vs_open_action_prior_coef) * preflop_bb_vs_open_action_prior_loss
            loss = actor_loss + value_coef * vloss

            optimizer.zero_grad()
            if critic_head_only_gradient and float(value_coef) > 0.0:
                value_params = [
                    param for param in model.value_head.parameters()
                    if param.requires_grad
                ]
                if not value_params:
                    raise RuntimeError(
                        'critic head-only gradient has no trainable value-head parameters'
                    )
                # Obtain the critic gradient only with respect to value_head.
                # autograd.grad does not populate shared-trunk .grad fields, so
                # the high-variance critic cannot rewrite policy features.
                critic_grads = torch.autograd.grad(
                    float(value_coef) * vloss,
                    value_params,
                    retain_graph=True,
                    allow_unused=True,
                )
                actor_loss.backward()
                for param, grad in zip(value_params, critic_grads):
                    if grad is None:
                        continue
                    param.grad = grad if param.grad is None else param.grad + grad
                value_param_ids = {id(param) for param in value_params}
                actor_params = [
                    param for param in model.parameters()
                    if param.requires_grad and id(param) not in value_param_ids
                ]
                # Keep critic magnitude from shrinking the actor update through
                # a shared global clipping norm.
                nn.utils.clip_grad_norm_(actor_params, max_grad_norm)
                nn.utils.clip_grad_norm_(value_params, max_grad_norm)
            else:
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            optimizer.step()

            # GPU-side accumulation (.detach() to drop autograd, no sync).
            tp_t += ploss.detach()
            tv_t += vloss.detach()
            te_t += entropy.detach()
            tkl_t += approx_kl
            trkl_t += reference_policy_kl.detach()
            if preflop_teacher_used:
                tpt_t += preflop_teacher_loss.detach()
                tpt_n += 1
            epoch_kl_t += approx_kl
            epoch_updates += 1
            tcf_t += clip_frac
            tdb_t += delta1_bite_frac
            if use_action_prior:
                if (
                    postflop_action_prior_used
                    or preflop_action_prior_used
                    or preflop_sb_open_action_prior_used
                    or preflop_bb_vs_open_action_prior_used
                ):
                    tap_t += action_prior_loss.detach()
                    tap_n += 1
                if postflop_action_prior_used:
                    tap_post_t += postflop_action_prior_loss.detach()
                    tap_post_n += 1
                if preflop_action_prior_used:
                    tap_pre_t += preflop_action_prior_loss.detach()
                    tap_pre_n += 1
                if preflop_sb_open_action_prior_used:
                    tap_pre_sb_open_t += preflop_sb_open_action_prior_loss.detach()
                    tap_pre_sb_open_n += 1
                if preflop_bb_vs_open_action_prior_used:
                    tap_pre_bb_vs_open_t += preflop_bb_vs_open_action_prior_loss.detach()
                    tap_pre_bb_vs_open_n += 1
            # Keep ratio samples on GPU (concatenate later); each .detach() is free.
            if len(ratio_samples) < 8:   # 8 minibatches × ~1024 = ~8192 ratios
                ratio_samples.append(ratio.detach())
            nu += 1

        epochs_completed = epoch_index + 1
        if float(target_kl or 0.0) > 0.0:
            epoch_mean_kl = float((epoch_kl_t / max(epoch_updates, 1)).item())
            if epoch_mean_kl > float(target_kl):
                kl_early_stop_triggered = True
                kl_early_stop_epoch = epochs_completed
                remaining_epochs = max(int(epochs) - int(epochs_completed), 0)
                if bool(value_head_catchup) and remaining_epochs > 0:
                    if not hasattr(model, 'value_head'):
                        raise RuntimeError('H8 value-head catch-up requires model.value_head')
                    value_params = list(model.value_head.parameters())
                    value_param_ids = {id(param) for param in value_params}
                    non_value_params = [
                        param for param in model.parameters() if id(param) not in value_param_ids
                    ]
                    saved_requires_grad = {
                        id(param): bool(param.requires_grad) for param in model.parameters()
                    }
                    saved_training = bool(model.training)
                    actor_state_before = {
                        name: tensor.detach().clone()
                        for name, tensor in model.state_dict().items()
                        if not name.startswith('value_head.')
                    }
                    try:
                        model.eval()
                        for param in non_value_params:
                            param.requires_grad_(False)
                        for param in value_params:
                            param.requires_grad_(True)
                        sequential_indices = torch.arange(n, device=device)
                        for _ in range(remaining_epochs):
                            for start in range(0, n, mini_batch_size):
                                end = min(start + mini_batch_size, n)
                                idx = sequential_indices[start:end]
                                with autocast_ctx():
                                    _, catchup_values = model(
                                        cards_t[idx], actions_t[idx], extras_t[idx], masks_t[idx]
                                    )
                                if use_amp:
                                    catchup_values = catchup_values.float()
                                catchup_ret = torch.max(
                                    torch.min(ret_t[idx], delta3_t[idx]), -delta2_t[idx]
                                )
                                if value_head_catchup_loss == 'mse':
                                    catchup_vloss = F.mse_loss(
                                        catchup_values.squeeze(-1), catchup_ret
                                    )
                                elif value_head_catchup_loss == 'smooth_l1':
                                    catchup_vloss = F.smooth_l1_loss(
                                        catchup_values.squeeze(-1),
                                        catchup_ret,
                                        beta=float(value_head_catchup_smooth_l1_beta),
                                    )
                                elif value_head_catchup_loss == 'huber':
                                    if float(value_head_catchup_smooth_l1_beta) != 1.0:
                                        raise RuntimeError(
                                            'Huber catch-up kernel is registered only for delta=1.0'
                                        )
                                    catchup_vloss = F.huber_loss(
                                        catchup_values.squeeze(-1),
                                        catchup_ret,
                                        delta=1.0,
                                    )
                                else:
                                    raise RuntimeError(
                                        f'unsupported catch-up value loss: {value_head_catchup_loss}'
                                    )
                                catchup_loss = float(value_coef) * catchup_vloss
                                optimizer.zero_grad(set_to_none=True)
                                catchup_loss.backward()
                                if any(param.grad is not None for param in non_value_params):
                                    value_head_catchup_actor_state_unchanged = False
                                    raise RuntimeError(
                                        'H8 value-head catch-up leaked a gradient outside value_head'
                                    )
                                nn.utils.clip_grad_norm_(value_params, max_grad_norm)
                                optimizer.step()
                                value_head_catchup_loss_t += catchup_vloss.detach()
                                value_head_catchup_minibatches += 1
                        value_head_catchup_epochs = remaining_epochs
                    finally:
                        for param in model.parameters():
                            param.requires_grad_(saved_requires_grad[id(param)])
                        model.train(saved_training)
                    actor_state_after = model.state_dict()
                    value_head_catchup_actor_state_unchanged = (
                        value_head_catchup_actor_state_unchanged
                        and all(
                            torch.equal(before, actor_state_after[name])
                            for name, before in actor_state_before.items()
                        )
                    )
                    if not value_head_catchup_actor_state_unchanged:
                        raise RuntimeError(
                            'H8 value-head catch-up changed actor/trunk parameters or buffers'
                        )
                break

    # ONE GPU→CPU sync at the very end of all PPO epochs.
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
        'value_loss_raw_bb_equivalent': float(tv_t.item()) * inv_nu * value_scale * value_scale,
        'critic_contract': critic_contract,
        'critic_head_only_gradient': bool(critic_head_only_gradient),
        'effective_stack_divisor': value_scale,
        'h2_critic_target_override_rows': int(h2_override_mask.sum()),
        'h2_critic_target_override_fraction': float(h2_override_mask.mean()) if len(h2_override_mask) else 0.0,
        'entropy': float(te_t.item()) * inv_nu,
        'approx_kl': float(tkl_t.item()) * inv_nu,
        'reference_policy_kl': float(trkl_t.item()) * inv_nu,
        'reference_policy_kl_coef': float(reference_policy_kl_coef or 0.0),
        'preflop_teacher_loss': float(tpt_t.item()) / max(tpt_n, 1),
        'preflop_teacher_coef': float(preflop_teacher_coef or 0.0),
        'policy_postflop_only': bool(policy_postflop_only),
        'policy_position_only': str(policy_position_only),
        'policy_rows': (
            int(policy_selection_t.sum().item())
            if policy_postflop_only else n
        ),
        'ppo_epochs_completed': epochs_completed,
        'kl_early_stop_triggered': kl_early_stop_triggered,
        'kl_early_stop_epoch': kl_early_stop_epoch,
        'ppo_target_kl': float(target_kl or 0.0),
        'value_head_catchup_enabled': bool(value_head_catchup),
        'value_head_catchup_loss_mode': str(value_head_catchup_loss),
        'value_head_catchup_smooth_l1_beta': float(value_head_catchup_smooth_l1_beta),
        'value_head_catchup_epochs': int(value_head_catchup_epochs),
        'value_head_catchup_minibatches': int(value_head_catchup_minibatches),
        'value_head_catchup_loss': (
            float(value_head_catchup_loss_t.item()) / max(value_head_catchup_minibatches, 1)
        ),
        'value_head_catchup_actor_state_unchanged': bool(
            value_head_catchup_actor_state_unchanged
        ),
        'clip_frac': float(tcf_t.item()) * inv_nu,
        'delta1_bite_frac': float(tdb_t.item()) * inv_nu,
        'action_prior_loss': float(tap_t.item()) / max(tap_n, 1),
        'action_prior_coef': float(action_prior_coef or 0.0),
        'postflop_action_prior_loss': float(tap_post_t.item()) / max(tap_post_n, 1),
        'postflop_action_prior_coef': float(action_prior_coef or 0.0),
        'preflop_action_prior_loss': float(tap_pre_t.item()) / max(tap_pre_n, 1),
        'preflop_action_prior_coef': float(preflop_action_prior_coef or 0.0),
        'preflop_sb_open_action_prior_loss': float(tap_pre_sb_open_t.item()) / max(tap_pre_sb_open_n, 1),
        'preflop_sb_open_action_prior_coef': float(preflop_sb_open_action_prior_coef or 0.0),
        'preflop_bb_vs_open_action_prior_loss': float(tap_pre_bb_vs_open_t.item()) / max(tap_pre_bb_vs_open_n, 1),
        'preflop_bb_vs_open_action_prior_coef': float(preflop_bb_vs_open_action_prior_coef or 0.0),
        'ratio_p50': ratio_p50,
        'ratio_p95': ratio_p95,
        'ratio_p99': ratio_p99,
        'ratio_max': ratio_max,
    }


# ═══════════════════════════════════════════════════════════
# K-best opponent pool
# ═══════════════════════════════════════════════════════════

class KBestPool:
    """
    Honest recent-K opponent pool.

    The previous implementation sorted by ELO and truncated to the top K, but
    update_elo() was never called from the training loop. With every snapshot
    initialized to ELO=1500 the sort was a no-op and Python's stable-sort then
    truncating to K silently dropped every new snapshot once the pool was full.

    This version keeps the LAST K snapshots (FIFO). update_elo() is retained for
    future ELO ranking; recent-K is the honest behavior until ELO is wired in.
    """
    def __init__(self, k=5, elo_games_per_match=50, mode='recent'):
        self.k = k
        self.snapshots = []   # list of dicts: {state_dict, elo, id}
        self.elo_games = elo_games_per_match
        self.next_id = 0
        # mode: 'recent' (Patch 4 on, honest recent-K, default)
        #       'frozen_first_k' (Patch 4 off, reproduces V4-era buggy behavior:
        #          sort by elo desc + take first K. With all elo==1500 the stable
        #          sort keeps insertion order and new snapshots get dropped, so
        #          the pool is effectively frozen after the first K adds.)
        assert mode in ('recent', 'frozen_first_k'), f'unknown pool mode: {mode}'
        self.mode = mode

    def add(self, model_state, initial_elo=1500.0):
        snap = {
            'state_dict': {k: v.clone() for k, v in model_state.items()},
            'elo': initial_elo,
            'id': self.next_id,
        }
        self.next_id += 1
        self.snapshots.append(snap)
        if self.mode == 'recent':
            # Recent-K: keep the most-recently-added K snapshots (Patch 4 ON).
            if len(self.snapshots) > self.k:
                self.snapshots = self.snapshots[-self.k:]
        else:
            # frozen_first_k: V4-era buggy behavior (Patch 4 OFF).
            self.snapshots.sort(key=lambda x: x['elo'], reverse=True)
            if len(self.snapshots) > self.k:
                self.snapshots = self.snapshots[:self.k]

    def get_opponent(self, idx: int):
        """Return state_dict of opponent index idx mod pool size."""
        if not self.snapshots:
            return None
        return self.snapshots[idx % len(self.snapshots)]['state_dict']

    def size(self):
        return len(self.snapshots)

    def update_elo(self, idx: int, wins: int, total: int, k_factor=32):
        """Simple ELO update after a mini-tournament."""
        if idx >= len(self.snapshots):
            return
        snap = self.snapshots[idx]
        # Expected win rate based on ELO diff vs average pool ELO
        avg_elo = np.mean([s['elo'] for s in self.snapshots])
        ea = 1 / (1 + 10 ** ((avg_elo - snap['elo']) / 400))
        actual = wins / total if total > 0 else 0.5
        snap['elo'] += k_factor * (actual - ea)
        self.snapshots.sort(key=lambda x: x['elo'], reverse=True)


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--workers', type=int, default=28)
    parser.add_argument('--hands-per-iter', type=int, default=16384)
    parser.add_argument('--total-hands', type=int, default=1_000_000_000,
                        help='Absolute target total_hands. Controls both stop condition AND lr-decay schedule.')
    parser.add_argument('--max-additional-hands', type=int, default=0,
                        help='If >0, stop after this many ADDITIONAL hands past --resume checkpoint. '
                             'Use with a large --total-hands to suppress lr decay during a short extension.')
    parser.add_argument('--disable-lr-decay', action='store_true',
                        help='Skip the progress-based linear lr decay entirely.')
    parser.add_argument('--starting-stack', type=float, default=200.0, help='BB units')
    parser.add_argument('--lr', type=float, default=3e-4)
    parser.add_argument('--ppo-epochs', type=int, default=4)
    parser.add_argument('--mini-batch-size', type=int, default=1024)
    parser.add_argument('--epsilon', type=float, default=0.15)
    parser.add_argument('--gamma', type=float, default=0.999)
    parser.add_argument('--delta1', type=float, default=3.0)
    parser.add_argument('--entropy-coef', type=float, default=0.01)
    parser.add_argument('--k-best', type=int, default=5)
    parser.add_argument('--pool-mode', choices=('recent', 'frozen_first_k'), default='recent',
                        help="Pool refresh policy. 'recent' (default, Patch 4 ON) keeps the last K "
                             "snapshots. 'frozen_first_k' reproduces V4-era buggy behavior: pool "
                             "fills with first K snapshots then never refreshes (Patch 4 OFF).")
    parser.add_argument('--snapshot-every', type=int, default=200, help='iterations between snapshots')
    parser.add_argument('--save-interval', type=int, default=100)
    parser.add_argument('--out', default='models/alpha_holdem_v4.pt')
    parser.add_argument('--resume', default=None)
    parser.add_argument('--slumbot-mimic-path', default=None,
                        help='Path to a Slumbot mimic checkpoint. If set, the pool is '
                             'frozen to this single mimic and no further snapshots are added.')
    parser.add_argument('--self-play-fraction', type=float, default=0.2,
                        help='Probability per worker of using hero (self-play) vs an opponent. '
                             '0.0 forces opponent every hand.')
    parser.add_argument('--opponent-temperature', type=float, default=1.0,
                        help='Softmax temperature applied to opponent (pool) logits before sampling. '
                             'T>1 flattens (more action diversity), T<1 sharpens. Hero always uses T=1.')
    parser.add_argument('--bf16', action='store_true',
                        help='Enable bf16 mixed precision for inference + PPO updates (Ada/Ampere+ GPUs).')
    parser.add_argument('--compile', dest='compile_model', action='store_true',
                        help='Apply torch.compile to the hero model for fused kernels (PyTorch 2+).')
    args = parser.parse_args()

    device = args.device
    W = args.workers
    print(f'Device: {device}')
    if device == 'cuda':
        print(f'GPU: {torch.cuda.get_device_name(0)}')

    model = AlphaHoldemNet(num_actions=NUM_ACTIONS).to(device)
    dc = torch.zeros(1, 6, 4, 13, device=device)
    da = torch.zeros(1, 25, 4, 5, device=device)
    de = torch.zeros(1, 2, device=device)
    model(dc, da, de)
    print(f'Parameters: {count_parameters(model):,}')
    if args.bf16 and device == 'cuda':
        print('bf16 mixed precision: ENABLED')

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    pool = KBestPool(k=args.k_best, mode=args.pool_mode)
    slumbot_mimic_locked = False
    if args.slumbot_mimic_path:
        mimic_ckpt = torch.load(args.slumbot_mimic_path, map_location='cpu', weights_only=False)
        mimic_state = mimic_ckpt.get('model', mimic_ckpt)
        pool.add({k: v.clone() for k, v in mimic_state.items()})
        slumbot_mimic_locked = True
        print(f'Slumbot-mimic mode: opponent locked to {args.slumbot_mimic_path} '
              f'(self_play_fraction={args.self_play_fraction})')

    total_hands = 0
    iteration = 0
    if args.resume and os.path.exists(args.resume):
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model'])
        optimizer.load_state_dict(ckpt['optimizer'])
        # load_state_dict overwrote the lr from the checkpoint's optimizer state.
        # Force args.lr to actually take effect on resume.
        for pg in optimizer.param_groups:
            pg['lr'] = args.lr
        total_hands = ckpt.get('total_hands', 0)
        iteration = ckpt.get('iteration', 0)
        if 'pool_snapshots' in ckpt and not slumbot_mimic_locked:
            for snap in ckpt['pool_snapshots']:
                pool.snapshots.append(snap)
            # Resume in recent-K order: prefer the K most-recent snapshots by id.
            # (Older checkpoints have all-equal elo, so id is the only stable key.)
            pool.snapshots.sort(key=lambda x: x.get('id', 0))
            if len(pool.snapshots) > pool.k:
                pool.snapshots = pool.snapshots[-pool.k:]
            # Continue next_id past whatever ids are in the checkpoint so new
            # snapshots stay strictly ordered.
            if pool.snapshots:
                pool.next_id = max(s.get('id', 0) for s in pool.snapshots) + 1
        if slumbot_mimic_locked:
            # Mimic was added first (before resume), keep only that snapshot.
            pool.snapshots = pool.snapshots[:1]
        print(f'Resumed: {total_hands:,} hands, {len(pool.snapshots)} snapshots in pool (K={pool.k})')

    # Apply torch.compile AFTER load_state_dict so the saved state_dict keys match
    if args.compile_model:
        print('torch.compile: wrapping model with mode=reduce-overhead...')
        try:
            model = torch.compile(model, mode='reduce-overhead', fullgraph=False)
            model(dc, da, de)
            model(torch.zeros(64, 6, 4, 13, device=device),
                  torch.zeros(64, 25, 4, 5, device=device),
                  torch.zeros(64, 2, device=device))
            print('  compile warmup done.')
        except Exception as e:
            print(f'  compile failed ({e}); continuing without compile.')

    log_path = args.out.replace('.pt', '.log')

    # Allocate shared memory (persistent).
    # Split opponent buffer into two single-writer/single-reader buffers:
    #   assigned_opp_shm   — main writes once per iter; worker reads at hand start.
    #   request_shm        — worker writes per decision; main reads for inference grouping.
    obs_shm = shared_memory.SharedMemory(create=True, size=W * OBS_SIZE * 4)
    result_shm = shared_memory.SharedMemory(create=True, size=W * RESULT_SIZE * 4)
    status_shm = shared_memory.SharedMemory(create=True, size=W * 4)
    assigned_opp_shm = shared_memory.SharedMemory(create=True, size=W * 4)
    request_shm = shared_memory.SharedMemory(create=True, size=W * 4)

    obs_np = np.ndarray((W * OBS_SIZE,), dtype=np.float32, buffer=obs_shm.buf)
    result_np = np.ndarray((W * RESULT_SIZE,), dtype=np.float32, buffer=result_shm.buf)
    status_np = np.ndarray((W,), dtype=np.int32, buffer=status_shm.buf)
    assigned_opp_id_np = np.ndarray((W,), dtype=np.int32, buffer=assigned_opp_shm.buf)
    request_model_id_np = np.ndarray((W,), dtype=np.int32, buffer=request_shm.buf)
    obs_np[:] = 0; result_np[:] = 0; status_np[:] = IDLE
    assigned_opp_id_np[:] = -1
    request_model_id_np[:] = -1

    epsilon_val = mp.Value('d', args.epsilon)
    stop_event = mp.Event()

    pipes = []
    procs = []
    for w in range(W):
        parent_conn, child_conn = mp.Pipe()
        pipes.append(parent_conn)
        p = mp.Process(
            target=worker_process,
            args=(w, obs_shm.name, result_shm.name, status_shm.name,
                  assigned_opp_shm.name, request_shm.name,
                  child_conn, stop_event, args.starting_stack),
            daemon=True,
        )
        p.start()
        child_conn.close()
        procs.append(p)

    print(f'\nStarted {W} workers @ {args.starting_stack} BB')
    print(f'Target: {args.total_hands:,} hands')
    print(f'Trinal-Clip PPO: eps={args.delta1 and 0.2}, delta1={args.delta1}, gamma={args.gamma}')
    print(f'K-best pool: K={args.k_best}, snapshot every {args.snapshot_every} iter')
    print('-' * 80)

    # Opponent models (load pool snapshots into GPU for inference)
    opp_models = []
    def rebuild_opp_models():
        """Load pool snapshots into AlphaHoldemNet instances on GPU."""
        opp_models.clear()
        for snap in pool.snapshots:
            m = AlphaHoldemNet(num_actions=NUM_ACTIONS).to(device)
            m(dc, da, de)  # lazy init
            m.load_state_dict(snap['state_dict'])
            m.eval()
            opp_models.append(m)

    rebuild_opp_models()

    reward_window = deque(maxlen=100)
    iter_transitions = []
    iter_reward = 0.0
    iter_hands = 0
    t0 = time.time()

    # Rotate opponent per worker each iteration.
    # NOTE: writes only to assigned_opp_id_np. Workers read this at hand start;
    # they NEVER write to it. (-1 = self-play, >=0 = pool index.)
    # Workers signal their per-decision model choice via request_model_id_np.
    def assign_opponents():
        sp_frac = args.self_play_fraction
        for w in range(W):
            if pool.size() == 0:
                assigned_opp_id_np[w] = -1  # self-play
            else:
                if sp_frac > 0 and random.random() < sp_frac:
                    assigned_opp_id_np[w] = -1
                else:
                    assigned_opp_id_np[w] = random.randint(0, pool.size() - 1)

    assign_opponents()

    start_hands = total_hands
    additional_cap = args.max_additional_hands

    try:
        model.eval()
        while total_hands < args.total_hands:
            if additional_cap > 0 and (total_hands - start_hands) >= additional_cap:
                print(f'[stop] hit --max-additional-hands cap ({additional_cap:,}); '
                      f'extended {total_hands - start_hands:,} hands from {start_hands:,}.')
                break
            # Run batched GPU inference (hero or pool opponents).
            # Grouping uses request_model_id_np (worker-owned), not assignment.
            # epsilon is folded into the hero behavior policy in master inference.
            run_inference_kbest(
                model, opp_models,
                obs_np, result_np, status_np, request_model_id_np,
                W, device,
                epsilon=float(epsilon_val.value),
                opponent_temperature=args.opponent_temperature,
                bf16=args.bf16,
            )

            # Drain pipes
            for pipe in pipes:
                try:
                    while pipe.poll():
                        data = pipe.recv()
                        if data is None:
                            continue
                        for t in data:
                            iter_transitions.append(t)
                            if t[8] > 0.5:
                                iter_reward += t[6]
                                iter_hands += 1
                except (BrokenPipeError, EOFError):
                    pass

            # PPO update when enough hands
            if iter_hands >= args.hands_per_iter and len(iter_transitions) > 0:
                iteration += 1
                collect_time = time.time() - t0

                progress = total_hands / args.total_hands
                eps_decay = max(0.05, args.epsilon * (1 - max(0, progress - 0.8) / 0.2))
                epsilon_val.value = eps_decay

                # LR decay: linear from args.lr to args.lr / 3 over second half of training
                if (not args.disable_lr_decay) and progress >= 0.5:
                    decay_frac = (progress - 0.5) / 0.5  # 0 → 1 in second half
                    new_lr = args.lr * (1 - decay_frac * (1 - 1/3))  # decay to 1/3
                    for pg in optimizer.param_groups:
                        pg['lr'] = new_lr

                t1 = time.time()
                stats = trinal_clip_ppo_update(
                    model, optimizer, iter_transitions, device,
                    epochs=args.ppo_epochs,
                    mini_batch_size=args.mini_batch_size,
                    delta1=args.delta1,
                    gamma=args.gamma,
                    entropy_coef=args.entropy_coef,
                    bf16=args.bf16,
                )
                ppo_time = time.time() - t1

                total_hands += iter_hands
                elapsed = time.time() - t0
                h_per_s = iter_hands / elapsed if elapsed > 0 else 0
                avg_rew = iter_reward / max(iter_hands, 1)
                reward_window.append(avg_rew)
                rew100 = np.mean(reward_window)

                log_line = (
                    f"[{iteration:5d}] "
                    f"hands={total_hands:,} "
                    f"rew={avg_rew:+.3f} "
                    f"rew100={rew100:+.3f} "
                    f"ploss={stats['policy_loss']:.4f} "
                    f"vloss={stats['value_loss']:.4f} "
                    f"ent={stats['entropy']:.4f} "
                    f"kl={stats['approx_kl']:+.4f} "
                    f"clipfrac={stats['clip_frac']:.3f} "
                    f"d1bite={stats['delta1_bite_frac']:.3f} "
                    f"r50={stats['ratio_p50']:.2f}/r95={stats['ratio_p95']:.2f}/r99={stats['ratio_p99']:.2f}/rmax={stats['ratio_max']:.2f} "
                    f"eps={eps_decay:.3f} "
                    f"pool={pool.size()} "
                    f"trans={len(iter_transitions)} "
                    f"h/s={h_per_s:.0f} "
                    f"col={collect_time:.1f} ppo={ppo_time:.1f} "
                    f"t={elapsed:.1f}s"
                )
                print(log_line)
                with open(log_path, 'a') as f:
                    f.write(log_line + '\n')

                # Snapshot to pool (skipped if opponent is locked to Slumbot mimic)
                if not slumbot_mimic_locked and iteration % args.snapshot_every == 0:
                    pool.add({k.replace('_orig_mod.', '', 1): v.cpu()
                              for k, v in model.state_dict().items()})
                    rebuild_opp_models()
                    print(f'  [Pool] Added snapshot. Size: {pool.size()}')

                # Save checkpoint
                if iteration % args.save_interval == 0:
                    torch.save({
                        'model': {k.replace('_orig_mod.', '', 1): v for k, v in model.state_dict().items()},
                        'optimizer': optimizer.state_dict(),
                        'total_hands': total_hands,
                        'iteration': iteration,
                        'pool_snapshots': pool.snapshots,
                        # Encoder metadata — so play_slumbot.py / evaluate.py never have to guess.
                        'env_version': 'v4',
                        'obs_version': 'v4',
                        'action_space_version': '9slot_v4',
                        'starting_stack_bb': args.starting_stack,
                    }, args.out)
                    print(f'  [Save] {args.out} ({total_hands:,} hands, pool={pool.size()})')

                # Rotate opponents for next batch
                assign_opponents()

                iter_transitions = []
                iter_reward = 0.0
                iter_hands = 0
                t0 = time.time()
                model.eval()

            time.sleep(0.00001)

    except KeyboardInterrupt:
        print('\nInterrupted.')
    finally:
        stop_event.set()
        time.sleep(1)
        for p in procs:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()
        obs_shm.close(); obs_shm.unlink()
        result_shm.close(); result_shm.unlink()
        status_shm.close(); status_shm.unlink()
        assigned_opp_shm.close(); assigned_opp_shm.unlink()
        request_shm.close(); request_shm.unlink()

    torch.save({
        'model': {k.replace('_orig_mod.', '', 1): v for k, v in model.state_dict().items()},
        'optimizer': optimizer.state_dict(),
        'total_hands': total_hands,
        'iteration': iteration,
        'pool_snapshots': pool.snapshots,
    }, args.out)
    print(f'Done! {total_hands:,} hands. Saved to {args.out}')


if __name__ == '__main__':
    mp.set_start_method('spawn')
    main()
