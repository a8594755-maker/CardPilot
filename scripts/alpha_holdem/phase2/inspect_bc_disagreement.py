"""Stratified BC vs teacher disagreement analyzer.

Loads a BC checkpoint and a teacher-data JSONL, runs BC on each row, compares
its predicted action against the teacher's action, and stratifies the
disagreement across decision-relevant subspaces:

  - position (SB / BB)
  - street (preflop / flop / turn / river)
  - facing_bet (yes / no)
  - "BB facing aggression" (BB + street>=0 + facing_bet)
  - "preflop 3-bet / jam spot" (preflop + facing_bet + teacher_action in raise/jam slots)
  - "river facing bet" (street=3 + facing_bet)
  - "high-pot state" (pot_before > median)

For each slice reports:
  - n samples
  - disagreement rate (%)
  - top-K teacher→BC slot confusions (what teacher said vs what BC said when wrong)

Usage:
  python inspect_bc_disagreement.py \
    --ckpt models/bc/v3_anchor_5M_first/best.pt \
    --data data/phase2/teacher_v3_5M.jsonl \
    --max-rows 50000 \
    --seed 123 \
    --out reports/phase2/day1_bc_disagreement
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
sys.path.insert(0, str(REPO_ROOT / 'scripts' / 'alpha_holdem'))
sys.path.insert(0, str(THIS_DIR / 'common'))
from manifest import write_manifest, write_md_report
from alpha_holdem.network import AlphaHoldemNet

NUM_ACTIONS = 9
CARD_SHAPE = (6, 4, 13)
ACTION_SHAPE = (25, 4, 5)


def reservoir_sample(path: Path, k: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    reservoir = []
    with open(path, encoding='utf-8') as f:
        for i, ln in enumerate(f):
            ln = ln.strip()
            if not ln:
                continue
            if len(reservoir) < k:
                reservoir.append(json.loads(ln))
            else:
                j = int(rng.integers(0, i + 1))
                if j < k:
                    reservoir[j] = json.loads(ln)
    return reservoir


def load_bc(ckpt_path: str, device: str):
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    norm = ck.get('norm_layer', 'gn')
    m = AlphaHoldemNet(num_actions=NUM_ACTIONS, norm_layer=norm).to(device)
    m.eval()
    m(torch.zeros(2, *CARD_SHAPE, device=device),
      torch.zeros(2, *ACTION_SHAPE, device=device),
      torch.zeros(2, 2, device=device))
    m.load_state_dict(ck['model'])
    m.eval()
    return m


def to_batch(rows, device: str):
    n = len(rows)
    cards = np.empty((n, *CARD_SHAPE), dtype=np.float32)
    actions = np.empty((n, *ACTION_SHAPE), dtype=np.float32)
    extras = np.empty((n, 2), dtype=np.float32)
    masks = np.empty((n, NUM_ACTIONS), dtype=np.float32)
    teacher_actions = np.empty((n,), dtype=np.int64)
    streets = np.empty((n,), dtype=np.int64)
    positions = np.empty((n,), dtype=np.int64)
    facing_bet = np.empty((n,), dtype=np.int64)
    pot_before = np.empty((n,), dtype=np.int64)
    to_call = np.empty((n,), dtype=np.int64)
    action_str_before_len = np.empty((n,), dtype=np.int64)
    for i, r in enumerate(rows):
        cards[i] = np.array(r['card_obs'], dtype=np.float32).reshape(CARD_SHAPE)
        actions[i] = np.array(r['action_obs'], dtype=np.float32).reshape(ACTION_SHAPE)
        extras[i] = np.array(r['extra_obs'], dtype=np.float32)
        masks[i] = np.array(r['legal_mask'], dtype=np.float32)
        teacher_actions[i] = int(r['teacher_action'])
        streets[i] = int(r['street'])
        positions[i] = int(r['client_pos'])
        facing_bet[i] = 1 if int(r.get('to_call', 0)) > 0 else 0
        pot_before[i] = int(r.get('pot_before', 0))
        to_call[i] = int(r.get('to_call', 0))
        # Best-effort detection of "3-bet spot": preflop with the opp having already raised
        # action_str_before is not in our dump; approximate via to_call > 1 BB (= raise occurred)
        action_str_before_len[i] = int(r.get('to_call', 0))
    return {
        'cards': torch.from_numpy(cards).to(device),
        'actions': torch.from_numpy(actions).to(device),
        'extras': torch.from_numpy(extras).to(device),
        'masks': torch.from_numpy(masks).to(device),
        'teacher': teacher_actions,
        'streets': streets,
        'positions': positions,
        'facing_bet': facing_bet,
        'pot_before': pot_before,
        'to_call': to_call,
    }


def predict(model, batch, batch_size: int = 4096) -> np.ndarray:
    n = len(batch['teacher'])
    preds = np.empty((n,), dtype=np.int64)
    with torch.no_grad():
        for s in range(0, n, batch_size):
            e = min(s + batch_size, n)
            logits, _ = model(batch['cards'][s:e], batch['actions'][s:e],
                              batch['extras'][s:e], batch['masks'][s:e])
            preds[s:e] = logits.argmax(dim=-1).cpu().numpy()
    return preds


def slice_stats(name: str, mask: np.ndarray, teacher: np.ndarray, pred: np.ndarray,
                top_k: int = 5) -> dict:
    n = int(mask.sum())
    if n == 0:
        return {'name': name, 'n': 0, 'disagreement_rate': None, 'top_confusions': []}
    sel_t = teacher[mask]
    sel_p = pred[mask]
    disagree = (sel_t != sel_p)
    rate = float(disagree.mean())
    # Top-K confusions: (teacher_slot, bc_slot) most-frequent disagreement pairs
    pairs = Counter()
    for t, p in zip(sel_t[disagree], sel_p[disagree]):
        pairs[(int(t), int(p))] += 1
    top = pairs.most_common(top_k)
    return {
        'name': name,
        'n': n,
        'disagreement_rate': rate,
        'disagreement_count': int(disagree.sum()),
        'top_confusions': [(f'teacher={t}→bc={p}', c) for (t, p), c in top],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ckpt', required=True)
    p.add_argument('--data', required=True)
    p.add_argument('--max-rows', type=int, default=50000)
    p.add_argument('--seed', type=int, default=123)
    p.add_argument('--device', default='cuda')
    p.add_argument('--out', required=True)
    args = p.parse_args()

    device = 'cuda' if (args.device == 'cuda' and torch.cuda.is_available()) else 'cpu'
    print(f'Device: {device}')

    print(f'Reservoir-sampling {args.max_rows} rows from {args.data} (seed={args.seed})...')
    rows = reservoir_sample(Path(args.data), args.max_rows, args.seed)
    print(f'  {len(rows)} rows loaded')

    print(f'Loading BC checkpoint: {args.ckpt}')
    model = load_bc(args.ckpt, device)

    t0 = time.time()
    batch = to_batch(rows, device)
    preds = predict(model, batch)
    elapsed = time.time() - t0
    print(f'Forward done in {elapsed:.1f}s')

    teacher = batch['teacher']
    streets = batch['streets']
    positions = batch['positions']  # Slumbot: 0=BB, 1=SB
    facing = batch['facing_bet']
    pot = batch['pot_before']
    to_call = batch['to_call']

    pot_median = int(np.median(pot[pot > 0])) if (pot > 0).any() else 0
    print(f'Pot median (nonzero): {pot_median}')

    overall_disagree = (teacher != preds).mean()
    print(f'\nOverall disagreement: {100*overall_disagree:.2f}% ({int((teacher!=preds).sum())} / {len(teacher)})')

    n = len(teacher)
    slices = []
    slices.append(slice_stats('all', np.ones(n, bool), teacher, preds))
    slices.append(slice_stats('SB (pos=1)', positions == 1, teacher, preds))
    slices.append(slice_stats('BB (pos=0)', positions == 0, teacher, preds))
    slices.append(slice_stats('preflop', streets == 0, teacher, preds))
    slices.append(slice_stats('flop', streets == 1, teacher, preds))
    slices.append(slice_stats('turn', streets == 2, teacher, preds))
    slices.append(slice_stats('river', streets == 3, teacher, preds))
    slices.append(slice_stats('facing_bet=1', facing == 1, teacher, preds))
    slices.append(slice_stats('facing_bet=0 (no bet)', facing == 0, teacher, preds))
    # Critical state subspaces
    slices.append(slice_stats('BB facing aggression (pos=0 & facing_bet)',
                              (positions == 0) & (facing == 1), teacher, preds))
    slices.append(slice_stats('preflop 3-bet spot (preflop+facing_bet+to_call>=2BB)',
                              (streets == 0) & (facing == 1) & (to_call >= 200),
                              teacher, preds))
    slices.append(slice_stats('river facing bet (street=3+facing_bet)',
                              (streets == 3) & (facing == 1), teacher, preds))
    slices.append(slice_stats('high-pot state (pot > median nonzero pot)',
                              pot > pot_median, teacher, preds))
    slices.append(slice_stats('teacher chose raise (slots 2-7)',
                              (teacher >= 2) & (teacher <= 7), teacher, preds))
    slices.append(slice_stats('teacher chose jam/allin (slot 8)',
                              teacher == 8, teacher, preds))
    slices.append(slice_stats('teacher chose fold (slot 0) facing_bet',
                              (teacher == 0) & (facing == 1), teacher, preds))

    # Print stratified report
    print('\n=== Stratified disagreement ===')
    print(f'{"slice":<55s} {"n":>6s} {"disagree%":>10s}  top confusions')
    print('-' * 130)
    for s in slices:
        if s['n'] == 0:
            print(f'{s["name"]:<55s} {"0":>6s} {"-":>10s}')
            continue
        rate_str = f'{100*s["disagreement_rate"]:6.2f}%'
        conf_str = '; '.join(f'{k}={v}' for k, v in s['top_confusions'][:3])
        print(f'{s["name"]:<55s} {s["n"]:>6d} {rate_str:>10s}  {conf_str}')

    # MD report
    md_lines = [
        f'BC ckpt: `{args.ckpt}`',
        f'Data: `{args.data}` (sampled {len(rows)} rows, seed={args.seed})',
        f'Pot median (nonzero): {pot_median}',
        f'Overall disagreement: {100*overall_disagree:.2f}%',
        '',
        '### Stratified disagreement',
        '',
        '| slice | n | disagreement % | top confusions |',
        '|---|---:|---:|---|',
    ]
    for s in slices:
        if s['n'] == 0:
            md_lines.append(f'| {s["name"]} | 0 | - | - |')
            continue
        conf = '; '.join(f'{k}={v}' for k, v in s['top_confusions'][:3])
        md_lines.append(f'| {s["name"]} | {s["n"]} | {100*s["disagreement_rate"]:.2f}% | {conf} |')

    out_dir = REPO_ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_md_report(out_dir / 'report.md', title='BC vs heuristic_v3 disagreement analysis',
                    sections=[('Summary', '\n'.join(md_lines))])
    (out_dir / 'slices.json').write_text(json.dumps(slices, indent=2), encoding='utf-8')
    write_manifest(out_dir / 'manifest.json',
                   script='phase2/inspect_bc_disagreement.py', version='0.1.0',
                   args=vars(args), seed=args.seed,
                   inputs=[args.ckpt, args.data],
                   outputs=[out_dir / 'report.md', out_dir / 'slices.json'],
                   extra={'pot_median': pot_median, 'overall_disagree': float(overall_disagree)})

    print(f'\n[OK] {out_dir}')


if __name__ == '__main__':
    main()
