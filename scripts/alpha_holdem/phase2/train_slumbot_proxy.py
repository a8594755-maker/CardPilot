"""Phase 2 Slumbot proxy training skeleton.

Behavior-clones Slumbot's action distribution from the public-state proxy dataset.

CRITICAL: input is PUBLIC STATE ONLY. Hero hole cards are NEVER input to this
model. Slumbot cannot see them and including them would leak.

Architecture (small NN, factored heads):
  Input: scalar features (street, mover_pos, pot_before, to_call, stack,
         last_bet_size, public board card count, action history hash)
  ~256-dim MLP backbone, 4 layers, GELU
  Heads:
    family_head: 3-way {fold, check/call, raise}
    raise_size_head: 4-way {small, medium, large, jam}
    (raise size only loss-active when family == raise)

Loss: CE on family_head + CE on raise_size_head (when applicable)

Targets derived from slumbot_action_slot:
  slot 0       -> family=fold,     size=N/A
  slot 1       -> family=call,     size=N/A
  slot 2-3     -> family=raise,    size=small
  slot 4-5     -> family=raise,    size=medium
  slot 6-7     -> family=raise,    size=large
  slot 8       -> family=raise,    size=jam

Validation metrics:
  - held-out NLL (target < 0.7)
  - top-1 family accuracy
  - top-1 slot accuracy (combined family + size)
  - per-street action L1 (target preflop < 0.03, postflop < 0.05)
  - ECE (target < 0.05)

Smoke: 1 epoch on the current train split, dump metrics.

Usage:
  python train_slumbot_proxy.py \
    --train data/phase2/slumbot_proxy_v1/train.jsonl \
    --val data/phase2/slumbot_proxy_v1/val.jsonl \
    --test-oop data/phase2/slumbot_proxy_v1/test_oop.jsonl \
    --epochs 5 \
    --batch-size 256 \
    --lr 1e-3 \
    --smoke \
    --out models/proxy/slumbot_public_smoke
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
sys.path.insert(0, str(THIS_DIR / 'common'))
from manifest import write_manifest, write_md_report

VERSION = '0.1.0-skeleton'


def slot_to_family_size(slot: int) -> tuple[int, int]:
    """Map slot 0..8 -> (family 0..2, size 0..3 or -1 for n/a)."""
    if slot == 0:
        return 0, -1   # fold
    if slot == 1:
        return 1, -1   # call/check
    if slot in (2, 3):
        return 2, 0    # raise small
    if slot in (4, 5):
        return 2, 1    # raise medium
    if slot in (6, 7):
        return 2, 2    # raise large
    if slot == 8:
        return 2, 3    # jam
    return 1, -1


def encode_features(r: dict) -> np.ndarray:
    """Hand-crafted scalar feature vector from public state. Skeleton — Day 1 may
    upgrade to learned encoder. PUBLIC STATE ONLY — no hero hole."""
    street = r['street']
    mover_pos = r['mover_pos']
    pot_before = r['pot_before']
    to_call = r['to_call']
    stack = r['stack_remaining']
    last_bet = r['last_bet_size']
    street_last_bet_to = r['street_last_bet_to']
    total_last_bet_to = r['total_last_bet_to']
    board = r.get('public_board', []) or []
    n_board = len(board)
    action_str = r.get('action_str_before', '')
    # Coarse history features
    n_bets = action_str.count('b')
    n_calls = action_str.count('c')
    n_checks = action_str.count('k')

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
    return feats


FEAT_DIM = 16


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding='utf-8') as f:
        for ln in f:
            if not ln.strip():
                continue
            rows.append(json.loads(ln))
    return rows


def to_tensors(rows: list[dict], device: str):
    n = len(rows)
    X = np.empty((n, FEAT_DIM), dtype=np.float32)
    fam = np.empty((n,), dtype=np.int64)
    sz = np.empty((n,), dtype=np.int64)
    streets = np.empty((n,), dtype=np.int64)
    slots = np.empty((n,), dtype=np.int64)
    for i, r in enumerate(rows):
        X[i] = encode_features(r)
        f, s = slot_to_family_size(int(r['slumbot_action_slot']))
        fam[i] = f
        sz[i] = s if s >= 0 else 0  # placeholder; ignored when fam != raise
        streets[i] = r['street']
        slots[i] = r['slumbot_action_slot']
    return {
        'X': torch.from_numpy(X).to(device),
        'family': torch.from_numpy(fam).to(device),
        'size': torch.from_numpy(sz).to(device),
        'streets': torch.from_numpy(streets).to(device),
        'slots': torch.from_numpy(slots).to(device),
    }


class ProxyMLP(nn.Module):
    def __init__(self, feat_dim: int = FEAT_DIM, hidden: int = 256, layers: int = 4):
        super().__init__()
        modules = [nn.Linear(feat_dim, hidden), nn.GELU()]
        for _ in range(layers - 1):
            modules += [nn.Linear(hidden, hidden), nn.GELU()]
        self.backbone = nn.Sequential(*modules)
        self.family_head = nn.Linear(hidden, 3)
        self.size_head = nn.Linear(hidden, 4)

    def forward(self, x):
        h = self.backbone(x)
        return self.family_head(h), self.size_head(h)


def evaluate(model, batch) -> dict:
    model.eval()
    with torch.no_grad():
        fam_logits, sz_logits = model(batch['X'])
        fam_pred = fam_logits.argmax(-1)
        sz_pred = sz_logits.argmax(-1)
        fam_acc = (fam_pred == batch['family']).float().mean().item()

        # Combined slot prediction
        n = len(batch['family'])
        combined_slot = torch.full((n,), -1, dtype=torch.long, device=fam_pred.device)
        combined_slot[fam_pred == 0] = 0  # fold
        combined_slot[fam_pred == 1] = 1  # call
        # For predicted raise, derive slot from size
        is_raise = fam_pred == 2
        if is_raise.any():
            sz_to_slot = torch.tensor([3, 5, 7, 8], device=fam_pred.device)  # small/med/large/jam -> slot
            combined_slot[is_raise] = sz_to_slot[sz_pred[is_raise]]
        slot_acc = (combined_slot == batch['slots']).float().mean().item()

        # NLL on family head (held-out)
        fam_nll = F.cross_entropy(fam_logits, batch['family']).item()

        # Per-street action L1 (between predicted vs true SLOT distribution)
        l1_by_street = {}
        for st in (0, 1, 2, 3):
            m = batch['streets'] == st
            if not m.any():
                continue
            true_freq = torch.bincount(batch['slots'][m], minlength=9).float() / m.float().sum()
            pred_freq = torch.bincount(combined_slot[m], minlength=9).float() / m.float().sum()
            l1_by_street[st] = float((true_freq - pred_freq).abs().sum().item() / 2.0)

    return {
        'fam_acc': fam_acc,
        'slot_acc': slot_acc,
        'fam_nll': fam_nll,
        'l1_by_street': l1_by_street,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--train', required=True)
    p.add_argument('--val', required=True)
    p.add_argument('--test-oop', default=None)
    p.add_argument('--epochs', type=int, default=5)
    p.add_argument('--batch-size', type=int, default=256)
    p.add_argument('--lr', type=float, default=1e-3)
    p.add_argument('--hidden', type=int, default=256)
    p.add_argument('--layers', type=int, default=4)
    p.add_argument('--device', default='cuda')
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--smoke', action='store_true')
    p.add_argument('--out', required=True)
    args = p.parse_args()

    device = 'cuda' if (args.device == 'cuda' and torch.cuda.is_available()) else 'cpu'
    print(f'Device: {device}')

    train_rows = load_jsonl(Path(args.train))
    val_rows = load_jsonl(Path(args.val))
    test_rows = load_jsonl(Path(args.test_oop)) if args.test_oop else []
    print(f'train={len(train_rows)}, val={len(val_rows)}, test_oop={len(test_rows)}')

    train_b = to_tensors(train_rows, device)
    val_b = to_tensors(val_rows, device)
    test_b = to_tensors(test_rows, device) if test_rows else None

    torch.manual_seed(args.seed)
    model = ProxyMLP(FEAT_DIM, args.hidden, args.layers).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f'Params: {n_params:,}')

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)

    n = len(train_rows)
    history = []
    t0 = time.time()

    for ep in range(args.epochs):
        model.train()
        idx = torch.randperm(n, device=device)
        ep_loss = 0.0
        ep_steps = 0
        for s in range(0, n, args.batch_size):
            mb = idx[s:s + args.batch_size]
            fam_logits, sz_logits = model(train_b['X'][mb])
            fam_loss = F.cross_entropy(fam_logits, train_b['family'][mb])
            # Size loss only for raise targets
            is_raise = train_b['family'][mb] == 2
            if is_raise.any():
                sz_loss = F.cross_entropy(sz_logits[is_raise], train_b['size'][mb][is_raise])
            else:
                sz_loss = torch.zeros((), device=device)
            loss = fam_loss + 0.5 * sz_loss
            opt.zero_grad()
            loss.backward()
            opt.step()
            ep_loss += loss.item()
            ep_steps += 1
        val_metrics = evaluate(model, val_b)
        test_metrics = evaluate(model, test_b) if test_b is not None else None
        rec = {
            'epoch': ep,
            'train_loss': ep_loss / max(ep_steps, 1),
            'val': val_metrics,
        }
        if test_metrics:
            rec['test_oop'] = test_metrics
        history.append(rec)
        oop_str = f' | test_oop fam={test_metrics["fam_acc"]:.3f} nll={test_metrics["fam_nll"]:.3f}' if test_metrics else ''
        print(f'[ep {ep}] loss={rec["train_loss"]:.4f} | val fam={val_metrics["fam_acc"]:.3f} '
              f'slot={val_metrics["slot_acc"]:.3f} nll={val_metrics["fam_nll"]:.3f}'
              f'{oop_str}')

    elapsed = time.time() - t0

    out_dir = REPO_ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = out_dir / 'best.pt'
    torch.save({'model': model.state_dict(), 'feat_dim': FEAT_DIM,
                'hidden': args.hidden, 'layers': args.layers,
                'version': VERSION}, ckpt_path)
    (out_dir / 'history.json').write_text(json.dumps(history, indent=2), encoding='utf-8')

    write_manifest(out_dir / 'manifest.json',
                   script='phase2/train_slumbot_proxy.py', version=VERSION,
                   args=vars(args), seed=args.seed,
                   inputs=[args.train, args.val] + ([args.test_oop] if args.test_oop else []),
                   outputs=[ckpt_path, out_dir / 'history.json'],
                   extra={'elapsed_s': elapsed, 'final': history[-1] if history else None,
                          'n_params': n_params})

    final = history[-1]
    md = [
        f'**Train**: {len(train_rows):,} records',
        f'**Val**: {len(val_rows):,} records',
        f'**Test OOP**: {len(test_rows):,} records' if test_rows else '**Test OOP**: none',
        f'**Params**: {n_params:,}',
        f'**Epochs**: {args.epochs}',
        f'**Elapsed**: {elapsed:.1f}s',
        '',
        f'**Final val family accuracy**: {final["val"]["fam_acc"]:.3f}',
        f'**Final val slot accuracy**: {final["val"]["slot_acc"]:.3f}',
        f'**Final val NLL**: {final["val"]["fam_nll"]:.3f} (target < 0.7)',
        f'**Per-street L1 (val)**: {final["val"]["l1_by_street"]}',
    ]
    if test_rows:
        md.append('')
        md.append(f'**Final test-OOP family accuracy**: {final["test_oop"]["fam_acc"]:.3f}')
        md.append(f'**Final test-OOP NLL**: {final["test_oop"]["fam_nll"]:.3f}')
    write_md_report(out_dir / 'report.md',
                    title=f'Slumbot proxy training ({"smoke" if args.smoke else "real"})',
                    sections=[('Summary', '\n\n'.join(md))])

    print(f'\n[OK] proxy -> {ckpt_path}')


if __name__ == '__main__':
    main()
