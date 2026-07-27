"""Phase 2 Population PPO with KL-to-anchor — SKELETON.

This skeleton validates the structural contract for the real Phase D trainer:
  - Load BC anchor checkpoint as init AND as KL anchor
  - Load opponent pool: frozen anchors (V4 / PathB / v3), heuristics,
    scripted (TODO), Slumbot proxy (TODO env wiring)
  - Sample opponent per game from the configured mix
  - Run PPO update with: standard PPO clip + KL-to-anchor penalty
  - Data-driven anchor_kl decay (NOT fixed schedule)
  - Hard guards on fold/jam collapse

Smoke mode here does NOT run real Slumbot episodes. It:
  - Synthesizes a small batch of states via vec_game_state random rollout
  - Computes the loss with all components active
  - Runs 1 optimizer step
  - Saves a checkpoint + manifest

Real Day 1+ training will wire in:
  - vec_game_state-based parallel self-play with sampled opponents
  - Per-checkpoint eval matrix call
  - Data-driven anchor_kl decay
  - Hard-guard early-stop

Usage (smoke):
  python train_population_ppo.py \
    --anchor-ckpt models/bc/v3_anchor_smoke/best.pt \
    --opponent-mix "self=0.40,heur_v3=0.30,scripted_aggro=0.15,proxy=0.15" \
    --rollout-steps 256 \
    --num-envs 64 \
    --ppo-epochs 2 \
    --minibatch-size 64 \
    --lr 1e-4 \
    --entropy-coef 0.01 \
    --anchor-kl-coef 0.05 \
    --target-kl 0.03 \
    --smoke \
    --out models/ppo/popmix_smoke
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
sys.path.insert(0, str(REPO_ROOT / 'scripts' / 'alpha_holdem'))
sys.path.insert(0, str(THIS_DIR / 'common'))

from manifest import write_manifest, write_md_report
from alpha_holdem.network import AlphaHoldemNet, count_parameters
from vec_game_state import VecHUNLState
from train_vec import encode_obs_batched

VERSION = '0.1.0-skeleton'

NUM_ACTIONS = 9


def load_policy(ckpt_path: str, device: str) -> tuple[AlphaHoldemNet, dict]:
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    norm = ck.get('norm_layer', 'gn')
    m = AlphaHoldemNet(num_actions=NUM_ACTIONS, norm_layer=norm).to(device)
    m.eval()
    m(torch.zeros(2, 6, 4, 13, device=device),
      torch.zeros(2, 25, 4, 5, device=device),
      torch.zeros(2, 2, device=device))
    m.load_state_dict(ck['model'])
    return m, ck


def parse_mix(s: str) -> dict[str, float]:
    parts = [p.strip() for p in s.split(',') if p.strip()]
    mix = {}
    for p in parts:
        k, _, v = p.partition('=')
        mix[k.strip()] = float(v)
    total = sum(mix.values())
    return {k: v / total for k, v in mix.items()}


def card_int_to_str(c: int):
    if c < 0: return None
    return '23456789TJQKA'[c // 4] + 'shdc'[c % 4]


def compute_gae(rewards, values, dones, gamma=0.999, lam=0.95):
    """Standard GAE-λ. rewards, values, dones are per-transition arrays in order.

    Hand boundaries are flagged by dones[t]=1, which both terminates the bootstrap
    and resets the running advantage accumulator. For hands where the last
    transition has reward=terminal_reward, intermediate steps have reward=0.
    """
    n = len(rewards)
    advantages = np.zeros(n, dtype=np.float32)
    last_gae = 0.0
    last_value = 0.0
    for t in reversed(range(n)):
        if dones[t]:
            # End of hand: no bootstrap from future. Reset accumulator.
            delta = rewards[t] - values[t]
            advantages[t] = delta
            last_gae = delta
            last_value = 0.0
        else:
            delta = rewards[t] + gamma * last_value - values[t]
            advantages[t] = delta + gamma * lam * last_gae
            last_gae = advantages[t]
            last_value = values[t]
    returns = advantages + values
    return advantages, returns


def real_rollout(policy: nn.Module, opponent_mix: dict, n_envs: int, n_hero_hands: int,
                 device: str, seed: int = 42,
                 gamma: float = 0.999, gae_lambda: float = 0.95) -> dict:
    """Run real heads-up rollouts: hero=policy, opp=sampled per-game from opponent_mix.

    Returns flat tensors of hero transitions (s, a, log_prob, value, reward, done, mask)
    PLUS proper GAE-λ advantages and bootstrapped returns.
    """
    from scripted_policies import get_policy
    rng = np.random.default_rng(seed)
    state = VecHUNLState(N=n_envs, effective_stack=200.0, seed=seed)
    state.reset_all()

    # Per-game opponent
    opp_keys = list(opponent_mix.keys())
    opp_probs = np.array([opponent_mix[k] for k in opp_keys])
    per_game_opp = rng.choice(opp_keys, size=n_envs, p=opp_probs).tolist()

    # Per-game hero buffer (lists of transitions until hand ends)
    per_game_buf = [[] for _ in range(n_envs)]
    completed = []  # list of dicts {cards, actions, extras, masks, hero_action, log_prob, value, reward}

    hero_hands_done = 0
    safety_iters = n_hero_hands * 100
    it = 0
    while hero_hands_done < n_hero_hands and it < safety_iters:
        it += 1
        card_np, action_np, extra_np, mask_np = encode_obs_batched(state)
        cp_np = state.current_player.astype(np.int64)
        hero_seat_np = state.hero_player.astype(np.int64)
        is_hero = (cp_np == hero_seat_np)
        to_call_np = state.to_call()

        # Forward policy on all rows (hero rows need real, opp rows ignored)
        policy.eval()
        with torch.no_grad():
            ct = torch.from_numpy(card_np).to(device)
            at = torch.from_numpy(action_np).to(device)
            et = torch.from_numpy(extra_np).to(device)
            mt = torch.from_numpy(mask_np).to(device)
            logits, values = policy(ct, at, et, mt)
            probs = F.softmax(logits, dim=-1)
            dist = torch.distributions.Categorical(probs)
            sampled_all = dist.sample()
            log_probs_all = dist.log_prob(sampled_all)
        # PERF: batch GPU→CPU sync once per step instead of per-game .item() calls
        sampled_np = sampled_all.cpu().numpy()
        log_probs_np = log_probs_all.cpu().numpy()
        values_np = values.squeeze(-1).cpu().numpy()

        # Build actions array — heroes use sampled, opps use their strategy
        chosen = np.zeros(n_envs, dtype=np.int64)
        for i in range(n_envs):
            if state.is_done[i]:
                continue
            if is_hero[i]:
                chosen[i] = int(sampled_np[i])
                # Record transition
                per_game_buf[i].append({
                    'cards': card_np[i].copy(),
                    'actions_obs': action_np[i].copy(),
                    'extras': extra_np[i].copy(),
                    'mask': mask_np[i].copy(),
                    'hero_action': chosen[i],
                    'log_prob': float(log_probs_np[i]),
                    'value': float(values_np[i]),
                })
            else:
                opp_name = per_game_opp[i]
                if opp_name == 'self':
                    chosen[i] = int(sampled_np[i])
                else:
                    fn = get_policy(opp_name)
                    cur = int(cp_np[i])
                    hole = [card_int_to_str(int(state.holes[i, cur, k])) for k in (0, 1)]
                    board = [card_int_to_str(int(c)) for c in state.board[i] if c >= 0]
                    st_dict = {'st': int(state.street[i]), 'to_call': int(to_call_np[i]),
                               'pot_before': int(state.pot[i])}
                    client_pos = 1 if cur == 1 else 0
                    try:
                        chosen[i] = fn(hole, board, st_dict, client_pos, mask_np[i].tolist())
                    except Exception:
                        chosen[i] = next((s for s in range(9) if mask_np[i][s]), 0)

        state.step(chosen)

        if state.is_done.any():
            rewards = state.terminal_rewards()
            done_idx = np.where(state.is_done)[0]
            for i in done_idx:
                buf = per_game_buf[i]
                if buf:
                    r = float(rewards[i])
                    for j, t in enumerate(buf):
                        last = (j == len(buf) - 1)
                        completed.append({**t,
                                          'reward': r if last else 0.0,
                                          'done': 1.0 if last else 0.0})
                    hero_hands_done += 1
                per_game_buf[i] = []
                # New opponent assignment for the reset hand
                per_game_opp[i] = rng.choice(opp_keys, p=opp_probs)
                if hero_hands_done >= n_hero_hands:
                    break
            state.reset_done()

    # Stack into tensors
    if not completed:
        return None
    n = len(completed)
    cards = torch.from_numpy(np.stack([t['cards'] for t in completed])).to(device)
    actions_obs = torch.from_numpy(np.stack([t['actions_obs'] for t in completed])).to(device)
    extras = torch.from_numpy(np.stack([t['extras'] for t in completed])).to(device)
    masks = torch.from_numpy(np.stack([t['mask'] for t in completed])).to(device)
    hero_actions = torch.tensor([t['hero_action'] for t in completed], device=device, dtype=torch.long)
    old_log_probs = torch.tensor([t['log_prob'] for t in completed], device=device, dtype=torch.float32)
    old_values_np = np.array([t['value'] for t in completed], dtype=np.float32)
    rewards_np = np.array([t['reward'] for t in completed], dtype=np.float32)
    dones_np = np.array([t['done'] for t in completed], dtype=np.float32)

    # Proper GAE-λ computed in numpy (transitions are already in hand-order; each
    # hand's last transition has done=1, which resets the GAE accumulator).
    advantages_np, returns_np = compute_gae(rewards_np, old_values_np, dones_np,
                                             gamma=gamma, lam=gae_lambda)

    old_values = torch.from_numpy(old_values_np).to(device)
    rewards = torch.from_numpy(rewards_np).to(device)
    dones = torch.from_numpy(dones_np).to(device)
    advantages = torch.from_numpy(advantages_np).to(device)
    returns = torch.from_numpy(returns_np).to(device)

    # Diagnostics for advantage distribution (logged in caller)
    adv_stats = {
        'mean': float(advantages_np.mean()),
        'std': float(advantages_np.std()),
        'min': float(advantages_np.min()),
        'max': float(advantages_np.max()),
        'p5': float(np.percentile(advantages_np, 5)),
        'p95': float(np.percentile(advantages_np, 95)),
    }
    ret_stats = {
        'mean': float(returns_np.mean()),
        'std': float(returns_np.std()),
        'min': float(returns_np.min()),
        'max': float(returns_np.max()),
    }
    return {
        'cards': cards, 'actions_obs': actions_obs, 'extras': extras, 'masks': masks,
        'hero_actions': hero_actions, 'old_log_probs': old_log_probs, 'old_values': old_values,
        'rewards': rewards, 'dones': dones, 'advantages': advantages, 'returns': returns,
        'n_hero_hands': hero_hands_done, 'n_transitions': n,
        'adv_stats': adv_stats, 'ret_stats': ret_stats,
    }


def kl_to_anchor(policy_logits: torch.Tensor, anchor_logits: torch.Tensor,
                 legal_mask: torch.Tensor) -> torch.Tensor:
    """KL( policy || anchor ) on the legal-masked action distribution."""
    p = F.softmax(policy_logits, dim=-1).clamp_min(1e-12)
    q = F.softmax(anchor_logits, dim=-1).clamp_min(1e-12)
    return (p * (p.log() - q.log())).sum(dim=-1).mean()


# 9-slot -> 4-class grouping for per-class anchor KL (Option B). Pins the
# fold/call/raise/allin CLASS proportions to BC while leaving within-class
# (card-dependent raise-size) choice free — targets the CC-drift failure mode
# where full-dist KL preserves mix SHAPE but not per-decision discipline.
ACTION_CLASS_SLOTS = ([0], [1], [2, 3, 4, 5, 6, 7], [8])  # fold / call / raise / allin


def class_kl_to_anchor(policy_logits: torch.Tensor, anchor_logits: torch.Tensor,
                       legal_mask: torch.Tensor) -> torch.Tensor:
    """KL( policy_class || anchor_class ) on the 4-way fold/call/raise/allin class dist."""
    p = F.softmax(policy_logits, dim=-1)
    q = F.softmax(anchor_logits, dim=-1)
    p_cls = torch.stack([p[..., idx].sum(dim=-1) for idx in ACTION_CLASS_SLOTS], dim=-1).clamp_min(1e-12)
    q_cls = torch.stack([q[..., idx].sum(dim=-1) for idx in ACTION_CLASS_SLOTS], dim=-1).clamp_min(1e-12)
    return (p_cls * (p_cls.log() - q_cls.log())).sum(dim=-1).mean()


def check_collapse_guards(action_mix: dict[int, float]) -> list[str]:
    """Return list of warning strings if hard-guards trip."""
    warnings = []
    for slot, freq in action_mix.items():
        if slot == 0 and freq > 0.92:
            warnings.append(f'fold rate {freq:.2f} > 0.92 (collapse)')
        if slot == 8 and freq > 0.15:
            warnings.append(f'all-in rate {freq:.2f} > 0.15 (over-aggressive)')
    return warnings


def ppo_update_pass(policy, anchor, opt, rollout, *, ppo_epochs: int, minibatch_size: int,
                    eps_clip: float = 0.2, entropy_coef: float = 0.01,
                    anchor_kl_coef: float = 0.05, target_kl: float = 0.03,
                    value_coef: float = 0.5, max_grad_norm: float = 1.0,
                    kl_mode: str = 'full') -> dict:
    """One full PPO update pass over collected rollout. Returns aggregate metrics."""
    cards = rollout['cards']
    actions_obs = rollout['actions_obs']
    extras = rollout['extras']
    masks = rollout['masks']
    hero_actions = rollout['hero_actions']
    old_log_probs = rollout['old_log_probs']
    advantages = rollout['advantages']
    returns = rollout['returns']
    n = rollout['n_transitions']
    device = cards.device

    if n > 1:
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

    policy.train()
    sums = {'policy_loss': 0.0, 'value_loss': 0.0, 'entropy': 0.0,
            'anchor_kl': 0.0, 'class_kl': 0.0, 'approx_kl': 0.0, 'clipfrac': 0.0, 'steps': 0}
    early_stopped = False
    epochs_done = 0
    for ep in range(ppo_epochs):
        idx = torch.randperm(n, device=device)
        epoch_kl_total = 0.0
        epoch_steps = 0
        for s in range(0, n, minibatch_size):
            mb = idx[s:s + minibatch_size]
            logits, values = policy(cards[mb], actions_obs[mb], extras[mb], masks[mb])
            with torch.no_grad():
                a_logits, _ = anchor(cards[mb], actions_obs[mb], extras[mb], masks[mb])
            probs = F.softmax(logits, dim=-1)
            dist = torch.distributions.Categorical(probs)
            new_lp = dist.log_prob(hero_actions[mb])
            ratio = torch.exp(new_lp - old_log_probs[mb])
            adv = advantages[mb]
            surr1 = ratio * adv
            surr2 = torch.clamp(ratio, 1 - eps_clip, 1 + eps_clip) * adv
            policy_loss = -torch.min(surr1, surr2).mean()
            value_loss = F.mse_loss(values.squeeze(-1), returns[mb])
            entropy = dist.entropy().mean()
            anchor_kl = kl_to_anchor(logits, a_logits, masks[mb])
            class_kl = class_kl_to_anchor(logits, a_logits, masks[mb])
            with torch.no_grad():
                approx_kl = (old_log_probs[mb] - new_lp).mean().item()
                clipfrac = ((ratio < 1 - eps_clip) | (ratio > 1 + eps_clip)).float().mean().item()
            if kl_mode == 'class':
                kl_penalty = class_kl
            elif kl_mode == 'both':
                kl_penalty = anchor_kl + class_kl
            else:
                kl_penalty = anchor_kl
            loss = (policy_loss + value_coef * value_loss - entropy_coef * entropy
                    + anchor_kl_coef * kl_penalty)
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), max_grad_norm)
            opt.step()
            sums['policy_loss'] += policy_loss.item()
            sums['value_loss'] += value_loss.item()
            sums['entropy'] += entropy.item()
            sums['anchor_kl'] += anchor_kl.item()
            sums['class_kl'] += class_kl.item()
            sums['approx_kl'] += approx_kl
            sums['clipfrac'] += clipfrac
            sums['steps'] += 1
            epoch_kl_total += approx_kl
            epoch_steps += 1
        epochs_done += 1
        if target_kl > 0 and epoch_steps > 0:
            mean_epoch_kl = epoch_kl_total / epoch_steps
            if abs(mean_epoch_kl) > target_kl:
                early_stopped = True
                break

    n_steps = max(sums['steps'], 1)
    return {
        'policy_loss': sums['policy_loss'] / n_steps,
        'value_loss': sums['value_loss'] / n_steps,
        'entropy': sums['entropy'] / n_steps,
        'anchor_kl': sums['anchor_kl'] / n_steps,
        'class_kl': sums['class_kl'] / n_steps,
        'approx_kl': sums['approx_kl'] / n_steps,
        'clipfrac': sums['clipfrac'] / n_steps,
        'epochs_done': epochs_done,
        'early_stopped': early_stopped,
    }


def evaluate_action_mix(policy, rollout) -> dict[int, float]:
    """Run policy in eval mode on the rollout transitions and return action mix."""
    policy.eval()
    with torch.no_grad():
        logits, _ = policy(rollout['cards'], rollout['actions_obs'],
                            rollout['extras'], rollout['masks'])
        preds = logits.argmax(-1)
        n = len(preds)
        counts = torch.bincount(preds, minlength=NUM_ACTIONS).float()
    return {int(s): float(counts[s] / max(n, 1)) for s in range(NUM_ACTIONS)}


def save_checkpoint(policy, opt, path: Path, *, total_hands: int, iteration: int,
                    anchor_kl_coef: float, opponent_mix: dict, args):
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        'model': policy.state_dict(),
        'optimizer': opt.state_dict(),
        'env_version': 'v4',
        'obs_version': 'v4',
        'action_space_version': '9slot_v4',
        'starting_stack_bb': 200.0,
        'trainer': 'population_ppo',
        'norm_layer': 'gn',
        'freeze_bn_stats': False,
        'total_hands': total_hands,
        'iteration': iteration,
        'anchor_kl_coef': anchor_kl_coef,
        'opponent_mix': opponent_mix,
        'init_anchor_ckpt': args.anchor_ckpt,
    }, path)


def train_real(args, device: str) -> dict:
    """RL-1 production training loop. Iterates: collect → PPO update → log → checkpoint.

    Hard stops on fold/jam collapse or anchor-KL explosion. Anchor-KL decay is
    DATA-DRIVEN: decay only when last decay-window mean approx_kl < 0.5 × current coef.
    """
    print(f'=== Population PPO REAL training ===')
    print(f'Init ckpt:    {args.anchor_ckpt}')
    print(f'Total hands:  {args.total_hands:,}')
    print(f'Per-iter:     {args.hands_per_iter:,}')
    print(f'PPO epochs:   {args.ppo_epochs}')
    print(f'target_kl:    {args.target_kl}')
    print(f'lr:           {args.lr}')
    print(f'anchor_kl0:   {args.anchor_kl_coef}')

    policy, _ = load_policy(args.anchor_ckpt, device)
    anchor, _ = load_policy(args.anchor_ckpt, device)
    anchor.eval()
    for p in anchor.parameters():
        p.requires_grad_(False)
    print(f'Policy params: {count_parameters(policy):,}')

    if args.warmup_ckpt:
        # Overlay value-head warmup weights onto the trainable policy. The KL
        # anchor reference (BC) is NOT touched — it remains the original BC
        # distribution so anchor_kl measures drift from BC, not from warmup.
        # Verifying policy_head bit-exact between BC and warmup defends against
        # accidentally promoting a different policy via the warmup path.
        print(f'Warmup ckpt:  {args.warmup_ckpt}')
        pre_ph = {n: p.detach().clone() for n, p in policy.policy_head.named_parameters()}
        wm = torch.load(args.warmup_ckpt, map_location=device, weights_only=False)
        if 'model' not in wm:
            raise RuntimeError(f'warmup ckpt {args.warmup_ckpt} has no "model" key')
        policy.load_state_dict(wm['model'])
        max_delta = 0.0
        for n, p in policy.policy_head.named_parameters():
            d = (p - pre_ph[n]).abs().max().item()
            if d > max_delta:
                max_delta = d
        print(f'Warmup policy_head delta vs BC anchor: {max_delta:.3e} '
              f'(expected ~0 for frozen-policy_head warmup)')
        if max_delta > 1e-4:
            print(f'WARNING: warmup policy_head drift {max_delta:.3e} exceeds 1e-4; '
                  f'BC policy distribution may be altered before PPO starts')
        wm_meta = wm.get('warmup_meta')
        if wm_meta:
            print(f'Warmup meta:  vloss {wm_meta.get("initial_value_loss", "?")} -> '
                  f'{wm_meta.get("final_value_loss", "?")}, '
                  f'rollout_hands={wm_meta.get("rollout_hands", "?")}')

    opt = torch.optim.AdamW(policy.parameters(), lr=args.lr, weight_decay=1e-4)
    opp_mix = parse_mix(args.opponent_mix)
    print(f'Opponent mix (normalized): {opp_mix}')

    out_dir = REPO_ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / 'train.log'
    log_fp = open(log_path, 'a', encoding='utf-8')

    total_hands = 0
    iteration = 0
    history = []
    anchor_kl_coef = args.anchor_kl_coef
    last_decay_check_iter = 0
    decay_window_kls: list[float] = []
    checkpoint_hands = sorted(set([int(x) for x in args.checkpoint_at.split(',') if x.strip()]))
    benched_at: set[int] = set()
    hard_stop_reason = None
    # Sustained-failure counters (added 2026-05-30 per scale-test gates):
    # - vloss sustained > 1000 after 500k hands (cold-start critic that never recovered)
    # - cc sustained < 3% (RL-1-style passive→over-aggressive collapse)
    consec_high_vloss = 0
    consec_low_cc = 0
    t_start = time.time()

    while total_hands < args.total_hands:
        iteration += 1
        # Collect rollout
        t0 = time.time()
        rollout = real_rollout(policy, opp_mix, args.num_envs,
                               args.hands_per_iter, device=device,
                               seed=args.seed + iteration,
                               gamma=args.gamma, gae_lambda=args.gae_lambda)
        if rollout is None:
            print(f'[iter {iteration}] WARNING: no transitions collected')
            continue
        t_collect = time.time() - t0
        n_trans = rollout['n_transitions']
        n_hands_iter = rollout['n_hero_hands']

        # PPO update
        t0 = time.time()
        metrics = ppo_update_pass(policy, anchor, opt, rollout,
                                  ppo_epochs=args.ppo_epochs,
                                  minibatch_size=args.minibatch_size,
                                  eps_clip=args.eps_clip,
                                  entropy_coef=args.entropy_coef,
                                  anchor_kl_coef=anchor_kl_coef,
                                  target_kl=args.target_kl,
                                  value_coef=args.value_coef,
                                  max_grad_norm=args.max_grad_norm,
                                  kl_mode=args.kl_mode)
        t_update = time.time() - t0

        # Eval-mode action mix
        action_mix = evaluate_action_mix(policy, rollout)
        warnings = check_collapse_guards(action_mix)

        # Update tracking
        total_hands += n_hands_iter
        decay_window_kls.append(abs(metrics['approx_kl']))
        rec = {
            'iter': iteration,
            'total_hands': total_hands,
            'n_trans': n_trans,
            'collect_s': t_collect,
            'update_s': t_update,
            'anchor_kl_coef': anchor_kl_coef,
            'action_mix': action_mix,
            'warnings': warnings,
            **metrics,
            'adv_stats': rollout['adv_stats'],
        }
        history.append(rec)

        # Log line
        am_str = f'F={action_mix[0]:.2f}/CC={action_mix[1]:.2f}/' \
                 f'R={sum(action_mix[s] for s in range(2,8)):.2f}/A={action_mix[8]:.2f}'
        log_line = (
            f'[iter {iteration:4d}] hands={total_hands:,}/{args.total_hands:,}  '
            f'ploss={metrics["policy_loss"]:+.4f}  vloss={metrics["value_loss"]:.3f}  '
            f'ent={metrics["entropy"]:.3f}  '
            f'kl={metrics["approx_kl"]:+.4f}  akl={metrics["anchor_kl"]:.4f}  '
            f'ckl={metrics["class_kl"]:.4f}  '
            f'akl_coef={anchor_kl_coef:.4f}  '
            f'clip={metrics["clipfrac"]:.3f}  '
            f'ppoEp={metrics["epochs_done"]}{"*" if metrics["early_stopped"] else ""}  '
            f'mix[{am_str}]  '
            f't=c{t_collect:.1f}+u{t_update:.1f}s'
        )
        if warnings:
            log_line += '  WARN=' + ';'.join(warnings)
        print(log_line)
        log_fp.write(log_line + '\n')
        log_fp.flush()

        # Hard stops
        if action_mix[0] > 0.92:
            hard_stop_reason = f'fold rate {action_mix[0]:.2f} > 0.92 collapse'
            break
        if action_mix[8] > 0.15:
            hard_stop_reason = f'all-in rate {action_mix[8]:.2f} > 0.15 over-aggressive'
            break
        if metrics['anchor_kl'] > 5.0:
            hard_stop_reason = f'anchor_kl {metrics["anchor_kl"]:.2f} explosion'
            break
        # Sustained vloss (only after 500k — cold-start is allowed to be noisy).
        if total_hands > 500_000 and metrics['value_loss'] > 1000:
            consec_high_vloss += 1
        else:
            consec_high_vloss = 0
        if consec_high_vloss >= 3:
            hard_stop_reason = (f'value_loss > 1000 for {consec_high_vloss} consecutive iters '
                                f'after 500k hands (last={metrics["value_loss"]:.0f}); '
                                f'critic did not recover')
            break
        # Sustained cc collapse (RL-1-style passive→aggressive degeneration).
        if action_mix[1] < 0.03:
            consec_low_cc += 1
        else:
            consec_low_cc = 0
        if consec_low_cc >= 3:
            hard_stop_reason = (f'cc rate < 3% for {consec_low_cc} consecutive iters '
                                f'(last={action_mix[1]:.4f}); call/check mass collapsed')
            break

        # Anchor KL data-driven decay: only decay when recent mean approx_kl < 0.5 × current coef
        # Check every 2M hands
        if total_hands - last_decay_check_iter >= 2_000_000 and len(decay_window_kls) >= 5:
            recent_kl_mean = float(np.mean(decay_window_kls[-20:]))
            if recent_kl_mean < 0.5 * anchor_kl_coef and anchor_kl_coef > 0.001:
                anchor_kl_coef = anchor_kl_coef * 0.5
                print(f'  [anchor_kl decay] recent_kl {recent_kl_mean:.4f} < 0.5*coef; '
                      f'new coef={anchor_kl_coef:.4f}')
            else:
                print(f'  [anchor_kl hold] recent_kl {recent_kl_mean:.4f} >= 0.5*coef={anchor_kl_coef:.4f}')
            last_decay_check_iter = total_hands
            decay_window_kls = []

        # Checkpoint at milestones
        for ck_h in checkpoint_hands:
            if total_hands >= ck_h and ck_h not in benched_at:
                ck_path = out_dir / f'ckpt_{ck_h//1000000}M.pt'
                save_checkpoint(policy, opt, ck_path,
                                total_hands=total_hands, iteration=iteration,
                                anchor_kl_coef=anchor_kl_coef, opponent_mix=opp_mix, args=args)
                print(f'  [CKPT] saved {ck_path}  ({total_hands:,} hands)')
                benched_at.add(ck_h)

    # Final checkpoint (overwrites if needed)
    final_path = out_dir / 'final.pt'
    save_checkpoint(policy, opt, final_path,
                    total_hands=total_hands, iteration=iteration,
                    anchor_kl_coef=anchor_kl_coef, opponent_mix=opp_mix, args=args)
    log_fp.close()
    elapsed = time.time() - t_start

    # Manifest + summary
    write_manifest(out_dir / 'manifest.json',
                   script='phase2/train_population_ppo.py', version=VERSION,
                   args=vars(args), seed=args.seed,
                   inputs=[args.anchor_ckpt],
                   outputs=[final_path, log_path, out_dir / 'history.json'],
                   extra={'elapsed_s': elapsed, 'total_hands': total_hands,
                          'iterations': iteration,
                          'final_anchor_kl_coef': anchor_kl_coef,
                          'hard_stop_reason': hard_stop_reason,
                          'final_action_mix': history[-1]['action_mix'] if history else None})
    (out_dir / 'history.json').write_text(json.dumps(history, indent=2), encoding='utf-8')

    final_am = history[-1]['action_mix'] if history else {}
    md = [
        f'**Init**: {args.anchor_ckpt}',
        f'**Opponent mix**: {opp_mix}',
        f'**Total hands**: {total_hands:,} / target {args.total_hands:,}',
        f'**Iterations**: {iteration}',
        f'**Elapsed**: {elapsed:.0f}s ({elapsed/60:.1f} min)',
        f'**Hard stop**: {hard_stop_reason or "none"}',
        '',
        '### Final action mix',
        f'F={final_am.get(0,0):.3f}  CC={final_am.get(1,0):.3f}  '
        f'R(2-7)={sum(final_am.get(s,0) for s in range(2,8)):.3f}  '
        f'A={final_am.get(8,0):.3f}',
        '',
        f'Final anchor_kl_coef: {anchor_kl_coef:.4f}',
    ]
    write_md_report(out_dir / 'report.md',
                    title=f'Population PPO RL-1 ({"smoke" if args.smoke else "real"})',
                    sections=[('Summary', '\n'.join(md))])

    return {
        'total_hands': total_hands,
        'iterations': iteration,
        'elapsed_s': elapsed,
        'hard_stop_reason': hard_stop_reason,
        'final_action_mix': final_am,
        'history_length': len(history),
    }


def smoke_one_step(args, device: str) -> dict:
    """Run a single PPO update on REAL vec_game_state rollouts with sampled opponents."""
    # Build policy from BC anchor and a frozen copy as anchor
    policy, ck = load_policy(args.anchor_ckpt, device)
    anchor, _ = load_policy(args.anchor_ckpt, device)
    anchor.eval()
    for p in anchor.parameters():
        p.requires_grad_(False)
    print(f'Policy params: {count_parameters(policy):,}')

    opt = torch.optim.AdamW(policy.parameters(), lr=args.lr, weight_decay=1e-4)

    opp_mix = parse_mix(args.opponent_mix)
    print(f'Opponent mix (normalized): {opp_mix}')

    # === REAL ROLLOUT: collect transitions from heads-up play vs sampled opponents ===
    n_hero_hands_target = max(args.rollout_steps, 32)
    print(f'Rolling out {args.num_envs} envs to collect {n_hero_hands_target} hero hands...')
    t_collect_0 = time.time()
    rollout = real_rollout(policy, opp_mix, args.num_envs, n_hero_hands_target,
                           device=device, seed=args.seed)
    collect_t = time.time() - t_collect_0
    if rollout is None:
        return {'error': 'no transitions collected'}
    n = rollout['n_transitions']
    print(f'Collected {n} hero transitions from {rollout["n_hero_hands"]} hands in {collect_t:.2f}s')
    print(f'  Adv stats: mean={rollout["adv_stats"]["mean"]:+.3f}  std={rollout["adv_stats"]["std"]:.3f}  '
          f'[{rollout["adv_stats"]["min"]:+.2f}, {rollout["adv_stats"]["max"]:+.2f}]  '
          f'p5/p95=[{rollout["adv_stats"]["p5"]:+.2f}, {rollout["adv_stats"]["p95"]:+.2f}]')
    print(f'  Ret stats: mean={rollout["ret_stats"]["mean"]:+.3f}  std={rollout["ret_stats"]["std"]:.3f}  '
          f'[{rollout["ret_stats"]["min"]:+.2f}, {rollout["ret_stats"]["max"]:+.2f}]')

    cards = rollout['cards']
    actions_obs = rollout['actions_obs']
    extras = rollout['extras']
    masks = rollout['masks']
    hero_actions = rollout['hero_actions']
    old_log_probs = rollout['old_log_probs']
    advantages = rollout['advantages']
    returns = rollout['returns']

    # Normalize advantages
    if n > 1:
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

    # PPO update with KL-to-anchor
    policy.train()
    losses_log = []
    for ep in range(args.ppo_epochs):
        idx = torch.randperm(n, device=device)
        for s in range(0, n, args.minibatch_size):
            mb = idx[s:s + args.minibatch_size]
            logits, values = policy(cards[mb], actions_obs[mb], extras[mb], masks[mb])
            with torch.no_grad():
                a_logits, _ = anchor(cards[mb], actions_obs[mb], extras[mb], masks[mb])
            probs = F.softmax(logits, dim=-1)
            dist = torch.distributions.Categorical(probs)
            new_lp = dist.log_prob(hero_actions[mb])
            ratio = torch.exp(new_lp - old_log_probs[mb])
            adv = advantages[mb]
            surr1 = ratio * adv
            surr2 = torch.clamp(ratio, 1 - 0.2, 1 + 0.2) * adv
            policy_loss = -torch.min(surr1, surr2).mean()
            value_loss = F.mse_loss(values.squeeze(-1), returns[mb])
            entropy = dist.entropy().mean()
            anchor_kl = kl_to_anchor(logits, a_logits, masks[mb])
            loss = (policy_loss
                    + 0.5 * value_loss
                    - args.entropy_coef * entropy
                    + args.anchor_kl_coef * anchor_kl)

            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            opt.step()

            losses_log.append({
                'policy_loss': policy_loss.item(),
                'value_loss': value_loss.item(),
                'entropy': entropy.item(),
                'anchor_kl': anchor_kl.item(),
                'total_loss': loss.item(),
            })

    # Post-update action mix
    policy.eval()
    with torch.no_grad():
        logits, _ = policy(cards, actions_obs, extras, masks)
        preds = logits.argmax(-1)
        counts = torch.bincount(preds, minlength=NUM_ACTIONS).float()
        action_mix = {int(s): float(counts[s] / n) for s in range(NUM_ACTIONS)}
    print(f'Final action mix: {action_mix}')
    warnings = check_collapse_guards(action_mix)
    if warnings:
        print(f'[guards] {warnings}')

    return {
        'mode': 'real_rollouts',
        'n_hero_hands': rollout['n_hero_hands'],
        'n_transitions': n,
        'collect_elapsed_s': collect_t,
        'losses_per_minibatch': losses_log,
        'final_action_mix': action_mix,
        'guard_warnings': warnings,
        'opponent_mix_normalized': opp_mix,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--anchor-ckpt', required=True, help='BC anchor checkpoint path')
    p.add_argument('--warmup-ckpt', default=None,
                   help='Optional value-head warmup checkpoint. After loading the BC '
                        'anchor into the trainable policy, this file is overlaid via '
                        'load_state_dict. The KL anchor reference is NEVER overlaid — '
                        'it stays bit-exact with the BC anchor for valid KL comparison. '
                        'Drift in policy_head between BC and warmup is reported; '
                        'expect ~0 if the warmup ran with frozen policy_head.')
    p.add_argument('--opponent-mix', default='self=0.40,heuristic_v3=0.30,scripted_aggro=0.15,fold=0.15')
    p.add_argument('--rollout-steps', type=int, default=256, help='(smoke-only) hero hands per smoke step')
    p.add_argument('--num-envs', type=int, default=64)
    p.add_argument('--ppo-epochs', type=int, default=2)
    p.add_argument('--minibatch-size', type=int, default=64)
    p.add_argument('--lr', type=float, default=3e-5)
    p.add_argument('--entropy-coef', type=float, default=0.01)
    p.add_argument('--anchor-kl-coef', type=float, default=0.05,
                   help='Initial value; real training uses data-driven decay')
    p.add_argument('--kl-mode', choices=['full', 'class', 'both'], default='full',
                   help="Anchor-KL form. 'full'=KL over all 9 slots (default, prior behavior). "
                        "'class'=KL over the 4-way fold/call/raise/allin CLASS dist only "
                        "(Option B: pins class proportions to BC, frees within-class raise sizing). "
                        "'both'=sum of full + class. anchor_kl_coef (and its decay) scales the chosen term.")
    p.add_argument('--target-kl', type=float, default=0.03)
    p.add_argument('--eps-clip', type=float, default=0.2)
    p.add_argument('--value-coef', type=float, default=0.5)
    p.add_argument('--max-grad-norm', type=float, default=1.0)
    p.add_argument('--gamma', type=float, default=0.999)
    p.add_argument('--gae-lambda', type=float, default=0.95)
    p.add_argument('--device', default='cuda')
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--smoke', action='store_true',
                   help='Run 1 PPO step on synthetic data; validates plumbing only')
    # Real training loop knobs
    p.add_argument('--total-hands', type=int, default=5_000_000,
                   help='RL-1 default = 5M. Real training only.')
    p.add_argument('--hands-per-iter', type=int, default=50_000,
                   help='Hero hands collected per PPO update iteration.')
    p.add_argument('--checkpoint-at', type=str, default='1000000,3000000,5000000',
                   help='Comma-separated hand counts where to save milestone checkpoints.')
    p.add_argument('--out', required=True)
    args = p.parse_args()

    device = 'cuda' if (args.device == 'cuda' and torch.cuda.is_available()) else 'cpu'
    print(f'Device: {device}')
    torch.manual_seed(args.seed)

    if not args.smoke:
        # Real training (RL-1 5M etc.) — writes its own manifest + report inside train_real
        result = train_real(args, device)
        print(f'\n=== RL run complete ===')
        print(f'Hands trained: {result["total_hands"]:,}')
        print(f'Iterations:    {result["iterations"]}')
        print(f'Elapsed:       {result["elapsed_s"]:.0f}s ({result["elapsed_s"]/60:.1f} min)')
        if result['hard_stop_reason']:
            print(f'HARD STOP:    {result["hard_stop_reason"]}')
        print(f'Final action mix: {result["final_action_mix"]}')
        return

    t0 = time.time()
    result = smoke_one_step(args, device)
    elapsed = time.time() - t0
    print(f'\nElapsed: {elapsed:.1f}s')

    out_dir = REPO_ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'smoke_result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')

    write_manifest(out_dir / 'manifest.json',
                   script='phase2/train_population_ppo.py', version=VERSION,
                   args=vars(args), seed=args.seed,
                   inputs=[args.anchor_ckpt],
                   outputs=[out_dir / 'smoke_result.json'],
                   extra={'elapsed_s': elapsed, 'mode': 'smoke'})

    md = [
        f'**Anchor ckpt**: `{args.anchor_ckpt}`',
        f'**Opponent mix**: `{result["opponent_mix_normalized"]}`',
        f'**Rollout**: {args.num_envs} envs × {args.rollout_steps} steps',
        f'**PPO epochs**: {args.ppo_epochs}, minibatch {args.minibatch_size}',
        f'**Anchor KL coef (initial)**: {args.anchor_kl_coef}',
        f'**Target KL**: {args.target_kl}',
        f'**Elapsed**: {elapsed:.1f}s',
        '',
        '## Final action mix',
        '',
        f'`{result["final_action_mix"]}`',
        '',
        '## Guards',
        f'{"⚠ " + ", ".join(result["guard_warnings"]) if result["guard_warnings"] else "all guards pass"}',
        '',
        '## Notes',
        '',
        'This is a skeleton. Day 1+ training will wire in:',
        '- vec_game_state-based parallel self-play with actual opponents from the pool',
        '- GAE advantage computation (not fake random)',
        '- Per-checkpoint Slumbot bench + internal opponent suite via eval_matrix',
        '- Data-driven anchor_kl decay (only when mean approx_kl < 0.5 × current anchor_kl over 2M hands)',
        '- Hard-guard automatic stop (preflop allin > 15%, any-street fold > 92%, etc.)',
    ]
    write_md_report(out_dir / 'report.md',
                    title='Population PPO smoke (skeleton)',
                    sections=[('Summary', '\n'.join(md))])

    print(f'\n[OK] PPO smoke -> {out_dir}')


if __name__ == '__main__':
    main()
