"""Review immutable stage1 evidence and stage2's initial save; no model play."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
import time

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def stats(values):
    mean = 100 * statistics.mean(values)
    half = 196 * statistics.stdev(values) / math.sqrt(len(values))
    return {'bb100': mean, 'low': mean - half, 'high': mean + half}


def review():
    started = time.perf_counter()
    inputs = {}

    def track(path):
        inputs[str(path)] = sha(path)
        return path

    stage = json.loads(track(BASE / 'stage1_analysis.json').read_text())
    require(stage['passed'], 'stage1 controller audit did not pass')
    raw = {}
    for arm in ('static', 'moving256'):
        directory = BASE / f'eval_{arm}_stage1'
        summary = json.loads(track(directory / 'summary.json').read_text())
        path = track(directory / 'common_deck_pairs.jsonl.gz')
        require(inputs[str(path)] == summary['raw_pairs_sha256'], 'raw hash mismatch')
        require(summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 32768,
                'incomplete arm evaluation')
        for name, model_path in summary['input_paths'].items():
            require(sha(track(Path(model_path))) == summary['input_sha256'][name], 'model changed')
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        require(len(rows) == 8192 and len({tuple(row['deck']) for row in rows}) == 8192,
                'wrong number of unique paired decks')
        require(all(sorted(row['deck']) == list(range(52)) for row in rows), 'invalid deck')
        raw[arm] = {(row['anchor'], row['anchor_seed'], row['pair_index']): row for row in rows}
        require(len(raw[arm]) == 8192, 'duplicate pair identity')
    require(raw['static'].keys() == raw['moving256'].keys(), 'arm identity mismatch')
    values, by_anchor, by_seat = [], {}, {0: [], 1: []}
    for key, left in raw['static'].items():
        right = raw['moving256'][key]
        require(left['deck'] == right['deck'] and left['control_rewards_bb'] == right['control_rewards_bb'],
                'same-deck repeated parent result differs')
        delta = [right['treatment_rewards_bb'][seat] - left['treatment_rewards_bb'][seat] for seat in (0, 1)]
        value = statistics.mean(delta)
        values.append(value)
        by_anchor.setdefault(key[0], []).append(value)
        for seat in (0, 1):
            by_seat[seat].append(delta[seat])
    require(set(by_anchor) == {'standard10', 'cfr4', 'legacy_iter16', 'legacy_mixed65k'}
            and all(len(v) == 2048 for v in by_anchor.values()), 'anchor coverage mismatch')
    compared = [(stats(values), stage['moving_minus_static']['pooled'])]
    compared += [(stats(v), stage['moving_minus_static']['by_anchor'][k]) for k, v in by_anchor.items()]
    compared += [(stats(v), stage['moving_minus_static']['by_seat'][str(k)]) for k, v in by_seat.items()]
    for calculated, stored in compared:
        for key, stored_key in [('bb100', 'bb100'), ('low', 'ci95_low_bb100'), ('high', 'ci95_high_bb100')]:
            require(math.isclose(calculated[key], stored[stored_key], abs_tol=1e-9), 'paired statistics differ')
    collapse = (sum(stats(v)['high'] < -25 for v in by_anchor.values()) >= 3
                and all(stats(v)['high'] < 0 for v in by_seat.values()))
    require(collapse == stage['broad_collapse'] and not collapse, 'stage2 admission differs')

    parent_path = track(BASE / 'moving256_stage1/latest.pt')
    initial_path = track(BASE / 'moving256_stage2/initial_resumed_state.pt')
    parent = torch.load(parent_path, map_location='cpu', weights_only=False)
    initial = torch.load(initial_path, map_location='cpu', weights_only=False)
    nan_fields = []

    def exact(left, right, path):
        if isinstance(left, torch.Tensor):
            return isinstance(right, torch.Tensor) and left.dtype == right.dtype and torch.equal(left, right)
        if isinstance(left, np.ndarray):
            return (isinstance(right, np.ndarray) and left.dtype == right.dtype and left.shape == right.shape
                    and left.tobytes() == right.tobytes())
        if isinstance(left, float) and math.isnan(left):
            matched = isinstance(right, float) and math.isnan(right) and struct.pack('d', left) == struct.pack('d', right)
            if matched:
                nan_fields.append(path)
            return matched
        if isinstance(left, dict):
            return (isinstance(right, dict) and left.keys() == right.keys()
                    and all(exact(left[k], right[k], f'{path}.{k}') for k in left))
        if isinstance(left, (tuple, list)):
            return (type(left) == type(right) and len(left) == len(right)
                    and all(exact(a, b, f'{path}[{i}]') for i, (a, b) in enumerate(zip(left, right))))
        return left == right

    keys = ['model', 'optimizer', 'ppo_replay_entries', 'ppo_replay_rng_state', 'ppo_replay_cumulative_rows',
            'pool_snapshots', 'pool_candidate_history', 'moving_source_policy_reference']
    restored = {key: exact(parent[key], initial[key], key) for key in keys}
    require(all(restored.values()), f'initial state differs: {restored}')
    require(parent['iteration'] == initial['iteration'] == 1324, 'iteration reset')
    require(parent['environment_hand_accounting']['completed_hands'] ==
            initial['environment_hand_accounting']['completed_hands'] == 6296793, 'hand counter reset')
    reference = initial['moving_source_policy_reference']
    require(reference['activation_iteration'] == 882 and reference['completed_updates'] == 442
            and reference['last_refresh_update'] == 256 and reference['reference_round'] == 1, 'reference rebased')
    require(all(sha(path) == digest for path, digest in inputs.items()), 'immutable input changed during review')
    return {
        'schema': 'cardpilot.phase_control.stage1_resume_review.v1', 'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'input_sha256': inputs,
        'source_sha256': {str(Path(__file__)): sha(__file__)},
        'paired_decks': 8192, 'moving_minus_static': stats(values), 'broad_collapse': collapse,
        'physical_evaluation_executions': 65536, 'distinct_policy_deck_seat_instances': 49152,
        'intentional_parent_repeat_excess_executions': 16384,
        'initial_resume_exact': restored, 'initial_iteration': 1324, 'initial_physical_hands': 6296793,
        'reference_completed_updates': 442, 'reference_round': 1, 'next_refresh_global_iteration': 1394,
        'byte_identical_nan_scalar_fields': len(nan_fields), 'nan_field_examples': nan_fields[:5],
        'scope': 'Stage1 paired statistics and stage2 initial saved boundary, including reference RNG. Not bitwise worker/in-flight continuation, seed replication or external strength.',
        'new_training_hands': 0, 'new_evaluation_hands': 0, 'new_offline_policy_queries': 0,
        'wall_seconds': time.perf_counter() - started,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    require(args.out.resolve().parent == HERE, 'output must be in the non-runtime post_analysis directory')
    require(not args.out.exists(), 'refusing to overwrite review evidence')
    torch.set_num_threads(1)
    result = review()
    with args.out.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({'passed': True, 'out': str(args.out), 'moving_minus_static': result['moving_minus_static'],
                      'initial_resume_exact': result['initial_resume_exact'], 'new_hands': 0}, indent=2))


if __name__ == '__main__':
    main()
