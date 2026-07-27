"""Phase 2 BC anchor training skeleton.

Behavior cloning from teacher JSONL (output of generate_teacher_data.py).
Trains an AlphaHoldemNet GN policy to imitate the teacher's action choices.

Loss: legal-masked cross-entropy on teacher_action.
Optional: inverse-sqrt-frequency sample weights to avoid collapse to fold-only.

Validation metrics (Day -2 / smoke):
  - overall top-1 accuracy
  - per-position (SB / BB) top-1 accuracy
  - per-street top-1 accuracy
  - balanced accuracy (macro-avg per action slot)
  - per-slot action frequency drift vs teacher

Smoke target: 1000-example overfit run, ~50 steps. Verifies forward+backward,
loss decreases, model loads/saves. NOT a real training run.

Usage:
  python train_bc_anchor.py \
    --train data/phase2/teacher_v3_smoke.jsonl \
    --val data/phase2/teacher_v3_smoke.jsonl \
    --epochs 5 \
    --batch-size 64 \
    --lr 3e-4 \
    --smoke \
    --out models/bc/v3_anchor_smoke
"""
from __future__ import annotations
import argparse
import json
import os
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

VERSION = '0.1.0-skeleton'

CARD_SHAPE = (6, 4, 13)
ACTION_SHAPE = (25, 4, 5)
EXTRA_DIM = 2
NUM_ACTIONS = 9


def load_jsonl(path: Path, max_rows: int | None = None, seed: int = 42) -> list[dict]:
    """Load JSONL into a list of dicts. If max_rows given, take a reservoir random
    sample (single-pass O(N) memory O(max_rows)) so we don't blow up on huge files.
    """
    rows = []
    if max_rows is None:
        with open(path, encoding='utf-8') as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                rows.append(json.loads(ln))
        return rows

    # Reservoir sampling for huge files
    rng = np.random.default_rng(seed)
    reservoir: list[dict] = []
    with open(path, encoding='utf-8') as f:
        for i, ln in enumerate(f):
            ln = ln.strip()
            if not ln:
                continue
            if len(reservoir) < max_rows:
                reservoir.append(json.loads(ln))
            else:
                j = int(rng.integers(0, i + 1))
                if j < max_rows:
                    reservoir[j] = json.loads(ln)
    return reservoir


def split_by_hand(rows: list[dict], val_frac: float = 0.05, seed: int = 42) -> tuple[list[dict], list[dict]]:
    """Split rows into train/val by HAND_ID (not by individual decision).

    All decisions from a given hand go to the same split. Prevents leakage
    where the model sees one decision from a hand during training and a
    later decision from the same hand during validation.
    """
    hand_ids = sorted({r.get('hand_id', -1) for r in rows})
    if hand_ids == [-1]:
        # Old data without hand_id: fall back to row-level random split with warning
        print('[warn] no hand_id field in data; falling back to row-level random split')
        rng = np.random.default_rng(seed)
        idx = np.arange(len(rows))
        rng.shuffle(idx)
        cut = int(len(rows) * (1.0 - val_frac))
        return [rows[i] for i in idx[:cut]], [rows[i] for i in idx[cut:]]

    rng = np.random.default_rng(seed)
    rng.shuffle(hand_ids)
    cut = int(len(hand_ids) * (1.0 - val_frac))
    train_hands = set(hand_ids[:cut])
    val_hands = set(hand_ids[cut:])
    train_rows = [r for r in rows if r['hand_id'] in train_hands]
    val_rows = [r for r in rows if r['hand_id'] in val_hands]
    return train_rows, val_rows


