"""Slumbot proxy v2 — P2-lite upgrade.

Upgrades over v1 (`train_slumbot_proxy.py`):
  - Board encoder: each public board card → (rank_embed + suit_embed); concat 5 slots
  - Richer scalar features: SPR (stack/pot), per-street move counts, etc.
  - Larger backbone: 2M-5M params (vs v1's 200k)
  - Factored heads (same as v1): family (3) + size (4)
  - ECE (expected calibration error) on family head
  - Per-raise-bucket size confusion matrix

CRITICAL CONTRACT (unchanged from v1): proxy sees PUBLIC STATE ONLY.
Hero hole cards are NEVER input. The dump records carry `hero_hole` for
analysis but this script does NOT read that field.

Usage:
  python train_slumbot_proxy_v2.py \
    --train data/phase2/slumbot_proxy_v2/train.jsonl \
    --val data/phase2/slumbot_proxy_v2/val.jsonl \
    --test-oop data/phase2/slumbot_proxy_v2/test_oop.jsonl \
    --epochs 30 --batch-size 1024 --lr 1e-3 \
    --out models/proxy/slumbot_public_v2
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

VERSION = '0.2.0'

NUM_RANKS = 13
NUM_SUITS = 4
RANK_EMB = 8
SUIT_EMB = 4
BOARD_SLOTS = 5  # flop(3) + turn + river
PER_CARD_EMB = RANK_EMB + SUIT_EMB

SCALAR_DIM = 20  # see encode_scalar_features

_RANK_IDX = {r: i for i, r in enumerate('23456789TJQKA')}
_SUIT_IDX = {s: i for i, s in enumerate('shdc')}


def slot_to_family_size(slot: int) -> tuple[int, int]:
    if slot == 0:
        return 0, -1
    if slot == 1:
        return 1, -1
    if slot in (2, 3):
        return 2, 0
    if slot in (4, 5):
        return 2, 1
    if slot in (6, 7):
        return 2, 2
    if slot == 8:
        return 2, 3
    return 1, -1


def encode_scalar_features(r: dict) -> np.ndarray:
    """Scalar features — extended from v1 (16 → 20 dims). Public state only."""
    street = r['street']
    mover_pos = r['mover_pos']
    pot = max(r['pot_before'], 0)
    to_call = max(r['to_call'], 0)
    stack = max(r['stack_remaining'], 0)
    last_bet = max(r['last_bet_size'], 0)
    street_last_bet_to = max(r['street_last_bet_to'], 0)
    total_last_bet_to = max(r['total_last_bet_to'], 0)
    board = r.get('public_board', []) or []
    n_board = len(board)
    action_str = r.get('action_str_before', '')
    n_bets = action_str.count('b')
    n_calls = action_str.count('c')
    n_checks = action_str.count('k')
    # SPR = stack-to-pot ratio (key for sizing decisions)
    spr = stack / max(pot, 1)
    spr_norm = min(spr / 50.0, 2.0)  # clamp + normalize

    feats = np.array([
        street,                                # 0
        mover_pos,                             # 1
        pot / 1000.0,                          # 2
        to_call / 1000.0,                      # 3
        stack / 20000.0,                       # 4
        last_bet / 1000.0,                     # 5
        street_last_bet_to / 1000.0,           # 6
        total_last_bet_to / 1000.0,            # 7
        n_board,                               # 8
        n_bets, n_calls, n_checks,             # 9-11
        1.0 if to_call > 0 else 0.0,           # 12
        np.log1p(pot) / 8.0,                   # 13
        np.log1p(to_call) / 8.0,               # 14
        np.log1p(stack) / 10.0,                # 15
        spr_norm,                              # 16
        np.log1p(spr) / 4.0,                   # 17
        n_bets + n_calls + n_checks,           # 18 (total actions on this hand)
        (to_call / max(pot, 1)),               # 19 (call-to-pot ratio, capped implicitly by data)
    ], dtype=np.float32)
    assert feats.shape[0] == SCALAR_DIM
    return feats


def encode_board(board: list) -> np.ndarray:
    """Return BOARD_SLOTS × 2 integer matrix (rank_idx, suit_idx) per card.
    Unrevealed slots → (-1, -1) and will be masked to zero embedding later.
    """
    out = np.full((BOARD_SLOTS, 2), -1, dtype=np.int64)
    for i, c in enumerate((board or [])[:BOARD_SLOTS]):
        if c and len(c) == 2:
            r, s = c[0], c[1]
            if r in _RANK_IDX and s in _SUIT_IDX:
                out[i, 0] = _RANK_IDX[r]
                out[i, 1] = _SUIT_IDX[s]
    return out


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
    scalars = np.empty((n, SCALAR_DIM), dtype=np.float32)
    boards = np.empty((n, BOARD_SLOTS, 2), dtype=np.int64)
    fam = np.empty((n,), dtype=np.int64)
    sz = np.empty((n,), dtype=np.int64)
    streets = np.empty((n,), dtype=np.int64)
    slots = np.empty((n,), dtype=np.int64)
    for i, r in enumerate(rows):
        scalars[i] = encode_scalar_features(r)
        boards[i] = encode_board(r.get('public_board', []) or [])
        slot = int(r['slumbot_action_slot'])
        f, s = slot_to_family_size(slot)
        fam[i] = f
        sz[i] = s if s >= 0 else 0
        streets[i] = r['street']
        slots[i] = slot
    return {
        'scalars': torch.from_numpy(scalars).to(device),
        'boards': torch.from_numpy(boards).to(device),
        'family': torch.from_numpy(fam).to(device),
        'size': torch.from_numpy(sz).to(device),
        'streets': torch.from_numpy(streets).to(device),
        'slots': torch.from_numpy(slots).to(device),
    }


class ProxyV2(nn.Module):
    """Board-aware proxy. Cards → embed → flatten → concat with scalars → MLP."""
    def __init__(self, scalar_dim: int = SCALAR_DIM, hidden: int = 768, layers: int = 4):
        super().__init__()
        # Embeddings: extra index 0 is reserved for "unrevealed" (we add 1 to ranks/suits at lookup)
        self.rank_embed = nn.Embedding(NUM_RANKS + 1, RANK_EMB, padding_idx=0)
        self.suit_embed = nn.Embedding(NUM_SUITS + 1, SUIT_EMB, padding_idx=0)
        board_dim = BOARD_SLOTS * PER_CARD_EMB
        in_dim = scalar_dim + board_dim
        modules = [nn.Linear(in_dim, hidden), nn.GELU(), nn.LayerNorm(hidden)]
        for _ in range(layers - 1):
            modules += [nn.Linear(hidden, hidden), nn.GELU(), nn.LayerNorm(hidden)]
        self.backbone = nn.Sequential(*modules)
        self.family_head = nn.Linear(hidden, 3)
        self.size_head = nn.Linear(hidden, 4)

    def encode_boards(self, boards: torch.Tensor) -> torch.Tensor:
        """boards: (B, BOARD_SLOTS, 2) int. -1 → 0 (padding); valid → +1 shift."""
        B = boards.shape[0]
        ranks = (boards[:, :, 0] + 1).clamp_min(0)
        suits = (boards[:, :, 1] + 1).clamp_min(0)
        r_emb = self.rank_embed(ranks)            # (B, BOARD_SLOTS, RANK_EMB)
        s_emb = self.suit_embed(suits)            # (B, BOARD_SLOTS, SUIT_EMB)
        x = torch.cat([r_emb, s_emb], dim=-1)     # (B, BOARD_SLOTS, PER_CARD_EMB)
        return x.reshape(B, BOARD_SLOTS * PER_CARD_EMB)

    def forward(self, scalars, boards):
        b = self.encode_boards(boards)
        x = torch.cat([scalars, b], dim=-1)
        h = self.backbone(x)
        return self.family_head(h), self.size_head(h)


def expected_calibration_error(probs: torch.Tensor, targets: torch.Tensor, n_bins: int = 15) -> float:
    """Standard ECE on multi-class predictions. Uses argmax confidence per row."""
    n = probs.shape[0]
    confs, preds = probs.max(dim=-1)
    correct = (preds == targets).float()
    confs = confs.cpu().numpy()
    correct = correct.cpu().numpy()
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        m = (confs > bins[i]) & (confs <= bins[i + 1])
        if not m.any():
            continue
        bin_conf = float(confs[m].mean())
        bin_acc = float(correct[m].mean())
        ece += (m.sum() / n) * abs(bin_acc - bin_conf)
    return float(ece)


def evaluate(model, batch, n_bins: int = 15) -> dict:
    model.eval()
    with torch.no_grad():
        fam_logits, sz_logits = model(batch['scalars'], batch['boards'])
        fam_probs = F.softmax(fam_logits, dim=-1)
        fam_pred = fam_logits.argmax(-1)
        sz_pred = sz_logits.argmax(-1)
        fam_acc = (fam_pred == batch['family']).float().mean().item()

        # Combined slot prediction
        n = len(batch['family'])
        combined = torch.full((n,), -1, dtype=torch.long, device=fam_pred.device)
        combined[fam_pred == 0] = 0
        combined[fam_pred == 1] = 1
        is_raise = fam_pred == 2
        if is_raise.any():
            sz_to_slot = torch.tensor([3, 5, 7, 8], device=fam_pred.device)
            combined[is_raise] = sz_to_slot[sz_pred[is_raise]]
        slot_acc = (combined == batch['slots']).float().mean().item()

        fam_nll = F.cross_entropy(fam_logits, batch['family']).item()
        ece = expected_calibration_error(fam_probs, batch['family'], n_bins=n_bins)

        l1_by_street = {}
        for st in (0, 1, 2, 3):
            m = batch['streets'] == st
            if not m.any():
                continue
            true_freq = torch.bincount(batch['slots'][m], minlength=9).float() / m.float().sum()
            pred_freq = torch.bincount(combined[m], minlength=9).float() / m.float().sum()
            l1_by_street[st] = float((true_freq - pred_freq).abs().sum().item() / 2.0)

        # Raise-size confusion: when teacher (=Slumbot) raises, how does size predict?
        is_raise_truth = batch['family'] == 2
        if is_raise_truth.any():
            true_sz = batch['size'][is_raise_truth].cpu().numpy()
            pred_sz_logits = sz_logits[is_raise_truth].argmax(-1).cpu().numpy()
            size_confusion = np.zeros((4, 4), dtype=int)
            for t, p in zip(true_sz, pred_sz_logits):
                if 0 <= t < 4 and 0 <= p < 4:
                    size_confusion[t, p] += 1
        else:
            size_confusion = np.zeros((4, 4), dtype=int)

    return {
        'fam_acc': fam_acc,
        'slot_acc': slot_acc,
        'fam_nll': fam_nll,
        'ece': ece,
        'l1_by_street': l1_by_street,
        'size_confusion': size_confusion.tolist(),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--train', required=True)
    p.add_argument('--val', required=True)
    p.add_argument('--test-oop', default=None)
    p.add_argument('--epochs', type=int, default=30)
    p.add_argument('--batch-size', type=int, default=1024)
    p.add_argument('--lr', type=float, default=1e-3)
    p.add_argument('--hidden', type=int, default=768)
    p.add_argument('--layers', type=int, default=4)
    p.add_argument('--device', default='cuda')
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--size-loss-coef', type=float, default=1.0)
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
    model = ProxyV2(scalar_dim=SCALAR_DIM, hidden=args.hidden, layers=args.layers).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f'Params: {n_params:,}')

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)

    n = len(train_rows)
    history = []
    t0 = time.time()
    best_val_nll = float('inf')
    best_post_l1 = float('inf')
    best_state_dict = None
    best_epoch = -1

    for ep in range(args.epochs):
        model.train()
        idx = torch.randperm(n, device=device)
        ep_loss = 0.0
        ep_steps = 0
        for s in range(0, n, args.batch_size):
            mb = idx[s:s + args.batch_size]
            fam_logits, sz_logits = model(train_b['scalars'][mb], train_b['boards'][mb])
            fam_loss = F.cross_entropy(fam_logits, train_b['family'][mb])
            is_raise = train_b['family'][mb] == 2
            if is_raise.any():
                sz_loss = F.cross_entropy(sz_logits[is_raise], train_b['size'][mb][is_raise])
            else:
                sz_loss = torch.zeros((), device=device)
            loss = fam_loss + args.size_loss_coef * sz_loss
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            ep_loss += loss.item()
            ep_steps += 1
        sched.step()
        val_m = evaluate(model, val_b)
        test_m = evaluate(model, test_b) if test_b is not None else None
        rec = {
            'epoch': ep, 'lr': sched.get_last_lr()[0],
            'train_loss': ep_loss / max(ep_steps, 1),
            'val': val_m,
        }
        if test_m:
            rec['test_oop'] = test_m
        history.append(rec)
        # Composite save criterion: among epochs with NLL < 0.7 (gate), pick the one
        # with the lowest postflop L1 average (improves bet-size fidelity for PPO use).
        nll_ok = val_m['fam_nll'] < 0.7
        post_l1_avg = sum(val_m['l1_by_street'].get(st, 0.0) for st in (1, 2, 3)) / 3
        if nll_ok and (best_state_dict is None or post_l1_avg < best_post_l1):
            best_post_l1 = post_l1_avg
            best_val_nll = val_m['fam_nll']
            best_epoch = ep
            best_state_dict = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        oop_str = (f' | test_oop fam={test_m["fam_acc"]:.3f} nll={test_m["fam_nll"]:.3f} '
                   f'ece={test_m["ece"]:.3f}' if test_m else '')
        l1 = val_m['l1_by_street']
        l1_str = '/'.join(f'{l1.get(st, 0):.3f}' for st in (0, 1, 2, 3))
        print(f'[ep {ep:2d}] loss={rec["train_loss"]:.4f} | val fam={val_m["fam_acc"]:.3f} '
              f'slot={val_m["slot_acc"]:.3f} nll={val_m["fam_nll"]:.3f} '
              f'ece={val_m["ece"]:.3f} '
              f'L1[pre/fl/tu/ri]={l1_str}'
              f'{oop_str}')

    elapsed = time.time() - t0

    out_dir = REPO_ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Save BEST-val checkpoint (not last epoch — proxy v2 overfits past epoch ~7)
    ckpt_path = out_dir / 'best.pt'
    save_state = best_state_dict if best_state_dict is not None else model.state_dict()
    torch.save({'model': save_state, 'scalar_dim': SCALAR_DIM,
                'hidden': args.hidden, 'layers': args.layers,
                'arch': 'proxy_v2_board_embed', 'version': VERSION,
                'best_epoch': best_epoch, 'best_val_nll': best_val_nll}, ckpt_path)
    print(f'  saved best-val ckpt: epoch={best_epoch}, val_nll={best_val_nll:.4f}')

    # Re-evaluate using best ckpt for the final report
    model.load_state_dict(save_state)
    final_val = evaluate(model, val_b)
    final_test = evaluate(model, test_b) if test_b is not None else None
    final_for_report = {'epoch': best_epoch, 'val': final_val}
    if final_test:
        final_for_report['test_oop'] = final_test
    (out_dir / 'history.json').write_text(json.dumps(history, indent=2), encoding='utf-8')

    write_manifest(out_dir / 'manifest.json',
                   script='phase2/train_slumbot_proxy_v2.py', version=VERSION,
                   args=vars(args), seed=args.seed,
                   inputs=[args.train, args.val] + ([args.test_oop] if args.test_oop else []),
                   outputs=[ckpt_path, out_dir / 'history.json'],
                   extra={'elapsed_s': elapsed, 'final': history[-1] if history else None,
                          'n_params': n_params, 'best_val_nll': best_val_nll})

    # Report uses best-val metrics, not last-epoch (which overfits)
    final = final_for_report
    md = [
        f'**Architecture**: board-embed + scalar MLP (LayerNorm + GELU)',
        f'**Params**: {n_params:,} (vs v1 ~200k)',
        f'**Train / Val / Test_OOP**: {len(train_rows):,} / {len(val_rows):,} / {len(test_rows):,}',
        f'**Epochs trained**: {args.epochs}  (best at epoch {best_epoch})',
        f'**Elapsed**: {elapsed:.1f}s',
        '',
        f'**Final val family accuracy**: {final["val"]["fam_acc"]:.3f}',
        f'**Final val NLL**: {final["val"]["fam_nll"]:.3f}  (target < 0.7)',
        f'**Final val ECE**: {final["val"]["ece"]:.3f}  (target < 0.08, ideal < 0.05)',
        f'**Final val L1 by street**:',
        f'  - preflop: {final["val"]["l1_by_street"].get(0, "n/a"):.3f}  (target < 0.08, ideal < 0.05)',
        f'  - flop:    {final["val"]["l1_by_street"].get(1, "n/a"):.3f}  (target ≥30% reduction)',
        f'  - turn:    {final["val"]["l1_by_street"].get(2, "n/a"):.3f}',
        f'  - river:   {final["val"]["l1_by_street"].get(3, "n/a"):.3f}',
    ]
    if test_rows:
        md.extend([
            '',
            f'**Final test-OOP family accuracy**: {final["test_oop"]["fam_acc"]:.3f}',
            f'**Final test-OOP NLL**: {final["test_oop"]["fam_nll"]:.3f}',
            f'**Final test-OOP ECE**: {final["test_oop"]["ece"]:.3f}',
            f'**Final test-OOP L1 by street**:',
            f'  - preflop: {final["test_oop"]["l1_by_street"].get(0, "n/a"):.3f}',
            f'  - flop:    {final["test_oop"]["l1_by_street"].get(1, "n/a"):.3f}',
            f'  - turn:    {final["test_oop"]["l1_by_street"].get(2, "n/a"):.3f}',
            f'  - river:   {final["test_oop"]["l1_by_street"].get(3, "n/a"):.3f}',
        ])
    md.append('')
    md.append('### Raise-size confusion (val, rows=true, cols=predicted; 0=small 1=med 2=large 3=jam)')
    for row in final['val']['size_confusion']:
        md.append('| ' + ' | '.join(str(x) for x in row) + ' |')

    write_md_report(out_dir / 'report.md',
                    title='Slumbot proxy v2 (board-aware)',
                    sections=[('Summary', '\n'.join(md))])

    print(f'\n[OK] proxy v2 -> {ckpt_path}')


if __name__ == '__main__':
    main()
