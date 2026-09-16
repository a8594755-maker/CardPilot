from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch


ROOT = Path(__file__).resolve().parent
CONTROL = ROOT.parent / 'v6-legacy-fresh-zero-elo-smoke-20260901'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_cell(directory: Path):
    summary = json.loads((directory / 'summary.json').read_text())
    pairs_path = directory / 'pairs.jsonl'
    pairs = [json.loads(line) for line in pairs_path.read_text().splitlines()]
    assert summary['status'] == 'COMPLETED'
    assert summary['evaluation_contract'] == 'physical_v6_legacy_v4_observation_v1'
    assert summary['pairs_sha256'] == sha256(pairs_path)
    assert len(pairs) == summary['pairs'] == 4096
    return summary, pairs


def paired(left, right):
    values = []
    for left_row, right_row in zip(left, right):
        assert left_row['pair_index'] == right_row['pair_index']
        assert left_row['deck'] == right_row['deck']
        values.append(
            left_row['candidate_pair_mean_bb']
            - right_row['candidate_pair_mean_bb']
        )
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean())
    half = float(1.96 * array.std(ddof=1) / math.sqrt(len(array)))
    return {'bb100': 100 * mean, 'ci95': [100 * (mean - half), 100 * (mean + half)]}


def model_state_sha(state):
    digest = hashlib.sha256()
    for key in sorted(state):
        tensor = state[key].detach().cpu().contiguous()
        digest.update(key.encode())
        digest.update(str(tensor.dtype).encode())
        digest.update(str(tuple(tensor.shape)).encode())
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def main():
    direct, direct_pairs = load_cell(ROOT / 'eval' / 'final_vs_init')
    treatment, treatment_pairs = load_cell(ROOT / 'eval' / 'final_vs_standard10')
    shared_init, shared_init_pairs = load_cell(CONTROL / 'eval' / 'init_vs_standard10')
    control, control_pairs = load_cell(CONTROL / 'eval' / 'final_vs_standard10')
    assert treatment['seed'] == shared_init['seed'] == control['seed'] == 20261203
    assert treatment['anchor_sha256'] == shared_init['anchor_sha256'] == control['anchor_sha256']

    treatment_init_delta = paired(treatment_pairs, shared_init_pairs)
    treatment_control_delta = paired(treatment_pairs, control_pairs)
    init_checkpoint = torch.load(ROOT / 'frozen' / 'init.pt', map_location='cpu', weights_only=False)
    control_init_checkpoint = torch.load(CONTROL / 'frozen' / 'init.pt', map_location='cpu', weights_only=False)
    final_checkpoint = torch.load(ROOT / 'frozen' / 'final.pt', map_location='cpu', weights_only=False)
    assert set(init_checkpoint['model']) == set(control_init_checkpoint['model'])
    assert all(
        torch.equal(init_checkpoint['model'][key], control_init_checkpoint['model'][key])
        for key in init_checkpoint['model']
    )
    init_state_sha = model_state_sha(init_checkpoint['model'])
    assert init_state_sha == model_state_sha(control_init_checkpoint['model'])

    changed = 0
    for key, tensor in final_checkpoint['model'].items():
        assert torch.isfinite(tensor).all()
        if not torch.equal(tensor, init_checkpoint['model'][key]):
            changed += 1
    optimizer = (final_checkpoint.get('optimizer') or {}).get('state') or {}
    assert optimizer
    for state in optimizer.values():
        for value in state.values():
            if torch.is_tensor(value):
                assert torch.isfinite(value).all()

    metrics = [json.loads(line) for line in (ROOT / 'training' / 'h1_training_metrics.jsonl').read_text().splitlines()]
    session = json.loads((ROOT / 'session_audit.json').read_text())
    control_analysis = json.loads((CONTROL / 'analysis.json').read_text())
    max_kl = max(float(row['approx_kl']) for row in metrics)
    max_clip = max(float(row['clip_frac']) for row in metrics)
    control_max_kl = float(control_analysis['training']['max_approx_kl'])
    control_max_clip = float(control_analysis['training']['max_clip_fraction'])
    gate_components = {
        'session_audit': session['status'] == 'PASS',
        'max_kl_reduced_50pct': max_kl <= 0.5 * control_max_kl,
        'max_clip_reduced_50pct': max_clip <= 0.5 * control_max_clip,
        'final_vs_init_lcb_positive': (
            direct['candidate_bb100'] - direct['candidate_ci95_bb100'] > 0
        ),
        'paired_standard10_transfer_nonnegative': treatment_init_delta['bb100'] >= 0,
    }
    output = {
        'schema': 'cardpilot.fresh_zero_kl_stop_analysis.v1',
        'status': 'PASS',
        'training': {
            'physical_environment_hands': session['actual_environment_hands'],
            'transition_bearing_hands': session['actual_transition_bearing_hands'],
            'max_approx_kl': max_kl,
            'control_max_approx_kl': control_max_kl,
            'max_clip_fraction': max_clip,
            'control_max_clip_fraction': control_max_clip,
            'kl_stop_trigger_count': sum(bool(row['kl_early_stop_triggered']) for row in metrics),
            'epochs_completed': [int(row['ppo_epochs_completed']) for row in metrics],
            'changed_model_tensors': changed,
            'total_model_tensors': len(final_checkpoint['model']),
            'optimizer_state_entries': len(optimizer),
            'initial_model_state_sha256': init_state_sha,
        },
        'evaluation': {
            'final_vs_init': {
                'bb100': direct['candidate_bb100'],
                'ci95': [direct['candidate_bb100'] - direct['candidate_ci95_bb100'], direct['candidate_bb100'] + direct['candidate_ci95_bb100']],
            },
            'final_vs_standard10': {
                'bb100': treatment['candidate_bb100'],
                'ci95': [treatment['candidate_bb100'] - treatment['candidate_ci95_bb100'], treatment['candidate_bb100'] + treatment['candidate_ci95_bb100']],
            },
            'paired_final_minus_shared_init_vs_standard10': treatment_init_delta,
            'paired_treatment_minus_control_final_vs_standard10': treatment_control_delta,
            'new_mirrored_evaluation_hands': 2 * 4096 * 2,
            'reused_shared_init_evaluation_hands': 4096 * 2,
            'tournament_evaluation_hands': session['tournament_evaluation_hands'],
        },
        'gate_components': gate_components,
        'scale_gate_passed': all(gate_components.values()),
        'decision': 'REJECT_EPOCH_BOUNDARY_KL_STOP_SCALE',
    }
    (ROOT / 'analysis.json').write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