def to_tensors(rows: list[dict], device: str):
    """Stack JSONL records into tensors for batched training."""
    n = len(rows)
    cards = np.empty((n, *CARD_SHAPE), dtype=np.float32)
    actions = np.empty((n, *ACTION_SHAPE), dtype=np.float32)
    extras = np.empty((n, EXTRA_DIM), dtype=np.float32)
    masks = np.empty((n, NUM_ACTIONS), dtype=np.float32)
    targets = np.empty((n,), dtype=np.int64)
    positions = np.empty((n,), dtype=np.int64)
    streets = np.empty((n,), dtype=np.int64)
    facing_bet = np.empty((n,), dtype=np.int64)
    for i, r in enumerate(rows):
        cards[i] = np.array(r['card_obs'], dtype=np.float32).reshape(CARD_SHAPE)
        actions[i] = np.array(r['action_obs'], dtype=np.float32).reshape(ACTION_SHAPE)
        extras[i] = np.array(r['extra_obs'], dtype=np.float32)
        masks[i] = np.array(r['legal_mask'], dtype=np.float32)
        targets[i] = int(r['teacher_action'])
        positions[i] = int(r['client_pos'])
        streets[i] = int(r['street'])
        facing_bet[i] = 1 if int(r.get('to_call', 0)) > 0 else 0
    return {
        'cards': torch.from_numpy(cards).to(device),
        'actions': torch.from_numpy(actions).to(device),
        'extras': torch.from_numpy(extras).to(device),
        'masks': torch.from_numpy(masks).to(device),
        'targets': torch.from_numpy(targets).to(device),
        'positions': torch.from_numpy(positions).to(device),
        'streets': torch.from_numpy(streets).to(device),
        'facing_bet': torch.from_numpy(facing_bet).to(device),
    }


def compute_per_sample_weights(batch: dict, action_weights: torch.Tensor,
                                fold_facing_bet_mult: float = 1.0,
                                bb_fold_facing_bet_mult: float = 1.0) -> torch.Tensor:
    """Per-sample loss weight = (inverse-sqrt class weight) × (slice multiplier).

    Slice multipliers (d1 targeted reweight):
      - if facing_bet=1 AND teacher_action=0 (fold facing bet): mult = fold_facing_bet_mult
      - if BB AND facing_bet=1 AND teacher_action=0: mult = bb_fold_facing_bet_mult (overrides)
      - else: mult = 1.0
    """
    base = action_weights[batch['targets']]
    is_facing_bet = batch['facing_bet'] == 1
    is_fold = batch['targets'] == 0
    is_bb = batch['positions'] == 0
    critical = is_facing_bet & is_fold
    bb_critical = critical & is_bb
    sb_critical = critical & ~is_bb
    mult = torch.ones_like(base)
    mult[sb_critical] = fold_facing_bet_mult
    mult[bb_critical] = bb_fold_facing_bet_mult
    return base * mult


def compute_action_weights(targets: torch.Tensor, num_actions: int = NUM_ACTIONS,
                           clip_min: float = 0.5, clip_max: float = 4.0) -> torch.Tensor:
    """Inverse-sqrt-frequency weighting per action class. Clipped [0.5, 4.0]."""
    counts = torch.bincount(targets, minlength=num_actions).float()
    counts = counts.clamp_min(1.0)
    freqs = counts / counts.sum()
    w = 1.0 / freqs.sqrt()
    w = w / w.mean()  # mean 1
    return w.clamp(clip_min, clip_max)


