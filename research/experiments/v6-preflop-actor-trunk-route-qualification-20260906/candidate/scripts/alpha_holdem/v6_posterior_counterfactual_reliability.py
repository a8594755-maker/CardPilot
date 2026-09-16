#!/usr/bin/env python3
"""Independent posterior-hole all-action reliability gate for exact physical v6."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v5_mirror_eval import init_model, read_checkpoint
from alpha_holdem.v6_bias_coordinate_search import parse_keyed
from alpha_holdem.v6_counterfactual_target_reliability import (
    mean_ci,
    model_slot_and_action,
    resample_future_deck,
    rollout_branch,
    select_best_slot,
)
from alpha_holdem.v6_history_consistent_hole_posterior import (
    deck_for_holes,
    replay_history,
    same_public_financial_state,
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def sample_disjoint_holes(
    support: list[list[int]], *, dev: int, confirm: int, rng: random.Random
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    if len(support) < dev + confirm:
        raise ValueError('posterior support is too small for disjoint samples')
    indices = rng.sample(range(len(support)), dev + confirm)
    samples = [tuple(support[index]) for index in indices]
    return samples[:dev], samples[dev:]


def reference_state(row: dict) -> ChipState:
    deck = deck_for_holes(
        candidate_seat=int(row['candidate_seat']),
        candidate_holes=tuple(row['candidate_holes']),
        opponent_holes=tuple(row['true_opponent_holes']),
        board=tuple(row['board']),
    )
    state = ChipState.new(deck)
    for event in row['history']:
        action = f"b{int(event['amount'])}" if event['kind'] == 'b' else event['kind']
        state = apply_incr(state, action)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--posterior-rows', type=Path, required=True)
    parser.add_argument('--posterior-rows-sha256', required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument(
        '--candidate-observation-style', choices=('legacy_v4', 'v6'), required=True
    )
    parser.add_argument('--opponent', action='append', default=[], metavar='LABEL=PATH')
    parser.add_argument('--opponent-style', action='append', default=[], metavar='LABEL=STYLE')
    parser.add_argument('--dev-samples', type=int, default=8)
    parser.add_argument('--confirm-samples', type=int, default=8)
    parser.add_argument('--sample-seed', type=int, required=True)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()

    opponents = parse_keyed(args.opponent, option='--opponent')
    styles = parse_keyed(args.opponent_style, option='--opponent-style')
    if not opponents or set(opponents) != set(styles):
        parser.error('opponent and opponent-style labels must match and be nonempty')
    if min(args.dev_samples, args.confirm_samples) < 1:
        parser.error('sample counts must be positive')
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    posterior_path = args.posterior_rows.resolve()
    if sha256_path(posterior_path) != args.posterior_rows_sha256.lower():
        raise ValueError('posterior rows SHA256 mismatch')
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)

    rows = [json.loads(line) for line in posterior_path.read_text().splitlines()]
    if not rows or {row['opponent'] for row in rows} - set(opponents):
        raise ValueError('posterior rows reference missing opponents')
    candidate_path = args.candidate.resolve()
    candidate_sha = sha256_path(candidate_path)
    candidate = init_model(read_checkpoint(candidate_path), args.device).eval()
    opponent_models = {}
    opponent_metadata = {}
    for label, raw_path in opponents.items():
        path = Path(raw_path).resolve()
        opponent_models[label] = init_model(read_checkpoint(path), args.device).eval()
        opponent_metadata[label] = {
            'path': str(path), 'sha256': sha256_path(path),
            'observation_style': styles[label],
        }

    rng = random.Random(args.sample_seed)
    output_rows = []
    continuation_rollouts = 0
    continuation_decisions = 0
    raw_path = args.out_dir / 'rows.jsonl'
    for row in rows:
        label = row['opponent']
        candidate_seat = int(row['candidate_seat'])
        reference = reference_state(row)
        dev_holes, confirm_holes = sample_disjoint_holes(
            row['accepted_opponent_holes'],
            dev=args.dev_samples,
            confirm=args.confirm_samples,
            rng=rng,
        )
        sampled_holes = dev_holes + confirm_holes
        sampled_states = []
        for holes in sampled_holes:
            replayed, matched = replay_history(
                reference,
                candidate_seat=candidate_seat,
                opponent_holes=holes,
                opponent_model=opponent_models[label],
                opponent_style=styles[label],
                device=args.device,
                require_opponent_match=True,
            )
            if not matched or not same_public_financial_state(reference, replayed):
                raise RuntimeError('posterior artifact contained an invalid accepted hole pair')
            sampled_states.append(replace(replayed, deck=resample_future_deck(replayed, rng)))
        source_slot, table, legal_slots = model_slot_and_action(
            candidate,
            sampled_states[0],
            observation_style=args.candidate_observation_style,
            device=args.device,
        )
        outcomes = {slot: [] for slot in legal_slots}
        for slot in legal_slots:
            for state in sampled_states:
                value, decisions = rollout_branch(
                    state,
                    table[slot],
                    candidate=candidate,
                    opponent=opponent_models[label],
                    candidate_seat=candidate_seat,
                    candidate_style=args.candidate_observation_style,
                    opponent_style=styles[label],
                    device=args.device,
                )
                outcomes[slot].append(value)
                continuation_rollouts += 1
                continuation_decisions += decisions
        dev_means = {
            slot: float(np.mean(values[:args.dev_samples]))
            for slot, values in outcomes.items()
        }
        confirm_means = {
            slot: float(np.mean(values[args.dev_samples:]))
            for slot, values in outcomes.items()
        }
        dev_slot = select_best_slot(dev_means, source_slot=source_slot)
        confirm_slot = select_best_slot(confirm_means, source_slot=source_slot)
        output_row = {
            'row_index': int(row['row_index']),
            'opponent': label,
            'candidate_seat': candidate_seat,
            'street': int(row['street']),
            'source_slot': source_slot,
            'legal_slots': legal_slots,
            'physical_actions': {str(slot): table[slot] for slot in legal_slots},
            'dev_holes': [list(value) for value in dev_holes],
            'confirm_holes': [list(value) for value in confirm_holes],
            'dev_means_bb': {str(slot): value for slot, value in dev_means.items()},
            'confirm_means_bb': {str(slot): value for slot, value in confirm_means.items()},
            'all_outcomes_bb': {str(slot): values for slot, values in outcomes.items()},
            'dev_selected_slot': dev_slot,
            'confirm_selected_slot': confirm_slot,
            'dev_confirm_agree': dev_slot == confirm_slot,
            'confirm_selected_minus_source_bb': (
                confirm_means[dev_slot] - confirm_means[source_slot]
            ),
            'new_allin': dev_slot == 8 and source_slot != 8,
        }
        with raw_path.open('a', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(output_row, sort_keys=True) + '\n')
        output_rows.append(output_row)

    by_stratum = {}
    for seat in (0, 1):
        for street in range(4):
            selected = [
                row for row in output_rows
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
    deltas = [row['confirm_selected_minus_source_bb'] for row in output_rows]
    mean, half = mean_ci(deltas)
    agreement = float(np.mean([row['dev_confirm_agree'] for row in output_rows]))
    new_allins = sum(row['new_allin'] for row in output_rows)
    gate = {
        'overall_agreement_at_least_0_80': agreement >= 0.80,
        'every_stratum_agreement_at_least_0_70': all(
            row['agreement'] >= 0.70 for row in by_stratum.values()
        ),
        'confirm_delta_lcb_positive': mean - half > 0.0,
        'no_stratum_confirm_delta_negative': all(
            row['confirm_delta_bb'] >= 0.0 for row in by_stratum.values()
        ),
        'new_allin_fraction_at_most_0_05': new_allins / len(output_rows) <= 0.05,
    }
    summary = {
        'schema': 'cardpilot.v6_posterior_counterfactual_reliability.v1',
        'status': 'COMPLETED',
        'posterior_rows': str(posterior_path),
        'posterior_rows_sha256': args.posterior_rows_sha256.lower(),
        'candidate': str(candidate_path),
        'candidate_sha256': candidate_sha,
        'opponents': opponent_metadata,
        'rows': len(output_rows),
        'dev_samples': args.dev_samples,
        'confirm_samples': args.confirm_samples,
        'sample_seed': args.sample_seed,
        'continuation_rollouts': continuation_rollouts,
        'continuation_decisions': continuation_decisions,
        'overall_dev_confirm_agreement': agreement,
        'overall_confirm_selected_minus_source_bb': mean,
        'overall_confirm_delta_ci95_bb': half,
        'new_allins': new_allins,
        'by_stratum': by_stratum,
        'gate_components': gate,
        'training_admitted': all(gate.values()),
        'rows_sha256': sha256_path(raw_path),
        'completed_at': datetime.now(timezone.utc).isoformat(),
        'command': [sys.executable, *sys.argv],
    }
    if sha256_path(candidate_path) != candidate_sha:
        raise RuntimeError('candidate checkpoint changed')
    (args.out_dir / 'summary.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    print(json.dumps({
        key: summary[key] for key in (
            'rows', 'continuation_rollouts', 'overall_dev_confirm_agreement',
            'overall_confirm_selected_minus_source_bb',
            'overall_confirm_delta_ci95_bb', 'new_allins', 'gate_components',
            'training_admitted',
        )
    }, sort_keys=True))


if __name__ == '__main__':
    main()
