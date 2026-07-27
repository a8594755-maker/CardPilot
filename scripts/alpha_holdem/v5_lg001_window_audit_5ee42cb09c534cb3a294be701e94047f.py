#!/usr/bin/env python3
"""Read-only fail-closed training-window auditor for registered LG001 checkpoints."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import torch
import train_v5_hybrid_h1 as trainer


def canonical_record_hash(record: dict) -> str:
    unsigned = dict(record)
    unsigned.pop('record_sha256', None)
    payload = json.dumps(unsigned, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def audit(checkpoint_path: Path, provenance_path: Path, arm: str, stage: str) -> dict:
    errors = []
    checkpoint_path = checkpoint_path.resolve()
    provenance_path = provenance_path.resolve()
    expected_dir = trainer.LG001_STAGE_PATHS.get((arm, stage))
    if expected_dir is None:
        errors.append('unregistered arm/stage')
    elif checkpoint_path != (expected_dir / 'latest.pt').resolve():
        errors.append('checkpoint path mismatch')
    if expected_dir is not None and provenance_path != (expected_dir / 'opponent_assignment_provenance.jsonl').resolve():
        errors.append('provenance path mismatch')
    if not checkpoint_path.is_file():
        errors.append('checkpoint absent')
    if not provenance_path.is_file():
        errors.append('provenance absent')
    if errors:
        return {'overall': 'FAIL_CLOSED', 'errors': errors, 'checks_passed': 0, 'checks_total': 24}

    checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
    contract = checkpoint.get('lg001') or {}
    if contract.get('registration_token') != trainer.LG001_REGISTRATION_TOKEN:
        errors.append('registration token mismatch')
    if contract.get('preregistration_sha256') != trainer.LG001_PREREGISTRATION_SHA256:
        errors.append('preregistration mismatch')
    if contract.get('source_checkpoint_sha256') != trainer.LG001_SOURCE_SHA256:
        errors.append('source lineage mismatch')
    if contract.get('arm') != arm or contract.get('stage') != stage:
        errors.append('arm/stage mismatch')
    if checkpoint.get('env_version') != 'v55' or checkpoint.get('obs_version') != 'v55':
        errors.append('environment/observation mismatch')
    if checkpoint.get('action_space_version') != '9slot_v5':
        errors.append('action-space mismatch')
    if checkpoint.get('critic_contract') != 'critic_v1' or checkpoint.get('value_coef') != 0.5:
        errors.append('critic contract mismatch')
    if 'optimizer' not in checkpoint:
        errors.append('optimizer missing')

    target = trainer.LG001_STAGE_TARGETS[stage]
    total_hands = int(checkpoint.get('total_hands', -1))
    if not target <= total_hands <= target + 50_000:
        errors.append('endpoint hand count outside registered interval')
    try:
        members = trainer.lg001_validate_frozen_pool(checkpoint.get('pool_snapshots') or [])
    except Exception as exc:
        members = []
        errors.append(f'frozen pool invalid: {exc}')
    if contract.get('pool_members') != members:
        errors.append('embedded pool member identities mismatch')
    expected_weights = {
        str(member_id): trainer.LG001_CONDITIONAL_WEIGHTS[arm][member_id]
        for member_id in trainer.LG001_MEMBER_ORDER
    }
    if contract.get('conditional_pool_weights') != expected_weights:
        errors.append('weight vector mismatch')
    if contract.get('assignment_seed') != trainer.LG001_ASSIGNMENT_SEED:
        errors.append('assignment seed mismatch')

    previous = None
    previous_iteration = None
    if stage == 'stage_b':
        parent_path = trainer.LG001_STAGE_PATHS[('treatment_diversity', 'stage_a')] / 'latest.pt'
        if Path(checkpoint.get('lineage_parent_checkpoint', '')).resolve() != parent_path.resolve():
            errors.append('Stage B lineage parent path mismatch')
        elif not parent_path.is_file():
            errors.append('Stage B lineage parent absent')
        else:
            parent = torch.load(parent_path, map_location='cpu', weights_only=False)
            parent_contract = parent.get('lg001') or {}
            previous = parent_contract.get('provenance_tail_sha256')
            previous_iteration = parent_contract.get('provenance_tail_iteration')
            if not previous or previous_iteration is None:
                errors.append('Stage B lineage parent provenance tail missing')
    lines = [line for line in provenance_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not lines:
        errors.append('provenance empty')
    for line_number, line in enumerate(lines, 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f'provenance line {line_number} invalid JSON: {exc}')
            break
        if record.get('record_sha256') != canonical_record_hash(record):
            errors.append(f'provenance line {line_number} hash mismatch')
        if record.get('previous_record_sha256') != previous:
            errors.append(f'provenance line {line_number} previous hash mismatch')
        applies = int(record.get('applies_to_iteration', -1))
        if previous_iteration is not None and applies != previous_iteration + 1:
            errors.append(f'provenance line {line_number} iteration discontinuity')
        lg = record.get('lg001') or {}
        try:
            expected = trainer.lg001_select_opponent(
                arm, applies, checkpoint['pool_snapshots'], validated_members=members,
            )
        except Exception as exc:
            errors.append(f'provenance line {line_number} assignment recompute failed: {exc}')
            expected = None
        if expected is not None and lg != expected:
            errors.append(f'provenance line {line_number} deterministic assignment mismatch')
        worker_indices = {int(row['opponent']['local_index']) for row in record.get('workers', [])}
        if expected is not None and worker_indices != {int(expected['local_index'])}:
            errors.append(f'provenance line {line_number} workers not on registered shared assignment')
        previous = record.get('record_sha256')
        previous_iteration = applies
    if contract.get('provenance_tail_sha256') != previous:
        errors.append('checkpoint provenance tail hash mismatch')
    if contract.get('provenance_tail_iteration') != previous_iteration:
        errors.append('checkpoint provenance tail iteration mismatch')
    if previous_iteration != int(checkpoint.get('iteration', -1)):
        errors.append('provenance tail does not match checkpoint iteration')

    total = 24
    return {
        'schema_version': 'v5.lg001.window_audit.v1',
        'overall': 'PASS' if not errors else 'FAIL_CLOSED',
        'errors': errors,
        'checks_passed': total - min(total, len(errors)),
        'checks_total': total,
        'checkpoint_sha256': trainer.lg001_file_sha256(checkpoint_path),
        'arm': arm,
        'stage': stage,
        'total_hands': total_hands,
        'iteration': int(checkpoint.get('iteration', -1)),
        'provenance_records': len(lines),
        'provenance_tail_sha256': previous,
        'files_written': 0,
        'strength_claim': 'NONE',
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--provenance', type=Path, required=True)
    parser.add_argument('--arm', choices=tuple(trainer.LG001_CONDITIONAL_WEIGHTS), required=True)
    parser.add_argument('--stage', choices=('stage_a', 'stage_b'), required=True)
    args = parser.parse_args()
    result = audit(args.checkpoint, args.provenance, args.arm, args.stage)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['overall'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