def evaluate(model, batch, action_weights: torch.Tensor | None = None) -> dict:
    """Return overall + per-position + per-street top-1 + balanced accuracy."""
    model.eval()
    with torch.no_grad():
        logits, _ = model(batch['cards'], batch['actions'], batch['extras'], batch['masks'])
        preds = logits.argmax(dim=-1)
        correct = (preds == batch['targets']).float()
        n = len(correct)

        # overall
        overall_acc = correct.mean().item()

        # per-position
        sb_mask = batch['positions'] == 1
        bb_mask = batch['positions'] == 0
        sb_acc = correct[sb_mask].mean().item() if sb_mask.any() else float('nan')
        bb_acc = correct[bb_mask].mean().item() if bb_mask.any() else float('nan')

        # per-street
        street_accs = {}
        for st in (0, 1, 2, 3):
            m = batch['streets'] == st
            street_accs[st] = correct[m].mean().item() if m.any() else float('nan')

        # balanced accuracy (macro-avg per-action recall)
        per_class_acc = []
        for a in range(NUM_ACTIONS):
            m = batch['targets'] == a
            if m.any():
                per_class_acc.append(correct[m].mean().item())
        balanced_acc = float(np.mean(per_class_acc)) if per_class_acc else float('nan')

        # action frequency drift (teacher vs model)
        teacher_freq = torch.bincount(batch['targets'], minlength=NUM_ACTIONS).float() / n
        model_freq = torch.bincount(preds, minlength=NUM_ACTIONS).float() / n
        action_l1 = (teacher_freq - model_freq).abs().sum().item() / 2.0  # total variation
    return {
        'overall_acc': overall_acc,
        'sb_acc': sb_acc,
        'bb_acc': bb_acc,
        'street_accs': street_accs,
        'balanced_acc': balanced_acc,
        'action_l1_tv': action_l1,
        'teacher_freq': teacher_freq.cpu().tolist(),
        'model_freq': model_freq.cpu().tolist(),
    }


