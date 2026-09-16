#!/usr/bin/env python3
"""Audit broad exact-v6 all-legal-action target reliability before training."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import sys

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.policy_contract_v6 import action_table, apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v5_mirror_eval import init_model, read_checkpoint
from alpha_holdem.v6_bias_coordinate_search import parse_keyed
from alpha_holdem.v6_elo_eval import greedy_action


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def resample_future_deck(state: ChipState, rng: random.Random) -> tuple[int, ...]:
    fixed_positions = {index: card for index, card in enumerate(state.deck[:4])}
    for board_index, card in enumerate(state.board):
        fixed_positions[51 - board_index] = card
    fixed_cards = set(fixed_positions.values())
    remaining = [card for card in range(52) if card not in fixed_cards]
    rng.shuffle(remaining)
    iterator = iter(remaining)
    deck = tuple(
        fixed_positions[index] if index in fixed_positions else next(iterator)
        for index in range(52)
    )
    assert len(set(deck)) == 52
    assert deck[:4] == state.deck[:4]
    assert tuple(deck[-index - 1] for index in range(len(state.board))) == state.board
    return deck


def select_best_slot(
    means: dict[int, float], *, source_slot: int
) -> int:
    if source_slot not in means:
        raise ValueError('source slot must be legal')
    # Prefer the frozen source action on an exact utility tie.
    return max(means, key=lambda slot: (means[slot], slot == source_slot, -slot))


def mean_ci(values: list[float]) -> tuple[float, float]:
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean()) if len(array) else 0.0
    std = float(array.std(ddof=1)) if len(array) > 1 else 0.0
    half = 1.96 * std / math.sqrt(max(len(array), 1))
    return mean, half


def model_slot_and_action(model, state, *, observation_style: str, device: str):
    from alpha_holdem.v6_elo_eval import _observation

    obs, table = _observation(model, state, observation_style)
    tensors = [
        torch.as_tensor(obs[key], dtype=torch.float32, device=device).unsqueeze(0)
        for key in ('card_info', 'action_info', 'extra_info', 'legal_mask')
    ]
    with torch.no_grad():
        logits, _ = model(*tensors)
    values = logits[0].detach().cpu().numpy().astype(np.float64)
    legal = np.flatnonzero(obs['legal_mask'])
    slot = int(legal[int(np.argmax(values[legal]))])
    return slot, table, [int(value) for value in legal]


def rollout_branch(
    state: ChipState,
    first_action: str,
    *,
    candidate,
    opponent,
    candidate_seat: int,
    candidate_style: str,
    opponent_style: str,
    device: str,
) -> tuple[float, int]:
    current = apply_incr(state, first_action)
    decisions = 0
    while not current.terminal:
        is_candidate = current.actor == candidate_seat
        action = greedy_action(
            candidate if is_candidate else opponent,
            current,
            observation_style=candidate_style if is_candidate else opponent_style,
            device=device,
        )
        current = apply_incr(current, action)
        decisions += 1
    return float(current.payoffs()[candidate_seat]) / 100.0, decisions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument(
        '--candidate-observation-style', choices=('legacy_v4', 'v6'), required=True
    )
    parser.add_argument('--opponent', action='append', default=[], metavar='LABEL=PATH')
    parser.add_argument('--opponent-style', action='append', default=[], metavar='LABEL=STYLE')
    parser.add_argument('--quota-per-stratum', type=int, default=32)
    parser.add_argument('--dev-runouts', type=int, default=8)
    parser.add_argument('--confirm-runouts', type=int, default=8)
    parser.add_argument('--trajectory-seed', type=int, required=True)
    parser.add_argument('--branch-seed', type=int, required=True)
    parser.add_argument('--max-trajectory-hands', type=int, default=5000)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()

    opponents = parse_keyed(args.opponent, option='--opponent')
    styles = parse_keyed(args.opponent_style, option='--opponent-style')
    if not opponents or set(opponents) != set(styles):
        parser.error('opponent and opponent-style labels must match and be nonempty')
    if any(style not in {'legacy_v4', 'v6'} for style in styles.values()):
        parser.error('opponent styles must be legacy_v4 or v6')
    if min(args.quota_per_stratum, args.dev_runouts, args.confirm_runouts) < 1:
        parser.error('quota and runout counts must be positive')
    if args.max_trajectory_hands < 1:
        parser.error('max trajectory hands must be positive')
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

    trajectory_rng = random.Random(args.trajectory_seed)
    quotas = {(seat, street): args.quota_per_stratum for seat in (0, 1) for street in range(4)}
    states: list[tuple[int, str, ChipState, int]] = []
    trajectory_hands = 0
    trajectory_decisions = 0
    opponent_labels = list(opponents)
    while any(value > 0 for value in quotas.values()) and trajectory_hands < args.max_trajectory_hands:
        hand_index = trajectory_hands
        candidate_seat = hand_index % 2
        opponent_label = opponent_labels[hand_index % len(opponent_labels)]
        opponent = opponent_models[opponent_label]
        deck = list(range(52))
        trajectory_rng.shuffle(deck)
        state = ChipState.new(deck)
        while not state.terminal:
            if state.actor == candidate_seat:
                key = (candidate_seat, state.street)
                if quotas[key] > 0:
                    _, _, legal = model_slot_and_action(
                        candidate,
                        state,
                        observation_style=args.candidate_observation_style,
                        device=args.device,
                    )
                    states.append((hand_index, opponent_label, state, candidate_seat))
                    quotas[key] -= 1
                action = greedy_action(
                    candidate,
                    state,
                    observation_style=args.candidate_observation_style,
                    device=args.device,
                )
            else:
                action = greedy_action(
                    opponent,
                    state,
                    observation_style=styles[opponent_label],
                    device=args.device,
                )
            state = apply_incr(state, action)
            trajectory_decisions += 1
        trajectory_hands += 1
    if any(value > 0 for value in quotas.values()):
        raise RuntimeError(f'failed to fill state quotas: {quotas}')

    branch_rng = random.Random(args.branch_seed)
    rows_path = args.out_dir / 'rows.jsonl'
    row_summaries = []
    continuation_rollouts = 0
    continuation_decisions = 0
    for row_index, (hand_index, opponent_label, state, candidate_seat) in enumerate(states):
        source_slot, table, legal_slots = model_slot_and_action(
            candidate,
            state,
            observation_style=args.candidate_observation_style,
            device=args.device,
        )
        runout_count = args.dev_runouts + args.confirm_runouts
        decks = [resample_future_deck(state, branch_rng) for _ in range(runout_count)]
        outcomes = {slot: [] for slot in legal_slots}
        for slot in legal_slots:
            for deck in decks:
                value, decisions = rollout_branch(
                    replace(state, deck=deck),
                    table[slot],
                    candidate=candidate,
                    opponent=opponent_models[opponent_label],
                    candidate_seat=candidate_seat,
                    candidate_style=args.candidate_observation_style,
                    opponent_style=styles[opponent_label],
                    device=args.device,
                )
                outcomes[slot].append(value)
                continuation_rollouts += 1
                continuation_decisions += decisions
        dev_means = {
            slot: float(np.mean(values[:args.dev_runouts]))
            for slot, values in outcomes.items()
        }
        confirm_means = {
            slot: float(np.mean(values[args.dev_runouts:]))
            for slot, values in outcomes.items()
        }
        dev_slot = select_best_slot(dev_means, source_slot=source_slot)
        confirm_slot = select_best_slot(confirm_means, source_slot=source_slot)
        confirm_delta = confirm_means[dev_slot] - confirm_means[source_slot]
        row = {
            'row_index': row_index,
            'trajectory_hand_index': hand_index,
            'opponent': opponent_label,
            'candidate_seat': candidate_seat,
            'street': state.street,
            'state': asdict(state),
            'source_slot': source_slot,
            'legal_slots': legal_slots,
            'physical_actions': {str(slot): table[slot] for slot in legal_slots},
            'dev_means_bb': {str(slot): value for slot, value in dev_means.items()},
            'confirm_means_bb': {str(slot): value for slot, value in confirm_means.items()},
            'all_outcomes_bb': {str(slot): values for slot, values in outcomes.items()},
            'dev_selected_slot': dev_slot,
            'confirm_selected_slot': confirm_slot,
            'dev_confirm_agree': dev_slot == confirm_slot,
            'confirm_selected_minus_source_bb': confirm_delta,
            'new_allin': dev_slot == 8 and source_slot != 8,
        }
        with rows_path.open('a', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(row, sort_keys=True) + '\n')
        row_summaries.append(row)

    by_stratum = {}
    for seat in (0, 1):
        for street in range(4):
            selected = [
                row for row in row_summaries
                if row['candidate_seat'] == seat and row['street'] == street
            ]
            deltas = [row['confirm_selected_minus_source_bb'] for row in selected]
            mean, half = mean_ci(deltas)
            by_stratum[f'seat{seat}_street{street}'] = {
                'rows': len(selected),
                'agreement': float(np.mean([row['dev_confirm_agree'] for row in selected])),
                'confirm_delta_bb': mean,
                'confirm_delta_ci95_bb': half,
                'new_allins': sum(row['new_allin'] for row in selected),
            }
    all_deltas = [row['confirm_selected_minus_source_bb'] for row in row_summaries]
    overall_mean, overall_half = mean_ci(all_deltas)
    agreement = float(np.mean([row['dev_confirm_agree'] for row in row_summaries]))
    gate = {
        'overall_agreement_at_least_0_80': agreement >= 0.80,
        'every_stratum_agreement_at_least_0_70': all(
            row['agreement'] >= 0.70 for row in by_stratum.values()
        ),
        'confirm_delta_lcb_positive': overall_mean - overall_half > 0.0,
        'no_stratum_confirm_delta_negative': all(
            row['confirm_delta_bb'] >= 0.0 for row in by_stratum.values()
        ),
        'new_allin_fraction_at_most_0_05': (
            sum(row['new_allin'] for row in row_summaries) / len(row_summaries) <= 0.05
        ),
    }
    output = {
        'schema': 'cardpilot.v6_counterfactual_target_reliability.v1',
        'status': 'COMPLETED',
        'candidate': str(candidate_path),
        'candidate_sha256': candidate_sha,
        'candidate_observation_style': args.candidate_observation_style,
        'opponents': opponent_metadata,
        'quota_per_stratum': args.quota_per_stratum,
        'rows': len(row_summaries),
        'trajectory_hands': trajectory_hands,
        'trajectory_decisions': trajectory_decisions,
        'dev_runouts': args.dev_runouts,
        'confirm_runouts': args.confirm_runouts,
        'continuation_rollouts': continuation_rollouts,
        'continuation_decisions': continuation_decisions,
        'overall_dev_confirm_agreement': agreement,
        'overall_confirm_selected_minus_source_bb': overall_mean,
        'overall_confirm_delta_ci95_bb': overall_half,
        'new_allins': sum(row['new_allin'] for row in row_summaries),
        'by_stratum': by_stratum,
        'gate_components': gate,
        'training_admitted': all(gate.values()),
        'rows_sha256': sha256_path(rows_path),
        'completed_at': datetime.now(timezone.utc).isoformat(),
        'command': [sys.executable, *sys.argv],
    }
    if sha256_path(candidate_path) != candidate_sha:
        raise RuntimeError('candidate checkpoint changed during reliability audit')
    for label, metadata in opponent_metadata.items():
        if sha256_path(Path(metadata['path'])) != metadata['sha256']:
            raise RuntimeError(f'opponent checkpoint changed: {label}')
    (args.out_dir / 'summary.json').write_text(
        json.dumps(output, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    print(json.dumps({
        'rows': output['rows'],
        'trajectory_hands': trajectory_hands,
        'continuation_rollouts': continuation_rollouts,
        'overall_dev_confirm_agreement': agreement,
        'overall_confirm_selected_minus_source_bb': overall_mean,
        'overall_confirm_delta_ci95_bb': overall_half,
        'gate_components': gate,
        'training_admitted': output['training_admitted'],
    }, sort_keys=True))


if __name__ == '__main__':
    main()
