"""In-process heads-up bench between two policy callables via vec_game_state.

For Phase 2 evaluation. Plays N parallel HUNL games where each game has:
  - Hero at one seat (SB or BB alternating per game and per hand)
  - Opponent at the other seat
  - Hero's policy_id is fixed per bench; opponent's policy is configurable

Records hero-perspective stats over the full bench:
  - bb/100 overall + per-position
  - hero action mix by street
  - terminal breakdown (hero_fold / opp_fold / showdown / allin_runout)
  - per-session-equivalent CI estimate (chunked variance)

Output: JSON summary + MD report + manifest.

Usage:
  python internal_bench.py \
    --hero heuristic_v3 \
    --opponent scripted_aggro \
    --hands 1000 \
    --seed 42 \
    --out reports/phase2/internal/heuristic_v3_vs_aggro
"""
from __future__ import annotations
import argparse
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
sys.path.insert(0, str(REPO_ROOT / 'scripts' / 'alpha_holdem'))
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(THIS_DIR / 'common'))

from manifest import write_manifest, write_md_report
from vec_game_state import VecHUNLState, S_PRE
from scripted_policies import get_policy

VERSION = '0.1.0-skeleton'
NUM_ACTIONS = 9
BB_CHIPS = 100  # 1 BB = 100 chips in Slumbot/vec convention


