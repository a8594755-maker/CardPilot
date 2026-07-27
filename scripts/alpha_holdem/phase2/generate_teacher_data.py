"""Phase 2 teacher data generator.

Generates (state, legal_mask, teacher_action) supervised examples by simulating
HUNL hands via vec_game_state and querying the teacher policy at each hero
decision point.

Output: JSONL (skeleton; Parquet later for scale). Each line is one decision:
  {
    "card_obs":       <flattened (6,4,13) one-hot>,
    "action_obs":     <flattened (25,4,5) one-hot>,
    "extra_obs":      [stack_hero_norm, stack_opp_norm],
    "legal_mask":     <9-vector>,
    "client_pos":     0 (BB) or 1 (SB),
    "street":         0/1/2/3,
    "to_call":        chips,
    "pot_before":     chips,
    "stack_remaining": chips,
    "hero_hole":      ["As","Kd"],
    "board":          ["Qh","7d","2c", ...],
    "opponent_type":  "self" / "random" / "call" / "fold" / etc.
    "teacher_action": 0..8 (chosen action slot)
  }

Skeleton smoke: 1000 examples, single opponent mix.

Usage:
  python generate_teacher_data.py \
    --teacher heuristic_v3 \
    --target-examples 1000 \
    --opponent-mix "self=1.0" \
    --workers 1 \
    --seed 42 \
    --out data/phase2/teacher_v3_smoke.jsonl
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT / 'scripts' / 'alpha_holdem'))
sys.path.insert(0, str(THIS_DIR / 'common'))

from manifest import write_manifest, write_md_report
from vec_game_state import VecHUNLState, S_PRE
from train_vec import encode_obs_batched

VERSION = '0.1.0-skeleton'

# Constants for HUNL chips (Slumbot convention used throughout)
BB_CHIPS = 100
SB_CHIPS = 50


def card_int_to_str(c: int) -> str:
    """Convert vec_game_state's 0..51 card index to 'Rs' format (rank+suit)."""
    if c < 0:
        return None
    rank = '23456789TJQKA'[c // 4]
    suit = 'shdc'[c % 4]
    return rank + suit


def hole_cards_for_player(state: VecHUNLState, i: int, pos: int) -> list[str]:
    """Return hero hole cards for game i, player at position pos, as ['As','Kd']."""
    h = state.holes[i, pos]
    return [card_int_to_str(int(h[0])), card_int_to_str(int(h[1]))]


def board_cards(state: VecHUNLState, i: int) -> list[str]:
    """Return community cards on the table for game i (only revealed cards)."""
    b = state.board[i]
    return [card_int_to_str(int(c)) for c in b if c >= 0]


def query_teacher(teacher_name: str, hole_cards, board, st_dict, client_pos, legal_mask):
    """Query the teacher policy. Returns action slot 0..8."""
    if teacher_name == 'heuristic_v3':
        from heuristic_policy_v3 import choose_action
    elif teacher_name == 'heuristic_v3_1':
        from heuristic_policy_v3_1 import choose_action
    elif teacher_name == 'heuristic_v2':
        from heuristic_policy_v2 import choose_action
    elif teacher_name == 'heuristic':
        from heuristic_policy import choose_action
    else:
        raise ValueError(f'Unknown teacher: {teacher_name}')
    return choose_action(hole_cards, board, st_dict, client_pos, legal_mask)


def parse_opponent_mix(s: str) -> dict[str, float]:
    """Parse 'self=0.35,random=0.10,...' into a dict, normalized to sum=1."""
    parts = [p.strip() for p in s.split(',') if p.strip()]
    mix = {}
    for p in parts:
        k, _, v = p.partition('=')
        mix[k.strip()] = float(v)
    total = sum(mix.values())
    if total <= 0:
        raise ValueError('opponent mix sums to 0')
    return {k: v / total for k, v in mix.items()}


def pick_opponent(mix: dict[str, float], rng: np.random.Generator) -> str:
    """Sample one opponent type from the mix."""
    keys = list(mix.keys())
    probs = np.array([mix[k] for k in keys])
    return keys[int(rng.choice(len(keys), p=probs))]


def opponent_action(opp_name: str, hole_cards, board, st_dict, client_pos,
                    legal_mask, teacher_choice_fn, rng):
    """Return action slot for the opponent on its turn."""
    if opp_name == 'self':
        return teacher_choice_fn(hole_cards, board, st_dict, client_pos, legal_mask)
    if opp_name == 'fold':
        for s in (0, 1):
            if legal_mask[s]:
                return s
        return 1
    if opp_name == 'call':
        return 1 if legal_mask[1] else 0
    if opp_name == 'random':
        legal_idx = [s for s in range(9) if legal_mask[s]]
        return int(rng.choice(legal_idx)) if legal_idx else 0
    # TODO Day -2: scripted_aggro, scripted_station, scripted_jammer, pathb10m, v4, slumbot_proxy
    return 1 if legal_mask[1] else 0  # fallback: call


def simulate_and_dump(teacher_name: str, opponent_mix: dict[str, float],
                     target_examples: int, out_path: Path, *,
                     N: int = 64, seed: int = 42) -> dict:
    """Roll out N parallel games until we collect target_examples hero decisions.
    Hero is the teacher; opponent is sampled per-hand from opponent_mix.

    Each record gets `hand_id` so downstream split-by-hand is possible (no
    per-decision leakage across train/val).
    """
    rng = np.random.default_rng(seed)
    state = VecHUNLState(N=N, effective_stack=200.0, seed=seed)
    state.reset_all()

    # Per-game opponent assignment, refreshed each hand
    per_game_opp = [pick_opponent(opponent_mix, rng) for _ in range(N)]
    # Per-game current hand_id (unique global hand identifier)
    next_hand_id = 0
    per_game_hand_id = list(range(N))
    next_hand_id = N

    teacher_choice_fn = lambda h, b, sd, cp, lm: query_teacher(teacher_name, h, b, sd, cp, lm)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fp = out_path.open('w', encoding='utf-8')

    examples_written = 0
    hands_played = 0
    # Action histograms for the manifest
    overall_hist = [0] * 9
    by_position_hist = {0: [0] * 9, 1: [0] * 9}
    by_street_hist = {0: [0] * 9, 1: [0] * 9, 2: [0] * 9, 3: [0] * 9}
    t0 = time.time()

    while examples_written < target_examples:
        card_np, action_np, extra_np, mask_np = encode_obs_batched(state)
        cp_np = state.current_player.astype(np.int64)
        # In vec_game_state, hero_player is a constant per game; current_player alternates
        is_hero_turn = (cp_np == state.hero_player.astype(np.int64))
        # to_call is a METHOD, not array
        to_call_np = state.to_call()

        chosen_actions = np.zeros(N, dtype=np.int64)
        for i in range(N):
            if state.is_done[i]:
                continue
            client_pos = int(state.hero_player[i]) if is_hero_turn[i] else int(1 - state.hero_player[i])
            hole = hole_cards_for_player(state, i, int(cp_np[i]))
            board = board_cards(state, i)
            st_dict = {
                'st': int(state.street[i]),
                'to_call': int(to_call_np[i]),
                'pot_before': int(state.pot[i]),
            }
            mask = mask_np[i].tolist()
            if is_hero_turn[i]:
                # Teacher decision
                act = teacher_choice_fn(hole, board, st_dict, client_pos, mask)
                # Record example
                record = {
                    'hand_id': per_game_hand_id[i],
                    'card_obs': card_np[i].astype(np.float32).flatten().tolist(),
                    'action_obs': action_np[i].astype(np.float32).flatten().tolist(),
                    'extra_obs': extra_np[i].astype(np.float32).tolist(),
                    'legal_mask': mask,
                    'client_pos': client_pos,
                    'street': int(state.street[i]),
                    'to_call': st_dict['to_call'],
                    'pot_before': st_dict['pot_before'],
                    'hero_hole': hole,
                    'board': board,
                    'opponent_type': per_game_opp[i],
                    'teacher_action': int(act),
                }
                fp.write(json.dumps(record) + '\n')
                examples_written += 1
                overall_hist[act] += 1
                by_position_hist[client_pos][act] += 1
                by_street_hist[int(state.street[i])][act] += 1
                chosen_actions[i] = act
                if examples_written >= target_examples:
                    break
            else:
                chosen_actions[i] = opponent_action(per_game_opp[i], hole, board, st_dict,
                                                     client_pos, mask, teacher_choice_fn, rng)

        if examples_written >= target_examples:
            break

        # Step all games
        state.step(chosen_actions)
        if state.is_done.any():
            done_rows = np.where(state.is_done)[0]
            hands_played += len(done_rows)
            # New opponent assignment + new hand_id for the newly-reset hands
            for i in done_rows:
                per_game_opp[i] = pick_opponent(opponent_mix, rng)
                per_game_hand_id[i] = next_hand_id
                next_hand_id += 1
            state.reset_done()

    fp.close()
    elapsed = time.time() - t0
    return {
        'examples_written': examples_written,
        'hands_played': hands_played,
        'total_unique_hand_ids': next_hand_id,
        'elapsed_s': elapsed,
        'examples_per_sec': examples_written / max(elapsed, 1e-6),
        'overall_action_hist': overall_hist,
        'by_position_action_hist': {str(k): v for k, v in by_position_hist.items()},
        'by_street_action_hist': {str(k): v for k, v in by_street_hist.items()},
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--teacher', default='heuristic_v3',
                   choices=['heuristic_v3', 'heuristic_v3_1', 'heuristic_v2', 'heuristic'])
    p.add_argument('--target-examples', type=int, default=1000,
                   help='Stop after this many supervised examples')
    p.add_argument('--opponent-mix', default='self=1.0',
                   help='Comma-separated opp=weight, e.g. self=0.35,random=0.10,call=0.10')
    p.add_argument('--workers', type=int, default=1, help='Skeleton: single-worker only')
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--parallel-games', type=int, default=64, help='vec_game_state N')
    p.add_argument('--out', required=True, help='Output JSONL path')
    args = p.parse_args()

    out_path = REPO_ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    opponent_mix = parse_opponent_mix(args.opponent_mix)
    print(f'Teacher: {args.teacher}')
    print(f'Opponent mix (normalized): {opponent_mix}')
    print(f'Target examples: {args.target_examples}')
    print(f'Output: {out_path}')

    stats = simulate_and_dump(args.teacher, opponent_mix, args.target_examples,
                              out_path, N=args.parallel_games, seed=args.seed)
    print(f'Stats: {stats}')

    write_manifest(out_path.with_suffix('.manifest.json'),
                   script='phase2/generate_teacher_data.py', version=VERSION,
                   args=vars(args), seed=args.seed,
                   outputs=[out_path],
                   extra={**stats, 'opponent_mix_normalized': opponent_mix})

    md_summary = [
        f'Teacher: `{args.teacher}`',
        f'Opponent mix: `{opponent_mix}`',
        f'Examples: {stats["examples_written"]:,}',
        f'Hands played: {stats["hands_played"]:,}',
        f'Unique hand_ids: {stats["total_unique_hand_ids"]:,}',
        f'Throughput: {stats["examples_per_sec"]:.1f} examples/sec',
        f'Elapsed: {stats["elapsed_s"]:.1f}s',
    ]
    total = max(stats['examples_written'], 1)
    md_hist = ['### Overall action histogram (slot 0..8)']
    md_hist.append(f'| slot | {" | ".join(str(s) for s in range(9))} |')
    md_hist.append(f'| --- | {" | ".join("---" for _ in range(9))} |')
    md_hist.append(f'| count | {" | ".join(str(stats["overall_action_hist"][s]) for s in range(9))} |')
    overall = stats['overall_action_hist']
    md_hist.append(f'| pct | {" | ".join(f"{100*overall[s]/total:.1f}%" for s in range(9))} |')
    md_hist.append('')
    md_hist.append('### By position (0=BB, 1=SB)')
    for pos in ('0', '1'):
        bp = stats['by_position_action_hist'][pos]
        tot = max(sum(bp), 1)
        md_hist.append(f'- pos={pos} (n={tot}): ' + ' '.join(f'{s}={100*bp[s]/tot:.1f}%' for s in range(9)))
    md_hist.append('')
    md_hist.append('### By street')
    for st in ('0', '1', '2', '3'):
        bs = stats['by_street_action_hist'][st]
        tot = max(sum(bs), 1)
        st_name = ['preflop', 'flop', 'turn', 'river'][int(st)]
        md_hist.append(f'- {st_name} (n={tot}): ' + ' '.join(f'{s}={100*bs[s]/tot:.1f}%' for s in range(9)))

    write_md_report(out_path.with_suffix('.report.md'),
                    title=f'Teacher data generation ({args.teacher})',
                    sections=[('Summary', '\n\n'.join(md_summary)),
                              ('Action histograms', '\n'.join(md_hist))])

    print(f'\n[OK] {stats["examples_written"]} examples -> {out_path}')


if __name__ == '__main__':
    main()
