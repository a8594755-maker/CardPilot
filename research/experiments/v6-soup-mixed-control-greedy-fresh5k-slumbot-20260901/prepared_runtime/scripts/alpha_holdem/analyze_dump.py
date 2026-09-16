"""Per-position / per-street analysis of Slumbot bench dumps.

Input: one or more JSONL files written by play_slumbot.py with --dump-slumbot.
Each line is one MOVE (hero or opp) annotated with:
  hand_idx, move_idx, who ('hero' or 'opp'), client_pos (0=hero BB, 1=hero SB),
  street (0..3), action_move ('b','c','k','f'), action_amount,
  pot_before, to_call, winnings_hero, showdown

Computes:
  - per-position (SB vs BB) win rate and showdown freq
  - hero preflop opening action mix when SB (open-raise / limp / fold ?)
  - hero preflop response when BB facing SB raise (fold / call / 3bet)
  - hero postflop action mix (c-bet freq, fold-to-bet freq)
  - all-in classification (preflop jam vs postflop low-SPR vs river jam)
  - showdown vs non-showdown chip flow
"""
import json, os, sys
from collections import defaultdict
from pathlib import Path


def load(paths):
    rows = []
    for p in paths:
        with open(p, encoding='utf-8') as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    continue
    return rows


def per_hand(rows):
    """Group by (file, hand_idx) and return hand-level summaries.

    Determines terminal_type from the move sequence (not from Slumbot's
    `showdown` field, which is unreliable — Slumbot returns opp_hole on
    folded hands too, making showdown=True always).
    """
    hands = {}
    for r in rows:
        key = (r.get('_file', ''), r['hand_idx'])
        if key not in hands:
            hands[key] = {
                'hand_idx': r['hand_idx'],
                'client_pos': r.get('client_pos', 1 - r.get('opp_pos', 0)),
                'winnings': r.get('winnings_hero', 0),
                'moves': [],
                'hero_hole': r.get('hero_hole'),
            }
        hands[key]['moves'].append(r)
    # Determine terminal_type per hand from last move + street count
    for h in hands.values():
        h['moves'].sort(key=lambda m: m['move_idx'])
        last = h['moves'][-1] if h['moves'] else None
        if last is None:
            h['terminal_type'] = 'unknown'
            h['ended_by_hero'] = False
            continue
        last_mv = last['action_move']
        last_who = last.get('who', 'opp')
        max_street = max(m['street'] for m in h['moves'])
        # Streets: 0=pre, 1=flop, 2=turn, 3=river
        if last_mv == 'f':
            h['terminal_type'] = 'hero_fold' if last_who == 'hero' else 'opp_fold'
            h['ended_by_hero'] = (last_who == 'hero')
        elif max_street == 3:
            # Hand reached river; if last move is check/call/bet on river, it's a showdown
            h['terminal_type'] = 'showdown'
            h['ended_by_hero'] = False
        elif last_mv == 'c':
            # Call that ends the hand pre-river — implies all-in call (runout shown)
            h['terminal_type'] = 'allin_runout'
            h['ended_by_hero'] = False
        else:
            h['terminal_type'] = 'other'
            h['ended_by_hero'] = False
    return list(hands.values())


