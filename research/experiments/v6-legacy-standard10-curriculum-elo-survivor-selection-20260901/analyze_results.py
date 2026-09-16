from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
CONTROL_ROOT = ROOT.parent / 'v6-legacy-fresh-zero-standard10-elo-curriculum-smoke-20260901'
CELLS = ('standard10', 'pure_no_stop', 'pure_kl_stop', 'pure_lr1e4')


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
    selection = json.loads((ROOT / 'selection_audit.json').read_text())
    assert selection['status'] == 'PASS' and selection['bit_identical']
    assert selection['selected_snapshot_id'] == 2

    candidate_hashes = set()
    cell_results = {}
    pooled_deltas = []
    changed_pairs_total = 0
    for name in CELLS:
        treatment_dir = ROOT / 'eval' / name
        control_dir = CONTROL_ROOT / 'eval' / name
        treatment_summary = json.loads((treatment_dir / 'summary.json').read_text())
        control_summary = json.loads((control_dir / 'summary.json').read_text())
        treatment_path = treatment_dir / 'pairs.jsonl'
        control_path = control_dir / 'pairs.jsonl'
        treatment = read_jsonl(treatment_path)
        control = read_jsonl(control_path)
        assert treatment_summary['status'] == control_summary['status'] == 'COMPLETED'
        assert treatment_summary['pairs_sha256'] == sha256(treatment_path)
        assert control_summary['pairs_sha256'] == sha256(control_path)
        assert treatment_summary['pairs'] == control_summary['pairs'] == 4096
        assert treatment_summary['seed'] == control_summary['seed']
        assert treatment_summary['anchor_sha256'] == control_summary['anchor_sha256']
        assert len(treatment) == len(control) == 4096
        candidate_hashes.add(treatment_summary['candidate_sha256'])

        for expected_index, (treatment_row, control_row) in enumerate(zip(treatment, control)):
            assert treatment_row['pair_index'] == control_row['pair_index'] == expected_index
            assert treatment_row['deck'] == control_row['deck']
        treatment_values = np.asarray(
            [float(row['candidate_pair_mean_bb']) * 100.0 for row in treatment],
            dtype=np.float64,
        )
        control_values = np.asarray(
            [float(row['candidate_pair_mean_bb']) * 100.0 for row in control],
            dtype=np.float64,
        )
        deltas = treatment_values - control_values
        changed_pairs = int(np.count_nonzero(deltas))
        changed_pairs_total += changed_pairs
        pooled_deltas.append(deltas)
        treatment_estimate = estimate(treatment_values)
        delta_estimate = estimate(deltas)
        assert abs(treatment_estimate['bb100'] - treatment_summary['candidate_bb100']) < 1e-9
        cell_results[name] = {
            'anchor_sha256': treatment_summary['anchor_sha256'],
            'candidate': treatment_estimate,
            'terminal_control_bb100': float(control_summary['candidate_bb100']),
            'survivor_minus_terminal': delta_estimate,
            'outcome_changed_pairs': changed_pairs,
            'treatment_pairs_sha256': treatment_summary['pairs_sha256'],
            'control_pairs_sha256': control_summary['pairs_sha256'],
        }

    assert len(candidate_hashes) == 1
    pooled = estimate(np.concatenate(pooled_deltas))
    lower_positive = sum(
        row['candidate']['ci95_lower_bb100'] > 0.0 for row in cell_results.values()
    )
    gate = {
        'selection_audit_pass': True,
        'greedy_behavior_differs': changed_pairs_total > 0,
        'all_four_points_positive': all(
            row['candidate']['bb100'] > 0.0 for row in cell_results.values()
        ),
        'two_candidate_lcbs_positive': lower_positive >= 2,
        'heldout_candidate_lcb_positive': any(
            cell_results[name]['candidate']['ci95_lower_bb100'] > 0.0
            for name in CELLS[1:]
        ),
        'pooled_delta_lcb_positive': pooled['ci95_lower_bb100'] > 0.0,
    }
    output = {
        'schema': 'cardpilot.elo_survivor_selection_analysis.v1',
        'status': 'PASS',
        'candidate_sha256': next(iter(candidate_hashes)),
        'selected_snapshot_id': selection['selected_snapshot_id'],
        'selected_terminal_elo': selection['selected_elo'],
        'cells': cell_results,
        'pooled_survivor_minus_terminal': pooled,
        'outcome_changed_pairs_total': changed_pairs_total,
        'new_evaluation_hands': 4 * 4096 * 2,
        'gate_components': gate,
        'scale_gate_passed': all(gate.values()),
        'decision': 'REJECT_HISTORICAL_ELO_SURVIVOR_DEPLOYMENT',
    }
    (ROOT / 'analysis.json').write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
