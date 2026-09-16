#!/usr/bin/env python3
"""Derivative-free exact-greedy search over shared actor-head bias weights."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.v5_mirror_eval import init_model, read_checkpoint
from alpha_holdem.v6_elo_eval import summarize_models


BIAS_KEYS = ('policy_head.bias', 'preflop_policy_head.bias')


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def parse_keyed(values: list[str], *, option: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if '=' not in value:
            raise ValueError(f'{option} requires LABEL=VALUE: {value!r}')
        label, item = value.split('=', 1)
        if not label or not item or label in parsed:
            raise ValueError(f'invalid or duplicate {option}: {value!r}')
        parsed[label] = item
    return parsed


def robust_score(deltas: list[float], *, dispersion_weight: float) -> float:
    values = np.asarray(deltas, dtype=np.float64)
    if values.size == 0 or not np.isfinite(values).all():
        raise ValueError('robust score requires finite deltas')
    return float(values.mean() - float(dispersion_weight) * values.std(ddof=0))


def set_bias_offsets(
    model: torch.nn.Module,
    source_biases: dict[str, torch.Tensor],
    offsets: np.ndarray,
) -> None:
    if offsets.shape != (18,) or not np.isfinite(offsets).all():
        raise ValueError('bias offsets must be a finite length-18 vector')
    named_parameters = dict(model.named_parameters())
    with torch.no_grad():
        for head_index, key in enumerate(BIAS_KEYS):
            target = named_parameters[key]
            source = source_biases[key].to(device=target.device, dtype=target.dtype)
            delta = torch.as_tensor(
                offsets[head_index * 9:(head_index + 1) * 9],
                device=target.device,
                dtype=target.dtype,
            )
            target.copy_(source + delta)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument(
        '--source-observation-style', choices=('legacy_v4', 'v6'), required=True
    )
    parser.add_argument('--anchor', action='append', default=[], metavar='LABEL=PATH')
    parser.add_argument(
        '--anchor-style', action='append', default=[], metavar='LABEL=STYLE'
    )
    parser.add_argument('--pairs', type=int, default=64)
    parser.add_argument('--seed-base', type=int, required=True)
    parser.add_argument('--step', type=float, default=0.05)
    parser.add_argument('--passes', type=int, default=1)
    parser.add_argument('--dispersion-weight', type=float, default=0.5)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()

    anchors = parse_keyed(args.anchor, option='--anchor')
    styles = parse_keyed(args.anchor_style, option='--anchor-style')
    if not anchors or set(anchors) != set(styles):
        parser.error('--anchor and --anchor-style labels must be identical and nonempty')
    if any(style not in {'legacy_v4', 'v6'} for style in styles.values()):
        parser.error('anchor styles must be legacy_v4 or v6')
    if args.pairs < 2 or args.passes < 1:
        parser.error('--pairs must be at least two and --passes positive')
    if not math.isfinite(args.step) or args.step <= 0.0:
        parser.error('--step must be finite and positive')
    if not math.isfinite(args.dispersion_weight) or args.dispersion_weight < 0.0:
        parser.error('--dispersion-weight must be finite and nonnegative')
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)

    source_path = args.source.resolve()
    source_sha = sha256_path(source_path)
    source_checkpoint = read_checkpoint(source_path)
    if any(key not in source_checkpoint['model'] for key in BIAS_KEYS):
        raise ValueError(f'source checkpoint must contain both actor biases: {BIAS_KEYS}')
    if any(tuple(source_checkpoint['model'][key].shape) != (9,) for key in BIAS_KEYS):
        raise ValueError('source actor biases must each have shape [9]')
    model = init_model(source_checkpoint, args.device).eval()
    source_biases = {
        key: source_checkpoint['model'][key].detach().cpu().clone()
        for key in BIAS_KEYS
    }

    anchor_models = {}
    anchor_metadata = {}
    for label, raw_path in anchors.items():
        path = Path(raw_path).resolve()
        checkpoint = read_checkpoint(path)
        anchor_models[label] = init_model(checkpoint, args.device).eval()
        anchor_metadata[label] = {
            'path': str(path),
            'sha256': sha256_path(path),
            'observation_style': styles[label],
        }

    summaries_path = args.out_dir / 'evaluation_summaries.jsonl'
    pairs_path = args.out_dir / 'raw_pairs.jsonl'
    evaluation_index = 0
    environment_training_hands = 0

    def evaluate(offsets: np.ndarray, label: str) -> dict[str, float]:
        nonlocal evaluation_index, environment_training_hands
        set_bias_offsets(model, source_biases, offsets)
        cell_values = {}
        for anchor_index, (anchor_label, anchor_model) in enumerate(anchor_models.items()):
            seed = int(args.seed_base) + anchor_index * 100003
            result = summarize_models(
                candidate=model,
                anchor=anchor_model,
                pairs=args.pairs,
                seed=seed,
                starting_stack=200.0,
                candidate_observation_style=args.source_observation_style,
                anchor_observation_style=styles[anchor_label],
                device=args.device,
                include_pair_outcomes=True,
            )
            pair_records = result.pop('paired_outcomes')
            summary_row = {
                'evaluation_index': evaluation_index,
                'candidate_label': label,
                'anchor': anchor_label,
                'anchor_sha256': anchor_metadata[anchor_label]['sha256'],
                'seed': seed,
                'offsets': offsets.tolist(),
                **result,
            }
            with summaries_path.open('a', encoding='utf-8', newline='\n') as handle:
                handle.write(json.dumps(summary_row, sort_keys=True) + '\n')
            with pairs_path.open('a', encoding='utf-8', newline='\n') as handle:
                for record in pair_records:
                    handle.write(json.dumps({
                        'evaluation_index': evaluation_index,
                        'candidate_label': label,
                        'anchor': anchor_label,
                        'seed': seed,
                        **record,
                    }, sort_keys=True) + '\n')
            cell_values[anchor_label] = float(result['candidate_bb100'])
            evaluation_index += 1
            environment_training_hands += int(args.pairs) * 2
        return cell_values

    offsets = np.zeros(18, dtype=np.float64)
    baseline_values = evaluate(offsets, 'source_baseline')
    current_values = dict(baseline_values)
    current_deltas = [0.0 for _ in baseline_values]
    current_score = robust_score(
        current_deltas, dispersion_weight=args.dispersion_weight
    )
    history = []
    for pass_index in range(args.passes):
        for coordinate in range(18):
            candidates = [{
                'direction': 0,
                'offsets': offsets.copy(),
                'values': dict(current_values),
                'deltas': dict(zip(baseline_values, current_deltas)),
                'score': current_score,
            }]
            for direction in (1, -1):
                trial = offsets.copy()
                trial[coordinate] += direction * args.step
                trial_values = evaluate(
                    trial,
                    f'pass{pass_index + 1}_coord{coordinate:02d}_{direction:+d}',
                )
                trial_deltas = {
                    key: trial_values[key] - baseline_values[key]
                    for key in baseline_values
                }
                candidates.append({
                    'direction': direction,
                    'offsets': trial,
                    'values': trial_values,
                    'deltas': trial_deltas,
                    'score': robust_score(
                        list(trial_deltas.values()),
                        dispersion_weight=args.dispersion_weight,
                    ),
                })
            # Stable sort preserves the current point on an exact tie.
            selected = max(candidates, key=lambda item: item['score'])
            offsets = selected['offsets'].copy()
            current_values = dict(selected['values'])
            current_deltas = list(selected['deltas'].values())
            current_score = float(selected['score'])
            history.append({
                'pass': pass_index + 1,
                'coordinate': coordinate,
                'head': BIAS_KEYS[coordinate // 9],
                'action_slot': coordinate % 9,
                'selected_direction': int(selected['direction']),
                'selected_score': current_score,
                'selected_offsets': offsets.tolist(),
                'selected_values': current_values,
                'selected_deltas': selected['deltas'],
                'candidate_scores': {
                    str(item['direction']): float(item['score'])
                    for item in candidates
                },
            })

    set_bias_offsets(model, source_biases, offsets)
    candidate_checkpoint = copy.deepcopy(source_checkpoint)
    candidate_checkpoint['model'] = {
        key: value.detach().cpu().clone()
        for key, value in model.state_dict().items()
    }
    candidate_checkpoint['derivative_free_training'] = {
        'algorithm': 'exact_greedy_coordinate_bias_search_v1',
        'source_checkpoint_sha256': source_sha,
        'bias_keys': list(BIAS_KEYS),
        'bias_offsets': offsets.tolist(),
        'environment_training_hands': environment_training_hands,
        'optimizer_state_matches_model': False,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    candidate_path = args.out_dir / 'candidate.pt'
    torch.save(candidate_checkpoint, candidate_path)
    if sha256_path(source_path) != source_sha:
        raise RuntimeError('source checkpoint changed during search')
    for label, metadata in anchor_metadata.items():
        if sha256_path(Path(metadata['path'])) != metadata['sha256']:
            raise RuntimeError(f'anchor checkpoint changed during search: {label}')

    output = {
        'schema': 'cardpilot.v6_bias_coordinate_search.v1',
        'status': 'COMPLETED',
        'algorithm': 'exact_greedy_coordinate_bias_search_v1',
        'source': str(source_path),
        'source_sha256': source_sha,
        'source_observation_style': args.source_observation_style,
        'anchors': anchor_metadata,
        'pairs_per_cell': int(args.pairs),
        'seed_base': int(args.seed_base),
        'step': float(args.step),
        'passes': int(args.passes),
        'dispersion_weight': float(args.dispersion_weight),
        'bias_keys': list(BIAS_KEYS),
        'selected_offsets': offsets.tolist(),
        'nonzero_offsets': int(np.count_nonzero(offsets)),
        'baseline_values_bb100': baseline_values,
        'selected_values_bb100': current_values,
        'selected_deltas_bb100': {
            key: current_values[key] - baseline_values[key]
            for key in baseline_values
        },
        'selected_robust_score': current_score,
        'history': history,
        'evaluated_cells': evaluation_index,
        'environment_training_hands': environment_training_hands,
        'candidate': str(candidate_path.resolve()),
        'candidate_sha256': sha256_path(candidate_path),
        'summaries_sha256': sha256_path(summaries_path),
        'raw_pairs_sha256': sha256_path(pairs_path),
        'completed_at': datetime.now(timezone.utc).isoformat(),
        'command': [sys.executable, *sys.argv],
    }
    (args.out_dir / 'search_summary.json').write_text(
        json.dumps(output, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    print(json.dumps({
        key: output[key]
        for key in (
            'status', 'selected_offsets', 'nonzero_offsets',
            'selected_deltas_bb100', 'selected_robust_score',
            'environment_training_hands', 'candidate_sha256',
        )
    }, sort_keys=True))


if __name__ == '__main__':
    main()