def card_int_to_str(c: int) -> str:
    if c < 0:
        return None
    rank = '23456789TJQKA'[c // 4]
    suit = 'shdc'[c % 4]
    return rank + suit


def hole_for_seat(state: VecHUNLState, i: int, seat: int) -> list[str]:
    h = state.holes[i, seat]
    return [card_int_to_str(int(h[0])), card_int_to_str(int(h[1]))]


def board_for_game(state: VecHUNLState, i: int) -> list[str]:
    b = state.board[i]
    return [card_int_to_str(int(c)) for c in b if c >= 0]


def run_match(hero_name: str, opp_name: str, n_hands: int, *,
              seed: int = 42, parallel_games: int = 256,
              starting_stack: float = 200.0) -> dict:
    """Play `n_hands` hands. Hero is at `state.hero_player[i]`; opponent at the other seat.

    vec_game_state alternates `hero_player` deterministically per-hand on reset,
    so SB/BB exposure should be ~50/50 over many hands.

    Returns hero-perspective summary dict.
    """
    hero_fn = get_policy(hero_name)
    opp_fn = get_policy(opp_name)

    rng = np.random.default_rng(seed)
    state = VecHUNLState(N=parallel_games, effective_stack=starting_stack, seed=seed)
    state.reset_all()

    # Per-game accumulators
    hands_played = 0
    hero_chips_total = 0
    hero_chips_by_position = {0: 0, 1: 0}     # 0=BB role, 1=SB role
    hands_by_position = {0: 0, 1: 0}
    hero_action_counts_by_street = defaultdict(lambda: defaultdict(int))
    hero_position_in_current_hand = state.hero_player.copy()  # snapshot per hand
    terminal_counts = defaultdict(int)
    terminal_chips = defaultdict(int)
    last_hero_action_in_hand = ['' for _ in range(parallel_games)]
    last_hero_action_street = [0 for _ in range(parallel_games)]
    hands_progress_chips_record = []  # for CI estimation

    # Pre-allocate per-game arrays so we can vectorize where possible
    t0 = time.time()
    max_iters = n_hands * 20  # safety: bound steps even if hands very long
    it = 0
    while hands_played < n_hands and it < max_iters:
        it += 1
        cp_np = state.current_player.astype(np.int64)
        legal = state.legal_mask()
        to_call_np = state.to_call()

        # Per-game decision dispatch
        chosen = np.zeros(parallel_games, dtype=np.int64)
        for i in range(parallel_games):
            if state.is_done[i]:
                continue
            cur = int(cp_np[i])
            hero_seat = int(state.hero_player[i])
            is_hero_turn = (cur == hero_seat)
            client_pos = 1 if cur == 1 else 0  # vec_game_state seat 0=BB, 1=SB (matches Slumbot)
            hole = hole_for_seat(state, i, cur)
            board = board_for_game(state, i)
            st_dict = {
                'st': int(state.street[i]),
                'to_call': int(to_call_np[i]),
                'pot_before': int(state.pot[i]),
            }
            mask = legal[i].tolist()
            fn = hero_fn if is_hero_turn else opp_fn
            try:
                act = fn(hole, board, st_dict, client_pos, mask)
            except Exception as e:
                # Fallback: legal action
                act = next((s for s in range(9) if mask[s]), 0)
            chosen[i] = act

            if is_hero_turn:
                hero_action_counts_by_street[int(state.street[i])][act] += 1
                last_hero_action_in_hand[i] = ['f', 'cc', 'r33', 'r50', 'r67', 'r75', 'r1', 'r15', 'allin'][act]
                last_hero_action_street[i] = int(state.street[i])

        # Step all games
        # Snapshot pre-step state for terminal classification
        pre_step_hero_seat = state.hero_player.copy()
        state.step(chosen)

        # Finalize terminated hands
        if state.is_done.any():
            rewards = state.terminal_rewards()
            done_idx = np.where(state.is_done)[0]
            for i in done_idx:
                hero_seat = int(pre_step_hero_seat[i])
                hero_pos_label = hero_seat  # 0=BB, 1=SB
                r = float(rewards[i])
                hero_chips_total += r
                hero_chips_by_position[hero_pos_label] += r
                hands_by_position[hero_pos_label] += 1
                hands_played += 1
                hands_progress_chips_record.append(r)

                # Classify terminal
                # Use the last action that was taken on this hand
                last_action = chosen[i]
                last_who_hero = (cp_np[i] == hero_seat)  # who just acted
                if last_action == 0:  # fold
                    if last_who_hero:
                        terminal_counts['hero_fold'] += 1
                        terminal_chips['hero_fold'] += r
                    else:
                        terminal_counts['opp_fold'] += 1
                        terminal_chips['opp_fold'] += r
                elif int(state.street[i]) >= 3:
                    # Could be either showdown (reached river) or allin runout that resolved at river
                    terminal_counts['showdown'] += 1
                    terminal_chips['showdown'] += r
                elif last_action == 1:
                    # Call that ended the hand → likely allin-runout
                    terminal_counts['allin_runout'] += 1
                    terminal_chips['allin_runout'] += r
                else:
                    terminal_counts['other'] += 1
                    terminal_chips['other'] += r

                if hands_played >= n_hands:
                    break

            state.reset_done()

    elapsed = time.time() - t0

    # Aggregate metrics. NOTE: vec_game_state.terminal_rewards() already returns
    # values in BB units (1 BB = 1.0), NOT in chips. So we don't divide by BB_CHIPS.
    bb_per_hand = hero_chips_total / max(hands_played, 1)
    bb100 = bb_per_hand * 100
    sb_bb100 = (hero_chips_by_position[1] / max(hands_by_position[1], 1)) * 100
    bb_bb100 = (hero_chips_by_position[0] / max(hands_by_position[0], 1)) * 100

    # Action mix
    action_mix_by_street = {}
    for st, counts in hero_action_counts_by_street.items():
        total = sum(counts.values()) or 1
        action_mix_by_street[int(st)] = {int(s): counts.get(s, 0) / total for s in range(NUM_ACTIONS)}

    # CI95 estimate using per-hand std (BB-unit rewards)
    if hands_played > 1:
        arr = np.array(hands_progress_chips_record, dtype=np.float64)
        std_bb = float(arr.std(ddof=1))
        ci_bb100 = 1.96 * std_bb / math.sqrt(hands_played) * 100
    else:
        ci_bb100 = float('nan')

    return {
        'hero': hero_name,
        'opponent': opp_name,
        'n_hands': hands_played,
        'n_hands_sb_role': hands_by_position[1],
        'n_hands_bb_role': hands_by_position[0],
        'bb100': bb100,
        'sb_bb100': sb_bb100,
        'bb_bb100': bb_bb100,
        'ci_bb100': ci_bb100,
        'total_chips': hero_chips_total,
        'action_mix_by_street': action_mix_by_street,
        'terminal_counts': dict(terminal_counts),
        'terminal_chips': dict(terminal_chips),
        'elapsed_s': elapsed,
        'hands_per_sec': hands_played / max(elapsed, 1e-6),
        'parallel_games': parallel_games,
        'seed': seed,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--hero', required=True)
    p.add_argument('--opponent', required=True)
    p.add_argument('--hands', type=int, default=1000)
    p.add_argument('--parallel-games', type=int, default=256)
    p.add_argument('--starting-stack', type=float, default=200.0)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--out', required=True)
    args = p.parse_args()

    print(f'[bench] {args.hero} vs {args.opponent}, n={args.hands}, N={args.parallel_games}')
    result = run_match(args.hero, args.opponent, args.hands,
                       seed=args.seed, parallel_games=args.parallel_games,
                       starting_stack=args.starting_stack)
    print(f'  bb/100 = {result["bb100"]:+.2f} +/- {result["ci_bb100"]:.1f}')
    print(f'  SB: {result["sb_bb100"]:+.2f}  BB: {result["bb_bb100"]:+.2f}')
    print(f'  terminal: {result["terminal_counts"]}')
    print(f'  elapsed: {result["elapsed_s"]:.2f}s ({result["hands_per_sec"]:.0f} hands/sec)')

    out_dir = REPO_ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / 'result.json'
    json_path.write_text(json.dumps(result, indent=2), encoding='utf-8')

    write_manifest(out_dir / 'manifest.json',
                   script='phase2/internal_bench.py', version=VERSION,
                   args=vars(args), seed=args.seed,
                   outputs=[json_path],
                   extra={'elapsed_s': result['elapsed_s']})

    md_lines = [
        f'**Hero**: `{args.hero}`',
        f'**Opponent**: `{args.opponent}`',
        f'**Hands**: {result["n_hands"]:,}',
        '',
        f'**Overall**: {result["bb100"]:+.2f} bb/100 (CI95 ±{result["ci_bb100"]:.1f})',
        f'**As SB**: {result["sb_bb100"]:+.2f} bb/100 (n={result["n_hands_sb_role"]})',
        f'**As BB**: {result["bb_bb100"]:+.2f} bb/100 (n={result["n_hands_bb_role"]})',
        '',
        '### Terminal breakdown',
        ' | '.join(f'{k}={v}' for k, v in result['terminal_counts'].items()),
        '',
        '### Hero action mix by street',
        ' | '.join(f'st={k}: {v}' for k, v in result['action_mix_by_street'].items()),
        '',
        f'**Throughput**: {result["hands_per_sec"]:.0f} hands/sec',
    ]
    write_md_report(out_dir / 'report.md',
                    title=f'{args.hero} vs {args.opponent}',
                    sections=[('Summary', '\n'.join(md_lines))])
    print(f'\n[OK] {out_dir}')


if __name__ == '__main__':
    main()
