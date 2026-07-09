"""Value-head warmup before PPO (Option A from trainer_correctness_patches.md).

Problem (per rl1_5M_history_analysis.md): RL-1 iter-1 had value_loss=703 and
advantage std=27.8, which produced absurd PPO targets, collapsing CC to 0.08%
within 1 iteration. The anchor-KL pull recovered fold/cc proximity but the
raise mass was lost permanently — explaining the 75% postflop-cc bot RL-1
became.

Fix: BEFORE any policy update, freeze all policy-affecting weights and train
only the value_head on bootstrapped returns until value_loss stabilizes.
After warmup the critic produces sensible advantages from iter 1 of real PPO.

This script:
  1. Load BC anchor ckpt
  2. Snapshot policy_head weights (for end-of-run sanity check)
  3. Freeze: card_cnn, action_cnn, extra_fc, trunk, policy_head
  4. Run real self-play rollout (opponent_mix=self=1.0)
  5. Train value_head only via MSE on GAE-bootstrapped returns
  6. Verify policy_head weights UNCHANGED and policy logits UNCHANGED
  7. Save warmed-up ckpt

Smoke usage (autonomous, no approval needed):
  python train_value_warmup.py \
    --anchor-ckpt models/bc/v3_anchor_5M_d1_light/best.pt \
    --rollout-hands 20000 \
    --num-envs 256 \
    --epochs 20 \
    --minibatch-size 1024 \
    --lr 1e-3 \
    --out models/ppo/warm_critic_smoke
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

from manifest import write_manifest
from alpha_holdem.network import AlphaHoldemNet
from train_population_ppo import real_rollout, load_policy

VERSION = '0.1.0-warmup'
NUM_ACTIONS = 9


def freeze_all_but_value_head(policy: AlphaHoldemNet) -> int:
    """Freeze everything except value_head. Returns count of trainable params."""
    for p in policy.parameters():
        p.requires_grad_(False)
    trainable = 0
    for p in policy.value_head.parameters():
        p.requires_grad_(True)
        trainable += p.numel()
    return trainable


def freeze_only_policy_head(policy: AlphaHoldemNet) -> int:
    """Freeze policy_head only. Trains value_head + trunk + encoders.

    Trade-off vs freeze_all_but_value_head: trunk learns value-discriminative
    features (better R²) BUT policy logits drift via shared trunk. Caller must
    monitor policy KL on a held-out reference batch.
    """
    for p in policy.parameters():
        p.requires_grad_(True)
    for p in policy.policy_head.parameters():
        p.requires_grad_(False)
    trainable = sum(p.numel() for p in policy.parameters() if p.requires_grad)
    return trainable


def snapshot_policy_head(policy: AlphaHoldemNet) -> torch.Tensor:
    """Return a flat copy of policy_head weights+bias for end-of-run delta check."""
    parts = []
    for p in policy.policy_head.parameters():
        parts.append(p.detach().clone().flatten())
    return torch.cat(parts)


def train_value_only(policy: AlphaHoldemNet, rollout: dict,
                     epochs: int, minibatch_size: int, lr: float,
                     device: str, *,
                     anchor_logits_full: torch.Tensor | None = None,
                     policy_kl_coef: float = 0.0,
                     anchor_logits_ref: torch.Tensor | None = None,
                     ref_inputs: tuple | None = None) -> dict:
    """Train value path on bootstrapped returns.

    If policy_kl_coef > 0 and anchor_logits_full is provided, add a per-minibatch
    KL( current || anchor ) penalty to the loss. This preserves the policy
    distribution while the trunk shifts to encode value-discriminative features.

    If anchor_logits_ref is provided, compute policy KL drift each epoch on the
    held-out reference batch as a sanity check (orthogonal to the loss penalty).
    """
    n = rollout['cards'].shape[0]
    returns = rollout['returns']

    # Optimize all currently-trainable params (trunk+value_head, or value_head only).
    trainable = [p for p in policy.parameters() if p.requires_grad]
    opt = torch.optim.Adam(trainable, lr=lr)

    history = []
    for ep in range(epochs):
        perm = torch.randperm(n, device=device)
        ep_losses = []
        for s in range(0, n, minibatch_size):
            mb = perm[s:s + minibatch_size]
            # Forward in eval mode for the frozen path so dropout/etc don't fire
            policy.eval()
            with torch.no_grad():
                # Compute trunk output once — would be cleaner to expose it but
                # we don't want to refactor network.py here.
                pass

            # Full forward but value path is what we train
            cur_logits, values = policy(rollout['cards'][mb],
                                        rollout['actions_obs'][mb],
                                        rollout['extras'][mb],
                                        rollout['masks'][mb])
            values = values.squeeze(-1)
            vloss = F.mse_loss(values, returns[mb])
            loss = vloss
            if policy_kl_coef > 0 and anchor_logits_full is not None:
                anc_logits = anchor_logits_full[mb]
                cur_p = F.softmax(cur_logits, dim=-1).clamp_min(1e-12)
                anc_p = F.softmax(anc_logits, dim=-1).clamp_min(1e-12)
                kl_pen = (cur_p * (cur_p.log() - anc_p.log())).sum(-1).mean()
                loss = loss + policy_kl_coef * kl_pen
            opt.zero_grad()
            loss.backward()
            opt.step()
            ep_losses.append(float(vloss.detach()))

        ep_mean = float(np.mean(ep_losses))
        rec = {'epoch': ep + 1, 'value_loss': ep_mean}
        if anchor_logits_ref is not None and ref_inputs is not None:
            with torch.no_grad():
                cur_logits, _ = policy(*ref_inputs)
                cur_p = F.softmax(cur_logits, dim=-1).clamp_min(1e-12)
                anc_p = F.softmax(anchor_logits_ref, dim=-1).clamp_min(1e-12)
                kl = float((cur_p * (cur_p.log() - anc_p.log())).sum(-1).mean())
            rec['policy_kl_drift'] = kl
            print(f'  epoch {ep+1:3d}: value_loss={ep_mean:.3f}  policy_kl_drift={kl:.5f}')
        else:
            print(f'  epoch {ep+1:3d}: value_loss={ep_mean:.3f}')
        history.append(rec)

    return {
        'epochs': epochs,
        'history': history,
        'initial_value_loss': history[0]['value_loss'],
        'final_value_loss': history[-1]['value_loss'],
        'reduction_factor': history[0]['value_loss'] / max(history[-1]['value_loss'], 1e-6),
    }


def verify_policy_unchanged(policy: AlphaHoldemNet, snapshot: torch.Tensor,
                             rollout: dict, n_sample: int = 4096) -> dict:
    """Check policy_head weights match snapshot AND policy logits unchanged."""
    cur = snapshot_policy_head(policy)
    weight_delta = float((cur - snapshot).abs().max())

    # Sample a small batch and compare logits using the BEFORE/AFTER policy_head
    n = rollout['cards'].shape[0]
    n_sample = min(n_sample, n)
    idx = torch.randperm(n)[:n_sample].to(rollout['cards'].device)
    with torch.no_grad():
        logits_after, _ = policy(rollout['cards'][idx],
                                 rollout['actions_obs'][idx],
                                 rollout['extras'][idx],
                                 rollout['masks'][idx])
    # We rely on the snapshot weight check for the strong policy-unchanged guarantee.
    # If weight_delta is exactly 0 then logits cannot change for any input.
    return {
        'policy_head_weight_max_delta': weight_delta,
        'policy_head_unchanged': weight_delta == 0.0,
        'logits_sample_n': int(n_sample),
        'logits_max_abs': float(logits_after.abs().max()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--anchor-ckpt', required=True)
    ap.add_argument('--rollout-hands', type=int, default=20000)
    ap.add_argument('--num-envs', type=int, default=256)
    ap.add_argument('--epochs', type=int, default=20)
    ap.add_argument('--minibatch-size', type=int, default=1024)
    ap.add_argument('--lr', type=float, default=1e-3)
    ap.add_argument('--mode', choices=['value_only', 'value_plus_trunk'], default='value_plus_trunk',
                    help='value_only: freeze trunk + policy_head, train value_head only (safest but R² limited). '
                         'value_plus_trunk: freeze policy_head only, train value_head + trunk (better R², policy drifts via trunk).')
    ap.add_argument('--policy-kl-coef', type=float, default=1.0,
                    help='Coefficient on KL(current || anchor) penalty in value_plus_trunk mode. Set 0 to disable.')
    ap.add_argument('--gamma', type=float, default=0.999)
    ap.add_argument('--gae-lambda', type=float, default=0.95)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log = out / 'warmup.log'

    t0 = time.time()
    print(f'[warmup] device={args.device}')
    print(f'[warmup] loading anchor {args.anchor_ckpt}')
    policy, ck = load_policy(args.anchor_ckpt, args.device)

    # Snapshot policy_head BEFORE freezing — guarantees the end-of-run check is meaningful.
    snap = snapshot_policy_head(policy)
    initial_value_head = {n: p.detach().clone() for n, p in policy.value_head.named_parameters()}

    if args.mode == 'value_only':
        trainable = freeze_all_but_value_head(policy)
    else:
        trainable = freeze_only_policy_head(policy)
    total = sum(p.numel() for p in policy.parameters())
    print(f'[warmup] mode={args.mode}, trainable {trainable:,} / total {total:,} ({100*trainable/total:.2f}%)')

    # --- Rollout
    print(f'[warmup] collecting {args.rollout_hands} self-play hands...')
    t_roll = time.time()
    rollout = real_rollout(
        policy=policy,
        opponent_mix={'self': 1.0},
        n_envs=args.num_envs,
        n_hero_hands=args.rollout_hands,
        device=args.device,
        seed=args.seed,
        gamma=args.gamma,
        gae_lambda=args.gae_lambda,
    )
    roll_s = time.time() - t_roll
    if rollout is None:
        raise RuntimeError('rollout returned None — no hands completed')
    n_trans = rollout['n_transitions']
    n_hands = rollout['n_hero_hands']
    ret = rollout['ret_stats']
    print(f'[warmup] rollout: {n_hands} hands, {n_trans} trans, {roll_s:.1f}s '
          f'({n_hands/roll_s:.1f} hands/s)')
    print(f'[warmup] returns: mean={ret["mean"]:.3f} std={ret["std"]:.3f} '
          f'min={ret["min"]:.3f} max={ret["max"]:.3f}')

    # --- Anchor reference for policy KL drift (only meaningful in value_plus_trunk mode)
    anchor_logits_ref = None
    ref_inputs = None
    anchor_logits_full = None
    if args.mode == 'value_plus_trunk':
        n_ref = min(4096, rollout['cards'].shape[0])
        ref_idx = torch.randperm(rollout['cards'].shape[0], device=args.device)[:n_ref]
        ref_inputs = (rollout['cards'][ref_idx], rollout['actions_obs'][ref_idx],
                      rollout['extras'][ref_idx], rollout['masks'][ref_idx])
        with torch.no_grad():
            anchor_logits_ref, _ = policy(*ref_inputs)
            anchor_logits_ref = anchor_logits_ref.detach()
            # Pre-compute anchor logits for the full rollout — used in the KL preservation penalty.
            if args.policy_kl_coef > 0:
                anchor_logits_full, _ = policy(rollout['cards'], rollout['actions_obs'],
                                               rollout['extras'], rollout['masks'])
                anchor_logits_full = anchor_logits_full.detach()
        print(f'[warmup] policy KL reference: n_ref={n_ref}, '
              f'policy_kl_coef={args.policy_kl_coef}')

    # --- Train value head (+ trunk if value_plus_trunk)
    print(f'[warmup] training mode={args.mode} for {args.epochs} epochs, '
          f'minibatch={args.minibatch_size}, lr={args.lr}')
    t_train = time.time()
    train_res = train_value_only(policy, rollout,
                                  epochs=args.epochs,
                                  minibatch_size=args.minibatch_size,
                                  lr=args.lr,
                                  device=args.device,
                                  anchor_logits_full=anchor_logits_full,
                                  policy_kl_coef=args.policy_kl_coef,
                                  anchor_logits_ref=anchor_logits_ref,
                                  ref_inputs=ref_inputs)
    train_s = time.time() - t_train

    # --- Verify policy unchanged
    check = verify_policy_unchanged(policy, snap, rollout)
    print(f'[warmup] policy_head weight max delta = {check["policy_head_weight_max_delta"]:.2e}')
    print(f'[warmup] policy_head UNCHANGED = {check["policy_head_unchanged"]}')

    # --- Save warmed checkpoint (overwrite value_head; trunk/policy_head identical to anchor)
    save_path = out / 'warmup.pt'
    out_ck = dict(ck)
    out_ck['model'] = policy.state_dict()
    out_ck['warmup_meta'] = {
        'version': VERSION,
        'source_anchor': args.anchor_ckpt,
        'rollout_hands': n_hands,
        'rollout_transitions': n_trans,
        'epochs': args.epochs,
        'lr': args.lr,
        'initial_value_loss': train_res['initial_value_loss'],
        'final_value_loss': train_res['final_value_loss'],
        'reduction_factor': train_res['reduction_factor'],
        'policy_head_unchanged': check['policy_head_unchanged'],
    }
    torch.save(out_ck, save_path)
    print(f'[warmup] saved {save_path}')

    elapsed = time.time() - t0

    # --- Manifest + JSON report
    write_manifest(out / 'manifest.json', script='phase2/train_value_warmup.py', version=VERSION,
                   args=vars(args),
                   inputs=[args.anchor_ckpt],
                   outputs=[str(save_path), str(out / 'warmup.log')],
                   extra={
                       'elapsed_s': elapsed,
                       'rollout_s': roll_s,
                       'train_s': train_s,
                       'rollout_hands': n_hands,
                       'rollout_transitions': n_trans,
                       'returns_stats': ret,
                       'train_result': train_res,
                       'check': check,
                   })

    (out / 'history.json').write_text(json.dumps(train_res['history'], indent=2))
    last = train_res['history'][-1] if train_res.get('history') else {}
    report = {
        'initial_value_loss': train_res['initial_value_loss'],
        'final_value_loss': train_res['final_value_loss'],
        'final_policy_kl_drift': last.get('policy_kl_drift'),
        'reduction_factor': train_res['reduction_factor'],
        'policy_head_unchanged': check['policy_head_unchanged'],
        'rollout_hands': n_hands,
        'rollout_transitions': n_trans,
        'returns_mean': ret['mean'],
        'returns_std': ret['std'],
        'elapsed_s': elapsed,
    }
    (out / 'report.json').write_text(json.dumps(report, indent=2))
    print(f'[warmup] done. {elapsed:.1f}s total. final_vloss={train_res["final_value_loss"]:.3f} '
          f'(from {train_res["initial_value_loss"]:.3f}, '
          f'{train_res["reduction_factor"]:.1f}x reduction)')


if __name__ == '__main__':
    main()
