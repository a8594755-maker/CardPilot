from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_cell(name: str):
    directory = ROOT / 'eval' / name
    summary = json.loads((directory / 'summary.json').read_text())
    pairs_path = directory / 'pairs.jsonl'
    pairs = [json.loads(line) for line in pairs_path.read_text().splitlines()]
    assert summary['status'] == 'COMPLETED'
    assert summary['evaluation_contract'] == (
        'physical_v6_legacy_v4_observation_v1'
    )
    assert summary['policy_mode'] == 'greedy'
    assert summary['pairs_sha256'] == sha256(pairs_path)
    assert len(pairs) == summary['pairs'] == 4096
    assert [row['pair_index'] for row in pairs] == list(range(4096))
    return summary, pairs


def mean_ci95(values):
    values = np.asarray(values, dtype=np.float64)
    mean = float(values.mean())
    half = float(1.96 * values.std(ddof=1) / math.sqrt(len(values)))
    return {'bb100': 100.0 * mean, 'ci95': [100.0 * (mean - half), 100.0 * (mean + half)]}


def main():
    direct, direct_pairs = load_cell('final_vs_init')
    initial, initial_pairs = load_cell('init_vs_standard10')
    final, final_pairs = load_cell('final_vs_standard10')
    assert initial['anchor_sha256'] == final['anchor_sha256']
    assert initial['seed'] == final['seed'] == 20261203
    for initial_row, final_row in zip(initial_pairs, final_pairs):
        assert initial_row['pair_index'] == final_row['pair_index']
        assert initial_row['deck'] == final_row['deck']
    paired_delta = mean_ci95([
        final_row['candidate_pair_mean_bb'] - initial_row['candidate_pair_mean_bb']
        for initial_row, final_row in zip(initial_pairs, final_pairs)
    ])

    init_path = ROOT / 'frozen' / 'init.pt'
    final_path = ROOT / 'frozen' / 'final.pt'
    init_checkpoint = torch.load(init_path, map_location='cpu', weights_only=False)
    final_checkpoint = torch.load(final_path, map_location='cpu', weights_only=False)
    init_state = init_checkpoint['model']
    final_state = final_checkpoint['model']
    assert set(init_state) == set(final_state)
    changed = []
    for key in init_state:
        assert torch.isfinite(init_state[key]).all(), key
        assert torch.isfinite(final_state[key]).all(), key
        if not torch.equal(init_state[key], final_state[key]):
            changed.append(key)
    optimizer_state = (final_checkpoint.get('optimizer') or {}).get('state') or {}
    assert optimizer_state
    optimizer_tensors = 0
    for state in optimizer_state.values():
        for value in state.values():
            if torch.is_tensor(value):
                assert torch.isfinite(value).all()
                optimizer_tensors += 1

    metrics = [
        json.loads(line)
        for line in (ROOT / 'training' / 'h1_training_metrics.jsonl').read_text().splitlines()
    ]
    session = json.loads((ROOT / 'session_audit.json').read_text())
    checkpoint_contracts = {
        row.get('evaluation_contract')
        for row in final_checkpoint.get('elo_tournament_history', [])
    }
    assert checkpoint_contracts == {'physical_v6_legacy_v4_observation_v1'}
    scale_gate = (
        direct['candidate_bb100'] - direct['candidate_ci95_bb100'] > 0.0
        and paired_delta['bb100'] > 0.0
        and session['status'] == 'PASS'
    )
    output = {
        'schema': 'cardpilot.fresh_zero_elo_smoke_analysis.v1',
        'status': 'PASS',
        'frozen_sha256': {
            'init': sha256(init_path),
            'final': sha256(final_path),
            'standard10': initial['anchor_sha256'],
        },
        'training': {
            'physical_environment_hands': session['actual_environment_hands'],
            'transition_bearing_hands': session['actual_transition_bearing_hands'],
            'iterations': session['final_iteration'],
            'max_approx_kl': max(float(row['approx_kl']) for row in metrics),
            'final_approx_kl': float(metrics[-1]['approx_kl']),
            'max_clip_fraction': max(float(row['clip_frac']) for row in metrics),
            'changed_model_tensors': len(changed),
            'total_model_tensors': len(init_state),
            'optimizer_state_entries': len(optimizer_state),
            'optimizer_tensors': optimizer_tensors,
            'elo_evaluation_contracts': sorted(checkpoint_contracts),
        },
        'evaluation': {
            'final_vs_init': {
                'bb100': direct['candidate_bb100'],
                'ci95': [
                    direct['candidate_bb100'] - direct['candidate_ci95_bb100'],
                    direct['candidate_bb100'] + direct['candidate_ci95_bb100'],
                ],
                'pair_wins': direct['pair_wins'],
                'pair_draws': direct['pair_draws'],
                'pair_losses': direct['pair_losses'],
            },
            'init_vs_standard10': {
                'bb100': initial['candidate_bb100'],
                'ci95': [
                    initial['candidate_bb100'] - initial['candidate_ci95_bb100'],
                    initial['candidate_bb100'] + initial['candidate_ci95_bb100'],
                ],
            },
            'final_vs_standard10': {
                'bb100': final['candidate_bb100'],
                'ci95': [
                    final['candidate_bb100'] - final['candidate_ci95_bb100'],
                    final['candidate_bb100'] + final['candidate_ci95_bb100'],
                ],
            },
            'paired_final_minus_init_vs_standard10': paired_delta,
            'new_mirrored_evaluation_hands': 3 * 4096 * 2,
            'tournament_evaluation_hands': session['tournament_evaluation_hands'],
        },
        'scale_gate_passed': scale_gate,
        'decision': (
            'ADMIT_SAME_RUN_262K_CONTINUATION'
            if scale_gate
            else 'REJECT_UNMODIFIED_FRESH_ZERO_PAPER_LR_SCALE'
        ),
    }
    (ROOT / 'analysis.json').write_text(
        json.dumps(output, indent=2, sort_keys=True) + '\n'
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
