#!/usr/bin/env python3
"""
AlphaHoldem multiprocessing trainer — true parallel game workers.

Architecture:
  - Main process: GPU inference server (reads shared memory, writes actions)
  - Worker processes: pure game logic, communicate via shared memory arrays
  - Each worker plays hands continuously, submits obs to shared buffer

Shared memory layout (per worker slot):
  - obs_buffer: card(6*4*13) + action(25*4*5) + extra(2) + mask(9) = 823 floats
  - result_buffer: action_idx(1) + log_prob(1) + value(1) = 3 floats
  - status flag: 0=idle, 1=waiting_for_inference, 2=result_ready

Usage:
  python scripts/alpha_holdem/train_mp.py --device cuda --workers 28
"""

import argparse
import os
import sys
import time
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
from alpha_holdem.environment import (
    HUNLEnvironment, NUM_ACTIONS,
)

# Observation sizes
CARD_SIZE = 6 * 4 * 13      # 312
ACTION_SIZE = 25 * 4 * 5    # 500
EXTRA_SIZE = 2
MASK_SIZE = NUM_ACTIONS      # 9
OBS_SIZE = CARD_SIZE + ACTION_SIZE + EXTRA_SIZE + MASK_SIZE  # 823

# Result sizes
RESULT_SIZE = 3  # action_idx, log_prob, value

# Status flags
IDLE = 0
WAITING = 1
READY = 2


# ═══════════════════════════════════════════════════════════
# Worker Process
# ═══════════════════════════════════════════════════════════

