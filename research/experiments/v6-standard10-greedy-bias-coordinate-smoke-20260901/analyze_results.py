from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch


ROOT = Path(__file__).resolve().parent
CELLS = ('standard10', 'procedural_soup', 'mixed_iter16', 'physical1m', 'freshzero_kl')
BIAS_KEYS = {'policy_head.bias', 'preflop_policy_head.bias'}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def estimate(values: np.ndarray) -> dict:
    count = int(values.size)
    mean = float(values.mean()) if count else 0.0
    std = float(values.std(ddof=1)) if count > 1 else 0.0
    half = 1.96 * std / math.sqrt(count) if count > 1 else 0.0
    return {
        'count': count,
        'bb100': mean,
        'ci95_half_width_bb100': half,
        'ci95_lower_bb100': mean - half,
        'ci95_upper_bb100': mean + half,
    }


def main() -> None:
    search_dir = ROOT / 'search'
    search = json.loads((search_dir / 'search_summary.json').read_text())
    assert search['status'] == 'COMPLETED'
    assert search['environment_training_hands'] == 18944
    assert search['summaries_sha256'] == sha256(search_dir / 'evaluation_summaries.jsonl')
    assert search['raw_pairs_sha256'] == sha256(search_dir / 'raw_pairs.jsonl')
    assert search['candidate_sha256'] == sha256(search_dir / 'candidate.pt')
    search_deltas = list(search['selected_deltas_bb100'].values())
    search_gate = {
        'nonzero_biases': int(search['nonzero_offsets']) > 0,
        'robust_score_positive': float(search['selected_robust_score']) > 0.0,
        'three_search_deltas_nonnegative': sum(value >= 0.0 for value in search_deltas) >= 3,
        'worst_search_delta_at_least_minus10': min(search_deltas) >= -10.0,
    }
    assert all(search_gate.values())

    source = torch.load('models/baseline/standard10/latest.pt', map_location='cpu', weights_only=False)
    candidate = torch.load(search_dir / 'candidate.pt', map_location='cpu', weights_only=False)
    assert source['model'].keys() == candidate['model'].keys()
    changed_keys = sorted(
        key for key in source['model']
        if not torch.equal(source['model'][key], candidate['model'][key])
    )
    assert set(changed_keys) == BIAS_KEYS
    assert all(torch.isfinite(value).all() for value in candidate['model'].values())
    training_metadata = candidate['derivative_free_training']
    assert training_metadata['environment_training_hands'] == 18944
    assert training_metadata['optimizer_state_matches_model'] is False

    cells = {}
    pooled_deltas = []
    changed_pairs_total = 0
    for name in CELLS:
        candidate_dir = ROOT / 'validation' / name / 'candidate'
        source_dir = ROOT / 'validation' / name / 'source'
        candidate_summary = json.loads((candidate_dir / 'summary.json').read_text())
        source_summary = json.loads((source_dir / 'summary.json').read_text())
        candidate_path = candidate_dir / 'pairs.jsonl'
        source_path = source_dir / 'pairs.jsonl'
        candidate_pairs = read_jsonl(candidate_path)
        source_pairs = read_jsonl(source_path)
        assert candidate_summary['status'] == source_summary['status'] == 'COMPLETED'
        assert candidate_summary['pairs_sha256'] == sha256(candidate_path)
        assert source_summary['pairs_sha256'] == sha256(source_path)
        assert candidate_summary['candidate_sha256'] == search['candidate_sha256']
        assert source_summary['candidate_sha256'] == search['source_sha256']
        assert candidate_summary['anchor_sha256'] == source_summary['anchor_sha256']
        assert candidate_summary['seed'] == source_summary['seed']
        assert candidate_summary['pairs'] == source_summary['pairs'] == 512
        assert len(candidate_pairs) == len(source_pairs) == 512
        for index, (candidate_row, source_row) in enumerate(zip(candidate_pairs, source_pairs)):
            assert candidate_row['pair_index'] == source_row['pair_index'] == index
            assert candidate_row['deck'] == source_row['deck']
        candidate_values = np.asarray(
            [float(row['candidate_pair_mean_bb']) * 100.0 for row in candidate_pairs]
        )
        source_values = np.asarray(
            [float(row['candidate_pair_mean_bb']) * 100.0 for row in source_pairs]
        )
        deltas = candidate_values - source_values
        changed_pairs = int(np.count_nonzero(deltas))
        changed_pairs_total += changed_pairs
        pooled_deltas.append(deltas)
        candidate_estimate = estimate(candidate_values)
        source_estimate = estimate(source_values)
        delta_estimate = estimate(deltas)
        assert abs(candidate_estimate['bb100'] - candidate_summary['candidate_bb100']) < 1e-9
        assert abs(source_estimate['bb100'] - source_summary['candidate_bb100']) < 1e-9
        cells[name] = {
            'anchor_sha256': candidate_summary['anchor_sha256'],
            'candidate': candidate_estimate,
            'source': source_estimate,
            'candidate_minus_source': delta_estimate,
            'outcome_changed_pairs': changed_pairs,
            'candidate_pairs_sha256': candidate_summary['pairs_sha256'],
            'source_pairs_sha256': source_summary['pairs_sha256'],
        }

    pooled = estimate(np.concatenate(pooled_deltas))
    positive_points = sum(
        row['candidate_minus_source']['bb100'] > 0.0 for row in cells.values()
    )
    positive_lcbs = sum(
        row['candidate_minus_source']['ci95_lower_bb100'] > 0.0
        for row in cells.values()
    )
    validation_gate = {
        'all_five_delta_points_positive': positive_points == len(CELLS),
        'three_individual_delta_lcbs_positive': positive_lcbs >= 3,
        'pooled_delta_lcb_positive': pooled['ci95_lower_bb100'] > 0.0,
    }
    passed = all(validation_gate.values())
    output = {
        'schema': 'cardpilot.v6_bias_coordinate_analysis.v1',
        'status': 'PASS',
        'source_sha256': search['source_sha256'],
        'candidate_sha256': search['candidate_sha256'],
        'changed_model_keys': changed_keys,
        'selected_offsets': search['selected_offsets'],
        'search_gate_components': search_gate,
        'validation_cells': cells,
        'pooled_candidate_minus_source': pooled,
        'positive_delta_points': positive_points,
        'positive_delta_lcbs': positive_lcbs,
        'outcome_changed_pairs_total': changed_pairs_total,
        'validation_gate_components': validation_gate,
        'validation_gate_passed': passed,
        'environment_training_hands': 18944,
        'new_validation_hands': len(CELLS) * 2 * 512 * 2,
        'decision': (
            'ADMIT_LARGER_INTERNAL_CONFIRMATION'
            if passed else 'REJECT_BIAS_ONLY_DIRECT_GREEDY_SEARCH'
        ),
    }
    (ROOT / 'analysis.json').write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
