"""Per-iteration diagnostic of RL-1 5M training history.

Reads models/ppo/rl1_5M_run1/history.json and extracts:
- Value-loss trajectory (cold-start magnitude, decay)
- Action-mix evolution (when did each action collapse / recover)
- Anchor-KL drift vs anchor_kl_coef
- Approx KL early-stop frequency
- Policy entropy collapse

Emits a markdown report to reports/rl1_5M_history_analysis.md.
"""
from __future__ import annotations
import json
from pathlib import Path

HIST = Path('models/ppo/rl1_5M_run1/history.json')
OUT = Path('reports/rl1_5M_history_analysis.md')

ACTION_LABELS = {
    0: 'fold', 1: 'cc',
    2: 'r-s', 3: 'r-m', 4: 'r-l',
    5: 'r-xl', 6: 'r-xxl', 7: 'r-big',
    8: 'allin',
}


def fmt_mix(mix: dict) -> str:
    parts = []
    for k in sorted(mix.keys(), key=int):
        v = mix[k]
        if v >= 0.001:
            parts.append(f"{ACTION_LABELS[int(k)]}={v*100:.1f}%")
    return ' '.join(parts)


def main():
    hist = json.loads(HIST.read_text())
    n = len(hist)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append('# RL-1 5M history analysis\n')
    lines.append(f'Source: `{HIST}` ({n} iterations, 50k hands/iter)\n')

    # --- Value loss trajectory
    lines.append('## Value-head cold-start trajectory\n')
    lines.append('| iter | hands | value_loss | policy_loss | anchor_kl | approx_kl | early_stop |')
    lines.append('|---:|---:|---:|---:|---:|---:|:--:|')
    sample_iters = [0, 1, 2, 4, 9, 19, 29, 39, 49, 59, 69, 79, 89, 99]
    for i in sample_iters:
        if i >= n:
            continue
        r = hist[i]
        es = '*' if r.get('early_stopped') else ''
        lines.append(
            f"| {r['iter']} | {r['total_hands']:,} | {r['value_loss']:.2f} | "
            f"{r['policy_loss']:.3f} | {r['anchor_kl']:.3f} | {r['approx_kl']:.3f} | {es} |"
        )
    lines.append('')

    # --- Value-loss summary stats
    vlosses = [r['value_loss'] for r in hist]
    lines.append(f'- value_loss[1]  = {vlosses[0]:.2f}  (cold start)')
    lines.append(f'- value_loss[5]  = {vlosses[4]:.2f}')
    lines.append(f'- value_loss[10] = {vlosses[9]:.2f}')
    lines.append(f'- value_loss[50] = {vlosses[49]:.2f}')
    lines.append(f'- value_loss[100]= {vlosses[-1]:.2f}  (FINAL)')
    lines.append(f'- value_loss min = {min(vlosses):.2f} @ iter {vlosses.index(min(vlosses))+1}')
    lines.append(f'- value_loss max = {max(vlosses):.2f} @ iter {vlosses.index(max(vlosses))+1}')
    lines.append('')

    # --- Anchor KL trajectory
    lines.append('## Anchor-KL drift\n')
    ak = [r['anchor_kl'] for r in hist]
    lines.append(f'- anchor_kl[1]   = {ak[0]:.3f}')
    lines.append(f'- anchor_kl[5]   = {ak[4]:.3f}')
    lines.append(f'- anchor_kl[10]  = {ak[9]:.3f}')
    lines.append(f'- anchor_kl[50]  = {ak[49]:.3f}')
    lines.append(f'- anchor_kl[100] = {ak[-1]:.3f}  (FINAL)')
    lines.append(f'- anchor_kl max  = {max(ak):.3f} @ iter {ak.index(max(ak))+1}')
    lines.append('')

    # --- Action mix evolution
    lines.append('## Action-mix evolution\n')
    lines.append('Anchor (BC) reference mix is ~fold 60% / cc 22% / raise 18%. Watch for cc collapse to 0.')
    lines.append('')
    lines.append('| iter | hands | mix |')
    lines.append('|---:|---:|:--|')
    for i in sample_iters:
        if i >= n:
            continue
        r = hist[i]
        lines.append(f"| {r['iter']} | {r['total_hands']:,} | {fmt_mix(r['action_mix'])} |")
    lines.append('')

    # --- Detect CC collapse + recovery
    cc_curve = [r['action_mix'].get('1', 0.0) for r in hist]
    cc_collapsed = next((i for i, v in enumerate(cc_curve) if v < 0.01), None)
    cc_recovered = None
    if cc_collapsed is not None:
        for i in range(cc_collapsed, n):
            if cc_curve[i] > 0.05:
                cc_recovered = i
                break
    lines.append('### CC (check/call) collapse / recovery')
    if cc_collapsed is not None:
        lines.append(f'- CC < 1% first seen at iter {cc_collapsed+1} (hands {hist[cc_collapsed]["total_hands"]:,})')
    else:
        lines.append('- CC never collapsed below 1%')
    if cc_recovered is not None:
        lines.append(f'- CC > 5% recovered at iter {cc_recovered+1} (hands {hist[cc_recovered]["total_hands"]:,})')
    else:
        lines.append('- CC did NOT recover above 5% by end of training')
    lines.append(f'- CC final = {cc_curve[-1]*100:.1f}%')
    lines.append('')

    # --- Fold dominance check
    fold_curve = [r['action_mix'].get('0', 0.0) for r in hist]
    high_fold = [i for i, v in enumerate(fold_curve) if v > 0.92]
    lines.append('### Fold dominance')
    lines.append(f'- fold range: {min(fold_curve)*100:.1f}% .. {max(fold_curve)*100:.1f}%')
    if high_fold:
        lines.append(f'- fold > 92% at {len(high_fold)} iters (would have hit hard-stop): iters {[i+1 for i in high_fold[:10]]}')
    else:
        lines.append('- never crossed fold > 92% hard-stop threshold')
    lines.append('')

    # --- Entropy collapse
    ents = [r['entropy'] for r in hist]
    lines.append('## Policy entropy')
    lines.append(f'- entropy[1]   = {ents[0]:.4f}')
    lines.append(f'- entropy[10]  = {ents[9]:.4f}')
    lines.append(f'- entropy[50]  = {ents[49]:.4f}')
    lines.append(f'- entropy[100] = {ents[-1]:.4f}')
    lines.append(f'- entropy min  = {min(ents):.4f} @ iter {ents.index(min(ents))+1}')
    lines.append('')

    # --- Advantage stats sample
    lines.append('## Advantage normalization sanity')
    lines.append('A healthy training run has |adv.mean| ~ 0 and adv.std ~ 1 after normalize. Cold value head means raw adv.std is huge.')
    lines.append('')
    lines.append('| iter | adv.mean | adv.std | p5 | p95 |')
    lines.append('|---:|---:|---:|---:|---:|')
    for i in sample_iters:
        if i >= n:
            continue
        r = hist[i]['adv_stats']
        lines.append(f"| {hist[i]['iter']} | {r['mean']:.2f} | {r['std']:.2f} | {r['p5']:.2f} | {r['p95']:.2f} |")
    lines.append('')

    # --- Early-stop frequency
    es_count = sum(1 for r in hist if r.get('early_stopped'))
    lines.append('## PPO epoch early-stopping')
    lines.append(f'- early-stopped iterations: {es_count} / {n}')
    lines.append(f'- ppo_epochs configured: 2 → expect ~50% early-stop is normal; >70% suggests target_kl=0.03 too tight')
    lines.append('')

    # --- Diagnosis
    lines.append('## Diagnosis')
    lines.append('')
    lines.append(f'1. **Cold-start value head**: iter-1 value_loss = {vlosses[0]:.1f}, '
                 f'~{vlosses[0]/max(vlosses[-1],1):.0f}x the final value. ')
    lines.append(f'   Initial adv.std = {hist[0]["adv_stats"]["std"]:.1f} (vs healthy ~10-20) → garbage critic produced garbage advantages.')
    lines.append(f'2. **Anchor-KL spike**: jumped from {ak[0]:.2f} to {max(ak[:5]):.2f} in iters 2-5 → policy moved far from anchor before critic could stabilize.')
    if cc_collapsed is not None:
        lines.append(f'3. **CC collapse**: check/call dropped to ~0% by iter {cc_collapsed+1}, '
                     f'{"recovered" if cc_recovered else "never recovered"} → '
                     f'policy degraded due to bad advantage signal.')
    lines.append(f'4. **Recovery via anchor KL**: final anchor_kl = {ak[-1]:.2f}, still high vs target 0.03 — the anchor pull kept the policy from total divergence but did not restore CC mass.')
    lines.append('')

    # --- Recommendation
    lines.append('## Recommended next step')
    lines.append('')
    lines.append('**Value-head warmup** before policy updates:')
    lines.append('- Freeze policy head & shared trunk.')
    lines.append('- Collect K=200k-500k hands of pure rollout from anchor.')
    lines.append('- Train value head only with MSE on bootstrapped returns until value_loss < 50.')
    lines.append('- Then unfreeze policy and resume PPO with reset optimizer state.')
    lines.append('- Expected outcome: iter-1 value_loss < 100 (vs 703), iter-1 anchor_kl < 0.5 (vs 1.75).')

    OUT.write_text('\n'.join(lines), encoding='utf-8')
    print(f'wrote {OUT}')
    print(f'iters analyzed: {n}')
    print(f'value_loss cold-start: {vlosses[0]:.1f} → final {vlosses[-1]:.1f}')
    print(f'CC collapse: iter {cc_collapsed+1 if cc_collapsed is not None else "n/a"}, '
          f'recovered: {"iter "+str(cc_recovered+1) if cc_recovered is not None else "no"}')


if __name__ == '__main__':
    main()
