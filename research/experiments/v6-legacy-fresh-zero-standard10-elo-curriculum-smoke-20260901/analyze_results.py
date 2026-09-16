from __future__ import annotations

import hashlib
import json
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parent
CELLS = ('standard10', 'pure_no_stop', 'pure_kl_stop', 'pure_lr1e4')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_cell(name):
    directory = ROOT / 'eval' / name
    summary = json.loads((directory / 'summary.json').read_text())
    pairs_path = directory / 'pairs.jsonl'
    pairs = [json.loads(line) for line in pairs_path.read_text().splitlines()]
    assert summary['status'] == 'COMPLETED'
    assert summary['evaluation_contract'] == 'physical_v6_legacy_v4_observation_v1'
    assert summary['pairs_sha256'] == sha256(pairs_path)
    assert len(pairs) == summary['pairs'] == 4096
    assert [row['pair_index'] for row in pairs] == list(range(4096))
    return summary, pairs


def main():
    loaded = {name: load_cell(name) for name in CELLS}
    candidate_hashes = {summary['candidate_sha256'] for summary, _ in loaded.values()}
    anchor_hashes = {summary['anchor_sha256'] for summary, _ in loaded.values()}
    assert len(candidate_hashes) == 1 and len(anchor_hashes) == 4
    for name in CELLS[1:]:
        summary, pairs = loaded[name]
        assert summary['pair_draws'] == 4096
        assert summary['candidate_bb100'] == 0.0
        assert all(row['candidate_pair_mean_bb'] == 0.0 for row in pairs)

    checkpoint = torch.load(ROOT / 'frozen' / 'final.pt', map_location='cpu', weights_only=False)
    initial = torch.load(ROOT / 'frozen' / 'init.pt', map_location='cpu', weights_only=False)
    assert all(torch.isfinite(value).all() for value in checkpoint['model'].values())
    changed = sum(
        not torch.equal(value, initial['model'][key])
        for key, value in checkpoint['model'].items()
    )
    optimizer = checkpoint['optimizer']['state']
    assert optimizer
    for state in optimizer.values():
        for value in state.values():
            if torch.is_tensor(value):
                assert torch.isfinite(value).all()
    final_ids = [int(row['id']) for row in checkpoint['pool_snapshots']]
    assert 0 in final_ids
    standard_snapshot = next(row for row in checkpoint['pool_snapshots'] if int(row['id']) == 0)
    assert standard_snapshot['score_components']['kind'] == 'initial_external_opponent'
    assert standard_snapshot['score_components']['checkpoint_sha256'] == (
        '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
    )

    assignments = [json.loads(line) for line in (ROOT / 'training' / 'opponent_assignments.jsonl').read_text().splitlines()]
    standard_worker_assignments = 0
    for row in assignments:
        standard_worker_assignments += sum(
            1
            for worker in row['workers']
            if worker['opponent']['kind'] == 'pool_snapshot'
            and int(worker['opponent']['snapshot_id']) == 0
        )
    assert standard_worker_assignments > 0

    metrics = [json.loads(line) for line in (ROOT / 'training' / 'h1_training_metrics.jsonl').read_text().splitlines()]
    session = json.loads((ROOT / 'session_audit.json').read_text())
    rows = {}
    for name, (summary, _) in loaded.items():
        rows[name] = {
            'bb100': summary['candidate_bb100'],
            'ci95': [summary['candidate_bb100'] - summary['candidate_ci95_bb100'], summary['candidate_bb100'] + summary['candidate_ci95_bb100']],
            'pair_wins': summary['pair_wins'],
            'pair_draws': summary['pair_draws'],
            'pair_losses': summary['pair_losses'],
        }
    lower_positive = sum(row['ci95'][0] > 0 for row in rows.values())
    components = {
        'session_audit': session['status'] == 'PASS',
        'standard10_survived': 0 in final_ids,
        'max_kl_at_most_1_5': max(float(row['approx_kl']) for row in metrics) <= 1.5,
        'max_clip_at_most_0_90': max(float(row['clip_frac']) for row in metrics) <= 0.90,
        'all_four_points_positive': all(row['bb100'] > 0 for row in rows.values()),
        'two_lcbs_positive': lower_positive >= 2,
        'heldout_lcb_positive': any(rows[name]['ci95'][0] > 0 for name in CELLS[1:]),
    }
    output = {
        'schema': 'cardpilot.standard10_elo_curriculum_analysis.v1',
        'status': 'PASS',
        'training': {
            'physical_environment_hands': session['actual_environment_hands'],
            'transition_bearing_hands': session['actual_transition_bearing_hands'],
            'max_approx_kl': max(float(row['approx_kl']) for row in metrics),
            'max_clip_fraction': max(float(row['clip_frac']) for row in metrics),
            'standard10_worker_assignments': standard_worker_assignments,
            'total_worker_assignments': len(assignments) * int(checkpoint['config']['workers']),
            'final_pool_snapshot_ids': final_ids,
            'standard10_final_elo': float(standard_snapshot['selection_score']),
            'changed_model_tensors': changed,
            'total_model_tensors': len(checkpoint['model']),
            'optimizer_state_entries': len(optimizer),
        },
        'evaluation': rows,
        'new_breadth_evaluation_hands': 4 * 4096 * 2,
        'tournament_evaluation_hands': session['tournament_evaluation_hands'],
        'gate_components': components,
        'scale_gate_passed': all(components.values()),
        'decision': 'REJECT_OPPONENT_ONLY_STANDARD10_CURRICULUM',
    }
    (ROOT / 'analysis.json').write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
