"""Phase 2 Slumbot proxy dataset builder.

Reads existing dump JSONLs from eval_logs/path_b/*_dump.jsonl, filters to
OPPONENT moves only (Slumbot's actions), strips hero hole cards, applies
holdout-by-hero-policy split.

Output structure:
  out_dir/
    train.jsonl      (records used for training)
    val.jsonl        (in-domain validation)
    test_oop.jsonl   (held-out hero policies — generalization test)
    manifest.json
    report.md

Critical: hero_hole MUST be excluded from proxy inputs. The proxy models
P(Slumbot action | public state). Slumbot cannot see hero's cards.

Public-state schema (per record):
  street, mover_pos (must be opp), pot_before, to_call, stack_remaining,
  last_bet_size, street_last_bet_to, total_last_bet_to,
  public_board, action_str_before, legal_mask (placeholder; not in dump),
  hero_policy_id (tag, for analysis), session_id (tag),
  --- target ---
  slumbot_action_move (b/c/k/f), slumbot_action_amount,
  slumbot_action_slot (0..8, derived)

Usage:
  python build_slumbot_proxy_dataset.py \
    --dumps "eval_logs/path_b/*_dump.jsonl" \
    --train-policies fold call random v4 pathb10m pathb50m heuristic_v1 \
    --val-policies heuristic_v2 \
    --test-policies heuristic_v3 heuristic_v3_1 \
    --out data/phase2/slumbot_proxy_v1
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from glob import glob
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]
sys.path.insert(0, str(THIS_DIR / 'common'))
from manifest import write_manifest, write_md_report

VERSION = '0.1.0-skeleton'

# Map dump-file tag substring -> canonical policy id
POLICY_TAG_PATTERNS = [
    ('path_b_10M_full',          'pathb10m'),
    ('path_b_50M_full',          'pathb50m'),
    ('path_b_10M',               'pathb10m'),
    ('path_b_50M',               'pathb50m'),
    ('path_b_0M',                'zero_random_init'),
    ('baseline_fold_dump',       'fold'),
    ('baseline_fold',            'fold'),
    ('baseline_call',            'call'),
    ('baseline_random',          'random'),
    ('baseline_heuristic_full',  'heuristic_v1'),
    ('baseline_heuristic',       'heuristic_v1'),
    ('heuristic_v2_full',        'heuristic_v2'),
    ('heuristic_v3_1_full',      'heuristic_v3_1'),
    ('heuristic_v3_full',        'heuristic_v3'),
]


def policy_from_filename(path: Path) -> str:
    name = path.name
    for pat, pid in POLICY_TAG_PATTERNS:
        if pat in name:
            return pid
    return 'unknown'


# Strip these from proxy input records — informational only OR hero leak
STRIP_FIELDS = {'hero_hole', 'opp_hole', 'showdown', 'winnings_hero', 'who',
                'client_pos'}  # client_pos is hero's seat; not visible to Slumbot


def derive_slot(move: str, amount: int, pot_before: int, mover_pos: int) -> int:
    """Map (action_move, action_amount) -> 9-slot action index.

    Slot map:
      0 = fold
      1 = check/call
      2..7 = raises by approximate pot fraction (0.33/0.50/0.67/0.75/1.0/1.5)
      8 = allin (placeholder — bench dumps don't expose stack)

    For Phase 2 skeleton, only the broad family (fold/call/check/bet) is critical.
    Sizing buckets are coarse and may be refined when stack info is in the dump.
    """
    if move == 'f':
        return 0
    if move in ('c', 'k'):
        return 1
    if move == 'b':
        if pot_before <= 0:
            return 5
        frac = amount / max(pot_before, 1)
        # Coarse buckets (TODO: refine when stack data lands in dump)
        if frac < 0.4:
            return 2
        if frac < 0.6:
            return 3
        if frac < 0.7:
            return 4
        if frac < 0.9:
            return 5
        if frac < 1.2:
            return 6
        return 7
    return 1  # unknown


def build_record(raw: dict) -> dict | None:
    """Build a public-state record for proxy training. Returns None if invalid."""
    who = raw.get('who', 'opp')
    if who != 'opp':
        return None  # only Slumbot moves
    move = raw['action_move']
    amt = int(raw.get('action_amount', 0))
    pot_before = int(raw.get('pot_before', 0))
    mover_pos = int(raw.get('mover_pos', raw.get('opp_pos', 0)))
    slot = derive_slot(move, amt, pot_before, mover_pos)
    rec = {
        'street': int(raw.get('street', 0)),
        'mover_pos': mover_pos,
        'pot_before': pot_before,
        'to_call': int(raw.get('to_call', 0)),
        'stack_remaining': int(raw.get('stack_remaining', 0)),
        'last_bet_size': int(raw.get('last_bet_size', 0)),
        'street_last_bet_to': int(raw.get('street_last_bet_to', 0)),
        'total_last_bet_to': int(raw.get('total_last_bet_to', 0)),
        'public_board': raw.get('board', []),
        'action_str_before': raw.get('action_str_before', ''),
        # Targets
        'slumbot_action_move': move,
        'slumbot_action_amount': amt,
        'slumbot_action_slot': slot,
    }
    # NOTE: legal mask is NOT in the dump. Day -1 proxy will reconstruct from
    # action_str_before via parse_action() at training time.
    return rec


def collect(dump_glob: str) -> dict[str, list[dict]]:
    """Returns {policy_id: [records]} for all matching dump files."""
    files = []
    for g in dump_glob.split(','):
        files.extend(glob(g.strip()))
    by_policy = {}
    skipped = 0
    for fp in files:
        pid = policy_from_filename(Path(fp))
        with open(fp, encoding='utf-8') as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    raw = json.loads(ln)
                except Exception:
                    skipped += 1
                    continue
                rec = build_record(raw)
                if rec is None:
                    continue
                rec['hero_policy_id'] = pid
                rec['source_file'] = Path(fp).name
                by_policy.setdefault(pid, []).append(rec)
    return by_policy, skipped


def write_jsonl(records: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r) + '\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dumps', default='eval_logs/path_b/*_dump.jsonl',
                   help='Glob (or comma-separated globs) of dump JSONLs')
    p.add_argument('--train-policies', nargs='+',
                   default=['fold', 'call', 'random', 'pathb10m', 'pathb50m',
                            'heuristic_v1', 'zero_random_init'])
    p.add_argument('--val-policies', nargs='+', default=['heuristic_v2'])
    p.add_argument('--test-policies', nargs='+',
                   default=['heuristic_v3', 'heuristic_v3_1'])
    p.add_argument('--out', required=True)
    args = p.parse_args()

    out_dir = REPO_ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)

    print(f'Collecting from: {args.dumps}')
    by_policy, skipped = collect(args.dumps)
    print(f'Skipped malformed: {skipped}')

    counts = {pid: len(recs) for pid, recs in by_policy.items()}
    print(f'Records per policy:')
    for pid, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f'  {pid:<25s} {n:>6d}')

    train = sum((by_policy.get(p, []) for p in args.train_policies), [])
    val = sum((by_policy.get(p, []) for p in args.val_policies), [])
    test = sum((by_policy.get(p, []) for p in args.test_policies), [])

    print(f'\nSplit sizes:')
    print(f'  train ({", ".join(args.train_policies)}): {len(train):>6d}')
    print(f'  val   ({", ".join(args.val_policies)}):   {len(val):>6d}')
    print(f'  test  ({", ".join(args.test_policies)}):  {len(test):>6d}')

    write_jsonl(train, out_dir / 'train.jsonl')
    write_jsonl(val, out_dir / 'val.jsonl')
    write_jsonl(test, out_dir / 'test_oop.jsonl')

    # Per-street action slot histogram
    from collections import Counter
    hist = {}
    for split_name, split_recs in [('train', train), ('val', val), ('test_oop', test)]:
        slots = Counter(r['slumbot_action_slot'] for r in split_recs)
        hist[split_name] = dict(slots)
    print(f'\nAction slot histogram:')
    for sname, h in hist.items():
        print(f'  {sname}: {dict(sorted(h.items()))}')

    write_manifest(out_dir / 'manifest.json',
                   script='phase2/build_slumbot_proxy_dataset.py', version=VERSION,
                   args=vars(args), seed=None,
                   inputs=[args.dumps],
                   outputs=[out_dir / 'train.jsonl', out_dir / 'val.jsonl',
                            out_dir / 'test_oop.jsonl'],
                   extra={'policy_counts': counts,
                          'train_size': len(train), 'val_size': len(val),
                          'test_oop_size': len(test),
                          'slot_histogram_by_split': hist,
                          'skipped_lines': skipped})

    md = [f'**Total opp records:** {sum(counts.values()):,}', '']
    md.append('### Records per policy')
    md.append('')
    md.append('| policy | n |')
    md.append('|---|---:|')
    for pid, n in sorted(counts.items(), key=lambda x: -x[1]):
        md.append(f'| {pid} | {n:,} |')
    md.append('')
    md.append('### Splits')
    md.append('')
    md.append(f'- train: {len(train):,} records ({", ".join(args.train_policies)})')
    md.append(f'- val:   {len(val):,} records ({", ".join(args.val_policies)})')
    md.append(f'- test (held-out policies): {len(test):,} records ({", ".join(args.test_policies)})')
    write_md_report(out_dir / 'report.md',
                    title='Slumbot proxy dataset',
                    sections=[('Summary', '\n'.join(md))])

    print(f'\n[OK] Proxy dataset -> {out_dir}')


if __name__ == '__main__':
    main()
