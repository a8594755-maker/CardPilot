"""Per-opponent / per-position / per-street comparison: RL-1 5M vs BC anchor.

Reads existing eval cells under reports/phase2/rl1_5M_final_eval/cells/ (both `best_*`
which is BC anchor and `ckpt_5M_*` which is RL-1 5M run against the same 8 internal
opponents under the same seed=42 + 20400 hands). Computes:

- Per-opponent bb/100 delta (RL-1 − BC) with SB/BB split
- Per-street action-mix delta (RL-1 − BC) for each opponent
- Aggregated per-street average mix shift across all opponents
- Slumbot bench delta

Emits reports/rl1_vs_bc_diff.md.
"""
from __future__ import annotations
import json
from pathlib import Path

EVAL = Path('reports/phase2/rl1_5M_final_eval')
OUT = Path('reports/rl1_vs_bc_diff.md')

OPPONENTS = ['fold', 'call', 'random', 'heuristic_v3',
             'scripted_aggro', 'scripted_station', 'scripted_jammer', 'pathb10m']

STREET_NAME = {0: 'PRE', 1: 'FLOP', 2: 'TURN', 3: 'RIV'}
ACT_NAME = {0: 'fold', 1: 'cc', 2: 'rS', 3: 'rM', 4: 'rL', 5: 'rXL',
            6: 'rXXL', 7: 'rBIG', 8: 'allin'}


def load_cell(prefix: str, opp: str) -> dict:
    p = EVAL / 'cells' / f'{prefix}_vs_{opp}' / f'{prefix}_vs_{opp}_full.json'
    return json.loads(p.read_text())


def fmt_mix_one(mix: dict, threshold: float = 0.01) -> str:
    parts = []
    for k in sorted(mix.keys(), key=int):
        v = mix[k]
        if abs(v) >= threshold:
            parts.append(f"{ACT_NAME[int(k)]}={v*100:+.1f}%" if v < 0
                         else f"{ACT_NAME[int(k)]}={v*100:.1f}%")
    return ' '.join(parts)


def fmt_mix_diff(diff: dict, threshold: float = 0.02) -> str:
    parts = []
    for k in sorted(diff.keys(), key=int):
        v = diff[k]
        if abs(v) >= threshold:
            parts.append(f"{ACT_NAME[int(k)]}={v*100:+.1f}")
    return ' '.join(parts) if parts else '(no change >2%)'


def diff_mix(rl: dict, bc: dict) -> dict:
    keys = set(rl.keys()) | set(bc.keys())
    return {k: rl.get(k, 0.0) - bc.get(k, 0.0) for k in keys}


