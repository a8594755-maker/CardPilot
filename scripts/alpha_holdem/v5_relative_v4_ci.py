#!/usr/bin/env python3
"""Independent Welch CI for an official promotion candidate minus fresh V4."""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scipy.stats import t as student_t


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_candidate(files: list[Path]) -> tuple[list[float], list[str]]:
    values: list[float] = []
    errors: list[str] = []
    for path in files:
        rows = 0
        with path.open(encoding='utf-8') as handle:
            for line_number, line in enumerate(handle, 1):
                try:
                    row = json.loads(line)
                    value = row.get('winnings_chips')
                    if value is None:
                        value = float(row['winnings_bb']) * 100.0
                    values.append(float(value)); rows += 1
                except Exception as exc:
                    errors.append(f'{path.name}:{line_number}: {exc}')
        if rows != 1700:
            errors.append(f'{path.name}: rows {rows} != 1700')
    return values, errors


def load_v4(files: list[Path]) -> tuple[list[float], list[str]]:
    values: list[float] = []
    errors: list[str] = []
    for path in files:
        per_hand: dict[int, float] = {}
        with path.open(encoding='utf-8') as handle:
            for line_number, line in enumerate(handle, 1):
                try:
                    row = json.loads(line); hand = int(row['hand_idx']); value = float(row['winnings_hero'])
                except Exception as exc:
                    errors.append(f'{path.name}:{line_number}: {exc}'); continue
                prior = per_hand.get(hand)
                if prior is not None and prior != value:
                    errors.append(f'{path.name}: winnings conflict hand {hand}')
                per_hand[hand] = value
        if sorted(per_hand) != list(range(1700)):
            errors.append(f'{path.name}: hand coverage is not 0..1699')
        values.extend(per_hand[index] for index in sorted(per_hand))
    return values, errors


def welch(candidate: list[float], baseline: list[float]) -> dict[str, float]:
    n1, n0 = len(candidate), len(baseline)
    mean1, mean0 = statistics.fmean(candidate), statistics.fmean(baseline)
    var1, var0 = statistics.variance(candidate), statistics.variance(baseline)
    a, b = var1 / n1, var0 / n0
    se = math.sqrt(a + b)
    df = (a + b) ** 2 / (a * a / (n1 - 1) + b * b / (n0 - 1))
    critical = float(student_t.ppf(0.975, df))
    delta = mean1 - mean0; halfwidth = critical * se
    return {
        'candidate_hands': n1, 'candidate_bb100': mean1, 'candidate_sd_chips': math.sqrt(var1),
        'baseline_hands': n0, 'baseline_bb100': mean0, 'baseline_sd_chips': math.sqrt(var0),
        'delta_candidate_minus_v4_bb100': delta, 'welch_standard_error_bb100': se,
        'welch_df': df, 'critical_t_975': critical, 'ci95_halfwidth_bb100': halfwidth,
        'ci95_lower_bb100': delta - halfwidth, 'ci95_upper_bb100': delta + halfwidth,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate-hands-glob', required=True)
    parser.add_argument('--v4-hands-glob', required=True)
    parser.add_argument('--candidate-checkpoint', required=True)
    parser.add_argument('--expected-candidate-sha256', required=True)
    parser.add_argument('--v4-model', required=True)
    parser.add_argument('--expected-v4-model-sha256', required=True)
    parser.add_argument('--v4-report', required=True)
    parser.add_argument('--expected-v4-report-sha256', required=True)
    parser.add_argument('--out-json', required=True)
    args = parser.parse_args()
    candidate_files = [Path(p) for p in sorted(glob.glob(args.candidate_hands_glob))]
    v4_files = [Path(p) for p in sorted(glob.glob(args.v4_hands_glob))]
    errors: list[str] = []
    if len(candidate_files) != 12: errors.append(f'candidate files {len(candidate_files)} != 12')
    if len(v4_files) != 12: errors.append(f'V4 files {len(v4_files)} != 12')
    checkpoint, v4_model, v4_report = Path(args.candidate_checkpoint), Path(args.v4_model), Path(args.v4_report)
    for label, path, expected in (
        ('candidate checkpoint', checkpoint, args.expected_candidate_sha256),
        ('V4 model', v4_model, args.expected_v4_model_sha256),
        ('V4 report', v4_report, args.expected_v4_report_sha256),
    ):
        if not path.exists() or sha256_path(path) != expected.lower(): errors.append(f'{label} SHA mismatch')
    candidate, candidate_errors = load_candidate(candidate_files); errors.extend(candidate_errors)
    baseline, baseline_errors = load_v4(v4_files); errors.extend(baseline_errors)
    if len(candidate) != 20400: errors.append(f'candidate hands {len(candidate)} != 20400')
    if len(baseline) != 20400: errors.append(f'V4 hands {len(baseline)} != 20400')
    stats = welch(candidate, baseline) if not errors else {}
    payload: dict[str, Any] = {
        'checked_at': datetime.now(timezone.utc).isoformat(), 'overall': 'PASS' if not errors else 'FAIL',
        'estimand': 'official greedy-direct treatment promotion bb/100 minus fresh current-harness V4 bb/100',
        'method': 'independent Welch two-sample 95% CI; identical Slumbot deal/session IDs not proven',
        'candidate_checkpoint': str(checkpoint), 'candidate_checkpoint_sha256': args.expected_candidate_sha256.lower(),
        'v4_model': str(v4_model), 'v4_model_sha256': args.expected_v4_model_sha256.lower(),
        'v4_report': str(v4_report), 'v4_report_sha256': args.expected_v4_report_sha256.lower(),
        'candidate_files': [{'path': str(p), 'sha256': sha256_path(p)} for p in candidate_files],
        'v4_files': [{'path': str(p), 'sha256': sha256_path(p)} for p in v4_files],
        'statistics': stats, 'relative_v4_pass': bool(stats and stats['ci95_lower_bb100'] > 0.0),
        'point_estimate_only_forbidden': True, 'errors': errors,
        'claim_scope': 'promotion routing only; not L5/L6 proof',
    }
    out = Path(args.out_json); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload['overall'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
