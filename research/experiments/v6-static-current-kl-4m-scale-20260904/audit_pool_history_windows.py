"""Reconstruct capped pool history from immutable archives; never edit old audits."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ORIGINAL_SHA = '11486bcb5582a574b875baf21cf7e672f742bcd5b64426a6aefbe098d00a44f2'
META_KEYS = ('id', 'hands', 'iteration', 'pool_strategy', 'selection_loss',
             'selection_score', 'score_components')


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def metadata(row):
    return {key: row.get(key) for key in META_KEYS}


def verify_windows(windows, metrics, assignments):
    """Pure metadata replay. Other endpoint/model/resume gates remain separate."""
    require(len(windows) >= 2, 'parent and final windows required')
    parent, final = windows[0], windows[-1]
    start, end = parent['iteration'], final['iteration']
    cadence, limit = parent['snapshot_every'], parent['history_limit']
    require(cadence > 0 and limit > 0 and end > start, 'invalid continuation')
    parent_max = max(row['id'] for row in parent['history'] + parent['active'])
    expected_iterations = [i for i in range(start + 1, end + 1) if i % cadence == 0]
    expected_ids = list(range(parent_max + 1, parent_max + 1 + len(expected_iterations)))
    merged, overlap_comparisons = {}, 0
    for window in windows:
        require(start <= window['iteration'] <= end, 'window outside continuation')
        require(window['snapshot_every'] == cadence and window['history_limit'] == limit,
                'cadence or retention changed')
        require(window['run_id'] == parent['run_id'] and window['strategy'] == 'loss-kbest',
                'run identity or strategy changed')
        last_id = parent_max + sum(i <= window['iteration'] for i in expected_iterations)
        require([row['id'] for row in window['history']]
                == list(range(max(0, last_id - limit + 1), last_id + 1)),
                'retained history does not match the configured suffix')
        for row in window['history']:
            key = row['id']
            if key in merged:
                require(canonical(merged[key]) == canonical(row), 'conflicting overlapping candidate')
                overlap_comparisons += 1
            else:
                merged[key] = row
    require(sorted(key for key in merged if key > parent_max) == expected_ids,
            'missing or extra continuation candidate')
    require([row['iteration'] for row in metrics] == list(range(1, end + 1)),
            'metric iteration gap')
    require([row['applies_to_iteration'] for row in assignments] == list(range(1, end + 1)),
            'assignment iteration gap')
    candidates = {iteration: merged[key] for key, iteration in zip(expected_ids, expected_iterations)}
    active = [metadata(row) for row in parent['active']]
    require(len(active) == 5 and len({row['id'] for row in active}) == 5,
            'parent pool is not five unique entries')
    require({0, 1, 2}.issubset(row['id'] for row in active), 'parent anchors missing')
    snapshots_by_iteration = {}
    for window in windows:
        snapshots_by_iteration.setdefault(window['iteration'], []).append(window)
    matched_windows = 0
    formula_labels = set()
    for iteration in range(start, end + 1):
        if iteration > start:
            refs = assignments[iteration - 1]['pool_snapshot_refs']
            expected_refs = [{'local_index': index, 'snapshot_hands': row['hands'],
                              'snapshot_id': row['id'], 'snapshot_iteration': row['iteration']}
                             for index, row in enumerate(active)]
            require(refs == expected_refs, 'assignment used a different pool')
            if iteration in candidates:
                candidate = candidates[iteration]
                require(candidate['iteration'] == iteration, 'candidate cadence mismatch')
                require(candidate['hands'] == metrics[iteration - 1]['hands'],
                        'candidate hand counter differs from raw metric')
                require(candidate['pool_strategy'] == 'loss-kbest', 'candidate strategy changed')
                components = candidate['score_components']
                # Executed frozen source uses .5, regardless of its formula text.
                expected_loss = float(components['policy_loss']) + .5 * math.log1p(
                    max(0.0, float(components['value_loss'])))
                require(math.isfinite(expected_loss) and math.isclose(
                    candidate['selection_loss'], expected_loss, rel_tol=1e-12, abs_tol=1e-12),
                    'candidate score does not match executed selection loss')
                require(candidate['selection_score'] == -candidate['selection_loss'],
                        'candidate score/loss mismatch')
                formula_labels.add(components.get('formula'))
                active.append(metadata(candidate))
                active.sort(key=lambda row: (row['selection_score'], row['hands'], row['id']), reverse=True)
                active = active[:5]
                ids = [row['id'] for row in active]
                require(candidate['active_ids_after'] == ids, 'survivor selection mismatch')
                require(candidate['selected'] is (candidate['id'] in ids), 'selected flag mismatch')
                require({0, 1, 2}.issubset(ids), 'original anchor lost')
        for window in snapshots_by_iteration.get(iteration, []):
            require(canonical(window['active']) == canonical(active), 'archive/final active metadata mismatch')
            matched_windows += 1
    require(matched_windows == len(windows), 'not every checkpoint was verified')
    return {'passed': True, 'parent_iteration': start, 'final_iteration': end,
            'configured_history_limit': limit, 'new_candidates_reconstructed': len(expected_ids),
            'first_new_candidate_id': expected_ids[0], 'last_new_candidate_id': expected_ids[-1],
            'new_candidates_retained_in_final': sum(row['id'] > parent_max for row in final['history']),
            'new_candidates_evicted_from_final': sum(row['id'] > parent_max for row in merged.values())
                                                 - sum(row['id'] > parent_max for row in final['history']),
            'overlapping_metadata_comparisons': overlap_comparisons,
            'verified_checkpoint_windows': matched_windows, 'verified_suffix_assignments': end - start,
            'final_active_ids': [row['id'] for row in active],
            'reconstructed_candidate_metadata_sha256': hashlib.sha256(canonical(
                [merged[key] for key in expected_ids]).encode()).hexdigest(),
            'executed_selection_formula': 'policy_loss + 0.5*log1p(max(0,value_loss))',
            'recorded_formula_labels_preserved': sorted(formula_labels),
            'formula_label_is_not_authoritative_for_executed_scoring': True}


def load_window(path, expected_sha):
    import torch
    require(sha(path) == expected_sha, f'checkpoint hash mismatch: {path}')
    checkpoint = torch.load(path, map_location='cpu', weights_only=False)
    require(sha(path) == expected_sha, 'checkpoint changed while reading')
    config = checkpoint['config']
    active = [metadata(row) for row in checkpoint['pool_snapshots']]
    require(canonical(active) == canonical(checkpoint['pool_active_metadata']),
            'pool metadata differs from serialized snapshots')
    return {'iteration': int(checkpoint['iteration']), 'snapshot_every': int(config['snapshot_every']),
            'history_limit': int(config['pool_history_limit']), 'run_id': config['run_id'],
            'strategy': config['pool_strategy'], 'history': checkpoint['pool_candidate_history'],
            'active': active}


def main():
    import torch
    torch.set_num_threads(1)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    require(not args.out.exists(), 'refusing to overwrite existing evidence')
    audit_path = BASE / 'training_audit.json'
    require(sha(audit_path) == ORIGINAL_SHA, 'original failed audit changed')
    original = json.loads(audit_path.read_text())
    hashes = {str(audit_path): ORIGINAL_SHA, str(Path(__file__).resolve()): sha(__file__),
              str(ROOT / 'scripts/alpha_holdem/train_v5.py'): sha(ROOT / 'scripts/alpha_holdem/train_v5.py')}
    require(hashes[str(ROOT / 'scripts/alpha_holdem/train_v5.py')]
            == '594f1de70f9a6abdf8076fe129a18056b5a3bd84087ad4f6cc2f1498850a6956',
            'original production source changed')
    results = []
    for run in original['runs']:
        require(run['gates']['dynamic_pool_healthy'] is False, 'unexpected original pool gate')
        specs = [(Path(run['parent']['path']), run['parent']['sha256'])]
        specs += [(Path(row['path']), row['sha256']) for row in run['archives']]
        specs += [(Path(run['run_dir']) / 'latest.pt', run['hashes']['checkpoint'])]
        windows = [load_window(path, digest) for path, digest in specs]
        hashes.update({str(path): digest for path, digest in specs})
        run_dir = Path(run['run_dir'])
        raw = []
        for key, name in (('metrics', 'h1_training_metrics.jsonl'),
                          ('assignments', 'opponent_assignments.jsonl')):
            path = run_dir / name
            require(sha(path) == run['hashes'][key], 'raw evidence hash mismatch')
            hashes[str(path)] = run['hashes'][key]
            raw.append([json.loads(line) for line in path.read_text().splitlines() if line.strip()])
        result = verify_windows(windows, *raw)
        result['name'] = run['name']
        result['checkpoint_sha256'] = run['hashes']['checkpoint']
        results.append(result)
        print(json.dumps({'name': run['name'], 'passed': True,
                          'new_candidates': result['new_candidates_reconstructed'],
                          'evicted': result['new_candidates_evicted_from_final']}), flush=True)
    require([row['name'] for row in results] == ['seed1', 'seed2', 'seed3'], 'all original seeds required')
    for path, digest in hashes.items():
        require(sha(path) == digest, 'input changed during replay')
    output = {'schema': 'cardpilot.static4m.capped_pool_window_audit.v1', 'passed': True,
              'new_training_hands': 0, 'new_evaluation_hands': 0, 'runs': results, 'input_sha256': hashes,
              'original_pool_failures_preserved': True, 'full_mechanics_qualified_by_this_report': False,
              'automatic_evaluation_or_scaling_authorized': False,
              'finding': 'Final-only audit required all new candidates although retention is capped; archives reconstruct full history and exact pool selection.'}
    with args.out.open('x', encoding='utf-8') as handle:
        json.dump(output, handle, indent=2, allow_nan=False)
        handle.write('\n')


if __name__ == '__main__':
    main()
