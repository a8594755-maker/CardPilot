#!/usr/bin/env python3
"""
AlphaHoldem persistent multiprocessing trainer.

Architecture:
  - Worker processes start ONCE and play hands forever (until stop_event).
  - For each action, workers write obs to shared memory, spin-wait for GPU result.
  - Main process continuously polls shared memory, batches WAITING workers,
    runs GPU forward pass, writes results back.
  - Workers send transitions via pipe every 50 hands.
  - Main drains pipes and runs PPO when enough hands accumulate.

This avoids the per-iteration process spawn overhead that made train_mp.py slow
(21 h/s), while bypassing the GIL that limits train_fast.py (1050 h/s).

Usage:
  python scripts/alpha_holdem/train_mp2.py --device cuda --workers 28
"""

import argparse
import os
import sys
import time
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
from alpha_holdem.environment import NUM_ACTIONS

# ═══════════════════════════════════════════════════════════
# Shared Memory Layout
# ═══════════════════════════════════════════════════════════

CARD_SIZE = 6 * 4 * 13       # 312
ACTION_SIZE = 25 * 4 * 5     # 500
EXTRA_SIZE = 2
MASK_SIZE = NUM_ACTIONS       # 9
OBS_SIZE = CARD_SIZE + ACTION_SIZE + EXTRA_SIZE + MASK_SIZE  # 823
RESULT_SIZE = 3               # action_idx, log_prob, value

# Status flags (int32)
IDLE = 0
WAITING = 1
READY = 2


# ═══════════════════════════════════════════════════════════
# Worker Process (persistent — starts once, runs forever)
# ═══════════════════════════════════════════════════════════

def worker_process(
    worker_id: int,
    obs_shm_name: str,
    result_shm_name: str,
    status_shm_name: str,
    transition_pipe,       # multiprocessing.connection.Connection (send end)
    stop_event,            # multiprocessing.Event
    epsilon_value,         # multiprocessing.Value('d', ...) — shared, updated by main
):
    """
    Persistent game worker. Plays hands in a loop until stop_event is set.
    For each action needed:
      1. Write observation to shared memory slot
      2. Set status = WAITING
      3. Spin-wait until status = READY
      4. Read action from result slot
    Sends transitions via pipe every 50 hands.
    """
    # Windows spawn: must import everything inside the function
    import sys
    import os
    import time
    import random
    import numpy as np
    from multiprocessing import shared_memory as shm_mod

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from alpha_holdem.environment import HUNLEnvironment, NUM_ACTIONS

    # Attach to shared memory (do NOT create — main owns these)
    obs_shm = shm_mod.SharedMemory(name=obs_shm_name)
    result_shm = shm_mod.SharedMemory(name=result_shm_name)
    status_shm = shm_mod.SharedMemory(name=status_shm_name)

    obs_buf = np.ndarray(
        (OBS_SIZE,), dtype=np.float32,
        buffer=obs_shm.buf[worker_id * OBS_SIZE * 4:(worker_id + 1) * OBS_SIZE * 4],
    )
    result_buf = np.ndarray(
        (RESULT_SIZE,), dtype=np.float32,
        buffer=result_shm.buf[worker_id * RESULT_SIZE * 4:(worker_id + 1) * RESULT_SIZE * 4],
    )
    status_buf = np.ndarray(
        (1,), dtype=np.int32,
        buffer=status_shm.buf[worker_id * 4:(worker_id + 1) * 4],
    )

    env = HUNLEnvironment(starting_stack=50.0)
    hands_played = 0
    local_transitions = []

    try:
        while not stop_event.is_set():
            obs = env.reset()
            done = False
            hero_player = hands_played % 2
            hand_buffer = []
            hand_reward = 0.0

            while not done and not stop_event.is_set():
                player = obs['player']
                is_hero = (player == hero_player)

                # Flatten observation components
                ci = obs['card_info'].flatten()
                ai = obs['action_info'].flatten()
                ei = obs['extra_info']
                lm = obs['legal_mask']

                # Write observation to shared memory slot
                obs_buf[:CARD_SIZE] = ci
                obs_buf[CARD_SIZE:CARD_SIZE + ACTION_SIZE] = ai
                obs_buf[CARD_SIZE + ACTION_SIZE:CARD_SIZE + ACTION_SIZE + EXTRA_SIZE] = ei
                obs_buf[CARD_SIZE + ACTION_SIZE + EXTRA_SIZE:] = lm

                # Signal: waiting for inference
                status_buf[0] = WAITING

                # Spin-wait until main process writes result
                while status_buf[0] != READY:
                    if stop_event.is_set():
                        break
                    time.sleep(0.000001)  # 1us — avoid 100% busy loop

                if stop_event.is_set():
                    break

                # Read result
                action_idx = int(result_buf[0])
                log_prob = float(result_buf[1])
                value = float(result_buf[2])

                # Reset status for next action
                status_buf[0] = IDLE

                # Epsilon-greedy exploration (read shared epsilon)
                eps = epsilon_value.value
                if random.random() < eps:
                    legal = np.where(lm > 0)[0]
                    if len(legal) > 0:
                        action_idx = int(random.choice(legal))

                if is_hero:
                    hand_buffer.append((
                        ci.copy(), ai.copy(), ei.copy(), lm.copy(),
                        action_idx, log_prob, value,
                    ))

                obs, reward, done = env.step(action_idx)

                if done:
                    hand_reward = reward if is_hero else -reward

            # Build transitions for this hand
            for i, (ci_s, ai_s, ei_s, lm_s, act, lp, val) in enumerate(hand_buffer):
                is_last = (i == len(hand_buffer) - 1)
                local_transitions.append((
                    ci_s, ai_s, ei_s, lm_s, act, lp,
                    hand_reward if is_last else 0.0,
                    val,
                    1.0 if is_last else 0.0,
                ))

            hands_played += 1

            # Batch-send transitions every 50 hands to reduce IPC overhead
            if hands_played % 50 == 0 and local_transitions:
                try:
                    transition_pipe.send(local_transitions)
                except BrokenPipeError:
                    break
                local_transitions = []

        # Send remaining transitions
        if local_transitions:
            try:
                transition_pipe.send(local_transitions)
            except BrokenPipeError:
                pass

        # Signal worker is done
        try:
            transition_pipe.send(None)
        except BrokenPipeError:
            pass

    finally:
        obs_shm.close()
        result_shm.close()
        status_shm.close()


