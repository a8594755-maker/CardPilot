from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch


ROOT = Path(__file__).resolve().parent
CONTROL = ROOT.parent / 'v6-legacy-fresh-zero-elo-smoke-20260901'
KL_STOP = ROOT.parent / 'v6-legacy-fresh-zero-kl-stop-smoke-20260901'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_cell(path):
    path = Path(path)
    summary = json.loads((path / 'summary.json').read_text())
    pairs_path = path / 'pairs.jsonl'
    pairs = [json.loads(line) for line in pairs_path.read_text().splitlines()]
    assert summary['status'] == 'COMPLETED'
    assert summary['evaluation_contract'] == 'physical_v6_legacy_v4_observation_v1'
    assert summary['pairs_sha256'] == sha256(pairs_path)
    assert len(pairs) == 4096
    return summary, pairs


def paired(left, right):
    values = []
    for a, b in zip(left, right):
        assert a['pair_index'] == b['pair_index'] and a['deck'] == b['deck']
        values.append(a['candidate_pair_mean_bb'] - b['candidate_pair_mean_bb'])
    values = np.asarray(values, dtype=np.float64)
    mean = float(values.mean())
    half = float(1.96 * values.std(ddof=1) / math.sqrt(len(values)))
    return {'bb100': mean * 100, 'ci95': [(mean - half) * 100, (mean + half) * 100]}


def main():
    direct, _ = load_cell(ROOT / 'eval' / 'final_vs_init')
    final, final_pairs = load_cell(ROOT / 'eval' / 'final_vs_standard10')
    shared_init, init_pairs = load_cell(CONTROL / 'eval' / 'init_vs_standard10')
    control, control_pairs = load_cell(CONTROL / 'eval' / 'final_vs_standard10')
    kl_stop, kl_stop_pairs = load_cell(KL_STOP / 'eval' / 'final_vs_standard10')
    assert final['seed'] == shared_init['seed'] == control['seed'] == kl_stop['seed']
    init_delta = paired(final_pairs, init_pairs)
    control_delta = paired(final_pairs, control_pairs)
    kl_stop_delta = paired(final_pairs, kl_stop_pairs)

    init_checkpoint = torch.load(ROOT / 'frozen' / 'init.pt', map_location='cpu', weights_only=False)
    shared_checkpoint = torch.load(CONTROL / 'frozen' / 'init.pt', map_location='cpu', weights_only=False)
    final_checkpoint = torch.load(ROOT / 'frozen' / 'final.pt', map_location='cpu', weights_only=False)
    assert all(torch.equal(init_checkpoint['model'][k], shared_checkpoint['model'][k]) for k in init_checkpoint['model'])
    changed = sum(not torch.equal(v, init_checkpoint['model'][k]) for k, v in final_checkpoint['model'].items())
    assert all(torch.isfinite(v).all() for v in final_checkpoint['model'].values())
    optimizer = final_checkpoint['optimizer']['state']
    assert optimizer
    for state in optimizer.values():
        for value in state.values():
            if torch.is_tensor(value):
                assert torch.isfinite(value).all()

    metrics = [json.loads(line) for line in (ROOT / 'training' / 'h1_training_metrics.jsonl').read_text().splitlines()]
    session = json.loads((ROOT / 'session_audit.json').read_text())
    max_kl = max(float(row['approx_kl']) for row in metrics)
    max_clip = max(float(row['clip_frac']) for row in metrics)
    components = {
        'session_audit': session['status'] == 'PASS',
        'max_kl_at_most_0_668909': max_kl <= 0.668909,
        'max_clip_at_most_0_425929': max_clip <= 0.425929,
        'final_vs_init_lcb_positive': direct['candidate_bb100'] - direct['candidate_ci95_bb100'] > 0,
        'paired_standard10_transfer_nonnegative': init_delta['bb100'] >= 0,
    }
    output = {
        'schema': 'cardpilot.fresh_zero_lr1e4_analysis.v1',
        'status': 'PASS',
        'training': {
            'physical_environment_hands': session['actual_environment_hands'],
            'transition_bearing_hands': session['actual_transition_bearing_hands'],
            'max_approx_kl': max_kl,
            'max_clip_fraction': max_clip,
            'kl_stop_trigger_count': sum(bool(row['kl_early_stop_triggered']) for row in metrics),
            'epochs_completed': [int(row['ppo_epochs_completed']) for row in metrics],
            'changed_model_tensors': changed,
            'total_model_tensors': len(final_checkpoint['model']),
            'optimizer_state_entries': len(optimizer),
        },
        'evaluation': {
            'final_vs_init': {'bb100': direct['candidate_bb100'], 'ci95': [direct['candidate_bb100'] - direct['candidate_ci95_bb100'], direct['candidate_bb100'] + direct['candidate_ci95_bb100']]},
            'final_vs_standard10': {'bb100': final['candidate_bb100'], 'ci95': [final['candidate_bb100'] - final['candidate_ci95_bb100'], final['candidate_bb100'] + final['candidate_ci95_bb100']]},
            'paired_final_minus_shared_init_vs_standard10': init_delta,
            'paired_lr1e4_minus_no_stop_control': control_delta,
            'paired_lr1e4_minus_lr3e4_kl_stop': kl_stop_delta,
            'new_mirrored_evaluation_hands': 2 * 4096 * 2,
            'reused_shared_init_evaluation_hands': 4096 * 2,
            'tournament_evaluation_hands': session['tournament_evaluation_hands'],
        },
        'gate_components': components,
        'scale_gate_passed': all(components.values()),
        'decision': 'REJECT_PURE_FRESH_ZERO_HISTORICAL_LEAGUE',
    }
    (ROOT / 'analysis.json').write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