def train(args):
    device = 'cuda' if (args.device == 'cuda' and torch.cuda.is_available()) else 'cpu'
    print(f'Device: {device}')

    print(f'Loading data: {args.train}')
    if args.max_rows:
        print(f'  (reservoir-sampling up to {args.max_rows:,} rows)')
    all_rows = load_jsonl(Path(args.train), max_rows=args.max_rows, seed=args.seed)
    print(f'  {len(all_rows)} total rows loaded')

    if args.auto_split:
        train_rows, val_rows = split_by_hand(all_rows, val_frac=args.val_frac, seed=args.seed)
        print(f'  auto-split by hand_id: {len(train_rows)} train / {len(val_rows)} val')
        unique_train_hands = len({r.get('hand_id', -1) for r in train_rows})
        unique_val_hands = len({r.get('hand_id', -1) for r in val_rows})
        print(f'  unique hands: {unique_train_hands} train / {unique_val_hands} val')
    elif args.val is not None and args.val != args.train:
        train_rows = all_rows
        val_rows = load_jsonl(Path(args.val))
        print(f'  loaded val from {args.val}: {len(val_rows)} rows')
    else:
        train_rows = all_rows
        val_rows = all_rows
        print('  [warn] val == train (smoke mode)')

    train_batch = to_tensors(train_rows, device)
    val_batch = to_tensors(val_rows, device)

    # Inverse-sqrt action weights (baseline)
    action_weights = compute_action_weights(train_batch['targets']).to(device)
    print(f'Action weights (per-class baseline): {action_weights.cpu().tolist()}')

    # Per-sample weights: baseline × slice multiplier
    # d1: fold_facing_bet_mult (SB), bb_fold_facing_bet_mult (BB)
    per_sample_weights = compute_per_sample_weights(
        train_batch, action_weights,
        fold_facing_bet_mult=args.fold_facing_bet_mult,
        bb_fold_facing_bet_mult=args.bb_fold_facing_bet_mult,
    )
    n_critical_sb = int(((train_batch['facing_bet'] == 1) & (train_batch['targets'] == 0)
                         & (train_batch['positions'] == 1)).sum().item())
    n_critical_bb = int(((train_batch['facing_bet'] == 1) & (train_batch['targets'] == 0)
                         & (train_batch['positions'] == 0)).sum().item())
    n_train = len(train_batch['targets'])
    print(f'Critical-slice examples: SB-fold-facing-bet={n_critical_sb} ({100*n_critical_sb/n_train:.2f}%)  '
          f'BB-fold-facing-bet={n_critical_bb} ({100*n_critical_bb/n_train:.2f}%)')
    print(f'Slice multipliers: SB={args.fold_facing_bet_mult}x  BB={args.bb_fold_facing_bet_mult}x')
    print(f'Per-sample weight stats: mean={per_sample_weights.mean().item():.3f}  '
          f'max={per_sample_weights.max().item():.3f}')

    # Build model — GN AlphaHoldemNet
    torch.manual_seed(args.seed)
    model = AlphaHoldemNet(num_actions=NUM_ACTIONS, norm_layer='gn').to(device)
    model.eval()
    # Lazy trunk init via dummy forward
    model(torch.zeros(2, *CARD_SHAPE, device=device),
          torch.zeros(2, *ACTION_SHAPE, device=device),
          torch.zeros(2, EXTRA_DIM, device=device))
    print(f'Params: {count_parameters(model):,}')

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    n = len(train_rows)
    step = 0
    history = []
    t0 = time.time()

    for ep in range(args.epochs):
        model.train()
        idx = torch.randperm(n, device=device)
        ep_loss = 0.0
        ep_steps = 0
        for s in range(0, n, args.batch_size):
            mb = idx[s:s + args.batch_size]
            logits, _ = model(train_batch['cards'][mb], train_batch['actions'][mb],
                              train_batch['extras'][mb], train_batch['masks'][mb])
            # Legal-masking is already inside the model forward.
            tgt = train_batch['targets'][mb]
            sample_w = per_sample_weights[mb]
            ce = F.cross_entropy(logits, tgt, reduction='none')
            loss = (ce * sample_w).mean()
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            ep_loss += loss.item()
            ep_steps += 1
            step += 1

        eval_metrics = evaluate(model, val_batch)
        train_loss = ep_loss / max(ep_steps, 1)
        history.append({'epoch': ep, 'step': step, 'train_loss': train_loss, **eval_metrics})
        print(f'[ep {ep}] loss={train_loss:.4f}  '
              f'overall={eval_metrics["overall_acc"]:.3f}  '
              f'sb={eval_metrics["sb_acc"]:.3f}  bb={eval_metrics["bb_acc"]:.3f}  '
              f'bal={eval_metrics["balanced_acc"]:.3f}  '
              f'act_L1={eval_metrics["action_l1_tv"]:.3f}')

    elapsed = time.time() - t0

    # Save
    out_dir = REPO_ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = out_dir / 'best.pt'
    torch.save({
        'model': model.state_dict(),
        'optimizer': opt.state_dict(),
        'env_version': 'v4',
        'obs_version': 'v4',
        'action_space_version': '9slot_v4',
        'starting_stack_bb': 200.0,
        'trainer': 'bc_anchor',
        'norm_layer': 'gn',
        'freeze_bn_stats': False,
        'teacher_jsonl': args.train,
        'epochs': args.epochs,
        'lr': args.lr,
    }, ckpt_path)

    # Training history
    (out_dir / 'history.json').write_text(json.dumps(history, indent=2), encoding='utf-8')

    write_manifest(out_dir / 'manifest.json',
                   script='phase2/train_bc_anchor.py', version=VERSION,
                   args=vars(args), seed=args.seed,
                   inputs=[args.train, args.val],
                   outputs=[ckpt_path, out_dir / 'history.json'],
                   extra={'elapsed_s': elapsed, 'final_metrics': history[-1]})

    md = []
    md.append(f'Train file: `{args.train}`  ({len(train_rows)} examples)')
    md.append(f'Val file:   `{args.val}`  ({len(val_rows)} examples)')
    md.append(f'Epochs:     {args.epochs}')
    md.append(f'Batch:      {args.batch_size}')
    md.append(f'LR:         {args.lr}')
    md.append(f'Norm:       gn')
    md.append(f'Params:     {count_parameters(model):,}')
    md.append(f'Elapsed:    {elapsed:.1f}s')
    md.append('')
    final = history[-1]
    md.append(f'Final overall acc: {final["overall_acc"]:.3f}')
    md.append(f'Final balanced acc: {final["balanced_acc"]:.3f}  (target >= 0.75)')
    md.append(f'Final SB / BB: {final["sb_acc"]:.3f} / {final["bb_acc"]:.3f}')
    md.append(f'Per-slot teacher vs model freq (TV/2): {final["action_l1_tv"]:.3f}  (target < 0.05)')
    md.append('')

    # Collapse / pathology checks
    md.append('### Collapse / pathology checks')
    teacher_freq = final['teacher_freq']
    model_freq = final['model_freq']
    md.append('')
    md.append('| slot | teacher % | model % | drift (pp) |')
    md.append('| --- | ---: | ---: | ---: |')
    for s in range(NUM_ACTIONS):
        t = teacher_freq[s] * 100
        m = model_freq[s] * 100
        md.append(f'| {s} | {t:.2f} | {m:.2f} | {m-t:+.2f} |')
    md.append('')

    fold_only = model_freq[0] > 0.95
    jam_only = model_freq[8] > 0.50
    no_call = model_freq[1] < 0.02 and teacher_freq[1] > 0.05
    no_raise = sum(model_freq[2:8]) < 0.005 and sum(teacher_freq[2:8]) > 0.02
    max_drift_pp = max(abs(model_freq[s] - teacher_freq[s]) for s in range(NUM_ACTIONS)) * 100
    gate_pass = {
        'no_fold_only_collapse (model fold % <= 95)': not fold_only,
        'no_jam_only_collapse (model allin % <= 50)': not jam_only,
        'has_call_check (if teacher does)': not no_call,
        'has_raises (if teacher does)': not no_raise,
        f'max_per_slot_drift_pp ({max_drift_pp:.1f}) <= 5': max_drift_pp <= 5.0,
        f'balanced_acc ({final["balanced_acc"]:.3f}) >= 0.75': final['balanced_acc'] >= 0.75,
    }
    md.append('### Day 1 gate checklist')
    md.append('')
    md.append('| check | status |')
    md.append('| --- | --- |')
    for k, ok in gate_pass.items():
        md.append(f'| {k} | {"PASS" if ok else "FAIL"} |')
    md.append('')
    md.append(f'**Overall gate**: {"PASS" if all(gate_pass.values()) else "FAIL"} (Slumbot bench is the final gate)')

    write_md_report(out_dir / 'report.md',
                    title=f'BC anchor training ({"smoke" if args.smoke else "real"})',
                    sections=[('Configuration & final metrics', '\n'.join(md))])

    print(f'\n[OK] BC anchor saved -> {ckpt_path}')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--train', required=True, help='Path to teacher JSONL (used for both train and val if --auto-split)')
    p.add_argument('--val', default=None, help='Optional explicit val JSONL; if omitted use --auto-split')
    p.add_argument('--auto-split', action='store_true', help='Split --train by hand_id into train/val')
    p.add_argument('--val-frac', type=float, default=0.05, help='Fraction of HANDS (not rows) held out for val')
    p.add_argument('--epochs', type=int, default=5)
    p.add_argument('--batch-size', type=int, default=64)
    p.add_argument('--lr', type=float, default=3e-4)
    p.add_argument('--weight-decay', type=float, default=1e-4)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    p.add_argument('--smoke', action='store_true', help='Skeleton-validation mode')
    p.add_argument('--out', required=True)
    p.add_argument('--max-rows', type=int, default=None,
                   help='Reservoir-sample up to this many rows from --train (avoids loading huge JSONL fully). '
                        'Recommend 1-2M for 5M+ files to fit in memory.')
    p.add_argument('--fold-facing-bet-mult', type=float, default=1.0,
                   help='Loss multiplier for (teacher=fold AND facing_bet=1) examples in SB position. '
                        'd1 default: 8.0. Use 1.0 to disable.')
    p.add_argument('--bb-fold-facing-bet-mult', type=float, default=1.0,
                   help='Loss multiplier for (teacher=fold AND facing_bet=1 AND position=BB) examples. '
                        'd1 default: 10.0. Overrides --fold-facing-bet-mult for BB. Use 1.0 to disable.')
    args = p.parse_args()
    train(args)


if __name__ == '__main__':
    main()