# ═══════════════════════════════════════════════════════════
# GPU Inference (main process)
# ═══════════════════════════════════════════════════════════

@torch.no_grad()
def run_inference_batch(
    model: AlphaHoldemNet,
    obs_np: np.ndarray,
    result_np: np.ndarray,
    status_np: np.ndarray,
    num_workers: int,
    device: str,
) -> int:
    """
    Check which workers are WAITING, batch their obs, run GPU forward pass,
    write results back and set READY. Returns number of inferences done.
    """
    waiting = []
    for w in range(num_workers):
        if status_np[w] == WAITING:
            waiting.append(w)

    if not waiting:
        return 0

    B = len(waiting)

    # Gather observations into contiguous arrays
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

    # Single batched GPU forward pass
    logits, values = model(cards_t, actions_t, extras_t, masks_t)
    probs = F.softmax(logits, dim=-1)
    dist = Categorical(probs)
    sampled = dist.sample()
    log_probs = dist.log_prob(sampled)

    sampled_np = sampled.cpu().numpy()
    lp_np = log_probs.cpu().numpy()
    val_np = values.squeeze(-1).cpu().numpy()

    # Write results back to shared memory and signal READY
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
    """Generalized Advantage Estimation."""
    advantages = np.zeros_like(rewards)
    last_gae = 0.0
    n = len(rewards)
    for t in reversed(range(n)):
        next_value = 0.0 if t == n - 1 else values[t + 1]
        delta = rewards[t] + gamma * next_value * (1 - dones[t]) - values[t]
        advantages[t] = last_gae = delta + gamma * lam * (1 - dones[t]) * last_gae
    returns = advantages + values
    return advantages, returns


