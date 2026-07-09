#!/usr/bin/env python3
"""Train a Slumbot mimic via behavior cloning on dumped (state, action) pairs.

Reads JSONL produced by play_slumbot.py --dump-slumbot. Each line carries
Slumbot's hole cards (revealed at hand end), the full public state at his
decision, and his chosen action. We treat Slumbot as the "hero" in the encoding
and train an AlphaHoldemNet to predict his 9-slot discrete action via cross
entropy. The trained checkpoint is drop-in compatible with hero-vs-opponent
training because it shares architecture and observation pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/ for alpha_holdem.* imports
sys.path.insert(0, str(Path(__file__).resolve().parent))      # scripts/alpha_holdem/ for play_slumbot

from alpha_holdem.network import AlphaHoldemNet, count_parameters
from alpha_holdem.environment_v55 import NUM_ACTIONS

# Reuse play_slumbot's encoding (battle-tested, matches v4 trainer)
from play_slumbot import (  # type: ignore
    BIG_BLIND,
    STACK_SIZE,
    build_action_table,
    closest_raise_slot,
    compute_commitments,
    encode_action_history,
    encode_cards,
    encode_extra,
    parse_action,
)


@dataclass
class Sample:
    card_t: np.ndarray   # (6, 4, 13)
    action_t: np.ndarray # (25, 4, 5)
    extra_t: np.ndarray  # (2,)
    mask_t: np.ndarray   # (9,)
    label: int           # 0..8


def slumbot_move_to_slot(move: str, amount: int, state: dict, mask: np.ndarray) -> int | None:
    """Map ('b', amt) / 'k' / 'c' / 'f' to the closest legal action slot 0-8.
    Returns None if the chosen action is illegal in the encoded table."""
    if move == 'f':
        return 0 if mask[0] > 0 else None
    if move in ('k', 'c'):
        return 1 if mask[1] > 0 else None
    if move == 'b':
        c = compute_commitments(state)
        pot = max(c['pot'], 1)
        # All-in detection: bet amount maxed against remaining street stack
        max_target = STACK_SIZE - (c['hero_total'] - c['hero_street'])
        if amount >= max_target - 1 and mask[8] > 0:
            return 8
        pot_frac = amount / pot
        slot = closest_raise_slot(pot_frac)
        if mask[slot] > 0:
            return slot
        # Fall back to any legal raise slot closest to chosen size
        candidates = [s for s in range(2, 9) if mask[s] > 0]
        if not candidates:
            return None
        return min(candidates, key=lambda s: abs(s - slot))
    return None


class SlumbotDataset(Dataset):
    def __init__(self, samples: list[Sample]):
        self.samples = samples

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        s = self.samples[idx]
        return {
            'card': torch.from_numpy(s.card_t),
            'action': torch.from_numpy(s.action_t),
            'extra': torch.from_numpy(s.extra_t),
            'mask': torch.from_numpy(s.mask_t),
            'label': torch.tensor(s.label, dtype=torch.long),
        }


def build_sample(row: dict, obs_version: str = 'v55') -> Sample | None:
    opp_hole = row.get('opp_hole')
    if not opp_hole:
        return None  # mimic needs Slumbot's hole cards
    action_str_before = row.get('action_str_before', '')
    state = parse_action(action_str_before)
    if 'error' in state:
        return None
    board = row.get('board', [])
    opp_pos = row.get('opp_pos', 0)

    # Slumbot is "hero" in the mimic's encoding
    card_t = encode_cards(opp_hole, board, state['st'])
    action_t = encode_action_history(state, opp_pos, state['pos'], obs_version=obs_version)
    c = compute_commitments(state)
    stacks = [STACK_SIZE - c['hero_total'], STACK_SIZE - c['opp_total']]
    extra_t = encode_extra(stacks)
    mask, _ = build_action_table(state)
    if mask.sum() == 0:
        return None

    label = slumbot_move_to_slot(
        row.get('action_move', ''),
        int(row.get('action_amount', 0)),
        state,
        mask,
    )
    if label is None:
        return None
    return Sample(card_t=card_t.astype(np.float32),
                  action_t=action_t.astype(np.float32),
                  extra_t=extra_t.astype(np.float32),
                  mask_t=mask.astype(np.float32),
                  label=int(label))


def load_jsonl_samples(paths: list[Path], obs_version: str, limit: int | None = None) -> list[Sample]:
    samples: list[Sample] = []
    seen = 0
    kept = 0
    for path in paths:
        with path.open('r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if not line.strip():
                    continue
                seen += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                s = build_sample(row, obs_version=obs_version)
                if s is not None:
                    samples.append(s)
                    kept += 1
                if limit and kept >= limit:
                    return samples
    print(f'Loaded {kept:,}/{seen:,} valid samples from {len(paths)} JSONL files', flush=True)
    return samples


def evaluate(model, loader, device) -> tuple[float, float]:
    model.eval()
    total_loss = 0.0
    total_correct = 0
    total = 0
    with torch.no_grad():
        for batch in loader:
            card = batch['card'].to(device)
            action = batch['action'].to(device)
            extra = batch['extra'].to(device)
            mask = batch['mask'].to(device)
            label = batch['label'].to(device)
            logits, _ = model(card, action, extra, mask)
            loss = F.cross_entropy(logits, label, reduction='sum')
            total_loss += float(loss.item())
            preds = logits.argmax(dim=-1)
            total_correct += int((preds == label).sum().item())
            total += label.size(0)
    model.train()
    return total_loss / max(total, 1), total_correct / max(total, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', default='models/v55_lab/slumbot_data',
                        help='Directory of JSONL files dumped by play_slumbot.py --dump-slumbot.')
    parser.add_argument('--out', default='models/v55_lab/slumbot_mimic.pt')
    parser.add_argument('--epochs', type=int, default=20)
    parser.add_argument('--batch-size', type=int, default=512)
    parser.add_argument('--lr', type=float, default=3e-4)
    parser.add_argument('--val-fraction', type=float, default=0.05)
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--obs-version', choices=('v4', 'v55'), default='v55')
    parser.add_argument('--limit', type=int, default=None)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    paths = sorted(data_dir.glob('*.jsonl'))
    if not paths:
        print(f'No JSONL files found in {data_dir}.', flush=True)
        return 1

    print(f'Reading from {len(paths)} JSONL files in {data_dir}', flush=True)
    samples = load_jsonl_samples(paths, args.obs_version, limit=args.limit)
    if not samples:
        print('No valid samples extracted.', flush=True)
        return 1

    rng = np.random.default_rng(0)
    rng.shuffle(samples)
    n_val = max(1, int(len(samples) * args.val_fraction))
    val = samples[:n_val]
    train = samples[n_val:]
    print(f'Train: {len(train):,}  Val: {len(val):,}', flush=True)

    train_loader = DataLoader(SlumbotDataset(train), batch_size=args.batch_size,
                              shuffle=True, num_workers=0, drop_last=True)
    val_loader = DataLoader(SlumbotDataset(val), batch_size=args.batch_size,
                            shuffle=False, num_workers=0)

    device = args.device
    model = AlphaHoldemNet(num_actions=NUM_ACTIONS).to(device)
    # Warmup forward to allocate buffers
    model(torch.zeros(1, 6, 4, 13, device=device),
          torch.zeros(1, 25, 4, 5, device=device),
          torch.zeros(1, 2, device=device))
    print(f'Model params: {count_parameters(model):,}', flush=True)

    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.StepLR(opt, step_size=10, gamma=0.5)

    best_val_loss = float('inf')
    best_state = None
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    for epoch in range(1, args.epochs + 1):
        model.train()
        running = 0.0
        seen = 0
        correct = 0
        for batch in train_loader:
            card = batch['card'].to(device)
            action = batch['action'].to(device)
            extra = batch['extra'].to(device)
            mask = batch['mask'].to(device)
            label = batch['label'].to(device)
            logits, _ = model(card, action, extra, mask)
            loss = F.cross_entropy(logits, label)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            running += float(loss.item()) * label.size(0)
            seen += label.size(0)
            correct += int((logits.argmax(dim=-1) == label).sum().item())
        sched.step()

        train_loss = running / max(seen, 1)
        train_acc = correct / max(seen, 1)
        val_loss, val_acc = evaluate(model, val_loader, device)
        elapsed = (time.time() - t0) / 60.0
        print(f'[ep {epoch:3d}] train_loss={train_loss:.4f} acc={train_acc:.3f}  '
              f'val_loss={val_loss:.4f} acc={val_acc:.3f}  elapsed={elapsed:.1f}min', flush=True)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        ckpt = {
            'model': best_state,
            'version': 'slumbot_mimic_v1',
            'obs_version': args.obs_version,
            'num_actions': NUM_ACTIONS,
            'val_loss': best_val_loss,
            'train_samples': len(train),
            'val_samples': len(val),
        }
        torch.save(ckpt, out_path)
        print(f'Saved {out_path} (val_loss={best_val_loss:.4f})', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
