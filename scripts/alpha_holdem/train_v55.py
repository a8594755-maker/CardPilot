#!/usr/bin/env python3
"""
AlphaHoldem V5.5 trainer — Phase 0 + Phase 2 of the V5.5 synthesis plan.

Phase 0 (bug fixes, no algorithm change):
- environment_v55.py: raise_cap_per_street=999, fixed action history, real action cache
- real_hands counter separate from inflated terminal count
- honest log line (no V5.0 false claims)

Phase 2 (EMA Shadow Opponent — biggest single GPU-utilization unlock):
- Replace K=5 LatestKPool with a SINGLE EMA-weighted shadow network.
- After each PPO update: theta_ema <- alpha * theta_ema + (1-alpha) * theta
- alpha=0.999 by default => half-life ~ ln(2)/ln(1/0.999) = 693 PPO steps,
  ~10h wall-clock at typical iter cadence. Strong fictitious-play behavior.
- Inference batch fragmentation drops from {1 hero + 5 opp} = 6 groups to
  {1 hero + 1 EMA} = 2 groups => inf_bs jumps 5 -> ~14 (2.8x GPU lift).
- Math: vs an EMA of past selves is the standard NFSP/fictitious-play setup;
  for zero-sum games the Cesaro average of best-responses converges to a
  Nash neighborhood (Robinson 1951). Concretely, the cycling that V4 hit at
  700M (vloss 102 -> 11000, entropy 1.15 -> 0.10) is what an EMA opponent
  is designed to break: the opponent doesn't react fast enough to follow
  exploits, so the model's gradient pulls toward a stable equilibrium.

V5.0 features RETAINED (structurally correct):
- --epsilon 0 default
- Split shm: assigned_opp_id (main writes) vs request_model_id (worker writes)
- Both-player collection (live but only triggers if --ema-only-fraction < 1.0,
  i.e., when some hands are pure self-play)
- New metrics scaffold (tdec/s, inf_bs)

V4 baseline preserved untouched: train_mp3.py + environment.py + alpha_holdem_v4_final.pt.

Domain-shift warning when resuming from V4 weights:
- V4 was trained under raise_cap_per_street=1 (no postflop re-raises).
- V5.5 unleashes the full action tree.
- Expect vloss spike + entropy oscillation in first 10-20M hands as the network
  adapts to states it's never seen (postflop check-raise / re-raise scenarios).
- This is transfer learning from a partially-correct prior, not a regression.

Typical resume from V4 final:
  python scripts/alpha_holdem/train_v55.py \\
    --resume models/alpha_holdem_v4_final.pt \\
    --out models/alpha_holdem_v55.pt \\
    --device cuda --workers 28 \\
    --total-hands 1500000000 \\
    --lr 1e-4 --epsilon 0
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

from alpha_holdem.network import AlphaHoldemNet, count_parameters
from alpha_holdem.environment_v55 import NUM_ACTIONS  # V5.5 env

# Reuse V4 GAE math; PPO update gets MMD-aware variant below.
from alpha_holdem.train_mp3 import compute_gae, trinal_clip_ppo_update


# ===========================================================
# MMD-augmented Trinal-Clip PPO (Sokota et al. 2022 idea)
# ===========================================================
# Adds a magnetic anchor term: -mmd_lambda * KL(pi_hero || pi_anchor)
# Anchor = EMA opponent. Pulls hero policy toward the slow-moving average,
# preventing the wild dimension-hopping that produced wave 2 cycling under
# pure EMA fictitious-play. Theory: under MMD, the joint dynamics have a
# last-iterate convergence guarantee for zero-sum games (vs Cesaro-only
# average convergence under naive fictitious-play).
#
# Implementation note: anchor is forwarded inside the PPO minibatch loop
# under torch.no_grad. Adds ~1 forward pass per minibatch (~80% PPO time
# overhead). Anchor weights frozen during PPO; only updated by ema.update()
# in main loop after PPO finishes.
def mmd_trinal_clip_ppo_update(
    model, optimizer, transitions, device,
    anchor_model,
    mmd_lambda: float,
    epochs=4, mini_batch_size=1024,
    eps=0.2, delta1=3.0,
    value_coef=0.5,
    entropy_coef=0.05,
    entropy_floor=0.3,
    max_grad_norm=0.5,
    gamma=0.999,
) -> dict:
    """Trinal-Clip PPO + MMD (KL-to-anchor) regularizer.

    Returns stats dict with policy_loss, value_loss, entropy, AND mmd_kl
    (mean KL divergence between hero and anchor across the update).
    """
    model.train()
    anchor_model.eval()
    n = len(transitions)

    card_arr = np.array([t[0].reshape(6, 4, 13) for t in transitions])
    action_arr = np.array([t[1].reshape(25, 4, 5) for t in transitions])
    extra_arr = np.array([t[2] for t in transitions])
    mask_arr = np.array([t[3] for t in transitions])
    act_arr = np.array([t[4] for t in transitions])
    lp_arr = np.array([t[5] for t in transitions])
    rew_arr = np.array([t[6] for t in transitions])
    val_arr = np.array([t[7] for t in transitions])
    done_arr = np.array([t[8] for t in transitions])
    hero_chips_arr = np.array([t[9] for t in transitions])
    villain_chips_arr = np.array([t[10] for t in transitions])

    advantages, returns = compute_gae(rew_arr, val_arr, done_arr, gamma=gamma)

    cards_t = torch.tensor(card_arr, dtype=torch.float32, device=device)
    actions_t = torch.tensor(action_arr, dtype=torch.float32, device=device)
    extras_t = torch.tensor(extra_arr, dtype=torch.float32, device=device)
    masks_t = torch.tensor(mask_arr, dtype=torch.float32, device=device)
    acts_t = torch.tensor(act_arr, dtype=torch.long, device=device)
    old_lp_t = torch.tensor(lp_arr, dtype=torch.float32, device=device)
    adv_t = torch.tensor(advantages, dtype=torch.float32, device=device)
    ret_t = torch.tensor(returns, dtype=torch.float32, device=device)
    delta2_t = torch.tensor(hero_chips_arr, dtype=torch.float32, device=device)
    delta3_t = torch.tensor(villain_chips_arr, dtype=torch.float32, device=device)

    if n > 1:
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

    tp = tv = te = tk = 0.0
    nu = 0

    for _ in range(epochs):
        indices = torch.randperm(n, device=device)
        for start in range(0, n, mini_batch_size):
            end = min(start + mini_batch_size, n)
            idx = indices[start:end]

            logits, values = model(cards_t[idx], actions_t[idx], extras_t[idx], masks_t[idx])
            probs = F.softmax(logits, dim=-1)
            log_probs = F.log_softmax(logits, dim=-1)
            dist = Categorical(probs)
            new_lp = dist.log_prob(acts_t[idx])
            entropy = dist.entropy().mean()

            # Trinal-Clip Policy Loss (Eq. 3)
            ratio = torch.exp(new_lp - old_lp_t[idx])
            adv_batch = adv_t[idx]
            ratio_clipped = torch.clamp(ratio, 1 - eps, 1 + eps)
            ratio_double_clipped = torch.clamp(ratio_clipped, max=delta1)
            surr1 = ratio * adv_batch
            surr2 = ratio_double_clipped * adv_batch
            ploss = -torch.min(surr1, surr2).mean()

            # Trinal-Clip Value Loss (Eq. 4)
            ret_batch = ret_t[idx]
            d2 = delta2_t[idx]
            d3 = delta3_t[idx]
            ret_clipped = torch.max(torch.min(ret_batch, d3), -d2)
            vloss = F.mse_loss(values.squeeze(-1), ret_clipped)

            # MMD KL anchor: KL(pi_hero || pi_anchor)
            with torch.no_grad():
                anchor_logits, _ = anchor_model(
                    cards_t[idx], actions_t[idx], extras_t[idx], masks_t[idx]
                )
                anchor_log_probs = F.log_softmax(anchor_logits, dim=-1)
            # KL(hero || anchor) = sum_a hero(a) * (log hero(a) - log anchor(a))
            mmd_kl = (probs * (log_probs - anchor_log_probs)).sum(dim=-1).mean()

            # Entropy boost when below floor (V4 safety net)
            ec = entropy_coef * 5.0 if entropy.item() < entropy_floor else entropy_coef

            loss = ploss + value_coef * vloss - ec * entropy + mmd_lambda * mmd_kl

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            optimizer.step()

            tp += ploss.item()
            tv += vloss.item()
            te += entropy.item()
            tk += mmd_kl.item()
            nu += 1

    return {
        'policy_loss': tp / max(nu, 1),
        'value_loss': tv / max(nu, 1),
        'entropy': te / max(nu, 1),
        'mmd_kl': tk / max(nu, 1),
    }

# ===========================================================
# Shared Memory Layout (unchanged from V5.0 — same network input shape)
# ===========================================================

CARD_SIZE = 6 * 4 * 13       # 312
ACTION_SIZE = 25 * 4 * 5     # 500
EXTRA_SIZE = 2
MASK_SIZE = NUM_ACTIONS       # 9
OBS_SIZE = CARD_SIZE + ACTION_SIZE + EXTRA_SIZE + MASK_SIZE  # 823
RESULT_SIZE = 3

IDLE = 0
WAITING = 1
READY = 2

HERO_MODEL_ID = -1


# ===========================================================
# Worker (V5.5): same as V5.0 logic, but:
#   - imports HUNLEnvironment from environment_v55 (gets the bug fixes for free)
#   - sends (real_hands_in_batch, transitions) tuple, not bare transition list
# ===========================================================

def worker_process_v55(
    worker_id,
    obs_shm_name,
    result_shm_name,
    status_shm_name,
    assigned_opp_shm_name,
    request_model_shm_name,
    transition_pipe,
    stop_event,
    epsilon_value,
    starting_stack,
    env_version,
    collect_self_play_both,
):
    """Persistent self-play worker. V5.5: env_v55 + real hand counter in pipe."""
    import sys as _sys
    import os as _os
    import time as _time
    import random as _random
    import numpy as _np
    from multiprocessing import shared_memory as _shm

    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..'))
    if env_version == 'v4':
        from alpha_holdem.environment import HUNLEnvironment
        env_kwargs = {'starting_stack': starting_stack}
    elif env_version == 'v55cap1':
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {'starting_stack': starting_stack, 'raise_cap_per_street': 1}
    elif env_version == 'v55cap1v4obs':
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {
            'starting_stack': starting_stack,
            'raise_cap_per_street': 1,
            'action_history_style': 'v4',
        }
    else:
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {'starting_stack': starting_stack}

    obs_shm = _shm.SharedMemory(name=obs_shm_name)
    result_shm = _shm.SharedMemory(name=result_shm_name)
    status_shm = _shm.SharedMemory(name=status_shm_name)
    assigned_shm = _shm.SharedMemory(name=assigned_opp_shm_name)
    request_shm = _shm.SharedMemory(name=request_model_shm_name)

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
    assigned_buf = _np.ndarray(
        (1,), dtype=_np.int32,
        buffer=assigned_shm.buf[worker_id * 4:(worker_id + 1) * 4],
    )
    request_buf = _np.ndarray(
        (1,), dtype=_np.int32,
        buffer=request_shm.buf[worker_id * 4:(worker_id + 1) * 4],
    )

    env = HUNLEnvironment(**env_kwargs)
    hands_played = 0
    local_transitions = []
    local_real_hands = 0   # V5.5: real hand counter for this batch
    local_hero_reward = 0.0

    try:
        while not stop_event.is_set():
            current_opp_id = int(assigned_buf[0])
            is_self_play = (current_opp_id == -1)

            obs = env.reset()
            done = False
            hero_player = hands_played % 2

            hand_buffers = {0: [], 1: []}
            last_actor = None

            while not done and not stop_event.is_set():
                player = obs['player']
                is_hero = (player == hero_player)

                req_model = HERO_MODEL_ID if (is_self_play or is_hero) else current_opp_id

                ci = obs['card_info'].flatten()
                ai = obs['action_info'].flatten()
                ei = obs['extra_info']
                lm = obs['legal_mask']

                obs_buf[:CARD_SIZE] = ci
                obs_buf[CARD_SIZE:CARD_SIZE + ACTION_SIZE] = ai
                obs_buf[CARD_SIZE + ACTION_SIZE:CARD_SIZE + ACTION_SIZE + EXTRA_SIZE] = ei
                obs_buf[CARD_SIZE + ACTION_SIZE + EXTRA_SIZE:] = lm

                request_buf[0] = req_model
                status_buf[0] = WAITING

                while status_buf[0] != READY:
                    if stop_event.is_set():
                        break
                    _time.sleep(0.000001)

                if stop_event.is_set():
                    break

                action_idx = int(result_buf[0])
                log_prob = float(result_buf[1])
                value = float(result_buf[2])
                status_buf[0] = IDLE

                eps = epsilon_value.value
                if is_hero and eps > 0.0 and _random.random() < eps:
                    legal = _np.where(lm > 0)[0]
                    if len(legal) > 0:
                        action_idx = int(_random.choice(legal))

                acted_by_trainable_model = is_hero or (is_self_play and collect_self_play_both)
                if acted_by_trainable_model:
                    hand_buffers[player].append((
                        ci.copy(), ai.copy(), ei.copy(), lm.copy(),
                        action_idx, log_prob, value,
                    ))

                last_actor = player
                obs, reward, done = env.step(action_idx)

            chips = {
                0: env.chips_committed(0),
                1: env.chips_committed(1),
            }
            rewards_per_player = {}
            if last_actor is not None:
                rewards_per_player[last_actor] = reward
                rewards_per_player[1 - last_actor] = -reward
            local_hero_reward += float(rewards_per_player.get(hero_player, 0.0))

            for p in (0, 1):
                buf = hand_buffers[p]
                if not buf:
                    continue
                pr = rewards_per_player.get(p, 0.0)
                p_chips = chips[p]
                v_chips = chips[1 - p]
                for i, (ci_s, ai_s, ei_s, lm_s, act, lp, val) in enumerate(buf):
                    is_last = (i == len(buf) - 1)
                    local_transitions.append((
                        ci_s, ai_s, ei_s, lm_s, act, lp,
                        pr if is_last else 0.0,
                        val,
                        1.0 if is_last else 0.0,
                        p_chips,
                        v_chips,
                    ))

            hands_played += 1
            local_real_hands += 1   # V5.5: count once per hand, not per terminal

            if hands_played % 50 == 0 and (local_transitions or local_real_hands):
                try:
                    transition_pipe.send((local_real_hands, local_hero_reward, local_transitions))
                except BrokenPipeError:
                    break
                local_transitions = []
                local_real_hands = 0
                local_hero_reward = 0.0

        if local_transitions or local_real_hands:
            try:
                transition_pipe.send((local_real_hands, local_hero_reward, local_transitions))
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


# ===========================================================
# Inference (V5.5): same flat-view group-by request_model_id as V5.0.
# Honest note: still has copy from advanced indexing + ascontiguousarray.
# Phase 1 (compact transitions) is where this gets a real fix.
# ===========================================================

@torch.no_grad()
def run_inference_v55(
    hero_model: AlphaHoldemNet,
    opp_models: list,
    obs_np, result_np, status_np, request_model_np,
    num_workers: int,
    device: str,
    batch_size_log: list,
) -> int:
    waiting_mask = (status_np == WAITING)
    if not waiting_mask.any():
        return 0

    obs_view = obs_np.reshape(num_workers, OBS_SIZE)
    waiting_idx = np.flatnonzero(waiting_mask)
    rm = request_model_np[waiting_idx]

    total = 0
    unique_models = np.unique(rm)
    for mid in unique_models:
        sel = waiting_idx[rm == mid]
        if sel.size == 0:
            continue
        model = hero_model if int(mid) == HERO_MODEL_ID else opp_models[int(mid) % len(opp_models)]

        batch_np = obs_view[sel]
        batch_t = torch.from_numpy(np.ascontiguousarray(batch_np)).to(device, non_blocking=True)
        cards_t = batch_t[:, :CARD_SIZE].view(-1, 6, 4, 13)
        actions_t = batch_t[:, CARD_SIZE:CARD_SIZE + ACTION_SIZE].view(-1, 25, 4, 5)
        extras_t = batch_t[:, CARD_SIZE + ACTION_SIZE:CARD_SIZE + ACTION_SIZE + EXTRA_SIZE]
        masks_t = batch_t[:, CARD_SIZE + ACTION_SIZE + EXTRA_SIZE:]

        logits, values = model(cards_t, actions_t, extras_t, masks_t)
        probs = F.softmax(logits, dim=-1)
        dist = Categorical(probs)
        sampled = dist.sample()
        log_probs = dist.log_prob(sampled)

        s_np = sampled.cpu().numpy()
        lp_np = log_probs.cpu().numpy()
        v_np = values.squeeze(-1).cpu().numpy()

        for i, w in enumerate(sel):
            r_off = int(w) * RESULT_SIZE
            result_np[r_off] = s_np[i]
            result_np[r_off + 1] = lp_np[i]
            result_np[r_off + 2] = v_np[i]
            status_np[int(w)] = READY

        batch_size_log.append(int(sel.size))
        total += int(sel.size)

    return total


# ===========================================================
# Phase 2: EMA Shadow Opponent (replaces LatestKPool)
# ===========================================================

class EMAOpponent:
    """Single shadow opponent with EMA-updated weights.

    Replaces K-best/LatestK pool. After each PPO step:
        theta_ema <- alpha * theta_ema + (1 - alpha) * theta

    EMA represents an exponentially weighted average of past policies.
    Playing against this is fictitious-play-ish (Brown 1951, Robinson 1951);
    in zero-sum settings the Cesaro mean of best-responses converges to a
    Nash neighborhood. Empirically used in NFSP/MFP literatures.

    Stored on CPU (state_dict cloned to CPU) to avoid duplicate GPU memory;
    `load_into(target_model)` copies to GPU each iter for inference.
    """

    def __init__(self, model: 'AlphaHoldemNet', alpha: float = 0.999):
        self.alpha = float(alpha)
        # CPU master copy (avoids holding two full nets on GPU)
        self.state_dict = {
            k: v.detach().cpu().clone() for k, v in model.state_dict().items()
        }

    def update(self, model: 'AlphaHoldemNet') -> None:
        """In-place EMA update. Call once per PPO step."""
        with torch.no_grad():
            for k, v in model.state_dict().items():
                # Skip non-floating-point tensors (buffers like int counters)
                target = self.state_dict[k]
                if hasattr(target, "device") and target.device.type != "cpu":
                    target = target.detach().cpu().clone()
                    self.state_dict[k] = target
                if target.is_floating_point() and v.is_floating_point():
                    target.mul_(self.alpha).add_(v.detach().cpu(), alpha=1.0 - self.alpha)
                else:
                    target.copy_(v.detach().cpu())

    def load_into(self, target_model: 'AlphaHoldemNet') -> None:
        """Copy EMA weights into a GPU model instance for inference."""
        target_model.load_state_dict(self.state_dict)

    def half_life_iters(self) -> float:
        """How many EMA updates to halve the contribution of any single past weight."""
        if self.alpha >= 1.0 or self.alpha <= 0.0:
            return float('inf')
        return math.log(0.5) / math.log(self.alpha)


# Legacy/V4-compatible snapshot pool.
class LatestKPool:
    def __init__(self, k=5, update_mode='latest'):
        self.k = k
        self.update_mode = update_mode
        self.snapshots = []
        self.next_id = 0

    def add(self, model_state, hands=0):
        if self.update_mode == 'frozen' and len(self.snapshots) >= self.k:
            return
        snap = {'state_dict': {kk: vv.detach().cpu().clone() for kk, vv in model_state.items()},
                'id': self.next_id, 'hands': hands}
        self.next_id += 1
        self.snapshots.append(snap)
        if len(self.snapshots) > self.k:
            if self.update_mode in ('oldest', 'frozen'):
                self.snapshots = self.snapshots[:self.k]
            else:
                self.snapshots = self.snapshots[-self.k:]

    def size(self):
        return len(self.snapshots)

    def load_from_checkpoint(self, snapshots, hands=0):
        self.snapshots = []
        self.next_id = 0
        for snap in snapshots or []:
            state_dict = snap.get('state_dict', snap) if isinstance(snap, dict) else snap
            snap_id = snap.get('id', self.next_id) if isinstance(snap, dict) else self.next_id
            self.snapshots.append({
                'state_dict': {kk: vv.detach().cpu().clone() for kk, vv in state_dict.items()},
                'id': snap_id,
                'hands': snap.get('hands', hands) if isinstance(snap, dict) else hands,
            })
            try:
                self.next_id = max(self.next_id, int(snap_id) + 1)
            except (TypeError, ValueError):
                self.next_id += 1
        if len(self.snapshots) > self.k:
            if self.update_mode in ('oldest', 'frozen'):
                self.snapshots = self.snapshots[:self.k]
            else:
                self.snapshots = self.snapshots[-self.k:]


# ===========================================================
# Main
# ===========================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--workers', type=int, default=28)
    parser.add_argument('--hands-per-iter', type=int, default=16384)
    parser.add_argument('--total-hands', type=int, default=2_000_000_000)
    parser.add_argument('--starting-stack', type=float, default=200.0)
    parser.add_argument('--lr', type=float, default=1e-4)
    parser.add_argument('--ppo-epochs', type=int, default=4)
    parser.add_argument('--mini-batch-size', type=int, default=1024)
    parser.add_argument('--epsilon', type=float, default=0.0)
    parser.add_argument('--epsilon-min', type=float, default=0.0)
    parser.add_argument('--gamma', type=float, default=0.999)
    parser.add_argument('--delta1', type=float, default=3.0)
    parser.add_argument('--entropy-coef', type=float, default=0.01)
    parser.add_argument('--entropy-floor', type=float, default=0.3)
    parser.add_argument('--k-best', type=int, default=5,
                        help='LatestK pool size for pool/hybrid opponent modes')
    parser.add_argument('--pool-update-mode', choices=('latest', 'oldest', 'frozen'), default='latest',
                        help='latest=keep newest K; oldest/frozen matches actual V4 K-best behavior when Elo is tied.')
    parser.add_argument('--collect-self-play-both', action='store_true', default=False,
                        help='Train on both seats in pure self-play hands. Off matches V4 hero-only collection.')
    parser.add_argument('--snapshot-every', type=int, default=200,
                        help='Pool snapshot cadence for pool/hybrid opponent modes')
    parser.add_argument('--save-interval', type=int, default=100)
    parser.add_argument('--archive-dir', default=None,
                        help='Optional directory for immutable candidate checkpoints')
    parser.add_argument('--archive-interval', type=int, default=0,
                        help='Archive checkpoint every N iterations. 0 disables archives.')
    parser.add_argument('--archive-max', type=int, default=12,
                        help='Keep only the newest N archived checkpoints for this run')
    parser.add_argument('--light-archive', action='store_true', default=False,
                        help='Archive model-only eval checkpoints instead of full optimizer state.')
    parser.add_argument('--out', default='models/alpha_holdem_v55.pt')
    parser.add_argument('--resume', default='models/alpha_holdem_v4_final.pt')
    parser.add_argument('--reset-optimizer', action='store_true', default=True)
    parser.add_argument('--no-reset-optimizer', dest='reset_optimizer', action='store_false')
    parser.add_argument('--reset-hand-counter', action='store_true', default=False)
    parser.add_argument('--opponent-mode', choices=('pool', 'ema', 'hybrid'), default='pool',
                        help='Default pool matches AlphaHoldem/V4 K-best diversity. '
                             'Use ema only for ablations; hybrid mixes EMA with the pool.')
    parser.add_argument('--env-version', choices=('v55', 'v4', 'v55cap1', 'v55cap1v4obs'), default='v55',
                        help='Training environment wrapper. v4 keeps the legacy abstraction; '
                             'v55 uses the expanded fixed action tree; v55cap1 uses '
                             'V5.5 observation/cache with V4 postflop raise cap; '
                             'v55cap1v4obs keeps V4 observation encoding with the V5.5 cache.')
    parser.add_argument('--self-play-fraction', type=float, default=0.2,
                        help='Fraction of workers assigned to pure self-play in pool/hybrid modes')
    parser.add_argument('--ema-fraction', type=float, default=0.3,
                        help='Fraction of workers assigned to EMA in hybrid mode')
    # Phase 2: EMA shadow opponent
    parser.add_argument('--ema-alpha', type=float, default=0.999,
                        help='EMA decay for shadow opponent (0.999 default = ~693 iter half-life)')
    parser.add_argument('--ema-only-fraction', type=float, default=0.5,
                        help='Fraction of hands played vs EMA (rest = pure self-play). 1.0=all EMA, 0.5=50/50')
    # Phase 2 MMD: magnetic anchor regularizer
    parser.add_argument('--mmd-lambda', type=float, default=0.0,
                        help='MMD regularizer strength: lambda * KL(pi_hero || pi_EMA) added to PPO loss. '
                             '0=disabled (pure fictitious-play). 0.1=mild magnetic pull. '
                             '1.0=strong (may stall learning). Recommended start 0.1.')
    parser.add_argument('--mmd-anchor', choices=('ema', 'fixed'), default='ema',
                        help='Anchor used by MMD KL. fixed freezes the resume policy as a V4 guardrail.')
    parser.add_argument('--disable-safety-stop', action='store_true', default=False,
                        help='Disable runtime stops for entropy/rew100 collapse signals')
    parser.add_argument('--min-runtime-entropy', type=float, default=0.05,
                        help='Stop when policy entropy drops below this value')
    parser.add_argument('--max-runtime-rew100', type=float, default=12.0,
                        help='Stop when abs(rew100) exceeds this value')
    parser.add_argument('--max-runtime-positive-rew100', type=float, default=6.0,
                        help='Stop on high positive rew100; in V5.5 this is treated as a self-play overfit signal')
    parser.add_argument('--min-safety-stop-iters', type=int, default=10,
                        help='Minimum PPO updates in this run before runtime safety stops can trigger')
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

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    pool = LatestKPool(k=args.k_best, update_mode=args.pool_update_mode)

    total_hands_real = 0   # V5.5: cumulative REAL hands (not inflated terminals)
    total_terminals = 0    # V5.0-style inflated count, kept for compat
    iteration = 0
    if args.resume and os.path.exists(args.resume):
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model'])
        if not args.reset_optimizer:
            optimizer.load_state_dict(ckpt['optimizer'])
            print('Loaded optimizer state')
        else:
            print('V5.5: optimizer reset (fresh Adam moments after env change)')

        if not args.reset_hand_counter:
            # NB: V4 ckpts have `total_hands` which is the REAL hand count
            # (V4 was hero-only, so terminals == real hands). Use as starting point.
            total_hands_real = ckpt.get('total_hands', 0)
            total_terminals = total_hands_real  # V4 had no inflation
            iteration = ckpt.get('iteration', 0)

        # Preserve V4/V5 pool snapshots. Pool mode is the default because it
        # matches AlphaHoldem's historical-opponent diversity more closely.
        if 'pool_snapshots' in ckpt:
            pool.load_from_checkpoint(ckpt['pool_snapshots'], hands=total_hands_real)

        print(f'Resumed: real_hands={total_hands_real:,}, pool={pool.size()} '
              f'(EMA seeds from current weights)')

    # Phase 2: create EMA opponent + a single GPU inference instance.
    ema = EMAOpponent(model, alpha=args.ema_alpha)

    # Restore EMA from ckpt if present (V5.5-phase2 ckpts only). V4 / V5.5-phase0
    # ckpts don't have one -> ema starts identical to current model weights.
    if 'ckpt' in locals() and 'ema_state_dict' in ckpt:
        loaded_ema = ckpt['ema_state_dict']
        if set(loaded_ema.keys()) == set(ema.state_dict.keys()):
            ema.state_dict = {k: v.detach().cpu().clone() for k, v in loaded_ema.items()}
            print(f'EMA: restored from ckpt (saved alpha={ckpt.get("ema_alpha", "?")})')
        else:
            print('EMA: ckpt key mismatch, seeding from current model instead')

    opp_model = AlphaHoldemNet(num_actions=NUM_ACTIONS).to(device)
    opp_model(dc, da, de)
    ema.load_into(opp_model)
    opp_model.eval()
    fixed_anchor_model = None
    if args.mmd_anchor == 'fixed':
        fixed_anchor_model = AlphaHoldemNet(num_actions=NUM_ACTIONS).to(device)
        fixed_anchor_model(dc, da, de)
        fixed_anchor_model.load_state_dict(model.state_dict())
        fixed_anchor_model.eval()
        for p in fixed_anchor_model.parameters():
            p.requires_grad_(False)
    print(f'EMA shadow opponent: alpha={args.ema_alpha}, '
          f'half-life={ema.half_life_iters():.0f} iters, '
          f'ema-only-fraction={args.ema_only_fraction}')

    train_log_path = args.out.replace('.pt', '_train.log')

    # Pause-flag mechanism: external scripts touch this file to request a
    # graceful save+exit (works regardless of OS signal delivery quirks).
    pause_flag_path = os.path.join(os.path.dirname(args.out) or '.', 'v55_pause.flag')
    # Clean stale flag from prior run, if any
    try:
        if os.path.exists(pause_flag_path):
            os.remove(pause_flag_path)
            print(f'Cleaned stale pause flag: {pause_flag_path}')
    except OSError:
        pass

    def checkpoint_payload(version):
        return {
            'model': model.state_dict(),
            'optimizer': optimizer.state_dict(),
            'ema_state_dict': ema.state_dict,
            'ema_alpha': ema.alpha,
            'pool_snapshots': pool.snapshots,
            'opponent_mode': args.opponent_mode,
            'env_version': args.env_version,
            'mmd_anchor': args.mmd_anchor,
            'pool_update_mode': args.pool_update_mode,
            'collect_self_play_both': args.collect_self_play_both,
            'total_hands': total_hands_real,
            'total_terminals': total_terminals,
            'iteration': iteration,
            'version': version,
        }

    def save_checkpoint(path, version):
        torch.save(checkpoint_payload(version), path)

    def save_light_checkpoint(path, version):
        torch.save({
            'model': model.state_dict(),
            'opponent_mode': args.opponent_mode,
            'env_version': args.env_version,
            'mmd_anchor': args.mmd_anchor,
            'pool_update_mode': args.pool_update_mode,
            'collect_self_play_both': args.collect_self_play_both,
            'total_hands': total_hands_real,
            'total_terminals': total_terminals,
            'iteration': iteration,
            'version': version,
            'light_archive': True,
        }, path)

    def archive_checkpoint(reason):
        if not args.archive_dir or args.archive_interval <= 0:
            return
        os.makedirs(args.archive_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(args.out))[0]
        archive_path = os.path.join(
            args.archive_dir,
            f'{stem}_iter{iteration}_hands{total_hands_real}_{reason}.pt',
        )
        if args.light_archive:
            save_light_checkpoint(archive_path, f'v5.5-phase2-{reason}-light')
        else:
            save_checkpoint(archive_path, f'v5.5-phase2-{reason}')
        print(f'  [Archive] {archive_path}')
        try:
            archived = sorted(
                (
                    os.path.join(args.archive_dir, name)
                    for name in os.listdir(args.archive_dir)
                    if name.startswith(stem + '_iter') and name.endswith('.pt')
                ),
                key=os.path.getmtime,
            )
            while args.archive_max > 0 and len(archived) > args.archive_max:
                old = archived.pop(0)
                os.remove(old)
        except OSError:
            pass

    def save_and_exit_for_pause():
        """Save current state with the pause-version tag, then return True so
        the main loop can break cleanly through the finally block."""
        save_checkpoint(args.out, 'v5.5-phase2-paused')
        archive_checkpoint('paused')
        print(f'\n[PAUSE] saved {args.out} (real_hands={total_hands_real:,}, iter={iteration})')
        try:
            os.remove(pause_flag_path)
        except OSError:
            pass

    obs_shm = shared_memory.SharedMemory(create=True, size=W * OBS_SIZE * 4)
    result_shm = shared_memory.SharedMemory(create=True, size=W * RESULT_SIZE * 4)
    status_shm = shared_memory.SharedMemory(create=True, size=W * 4)
    assigned_shm = shared_memory.SharedMemory(create=True, size=W * 4)
    request_shm = shared_memory.SharedMemory(create=True, size=W * 4)

    obs_np = np.ndarray((W * OBS_SIZE,), dtype=np.float32, buffer=obs_shm.buf)
    result_np = np.ndarray((W * RESULT_SIZE,), dtype=np.float32, buffer=result_shm.buf)
    status_np = np.ndarray((W,), dtype=np.int32, buffer=status_shm.buf)
    assigned_np = np.ndarray((W,), dtype=np.int32, buffer=assigned_shm.buf)
    request_np = np.ndarray((W,), dtype=np.int32, buffer=request_shm.buf)

    obs_np[:] = 0
    result_np[:] = 0
    status_np[:] = IDLE
    assigned_np[:] = -1
    request_np[:] = HERO_MODEL_ID

    epsilon_val = mp.Value('d', args.epsilon)
    stop_event = mp.Event()

    pipes = []
    procs = []
    for w in range(W):
        parent_conn, child_conn = mp.Pipe()
        pipes.append(parent_conn)
        p = mp.Process(
            target=worker_process_v55,
            args=(w, obs_shm.name, result_shm.name, status_shm.name,
                  assigned_shm.name, request_shm.name,
                  child_conn, stop_event, epsilon_val, args.starting_stack,
                  args.env_version, args.collect_self_play_both),
            daemon=True,
        )
        p.start()
        child_conn.close()
        procs.append(p)

    print(f'\nV5.5 trainer: {W} workers @ {args.starting_stack} BB')
    print(f'Target: {args.total_hands:,} real hands')
    print(f'PPO: eps_clip=0.2, delta1={args.delta1}, gamma={args.gamma}')
    print(f'V5.5 Phase 0+2: env={args.env_version} + opponent_mode={args.opponent_mode} '
          f'(pool={pool.size()}, pool_update={args.pool_update_mode}, ema_alpha={args.ema_alpha})')
    if args.mmd_lambda > 0.0:
        print(f'MMD: ON, lambda={args.mmd_lambda} '
              f'(KL(pi_hero || pi_{args.mmd_anchor}) magnetic anchor)')
    else:
        print('MMD: OFF (pure fictitious-play)')
    print('-' * 80)

    opp_models = []
    ema_opp_index = None
    pool_model_offset = 0

    def rebuild_opp_models():
        """Build GPU opponent list from pool snapshots plus optional EMA."""
        nonlocal ema_opp_index, pool_model_offset
        opp_models.clear()
        ema_opp_index = None
        if args.opponent_mode in ('ema', 'hybrid'):
            ema_opp_index = len(opp_models)
            opp_models.append(opp_model)
        pool_model_offset = len(opp_models)
        if args.opponent_mode in ('pool', 'hybrid'):
            for snap in pool.snapshots:
                m = AlphaHoldemNet(num_actions=NUM_ACTIONS).to(device)
                m(dc, da, de)
                m.load_state_dict(snap['state_dict'])
                m.eval()
                opp_models.append(m)

    rebuild_opp_models()

    reward_window = deque(maxlen=100)
    iter_transitions = []
    iter_reward = 0.0
    iter_terminals = 0
    iter_real_hands = 0
    iter_start = time.time()
    run_updates = 0
    inference_batch_sizes = []

    def assign_opponents():
        """Assign workers to self-play, pool opponents, or EMA."""
        for w in range(W):
            if args.opponent_mode == 'ema':
                assigned_np[w] = ema_opp_index if random.random() < args.ema_only_fraction else -1
                continue

            if args.opponent_mode == 'pool':
                if pool.size() == 0 or random.random() < args.self_play_fraction:
                    assigned_np[w] = -1
                else:
                    assigned_np[w] = pool_model_offset + random.randint(0, pool.size() - 1)
                continue

            # Hybrid: self-play first, then EMA, then historical pool.
            r = random.random()
            if r < args.self_play_fraction:
                assigned_np[w] = -1
            elif ema_opp_index is not None and r < args.self_play_fraction + args.ema_fraction:
                assigned_np[w] = ema_opp_index
            elif pool.size() > 0:
                assigned_np[w] = pool_model_offset + random.randint(0, pool.size() - 1)
            elif ema_opp_index is not None:
                assigned_np[w] = ema_opp_index
            else:
                assigned_np[w] = -1

    assign_opponents()

    try:
        model.eval()
        while total_hands_real < args.total_hands:
            # Pause-flag check (cheap stat() per inference cycle)
            if os.path.exists(pause_flag_path):
                save_and_exit_for_pause()
                break

            n_inf = run_inference_v55(
                model, opp_models,
                obs_np, result_np, status_np, request_np,
                W, device, inference_batch_sizes,
            )

            for pipe in pipes:
                try:
                    while pipe.poll():
                        data = pipe.recv()
                        if data is None:
                            continue
                        # V5.5: pipe sends (real_hands, hero_reward, transitions).
                        # Accept the older 2-tuple for compatibility with
                        # already-running workers from previous code.
                        if len(data) == 3:
                            real_hands_inc, hero_reward_inc, batch = data
                        else:
                            real_hands_inc, batch = data
                            hero_reward_inc = 0.0
                        iter_real_hands += int(real_hands_inc)
                        iter_reward += float(hero_reward_inc)
                        for t in batch:
                            iter_transitions.append(t)
                            if t[8] > 0.5:
                                iter_terminals += 1
                except (BrokenPipeError, EOFError):
                    pass

            # V5.5: trigger iter on REAL hand count, not inflated terminals
            if iter_real_hands >= args.hands_per_iter and len(iter_transitions) > 0:
                iteration += 1
                run_updates += 1
                collect_time = time.time() - iter_start

                progress = total_hands_real / args.total_hands
                if args.epsilon > 0.0:
                    eps_decay = max(
                        args.epsilon_min,
                        args.epsilon * (1 - max(0, progress - 0.8) / 0.2),
                    )
                    epsilon_val.value = eps_decay
                else:
                    eps_decay = 0.0

                if progress >= 0.5:
                    decay_frac = (progress - 0.5) / 0.5
                    new_lr = args.lr * (1 - decay_frac * (1 - 1/3))
                    for pg in optimizer.param_groups:
                        pg['lr'] = new_lr

                t1 = time.time()
                if args.mmd_lambda > 0.0:
                    mmd_anchor_model = fixed_anchor_model if fixed_anchor_model is not None else opp_model
                    stats = mmd_trinal_clip_ppo_update(
                        model, optimizer, iter_transitions, device,
                        anchor_model=mmd_anchor_model,
                        mmd_lambda=args.mmd_lambda,
                        epochs=args.ppo_epochs,
                        mini_batch_size=args.mini_batch_size,
                        delta1=args.delta1,
                        gamma=args.gamma,
                        entropy_coef=args.entropy_coef,
                        entropy_floor=args.entropy_floor,
                    )
                else:
                    stats = trinal_clip_ppo_update(
                        model, optimizer, iter_transitions, device,
                        epochs=args.ppo_epochs,
                        mini_batch_size=args.mini_batch_size,
                        delta1=args.delta1,
                        gamma=args.gamma,
                        entropy_coef=args.entropy_coef,
                        entropy_floor=args.entropy_floor,
                    )
                ppo_time = time.time() - t1

                # Phase 2: EMA update + sync into GPU inference instance
                ema.update(model)
                ema.load_into(opp_model)
                opp_model.eval()

                total_hands_real += iter_real_hands
                total_terminals += iter_terminals
                trainable_decisions = len(iter_transitions)

                avg_rew = iter_reward / max(iter_real_hands, 1)
                reward_window.append(avg_rew)
                rew100 = np.mean(reward_window)

                # V5.5 metrics — h/s now real, tdec/s unchanged in meaning
                real_h_per_s = iter_real_hands / max(collect_time, 1e-6)
                tdec_per_s = trainable_decisions / max(collect_time, 1e-6)
                infer_bs_mean = (sum(inference_batch_sizes) / len(inference_batch_sizes)
                                 if inference_batch_sizes else 0.0)
                inflate_ratio = iter_terminals / max(iter_real_hands, 1)

                kl_part = f"kl={stats.get('mmd_kl', 0):.4f} " if 'mmd_kl' in stats else ""
                log_line = (
                    f"[{iteration:5d}] "
                    f"real_hands={total_hands_real:,} "
                    f"rew100={rew100:+.3f} "
                    f"ploss={stats['policy_loss']:.4f} "
                    f"vloss={stats['value_loss']:.4f} "
                    f"ent={stats['entropy']:.4f} "
                    f"{kl_part}"
                    f"eps={eps_decay:.3f} "
                    f"opp={args.opponent_mode} "
                    f"pool={pool.size()} "
                    f"trans={trainable_decisions} "
                    f"real_h/s={real_h_per_s:.0f} "
                    f"tdec/s={tdec_per_s:.0f} "
                    f"inf_bs={infer_bs_mean:.1f} "
                    f"infl={inflate_ratio:.2f} "
                    f"collect={collect_time:.1f}s "
                    f"ppo={ppo_time:.1f}s"
                )
                print(log_line)
                with open(train_log_path, 'a') as f:
                    f.write(log_line + '\n')

                if (
                    not args.disable_safety_stop
                    and len(reward_window) >= 10
                    and run_updates >= args.min_safety_stop_iters
                ):
                    safety_reasons = []
                    if stats['entropy'] <= args.min_runtime_entropy:
                        safety_reasons.append(
                            f"entropy={stats['entropy']:.4f} <= {args.min_runtime_entropy}"
                        )
                    if abs(rew100) >= args.max_runtime_rew100:
                        safety_reasons.append(
                            f"abs(rew100)={abs(rew100):.3f} >= {args.max_runtime_rew100}"
                        )
                    if rew100 >= args.max_runtime_positive_rew100:
                        safety_reasons.append(
                            f"rew100={rew100:.3f} >= {args.max_runtime_positive_rew100}"
                        )
                    if safety_reasons:
                        print(f"[SAFETY_STOP] {'; '.join(safety_reasons)}")
                        save_and_exit_for_pause()
                        break

                if args.opponent_mode in ('pool', 'hybrid') and iteration % args.snapshot_every == 0:
                    before_pool = pool.size()
                    pool.add(model.state_dict(), hands=total_hands_real)
                    rebuild_opp_models()
                    print(
                        f'  [Pool] snapshot update={args.pool_update_mode} '
                        f'size={pool.size()} was={before_pool}'
                    )

                if iteration % args.save_interval == 0:
                    save_checkpoint(args.out, 'v5.5-phase2')
                    print(f'  [Save] {args.out} (real={total_hands_real:,})')
                    if args.archive_interval > 0 and iteration % args.archive_interval == 0:
                        archive_checkpoint('save')

                assign_opponents()
                iter_transitions = []
                iter_reward = 0.0
                iter_terminals = 0
                iter_real_hands = 0
                inference_batch_sizes = []
                iter_start = time.time()
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
        for shm in (obs_shm, result_shm, status_shm, assigned_shm, request_shm):
            shm.close()
            shm.unlink()

    save_checkpoint(args.out, 'v5.5-phase2')
    print(f'Done! real_hands={total_hands_real:,}. Saved to {args.out}')


if __name__ == '__main__':
    mp.set_start_method('spawn')
    main()