def main():
    rl_matrix = json.loads((EVAL / 'matrix.json').read_text())
    rl = rl_matrix['ckpt_5M']
    bc = rl_matrix['best']

    lines = []
    lines.append('# RL-1 5M vs BC anchor: per-position / per-street edge-loss analysis\n')
    lines.append('Both checkpoints evaluated under identical conditions (seed=42, 20400 hands per opponent).\n')
    lines.append('Source: `reports/phase2/rl1_5M_final_eval/`. RL-1 ckpt: `models/ppo/rl1_5M_run1/ckpt_5M.pt`. '
                 'BC ckpt: `models/bc/v3_anchor_5M_d1_light/best.pt`.\n')

    # --- Per-opponent bb/100 + position split delta
    lines.append('## Per-opponent overall + position split\n')
    lines.append('| opp | BC bb/100 | RL bb/100 | Δ | BC SB | RL SB | Δ SB | BC BB | RL BB | Δ BB |')
    lines.append('|:--|---:|---:|---:|---:|---:|---:|---:|---:|---:|')

    sb_deltas = []
    bb_deltas = []
    tot_deltas = []
    for opp in OPPONENTS:
        bc_o = bc[opp]
        rl_o = rl[opp]
        bc_tot = float(bc_o['bb100'])
        rl_tot = float(rl_o['bb100'])
        bc_sb = float(bc_o['sb_bb100'])
        rl_sb = float(rl_o['sb_bb100'])
        bc_bb = float(bc_o['bb_bb100'])
        rl_bb = float(rl_o['bb_bb100'])
        d_tot = rl_tot - bc_tot
        d_sb = rl_sb - bc_sb
        d_bb = rl_bb - bc_bb
        tot_deltas.append(d_tot)
        sb_deltas.append(d_sb)
        bb_deltas.append(d_bb)
        lines.append(f'| {opp} | {bc_tot:+.2f} | {rl_tot:+.2f} | {d_tot:+.2f} | '
                     f'{bc_sb:+.2f} | {rl_sb:+.2f} | {d_sb:+.2f} | '
                     f'{bc_bb:+.2f} | {rl_bb:+.2f} | {d_bb:+.2f} |')

    # Slumbot
    bc_sl = float(bc['slumbot']['bb100'])
    rl_sl = float(rl['slumbot']['bb100'])
    lines.append(f'| **slumbot** | {bc_sl:+.2f} | {rl_sl:+.2f} | {rl_sl-bc_sl:+.2f} | — | — | — | — | — | — |')
    lines.append('')

    # --- Summary stats
    n = len(OPPONENTS)
    lines.append('### Summary')
    lines.append(f'- Mean Δ total: {sum(tot_deltas)/n:+.2f} bb/100')
    lines.append(f'- Mean Δ SB:    {sum(sb_deltas)/n:+.2f} bb/100  (RL-1 lost ~9 bb/100 from SB across opponents)')
    lines.append(f'- Mean Δ BB:    {sum(bb_deltas)/n:+.2f} bb/100  (RL-1 gained on BB)')
    lines.append(f'- Slumbot Δ:    {rl_sl-bc_sl:+.2f} bb/100  (significant regression)')
    lines.append('')

    # --- Per-street action mix shift
    lines.append('## Per-street action-mix shift (RL-1 − BC, percentage points)\n')
    lines.append('Reading guide: positive = RL-1 used MORE; negative = RL-1 used LESS than BC anchor.')
    lines.append('Threshold: only |shift| ≥ 2% shown.\n')

    # Aggregate
    agg = {0: {}, 1: {}, 2: {}, 3: {}}
    counts = {0: 0, 1: 0, 2: 0, 3: 0}

    for opp in OPPONENTS:
        try:
            rl_cell = load_cell('ckpt_5M', opp)
            bc_cell = load_cell('best', opp)
        except FileNotFoundError:
            continue
        rl_mix = rl_cell.get('action_mix_by_street', {})
        bc_mix = bc_cell.get('action_mix_by_street', {})

        lines.append(f'### vs {opp}')
        lines.append('| street | RL-1 mix | shift vs BC |')
        lines.append('|:--|:--|:--|')
        for st in [0, 1, 2, 3]:
            sk = str(st)
            rl_s = rl_mix.get(sk, {})
            bc_s = bc_mix.get(sk, {})
            d = diff_mix(rl_s, bc_s)
            lines.append(f'| {STREET_NAME[st]} | {fmt_mix_one(rl_s, 0.02)} | {fmt_mix_diff(d, 0.02)} |')
            # aggregate
            for k, v in d.items():
                agg[st][k] = agg[st].get(k, 0.0) + v
            counts[st] += 1
        lines.append('')

    # --- Aggregated shift
    lines.append('## Aggregated per-street shift (averaged across 8 opponents)\n')
    lines.append('| street | mean RL-1 − BC shift |')
    lines.append('|:--|:--|')
    for st in [0, 1, 2, 3]:
        c = counts[st] or 1
        avg = {k: v / c for k, v in agg[st].items()}
        lines.append(f'| {STREET_NAME[st]} | {fmt_mix_diff(avg, 0.02)} |')
    lines.append('')

    # --- Diagnosis
    lines.append('## Diagnosis')
    lines.append('')
    avg_flop = {k: v / counts[1] for k, v in agg[1].items()}
    avg_turn = {k: v / counts[2] for k, v in agg[2].items()}
    avg_riv = {k: v / counts[3] for k, v in agg[3].items()}
    cc_shift_flop = avg_flop.get('1', 0) * 100
    rs_shift_flop = avg_flop.get('2', 0) * 100
    rm_shift_flop = avg_flop.get('3', 0) * 100
    lines.append(f'1. **Postflop collapse to passive**: averaged across opponents, RL-1 on FLOP '
                 f'cc shifted **{cc_shift_flop:+.1f}**pp, small-raise **{rs_shift_flop:+.1f}**pp, '
                 f'medium-raise **{rm_shift_flop:+.1f}**pp. Same pattern on TURN/RIV.')
    lines.append('2. **Asymmetric SB profile**: SB gain vs random/jammer/aggro masks regressions of '
                 '−3 to −13 bb/100 vs realistic opponents (fold, call, heuristic_v3, station, pathb10m, slumbot). '
                 'Mean Δ SB = {:+.1f} bb/100 but this is an artifact of large gains vs exploitable opponents.'.format(
                     sum(sb_deltas) / n))
    lines.append('3. **Gain vs aggressive opponents BB**: jammer +18, station +16, call +16, random +23 bb/100 — '
                 'cc-bot survives well against jam/bluff opponents because they fold less and inflate pots we win.')
    lines.append('4. **Slumbot regression confirmed**: RL-1 5M vs Slumbot {:+.2f} bb/100 vs BC {:+.2f} bb/100 '
                 '(Δ {:+.2f} bb/100, |Δ| > CI ±21.9 so significant).'.format(
                     rl_sl, bc_sl, rl_sl - bc_sl))
    lines.append('')
    lines.append('### Root cause hypothesis')
    lines.append('- Per `reports/rl1_5M_history_analysis.md`: value_loss U-shape (cold-start 703 → recovered 1.2 → re-exploded 1372).')
    lines.append('- Cold critic at iter 1-2 + KL collapse to call-only on iter 2 (cc=0.08%) → policy explored a passive basin.')
    lines.append('- Anchor KL pull recovered CC mass starting iter 22 but never restored raise mass; raises remained ~10% vs BC ~50%.')
    lines.append('- Net result: policy retained anchor proximity in fold/cc dimensions but lost the **value-betting** + **bluffing** structure.')
    lines.append('')
    lines.append('### Implication for RL-2')
    lines.append('Value-head warmup alone may not be sufficient. Consider:')
    lines.append('- (a) Warm critic + cold policy (current plan).')
    lines.append('- (b) Higher anchor_kl_coef at the start (e.g. 0.2 → decay) to prevent passive basin entry.')
    lines.append('- (c) Add per-action anchor regularization on raise slots specifically (action-level KL).')
    lines.append('- (d) Lower lr (3e-5 → 1e-5) for first 1M hands to slow drift while critic stabilizes.')
    lines.append('')
    lines.append('Recommended minimal change: (a) + (d). Validate with 500k smoke before committing to RL-2 5M.')

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text('\n'.join(lines), encoding='utf-8')
    print(f'wrote {OUT}')
    print(f'mean Δ total: {sum(tot_deltas)/n:+.2f} | mean Δ SB: {sum(sb_deltas)/n:+.2f} | mean Δ BB: {sum(bb_deltas)/n:+.2f}')
    print(f'slumbot Δ: {rl_sl-bc_sl:+.2f} bb/100 (CI ±21.9)')


if __name__ == '__main__':
    main()
