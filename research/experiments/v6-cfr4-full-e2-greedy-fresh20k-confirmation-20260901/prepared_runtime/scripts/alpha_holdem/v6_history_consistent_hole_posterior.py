#!/usr/bin/env python3
"""Enumerate opponent holes consistent with a frozen greedy action history."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
from pathlib import Path
import random
import sys

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState, Event
from alpha_holdem.v5_mirror_eval import init_model, read_checkpoint
from alpha_holdem.v6_bias_coordinate_search import parse_keyed
from alpha_holdem.v6_elo_eval import greedy_action


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def event_action(event: Event) -> str:
    return f'b{event.amount}' if event.kind == 'b' else event.kind


def deck_for_holes(
    *,
    candidate_seat: int,
    candidate_holes: tuple[int, int],
    opponent_holes: tuple[int, int],
    board: tuple[int, ...],
) -> tuple[int, ...]:
    holes = [None, None]
    holes[candidate_seat] = tuple(candidate_holes)
    holes[1 - candidate_seat] = tuple(opponent_holes)
    fixed_positions = {
        0: holes[0][0], 1: holes[0][1], 2: holes[1][0], 3: holes[1][1]
    }
    for index, card in enumerate(board):
        fixed_positions[51 - index] = card
    if len(set(fixed_positions.values())) != len(fixed_positions):
        raise ValueError('holes and board must be disjoint')
    remaining = iter(
        card for card in range(52) if card not in set(fixed_positions.values())
    )
    deck = tuple(
        fixed_positions[index] if index in fixed_positions else next(remaining)
        for index in range(52)
    )
    assert len(set(deck)) == 52
    return deck


def replay_history(
    reference: ChipState,
    *,
    candidate_seat: int,
    opponent_holes: tuple[int, int],
    opponent_model,
    opponent_style: str,
    device: str,
    require_opponent_match: bool,
) -> tuple[ChipState, bool]:
    deck = deck_for_holes(
        candidate_seat=candidate_seat,
        candidate_holes=reference.holes[candidate_seat],
        opponent_holes=opponent_holes,
        board=reference.board,
    )
    state = ChipState.new(deck)
    matched = True
    for event in reference.history:
        observed = event_action(event)
        if event.player == 1 - candidate_seat and require_opponent_match:
            predicted = greedy_action(
                opponent_model,
                state,
                observation_style=opponent_style,
                device=device,
            )
            if predicted != observed:
                matched = False
                break
        state = apply_incr(state, observed)
    return state, matched


def same_public_financial_state(left: ChipState, right: ChipState) -> bool:
    fields = (
        'initial', 'stacks', 'bets', 'pot', 'board', 'street', 'actor', 'pending',
        'last_full_raise', 'history', 'terminal', 'folded',
    )
    return all(getattr(left, field) == getattr(right, field) for field in fields)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument(
        '--candidate-observation-style', choices=('legacy_v4', 'v6'), required=True
    )
    parser.add_argument('--opponent', action='append', default=[], metavar='LABEL=PATH')
    parser.add_argument('--opponent-style', action='append', default=[], metavar='LABEL=STYLE')
    parser.add_argument('--quota-per-stratum', type=int, default=8)
    parser.add_argument('--trajectory-seed', type=int, required=True)
    parser.add_argument('--max-trajectory-hands', type=int, default=5000)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()

    opponents = parse_keyed(args.opponent, option='--opponent')
    styles = parse_keyed(args.opponent_style, option='--opponent-style')
    if not opponents or set(opponents) != set(styles):
        parser.error('opponent and opponent-style labels must match and be nonempty')
    if args.quota_per_stratum < 1 or args.max_trajectory_hands < 1:
        parser.error('quota and max trajectory hands must be positive')
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)

    candidate_path = args.candidate.resolve()
    candidate_sha = sha256_path(candidate_path)
    candidate = init_model(read_checkpoint(candidate_path), args.device).eval()
    opponent_models = {}
    opponent_metadata = {}
    for label, raw_path in opponents.items():
        path = Path(raw_path).resolve()
        opponent_models[label] = init_model(read_checkpoint(path), args.device).eval()
        opponent_metadata[label] = {
            'path': str(path),
            'sha256': sha256_path(path),
            'observation_style': styles[label],
        }

    rng = random.Random(args.trajectory_seed)
    quotas = {(seat, street): args.quota_per_stratum for seat in (0, 1) for street in range(4)}
    states = []
    labels = list(opponents)
    trajectory_hands = 0
    trajectory_decisions = 0
    while any(value > 0 for value in quotas.values()) and trajectory_hands < args.max_trajectory_hands:
        hand_index = trajectory_hands
        candidate_seat = hand_index % 2
        label = labels[hand_index % len(labels)]
        deck = list(range(52))
        rng.shuffle(deck)
        state = ChipState.new(deck)
        while not state.terminal:
            if state.actor == candidate_seat:
                key = (candidate_seat, state.street)
                if quotas[key] > 0:
                    states.append((hand_index, label, state, candidate_seat))
                    quotas[key] -= 1
                model = candidate
                style = args.candidate_observation_style
            else:
                model = opponent_models[label]
                style = styles[label]
            action = greedy_action(model, state, observation_style=style, device=args.device)
            state = apply_incr(state, action)
            trajectory_decisions += 1
        trajectory_hands += 1
    if any(value > 0 for value in quotas.values()):
        raise RuntimeError(f'failed to fill state quotas: {quotas}')

    rows_path = args.out_dir / 'posterior_rows.jsonl'
    support_counts = []
    by_stratum_counts = {(seat, street): [] for seat in (0, 1) for street in range(4)}
    total_hole_candidates = 0
    total_history_checks = 0
    for row_index, (hand_index, label, reference, candidate_seat) in enumerate(states):
        excluded = set(reference.holes[candidate_seat]) | set(reference.board)
        available = [card for card in range(52) if card not in excluded]
        accepted = []
        true_holes = tuple(sorted(reference.holes[1 - candidate_seat]))
        for hole_pair in combinations(available, 2):
            total_hole_candidates += 1
            replayed, matched = replay_history(
                reference,
                candidate_seat=candidate_seat,
                opponent_holes=hole_pair,
                opponent_model=opponent_models[label],
                opponent_style=styles[label],
                device=args.device,
                require_opponent_match=True,
            )
            total_history_checks += sum(
                event.player == 1 - candidate_seat for event in reference.history
            )
            if matched:
                if not same_public_financial_state(reference, replayed):
                    raise RuntimeError('matched replay changed public/financial state')
                accepted.append(list(hole_pair))
        if list(true_holes) not in accepted:
            raise RuntimeError('true trajectory opponent holes missing from posterior support')
        support = len(accepted)
        support_counts.append(support)
        by_stratum_counts[(candidate_seat, reference.street)].append(support)
        row = {
            'row_index': row_index,
            'trajectory_hand_index': hand_index,
            'opponent': label,
            'candidate_seat': candidate_seat,
            'street': reference.street,
            'candidate_holes': list(reference.holes[candidate_seat]),
            'board': list(reference.board),
            'history': [asdict(event) for event in reference.history],
            'true_opponent_holes': list(true_holes),
            'available_hole_combinations': len(available) * (len(available) - 1) // 2,
            'accepted_hole_combinations': support,
            'accepted_opponent_holes': accepted,
        }
        with rows_path.open('a', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(row, sort_keys=True) + '\n')

    by_stratum = {
        f'seat{seat}_street{street}': {
            'rows': len(values),
            'min_support': int(min(values)),
            'median_support': float(np.median(values)),
            'mean_support': float(np.mean(values)),
        }
        for (seat, street), values in by_stratum_counts.items()
    }
    rows_at_least_16 = sum(value >= 16 for value in support_counts)
    gate = {
        'true_holes_present_every_row': True,
        'all_public_financial_replays_exact': True,
        'at_least_95pct_rows_support16': rows_at_least_16 / len(support_counts) >= 0.95,
        'overall_median_support_at_least64': float(np.median(support_counts)) >= 64.0,
        'every_stratum_median_support_at_least32': all(
            row['median_support'] >= 32.0 for row in by_stratum.values()
        ),
    }
    output = {
        'schema': 'cardpilot.v6_history_consistent_hole_posterior.v1',
        'status': 'COMPLETED',
        'candidate': str(candidate_path),
        'candidate_sha256': candidate_sha,
        'candidate_observation_style': args.candidate_observation_style,
        'opponents': opponent_metadata,
        'rows': len(states),
        'quota_per_stratum': args.quota_per_stratum,
        'trajectory_hands': trajectory_hands,
        'trajectory_decisions': trajectory_decisions,
        'total_hole_candidates': total_hole_candidates,
        'total_history_checks': total_history_checks,
        'overall_min_support': int(min(support_counts)),
        'overall_median_support': float(np.median(support_counts)),
        'overall_mean_support': float(np.mean(support_counts)),
        'rows_with_support_at_least16': rows_at_least_16,
        'by_stratum': by_stratum,
        'gate_components': gate,
        'posterior_target_generation_admitted': all(gate.values()),
        'rows_sha256': sha256_path(rows_path),
        'completed_at': datetime.now(timezone.utc).isoformat(),
        'command': [sys.executable, *sys.argv],
    }
    if sha256_path(candidate_path) != candidate_sha:
        raise RuntimeError('candidate checkpoint changed')
    for label, metadata in opponent_metadata.items():
        if sha256_path(Path(metadata['path'])) != metadata['sha256']:
            raise RuntimeError(f'opponent checkpoint changed: {label}')
    (args.out_dir / 'summary.json').write_text(
        json.dumps(output, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    print(json.dumps({
        'rows': output['rows'],
        'trajectory_hands': trajectory_hands,
        'total_hole_candidates': total_hole_candidates,
        'overall_min_support': output['overall_min_support'],
        'overall_median_support': output['overall_median_support'],
        'gate_components': gate,
        'posterior_target_generation_admitted': output['posterior_target_generation_admitted'],
    }, sort_keys=True))


if __name__ == '__main__':
    main()
