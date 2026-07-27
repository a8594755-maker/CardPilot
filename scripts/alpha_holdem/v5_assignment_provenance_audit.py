#!/usr/bin/env python3
"""Fail-closed audit of hash-chained opponent assignment provenance JSONL."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def record_sha256(record: dict[str, Any]) -> str:
    base = {key: value for key, value in record.items() if key != 'record_sha256'}
    canonical = json.dumps(base, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def check_record(record: dict[str, Any], *, expected_run_id: str,
                 expected_mode: str, expected_workers: int,
                 expected_groups: int, expected_worker_seed_base: int,
                 previous_sha: str | None, previous_iteration: int | None) -> list[str]:
    errors: list[str] = []
    if record.get('schema_version') != 'v5.opponent_assignment_provenance.v1':
        errors.append('schema_version mismatch')
    if record.get('run_id') != expected_run_id:
        errors.append('run_id mismatch')
    if record.get('assignment_mode') != expected_mode:
        errors.append('assignment_mode mismatch')
    if int(record.get('worker_count', -1)) != expected_workers:
        errors.append('worker_count mismatch')
    if record.get('worker_seed_base') != expected_worker_seed_base:
        errors.append('worker_seed_base mismatch')
    if record.get('previous_record_sha256') != previous_sha:
        errors.append('hash-chain predecessor mismatch')
    if record.get('record_sha256') != record_sha256(record):
        errors.append('record_sha256 mismatch')
    iteration = int(record.get('applies_to_iteration', -1))
    if previous_iteration is not None and iteration != previous_iteration + 1:
        errors.append('iteration sequence is not contiguous')

    workers = record.get('workers') if isinstance(record.get('workers'), list) else []
    worker_ids = sorted(int(item.get('worker_id', -1)) for item in workers if isinstance(item, dict))
    if worker_ids != list(range(expected_workers)):
        errors.append('worker coverage mismatch')
    refs = record.get('pool_snapshot_refs') if isinstance(record.get('pool_snapshot_refs'), list) else []
    ref_by_local = {int(item['local_index']): item for item in refs if isinstance(item, dict)}
    for item in workers:
        opponent = item.get('opponent') if isinstance(item, dict) else None
        if not isinstance(opponent, dict):
            errors.append('worker opponent missing')
            continue
        if opponent.get('kind') == 'pool_snapshot':
            local = int(opponent.get('local_index', -1))
            ref = ref_by_local.get(local)
            if ref is None or int(ref.get('snapshot_id', -1)) != int(opponent.get('snapshot_id', -2)):
                errors.append('resolved pool snapshot mismatch')

    groups = record.get('group_metadata') if isinstance(record.get('group_metadata'), list) else []
    if expected_mode == 'per-iteration':
        if len(groups) != 1 or len(groups[0].get('workers', [])) != expected_workers:
            errors.append('per-iteration group shape mismatch')
        assigned = {item['opponent'].get('local_index') for item in workers if isinstance(item, dict)}
        if len(assigned) != 1:
            errors.append('per-iteration workers do not share one opponent')
    elif expected_mode == 'per-group':
        if len(groups) != expected_groups:
            errors.append('per-group group count mismatch')
        members = [int(worker) for group in groups for worker in group.get('workers', [])]
        if sorted(members) != list(range(expected_workers)):
            errors.append('per-group worker partition mismatch')
        sizes = [len(group.get('workers', [])) for group in groups]
        if sizes and max(sizes) - min(sizes) > 1:
            errors.append('per-group sizes are unbalanced')
        self_play_groups = [group for group in groups if int(group.get('opponent_id', 0)) == -1]
        if len(self_play_groups) != 1:
            errors.append('per-group requires exactly one self-play group')
        pool_groups = [group for group in groups if int(group.get('opponent_id', -1)) >= 0]
        local_ids = [int(group.get('opponent_id')) for group in pool_groups]
        if len(refs) >= len(pool_groups) and len(set(local_ids)) != len(local_ids):
            errors.append('pool groups are not distinct despite sufficient pool')
    return errors


def audit(path: Path, *, expected_run_id: str, expected_mode: str,
          expected_workers: int, expected_groups: int,
          expected_worker_seed_base: int, expected_first_iteration: int,
          expected_last_iteration: int | None) -> dict[str, Any]:
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except Exception as exc:  # noqa: BLE001
                errors.append(f'line {line_number}: invalid JSON: {exc}')
    except Exception as exc:  # noqa: BLE001
        errors.append(f'cannot read provenance: {exc}')

    previous_sha = None
    previous_iteration = None
    for index, record in enumerate(records):
        row_errors = check_record(
            record,
            expected_run_id=expected_run_id,
            expected_mode=expected_mode,
            expected_workers=expected_workers,
            expected_groups=expected_groups,
            expected_worker_seed_base=expected_worker_seed_base,
            previous_sha=previous_sha,
            previous_iteration=previous_iteration,
        )
        errors.extend(f'record {index}: {message}' for message in row_errors)
        previous_sha = record.get('record_sha256')
        previous_iteration = int(record.get('applies_to_iteration', -1))
    if not records:
        errors.append('no provenance records')
    else:
        first = int(records[0].get('applies_to_iteration', -1))
        last = int(records[-1].get('applies_to_iteration', -1))
        if first != expected_first_iteration:
            errors.append(f'first iteration {first} != expected {expected_first_iteration}')
        if expected_last_iteration is not None and last != expected_last_iteration:
            errors.append(f'last iteration {last} != expected {expected_last_iteration}')
    return {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'overall': 'PASS' if not errors else 'FAIL',
        'path': str(path),
        'file_sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
        'record_count': len(records),
        'first_iteration': records[0].get('applies_to_iteration') if records else None,
        'last_iteration': records[-1].get('applies_to_iteration') if records else None,
        'tail_record_sha256': previous_sha,
        'errors': errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--provenance-jsonl', required=True)
    parser.add_argument('--expected-run-id', required=True)
    parser.add_argument('--expected-mode', choices=('per-iteration', 'per-group'), required=True)
    parser.add_argument('--expected-workers', type=int, required=True)
    parser.add_argument('--expected-groups', type=int, default=5)
    parser.add_argument('--expected-worker-seed-base', type=int, required=True)
    parser.add_argument('--expected-first-iteration', type=int, required=True)
    parser.add_argument('--expected-last-iteration', type=int)
    parser.add_argument('--out-json', required=True)
    args = parser.parse_args()
    payload = audit(
        Path(args.provenance_jsonl),
        expected_run_id=args.expected_run_id,
        expected_mode=args.expected_mode,
        expected_workers=args.expected_workers,
        expected_groups=args.expected_groups,
        expected_worker_seed_base=args.expected_worker_seed_base,
        expected_first_iteration=args.expected_first_iteration,
        expected_last_iteration=args.expected_last_iteration,
    )
    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload['overall'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