def worker_process(
    worker_id: int,
    obs_shm_name: str,
    result_shm_name: str,
    status_shm_name: str,
    transition_pipe,  # multiprocessing.connection.Connection
    stop_event,  # multiprocessing.Event
    epsilon: float,
    hands_target: int,
):
    """Game worker: plays hands, writes obs to shared memory, reads actions back."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from alpha_holdem.environment import HUNLEnvironment, NUM_ACTIONS
    import numpy as np
    import random
    from multiprocessing import shared_memory

    # Attach to shared memory
    obs_shm = shared_memory.SharedMemory(name=obs_shm_name)
    result_shm = shared_memory.SharedMemory(name=result_shm_name)
    status_shm = shared_memory.SharedMemory(name=status_shm_name)

    obs_buf = np.ndarray((OBS_SIZE,), dtype=np.float32, buffer=obs_shm.buf[worker_id * OBS_SIZE * 4:(worker_id + 1) * OBS_SIZE * 4])
    result_buf = np.ndarray((RESULT_SIZE,), dtype=np.float32, buffer=result_shm.buf[worker_id * RESULT_SIZE * 4:(worker_id + 1) * RESULT_SIZE * 4])
    status_buf = np.ndarray((1,), dtype=np.int32, buffer=status_shm.buf[worker_id * 4:(worker_id + 1) * 4])

    env = HUNLEnvironment(starting_stack=50.0)
    hands_played = 0

    # Batch transitions and send periodically
    local_transitions = []

    while not stop_event.is_set() and hands_played < hands_target:
        obs = env.reset()
        done = False
        hero_player = hands_played % 2
        hand_buffer = []
        hand_reward = 0.0

        while not done and not stop_event.is_set():
            player = obs['player']
            is_hero = (player == hero_player)

            # Write observation to shared memory
            ci = obs['card_info'].flatten()
            ai = obs['action_info'].flatten()
            ei = obs['extra_info']
            lm = obs['legal_mask']
            obs_buf[:CARD_SIZE] = ci
            obs_buf[CARD_SIZE:CARD_SIZE + ACTION_SIZE] = ai
            obs_buf[CARD_SIZE + ACTION_SIZE:CARD_SIZE + ACTION_SIZE + EXTRA_SIZE] = ei
            obs_buf[CARD_SIZE + ACTION_SIZE + EXTRA_SIZE:] = lm

            # Signal: waiting for inference
            status_buf[0] = WAITING

            # Busy-wait for result (spin loop — fast for low latency)
            while status_buf[0] != READY:
                if stop_event.is_set():
                    break
                # Tiny sleep to avoid burning CPU in spin
                pass  # spin — fast enough at ~1μs per check

            if stop_event.is_set():
                break

            action_idx = int(result_buf[0])
            log_prob = float(result_buf[1])
            value = float(result_buf[2])

            # Reset status
            status_buf[0] = IDLE

            # Epsilon-greedy
            if random.random() < epsilon:
                legal = np.where(lm > 0)[0]
                action_idx = random.choice(legal) if len(legal) > 0 else action_idx

            if is_hero:
                hand_buffer.append((
                    ci.copy(), ai.copy(), ei.copy(), lm.copy(),
                    action_idx, log_prob, value,
                ))

            obs, reward, done = env.step(action_idx)

            if done:
                hand_reward = reward if is_hero else -reward

        # Build transitions
        for i, (ci, ai, ei, lm, act, lp, val) in enumerate(hand_buffer):
            is_last = (i == len(hand_buffer) - 1)
            local_transitions.append((
                ci, ai, ei, lm, act, lp,
                hand_reward if is_last else 0.0,
                val,
                1.0 if is_last else 0.0,
            ))

        hands_played += 1

        # Send transitions every 50 hands to reduce IPC overhead
        if hands_played % 50 == 0 and local_transitions:
            transition_pipe.send(local_transitions)
            local_transitions = []

    # Send remaining
    if local_transitions:
        transition_pipe.send(local_transitions)

    transition_pipe.send(None)  # signal done

    obs_shm.close()
    result_shm.close()
    status_shm.close()


# ═══════════════════════════════════════════════════════════
# GPU Inference Server (main process)
# ═══════════════════════════════════════════════════════════

@torch.no_grad()
def run_inference_batch(
    model: AlphaHoldemNet,
    obs_np: np.ndarray,
    result_np: np.ndarray,
    status_np: np.ndarray,
    num_workers: int,
    device: str,
):
    """
    Check which workers are WAITING, batch their obs, run inference, write results.
    Returns number of inferences done.
    """
    # Find waiting workers
    waiting = []
    for w in range(num_workers):
        if status_np[w] == WAITING:
            waiting.append(w)

    if not waiting:
        return 0

    B = len(waiting)

    # Gather observations
    cards_list = []
    actions_list = []
    extras_list = []
    masks_list = []

    for w in waiting:
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

    logits, values = model(cards_t, actions_t, extras_t, masks_t)
    probs = F.softmax(logits, dim=-1)
    dist = Categorical(probs)
    sampled = dist.sample()
    log_probs = dist.log_prob(sampled)

    sampled_np = sampled.cpu().numpy()
    lp_np = log_probs.cpu().numpy()
    val_np = values.squeeze(-1).cpu().numpy()

    # Write results back
    for i, w in enumerate(waiting):
        r_offset = w * RESULT_SIZE
        result_np[r_offset] = sampled_np[i]
        result_np[r_offset + 1] = lp_np[i]
        result_np[r_offset + 2] = val_np[i]
        status_np[w] = READY

    return B


# ═══════════════════════════════════════════════════════════
# GAE + PPO
# ═══════════════════════════════════════════════════════════

def compute_gae(rewards, values, dones, gamma=1.0, lam=0.95):
    advantages = np.zeros_like(rewards)
    last_gae = 0.0
    n = len(rewards)
    for t in reversed(range(n)):
        next_value = 0.0 if t == n - 1 else values[t + 1]
        delta = rewards[t] + gamma * next_value * (1 - dones[t]) - values[t]
        advantages[t] = last_gae = delta + gamma * lam * (1 - dones[t]) * last_gae
    return advantages, advantages + values


def ppo_update(model, optimizer, transitions, device,
               epochs=4, mini_batch_size=1024, clip_eps=0.2,
               value_coef=0.5, entropy_coef=0.1, max_grad_norm=0.5, min_entropy=0.3):
    model.train()
    n = len(transitions)

    # Unpack (each transition is a tuple of 9 elements)
    card_arr = np.array([t[0].reshape(6, 4, 13) for t in transitions])
    action_arr = np.array([t[1].reshape(25, 4, 5) for t in transitions])
    extra_arr = np.array([t[2] for t in transitions])
    mask_arr = np.array([t[3] for t in transitions])
    act_arr = np.array([t[4] for t in transitions])
    lp_arr = np.array([t[5] for t in transitions])
    rew_arr = np.array([t[6] for t in transitions])
    val_arr = np.array([t[7] for t in transitions])
    done_arr = np.array([t[8] for t in transitions])

    advantages, returns = compute_gae(rew_arr, val_arr, done_arr)

    cards_t = torch.tensor(card_arr, dtype=torch.float32, device=device)
    actions_t = torch.tensor(action_arr, dtype=torch.float32, device=device)
    extras_t = torch.tensor(extra_arr, dtype=torch.float32, device=device)
    masks_t = torch.tensor(mask_arr, dtype=torch.float32, device=device)
    acts_t = torch.tensor(act_arr, dtype=torch.long, device=device)
    old_lp_t = torch.tensor(lp_arr, dtype=torch.float32, device=device)
    adv_t = torch.tensor(advantages, dtype=torch.float32, device=device)
    ret_t = torch.tensor(returns, dtype=torch.float32, device=device)

    if n > 1:
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

    total_ploss = total_vloss = total_ent = 0.0
    num_updates = 0

    for _ in range(epochs):
        indices = torch.randperm(n, device=device)
        for start in range(0, n, mini_batch_size):
            end = min(start + mini_batch_size, n)
            idx = indices[start:end]

            logits, values = model(cards_t[idx], actions_t[idx], extras_t[idx], masks_t[idx])
            probs = F.softmax(logits, dim=-1)
            dist = Categorical(probs)
            new_lp = dist.log_prob(acts_t[idx])
            entropy = dist.entropy().mean()

            ratio = torch.exp(new_lp - old_lp_t[idx])
            surr1 = ratio * adv_t[idx]
            surr2 = torch.clamp(ratio, 1 - clip_eps, 1 + clip_eps) * adv_t[idx]
            ploss = -torch.min(surr1, surr2).mean()
            vloss = F.mse_loss(values.squeeze(-1), ret_t[idx])

            ent_coef = entropy_coef * 5.0 if entropy.item() < min_entropy else entropy_coef
            loss = ploss + value_coef * vloss - ent_coef * entropy

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            optimizer.step()

            total_ploss += ploss.item()
            total_vloss += vloss.item()
            total_ent += entropy.item()
            num_updates += 1

    return {
        'policy_loss': total_ploss / max(num_updates, 1),
        'value_loss': total_vloss / max(num_updates, 1),
        'entropy': total_ent / max(num_updates, 1),
    }


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='AlphaHoldem MP Trainer')
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--workers', type=int, default=28)
    parser.add_argument('--hands-per-iter', type=int, default=16384)
    parser.add_argument('--total-hands', type=int, default=1_000_000_000)
    parser.add_argument('--lr', type=float, default=3e-4)
    parser.add_argument('--ppo-epochs', type=int, default=4)
    parser.add_argument('--mini-batch-size', type=int, default=1024)
    parser.add_argument('--epsilon', type=float, default=0.15)
    parser.add_argument('--save-interval', type=int, default=100)
    parser.add_argument('--out', default='models/alpha_holdem_v3.pt')
    parser.add_argument('--resume', default=None)
    args = parser.parse_args()

    device = args.device
    print(f'Device: {device}')
    if device == 'cuda':
        print(f'GPU: {torch.cuda.get_device_name(0)}')

    model = AlphaHoldemNet(num_actions=NUM_ACTIONS).to(device)
    dummy_c = torch.zeros(1, 6, 4, 13, device=device)
    dummy_a = torch.zeros(1, 25, 4, 5, device=device)
    dummy_e = torch.zeros(1, 2, device=device)
    model(dummy_c, dummy_a, dummy_e)
    print(f'Parameters: {count_parameters(model):,}')

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    start_hands = 0
    if args.resume and os.path.exists(args.resume):
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model'])
        optimizer.load_state_dict(ckpt['optimizer'])
        start_hands = ckpt.get('total_hands', 0)
        print(f'Resumed: {start_hands:,} hands')

    log_path = args.out.replace('.pt', '.log')
    total_hands = start_hands
    iteration = 0
    reward_window = deque(maxlen=100)
    W = args.workers

    print(f'\nTarget: {args.total_hands:,} hands, {W} workers')
    print('-' * 80)

    # ── Allocate shared memory (persistent across iterations) ──
    obs_shm = shared_memory.SharedMemory(create=True, size=W * OBS_SIZE * 4)
    result_shm = shared_memory.SharedMemory(create=True, size=W * RESULT_SIZE * 4)
    status_shm = shared_memory.SharedMemory(create=True, size=W * 4)

    obs_np = np.ndarray((W * OBS_SIZE,), dtype=np.float32, buffer=obs_shm.buf)
    result_np = np.ndarray((W * RESULT_SIZE,), dtype=np.float32, buffer=result_shm.buf)
    status_np = np.ndarray((W,), dtype=np.int32, buffer=status_shm.buf)

    try:
     while total_hands < args.total_hands:
        t0 = time.time()
        iteration += 1

        progress = total_hands / args.total_hands
        eps = max(0.05, args.epsilon * (1 - max(0, progress - 0.8) / 0.2))
        hands_per_worker = args.hands_per_iter // W + 1

        obs_np[:] = 0
        result_np[:] = 0
        status_np[:] = IDLE

        stop_event = mp.Event()

        # ── Start worker processes ──
        pipes = []
        workers_list = []
        for w in range(W):
            parent_conn, child_conn = mp.Pipe()
            pipes.append(parent_conn)
            p = mp.Process(
                target=worker_process,
                args=(w, obs_shm.name, result_shm.name, status_shm.name,
                      child_conn, stop_event, eps, hands_per_worker),
                daemon=True,
            )
            p.start()
            workers_list.append(p)

        # ── Run inference server until all workers done ──
        model.eval()
        workers_done = 0
        all_transitions = []
        batch_reward = 0.0
        batch_hands = 0

        while workers_done < W:
            with torch.no_grad():
                run_inference_batch(model, obs_np, result_np, status_np, W, device)

            for i, pipe in enumerate(pipes):
                try:
                    while pipe.poll():
                        data = pipe.recv()
                        if data is None:
                            workers_done += 1
                        else:
                            for t in data:
                                all_transitions.append(t)
                                if t[8] > 0.5:
                                    batch_reward += t[6]
                                    batch_hands += 1
                except (BrokenPipeError, EOFError):
                    workers_done += 1

            time.sleep(0.0001)

        # ── Cleanup workers ──
        stop_event.set()
        for p in workers_list:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()

        if not all_transitions:
            print(f'[{iteration}] WARNING: no transitions')
            continue

        collect_time = time.time() - t0

        # ── PPO update ──
        t1 = time.time()
        update_stats = ppo_update(
            model, optimizer, all_transitions, device,
            epochs=args.ppo_epochs,
            mini_batch_size=args.mini_batch_size,
        )
        ppo_time = time.time() - t1

        total_hands += batch_hands
        elapsed = time.time() - t0
        h_per_s = batch_hands / elapsed if elapsed > 0 else 0
        avg_rew = batch_reward / max(batch_hands, 1)
        reward_window.append(avg_rew)
        rew100 = np.mean(reward_window) if reward_window else 0

        log_line = (
            f"[{iteration:5d}] "
            f"hands={total_hands:,} "
            f"rew={avg_rew:+.3f} "
            f"rew100={rew100:+.3f} "
            f"ploss={update_stats['policy_loss']:.4f} "
            f"vloss={update_stats['value_loss']:.4f} "
            f"ent={update_stats['entropy']:.4f} "
            f"eps={eps:.3f} "
            f"trans={len(all_transitions)} "
            f"h/s={h_per_s:.0f} "
            f"collect={collect_time:.1f}s "
            f"ppo={ppo_time:.1f}s "
            f"t={elapsed:.1f}s"
        )
        print(log_line)
        with open(log_path, 'a') as f:
            f.write(log_line + '\n')

        if iteration % args.save_interval == 0:
            torch.save({
                'model': model.state_dict(),
                'optimizer': optimizer.state_dict(),
                'total_hands': total_hands,
                'iteration': iteration,
            }, args.out)
            print(f'  [Save] {args.out} ({total_hands:,} hands)')

    finally:
        obs_shm.close()
        obs_shm.unlink()
        result_shm.close()
        result_shm.unlink()
        status_shm.close()
        status_shm.unlink()

    torch.save({
        'model': model.state_dict(),
        'optimizer': optimizer.state_dict(),
        'total_hands': total_hands,
        'iteration': iteration,
    }, args.out)
    print(f'\nDone! {total_hands:,} hands.')


if __name__ == '__main__':
    main()
