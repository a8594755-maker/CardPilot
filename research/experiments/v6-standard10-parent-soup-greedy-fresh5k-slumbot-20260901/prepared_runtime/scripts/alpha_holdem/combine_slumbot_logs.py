#!/usr/bin/env python3
"""
Combine multiple Slumbot benchmark log files into a single statistic.
Usage: python combine_slumbot_logs.py log1.log log2.log ...
"""
import sys
import re
import math


def parse_hand_rewards(log_path):
    """Extract per-hand rewards from a Slumbot eval log."""
    rewards = []
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # The log shows running totals at every 100 hands.
    # We need per-hand rewards but they're not logged individually.
    # Instead, extract final cumulative results and total hands.
    m_total = re.search(r'Total:\s+([+-]?\d+) chips', content)
    m_hands = re.search(r'Slumbot \((\d+,?\d*) hands\)', content)
    m_avg = re.search(r'Avg:\s+([+-]?\d+\.\d+) BB/hand', content)
    m_std = None  # not directly given

    if not m_total or not m_hands:
        return None

    total_chips = int(m_total.group(1))
    hands = int(m_hands.group(1).replace(',', ''))
    avg_bb = float(m_avg.group(1))

    # Parse interim avg checkpoints to estimate variance
    interim = re.findall(r'\[\s*(\d+)\]\s+avg\s+([+-]?\d+\.\d+)\s+BB/hand', content)
    interim_pts = [(int(n), float(v)) for n, v in interim]

    return {
        'log': log_path,
        'hands': hands,
        'total_chips': total_chips,
        'avg_bb': avg_bb,
        'interim': interim_pts,
    }


def main():
    if len(sys.argv) < 2:
        print('Usage: combine_slumbot_logs.py log1 log2 ...')
        sys.exit(1)

    results = []
    for path in sys.argv[1:]:
        r = parse_hand_rewards(path)
        if r:
            results.append(r)

    if not results:
        print('No valid logs parsed')
        sys.exit(1)

    print(f'Combined results from {len(results)} sessions:')
    total_hands = 0
    total_chips = 0
    for r in results:
        print(f'  {r["log"]}: {r["hands"]:,} hands, {r["avg_bb"]:+.4f} BB/hand, total {r["total_chips"]:+d} chips')
        total_hands += r['hands']
        total_chips += r['total_chips']

    if total_hands == 0:
        print('No hands')
        sys.exit(1)

    avg_chips = total_chips / total_hands
    avg_bb = avg_chips / 100  # 100 chips per BB
    bb100 = avg_bb * 100
    mbb = avg_bb * 1000

    # Estimate variance from per-session avgs (rough)
    bb_per_session = [r['avg_bb'] for r in results]
    if len(bb_per_session) > 1:
        # variance of session means * sessions ≈ within-session variance / hands
        # Better: use overall std estimate
        # Approx using Welford: weight by hands per session (all 5K = equal weight)
        n_sessions = len(bb_per_session)
        mean_session = sum(bb_per_session) / n_sessions
        var_session = sum((x - mean_session) ** 2 for x in bb_per_session) / max(n_sessions - 1, 1)
        # Total CI approx: per-hand std ~ session_std * sqrt(hands_per_session)
        # But this is a rough bound — use it
        # Simpler: pooled SE = sqrt(sum of session SEs squared / n^2)... but we don't have SEs
        # For our purpose: if we assume per-hand std is similar to single 2K run (~70 BB/100),
        # then 20K hands CI = 70 / sqrt(10) = 22.1 bb/100
    else:
        var_session = 0

    print('=' * 60)
    print(f'TOTAL: {total_hands:,} hands')
    print(f'  Avg:        {avg_bb:+.4f} BB/hand')
    print(f'  bb/100:     {bb100:+.2f}')
    print(f'  mbb/hand:   {mbb:+.1f}')
    print(f'  Total:      {total_chips:+,d} chips ({total_chips/100:+.1f} BB)')
    print(f'  Sessions:   {len(results)}')
    print('=' * 60)
    if total_hands >= 10000:
        # Rough CI scaling from 2K → N hands
        ci_2k = 700  # mbb at 2000 hands typical
        scale = math.sqrt(2000.0 / total_hands)
        ci_est = ci_2k * scale
        print(f'  Estimated CI (rough): ±{ci_est:.0f} mbb = ±{ci_est/10:.1f} bb/100')


if __name__ == '__main__':
    main()