def ppo_update(
    model: AlphaHoldemNet,
    optimizer: torch.optim.Optimizer,
    transitions: list,
    device: str,
    epochs: int = 4,
    mini_batch_size: int = 1024,
    clip_eps: float = 0.2,
    value_coef: float = 0.5,
    entropy_coef: float = 0.1,
    max_grad_norm: float = 0.5,
    min_entropy: float = 0.3,
) -> dict:
    """PPO update with adaptive entropy boost."""
    model.train()
    n = len(transitions)

    # Unpack transitions (each is a 9-tuple from workers)
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

    # Convert to GPU tensors
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

    total_ploss = 0.0
    total_vloss = 0.0
    total_ent = 0.0
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

            # Adaptive entropy: boost 5x when entropy drops below threshold
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
    parser = argparse.ArgumentParser(description='AlphaHoldem Persistent MP Trainer')
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--workers', type=int, default=28)
    parser.add_argument('--hands-per-iter', type=int, default=16384,
                        help='PPO update frequency (hands between updates)')
    parser.add_argument('--total-hands', type=int, default=1_000_000_000)
    parser.add_argument('--lr', type=float, default=3e-4)
    parser.add_argument('--ppo-epochs', type=int, default=4)
    parser.add_argument('--mini-batch-size', type=int, default=1024)
    parser.add_argument('--epsilon', type=float, default=0.15)
    parser.add_argument('--save-interval', type=int, default=100,
                        help='Save checkpoint every N iterations')
    parser.add_argument('--out', default='models/alpha_holdem_v3.pt')
    parser.add_argument('--resume', default=None, help='Path to checkpoint to resume from')
    args = parser.parse_args()

    device = args.device
    print(f'Device: {device}')
    if device == 'cuda':
        print(f'GPU: {torch.cuda.get_device_name(0)}')

    # ── Initialize model ──
    model = AlphaHoldemNet(num_actions=NUM_ACTIONS).to(device)
    # Force lazy init with dummy tensors
    dummy_c = torch.zeros(1, 6, 4, 13, device=device)
    dummy_a = torch.zeros(1, 25, 4, 5, device=device)
    dummy_e = torch.zeros(1, 2, device=device)
    model(dummy_c, dummy_a, dummy_e)
    print(f'Parameters: {count_parameters(model):,}')

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    start_hands = 0
    start_iteration = 0
    if args.resume and os.path.exists(args.resume):
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model'])
        optimizer.load_state_dict(ckpt['optimizer'])
        start_hands = ckpt.get('total_hands', 0)
        start_iteration = ckpt.get('iteration', 0)
        print(f'Resumed from {args.resume}: {start_hands:,} hands, iteration {start_iteration}')

    log_path = args.out.replace('.pt', '.log')
    total_hands = start_hands
    iteration = start_iteration
    reward_window = deque(maxlen=100)
    W = args.workers

    num_iters = (args.total_hands - start_hands) // args.hands_per_iter
    print(f'\nTarget: {args.total_hands:,} hands ({num_iters:,} iterations of {args.hands_per_iter:,})')
    print(f'Workers: {W} (persistent), PPO epochs: {args.ppo_epochs}')
    print('=' * 80)

    # ── Allocate shared memory ONCE ──
    obs_shm = shared_memory.SharedMemory(create=True, size=W * OBS_SIZE * 4)
    result_shm = shared_memory.SharedMemory(create=True, size=W * RESULT_SIZE * 4)
    status_shm = shared_memory.SharedMemory(create=True, size=W * 4)

    # NumPy views into shared memory (main process side)
    obs_np = np.ndarray((W * OBS_SIZE,), dtype=np.float32, buffer=obs_shm.buf)
    result_np = np.ndarray((W * RESULT_SIZE,), dtype=np.float32, buffer=result_shm.buf)
    status_np = np.ndarray((W,), dtype=np.int32, buffer=status_shm.buf)

    # Initialize to idle
    obs_np[:] = 0
    result_np[:] = 0
    status_np[:] = IDLE

    # Shared epsilon — workers read this, main updates it between iterations
    epsilon_value = mp.Value('d', args.epsilon)

    # Shared stop event
    stop_event = mp.Event()

    # ── Start persistent workers ONCE ──
    pipes = []        # parent ends (for receiving transitions)
    workers_list = []
    for w in range(W):
        parent_conn, child_conn = mp.Pipe()
        pipes.append(parent_conn)
        p = mp.Process(
            target=worker_process,
            args=(w, obs_shm.name, result_shm.name, status_shm.name,
                  child_conn, stop_event, epsilon_value),
            daemon=True,
        )
        p.start()
        child_conn.close()  # main doesn't need the send end
        workers_list.append(p)

    print(f'Started {W} persistent worker processes.')

    try:
        # ── Main loop: inference server + periodic PPO ──
        model.eval()
        all_transitions = []
        iter_hands = 0
        iter_reward = 0.0
        t_iter_start = time.time()
        t_last_log = time.time()
        workers_finished = 0
        total_inferences = 0

        while total_hands < args.total_hands and workers_finished < W:
            # --- Step 1: GPU inference for any WAITING workers ---
            n_inferred = run_inference_batch(model, obs_np, result_np, status_np, W, device)
            total_inferences += n_inferred

            # If no workers were waiting, yield briefly to avoid burning CPU
            if n_inferred == 0:
                time.sleep(0.00001)  # 10us

            # --- Step 2: Drain transition pipes (non-blocking) ---
            for i, pipe in enumerate(pipes):
                if pipe is None:
                    continue
                try:
                    while pipe.poll():
                        data = pipe.recv()
                        if data is None:
                            # Worker signaled completion
                            workers_finished += 1
                            pipes[i] = None
                        else:
                            for t in data:
                                all_transitions.append(t)
                                if t[8] > 0.5:  # done flag
                                    iter_reward += t[6]
                                    iter_hands += 1
                except (BrokenPipeError, EOFError):
                    workers_finished += 1
                    pipes[i] = None

            # --- Step 3: PPO update when enough hands accumulated ---
            if iter_hands >= args.hands_per_iter:
                t_ppo_start = time.time()
                collect_time = t_ppo_start - t_iter_start
                iteration += 1

                # Run PPO
                update_stats = ppo_update(
                    model, optimizer, all_transitions, device,
                    epochs=args.ppo_epochs,
                    mini_batch_size=args.mini_batch_size,
                )
                ppo_time = time.time() - t_ppo_start

                # Update counters
                total_hands += iter_hands
                elapsed = time.time() - t_iter_start
                h_per_s = iter_hands / elapsed if elapsed > 0 else 0
                avg_rew = iter_reward / max(iter_hands, 1)
                reward_window.append(avg_rew)
                rew100 = np.mean(reward_window) if reward_window else 0

                # Update epsilon (decay after 80% progress)
                progress = total_hands / args.total_hands
                eps = max(0.05, args.epsilon * (1 - max(0, progress - 0.8) / 0.2))
                epsilon_value.value = eps

                # Switch back to eval mode for inference
                model.eval()

                # Log
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

                # Save checkpoint
                if iteration % args.save_interval == 0:
                    torch.save({
                        'model': model.state_dict(),
                        'optimizer': optimizer.state_dict(),
                        'total_hands': total_hands,
                        'iteration': iteration,
                    }, args.out)
                    print(f'  [Save] {args.out} ({total_hands:,} hands)')

                # Reset iteration accumulators
                all_transitions = []
                iter_hands = 0
                iter_reward = 0.0
                t_iter_start = time.time()

    except KeyboardInterrupt:
        print('\nInterrupted — saving checkpoint...')

    finally:
        # ── Cleanup ──
        stop_event.set()

        # Wait for workers to exit gracefully
        for p in workers_list:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()

        # Clean up shared memory
        obs_shm.close()
        obs_shm.unlink()
        result_shm.close()
        result_shm.unlink()
        status_shm.close()
        status_shm.unlink()

    # Final save
    torch.save({
        'model': model.state_dict(),
        'optimizer': optimizer.state_dict(),
        'total_hands': total_hands,
        'iteration': iteration,
    }, args.out)
    print(f'\nDone! {total_hands:,} hands, {iteration} iterations. Model: {args.out}')


if __name__ == '__main__':
    mp.set_start_method('spawn')
    main()
