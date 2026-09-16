#!/usr/bin/env python3
"""Paired treatment-minus-control deltas for aligned mirror evaluations."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def aligned_anchors(document: dict) -> dict[str, dict]:
    return {str(row['anchor']): row for row in document['anchors']}


def paired_delta(control_path: Path, treatment_path: Path) -> dict:
    control = json.loads(control_path.read_text(encoding='utf-8'))
    treatment = json.loads(treatment_path.read_text(encoding='utf-8'))
    for field in ('seed', 'pairs', 'starting_stack', 'policy_mode', 'action_rng_schema'):
        if control.get(field) != treatment.get(field):
            raise ValueError(
                f'alignment mismatch for {field}: '
                f"{control.get(field)!r} != {treatment.get(field)!r}"
            )

    control_anchors = aligned_anchors(control)
    treatment_anchors = aligned_anchors(treatment)
    if set(control_anchors) != set(treatment_anchors):
        raise ValueError('control and treatment anchor sets differ')

    rows = []
    for name in sorted(control_anchors):
        control_row = control_anchors[name]
        treatment_row = treatment_anchors[name]
        if control_row.get('anchor_sha256') != treatment_row.get('anchor_sha256'):
            raise ValueError(f'anchor SHA mismatch for {name}')
        if control_row.get('action_rng') != treatment_row.get('action_rng'):
            raise ValueError(f'action random-stream mismatch for {name}')
        control_outcomes = np.asarray(
            control_row['paired_outcomes']['overall_bb_per_hand'],
            dtype=np.float64,
        )
        treatment_outcomes = np.asarray(
            treatment_row['paired_outcomes']['overall_bb_per_hand'],
            dtype=np.float64,
        )
        if control_outcomes.shape != treatment_outcomes.shape:
            raise ValueError(f'paired outcome length mismatch for {name}')
        deltas = treatment_outcomes - control_outcomes
        count = int(deltas.size)
        mean_bb100 = float(deltas.mean() * 100.0) if count else 0.0
        std_bb100 = float(deltas.std(ddof=1) * 100.0) if count > 1 else 0.0
        ci95 = 1.96 * std_bb100 / math.sqrt(count) if count > 1 else 0.0
        rows.append({
            'anchor': name,
            'anchor_sha256': control_row['anchor_sha256'],
            'pairs': count,
            'control_candidate_bb100': float(control_row['candidate_bb100']),
            'treatment_candidate_bb100': float(treatment_row['candidate_bb100']),
            'treatment_minus_control_bb100': mean_bb100,
            'paired_std_bb100': std_bb100,
            'paired_ci95_bb100': ci95,
            'paired_ci95_lower_bb100': mean_bb100 - ci95,
            'paired_ci95_upper_bb100': mean_bb100 + ci95,
        })

    return {
        'schema': 'cardpilot.paired_mirror_treatment_delta.v1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'control': {
            'path': str(control_path),
            'sha256': sha256_file(control_path),
            'candidate': control.get('candidate'),
        },
        'treatment': {
            'path': str(treatment_path),
            'sha256': sha256_file(treatment_path),
            'candidate': treatment.get('candidate'),
        },
        'alignment': {
            field: control.get(field)
            for field in ('seed', 'pairs', 'starting_stack', 'policy_mode', 'action_rng_schema')
        },
        'anchors': rows,
        'summary': {
            'mean_delta_bb100': float(np.mean([
                row['treatment_minus_control_bb100'] for row in rows
            ])),
            'min_delta_bb100': float(min(
                row['treatment_minus_control_bb100'] for row in rows
            )),
            'min_paired_ci95_lower_bb100': float(min(
                row['paired_ci95_lower_bb100'] for row in rows
            )),
            'all_point_estimates_positive': all(
                row['treatment_minus_control_bb100'] > 0.0 for row in rows
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--treatment', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = paired_delta(args.control, args.treatment)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    print(json.dumps(result['summary'], sort_keys=True))


if __name__ == '__main__':
    main()