def summarize(hands, label=''):
    n = len(hands)
    if n == 0:
        print(f'[{label}] no hands found')
        return
    win = sum(h['winnings'] for h in hands)
    bb100 = (win / n) / 100 * 100  # winnings is in chips, BIG_BLIND=100 → BB/hand×100 = bb/100
    # Slumbot convention (play_slumbot.py:12): client_pos=0 → hero is BB, =1 → hero is SB
    bb_hands = [h for h in hands if h['client_pos'] == 0]
    sb_hands = [h for h in hands if h['client_pos'] == 1]
    n_sb, n_bb = len(sb_hands), len(bb_hands)
    sb_win = sum(h['winnings'] for h in sb_hands) if sb_hands else 0
    bb_win = sum(h['winnings'] for h in bb_hands) if bb_hands else 0
    sb_bb100 = (sb_win / max(n_sb, 1)) / 100 * 100
    bb_bb100 = (bb_win / max(n_bb, 1)) / 100 * 100
    # Terminal-type breakdown (correctly derived from action sequence, NOT Slumbot's flag)
    term_counts = defaultdict(int)
    term_chips = defaultdict(int)
    for h in hands:
        t = h.get('terminal_type', 'unknown')
        term_counts[t] += 1
        term_chips[t] += h['winnings']

    print(f'\n=== {label}  (n={n}) ===')
    print(f'  overall  : {bb100:+.1f} bb/100   total_chips={win:+,}')
    print(f'  as SB    : {sb_bb100:+.1f} bb/100   n_sb={n_sb}   chips={sb_win:+,}')
    print(f'  as BB    : {bb_bb100:+.1f} bb/100   n_bb={n_bb}   chips={bb_win:+,}')
    print(f'  terminal breakdown:')
    for t in ['hero_fold', 'opp_fold', 'showdown', 'allin_runout', 'other', 'unknown']:
        if term_counts[t] == 0:
            continue
        pct = 100 * term_counts[t] / n
        avg = term_chips[t] / max(term_counts[t], 1) / 100  # BB/hand
        print(f'    {t:<14s}  n={term_counts[t]:>5d} ({pct:>4.1f}%)  '
              f'chips={term_chips[t]:+,}  avg={avg:+.3f} BB/hand')

    # Hero action mix
    hero_moves = [r for h in hands for r in h['moves'] if r.get('who') == 'hero']
    if not hero_moves:
        print(f'  (no hero moves dumped — old dump format?)')
        return
    by_street = defaultdict(lambda: defaultdict(int))
    for m in hero_moves:
        st = m['street']
        mv = m['action_move']
        by_street[st][mv] += 1
        if mv == 'b':
            # classify bet size vs pot
            pot = max(m['pot_before'], 1)
            amt = m['action_amount']
            sz = amt / pot
            if amt >= m['stack_remaining'] + m['to_call'] - 1:  # all-in proxy
                by_street[st]['_allin'] += 1
            elif sz < 0.5:
                by_street[st]['_b<50%'] += 1
            elif sz < 1.0:
                by_street[st]['_b50-100%'] += 1
            else:
                by_street[st]['_b>100%'] += 1
    street_names = ['preflop', 'flop', 'turn', 'river']
    print(f'  hero action mix by street:')
    for st in (0, 1, 2, 3):
        d = by_street[st]
        total = sum(v for k, v in d.items() if not k.startswith('_'))
        if total == 0:
            continue
        f = d.get('f', 0) / max(total, 1)
        c = d.get('c', 0) / max(total, 1)
        k = d.get('k', 0) / max(total, 1)
        b = d.get('b', 0) / max(total, 1)
        bsz = f"  bet_size{{<50%:{d.get('_b<50%',0)} 50-100%:{d.get('_b50-100%',0)} >100%:{d.get('_b>100%',0)} allin:{d.get('_allin',0)}}}"
        print(f'    {street_names[st]:<8s}  n={total:5d}  fold={f:.3f}  call={c:.3f}  check={k:.3f}  bet/raise={b:.3f}{bsz}')

    # Preflop SB open mix specifically (hero is first to act preflop; client_pos=1 → hero SB)
    sb_preflop_opens = [m for m in hero_moves
                        if m['street'] == 0 and m['client_pos'] == 1
                        and m['action_str_before'] == '']
    if sb_preflop_opens:
        d = defaultdict(int)
        for m in sb_preflop_opens:
            d[m['action_move']] += 1
            if m['action_move'] == 'b' and m['action_amount'] >= 19000:  # >= 190 BB ≈ jam
                d['_jam'] += 1
        n_open = sum(v for k, v in d.items() if not k.startswith('_'))
        print(f'  SB preflop open ({n_open}):')
        for mv in 'fckb':
            if d.get(mv, 0):
                print(f'    {mv}: {d[mv]:5d}  ({d[mv]/n_open*100:.1f}%)')
        if d.get('_jam', 0):
            print(f'    of which open-jams: {d["_jam"]} ({d["_jam"]/n_open*100:.1f}%)')

    # BB facing preflop raise (hero is BB → client_pos=0; SB has already acted with 'b')
    bb_facing_raise = [m for m in hero_moves
                       if m['street'] == 0 and m['client_pos'] == 0
                       and m['action_str_before'] and m['action_str_before'].startswith('b')]
    if bb_facing_raise:
        d = defaultdict(int)
        for m in bb_facing_raise:
            d[m['action_move']] += 1
        n_bb = sum(d.values())
        print(f'  BB preflop facing SB raise ({n_bb}):')
        for mv in 'fcb':
            if d.get(mv, 0):
                print(f'    {mv}: {d[mv]:5d}  ({d[mv]/n_bb*100:.1f}%)')


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--dumps', nargs='+', required=True, help='one or more dump.jsonl files (glob OK)')
    p.add_argument('--label', default='dump')
    args = p.parse_args()

    paths = []
    for g in args.dumps:
        from glob import glob
        ps = glob(g)
        paths.extend(ps) if ps else paths.append(g)

    all_rows = []
    for path in paths:
        if not os.path.exists(path):
            print(f'  [skip] {path} not found')
            continue
        with open(path, encoding='utf-8') as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                    r['_file'] = path
                    all_rows.append(r)
                except Exception:
                    pass
    print(f'Loaded {len(all_rows):,} move records from {len(paths)} files')

    hands = per_hand(all_rows)
    summarize(hands, label=args.label)


if __name__ == '__main__':
    main()
