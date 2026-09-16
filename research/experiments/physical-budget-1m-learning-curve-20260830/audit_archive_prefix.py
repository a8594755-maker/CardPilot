"""Read-only integrity audit of an immutable archive, not a terminal run audit."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/alpha_holdem'))
from train_v5 import restore_group_assignment_rng_from_evidence, validate_environment_hand_accounting
import random


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise RuntimeError('Refusing to overwrite prefix evidence')
    checkpoint_path = args.checkpoint.resolve()
    source_path = ROOT / 'models/baseline/standard10/latest.pt'
    source_hash = sha(source_path)
    assert source_hash == '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
    checkpoint_hash = sha(checkpoint_path)
    checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
    source = torch.load(source_path, map_location='cpu', weights_only=False)
    iteration = int(checkpoint['iteration'])
    run = checkpoint_path.parent.parent
    rows = [json.loads(line) for line in (run / 'h1_training_metrics.jsonl').read_text().splitlines()]
    rows = [r for r in rows if int(r['iteration']) <= iteration]
    assert [int(r['iteration']) for r in rows] == list(range(1, iteration + 1))
    physical = [int(r['environment_hand_accounting']['completed_hands']) for r in rows]
    assert all(b > a for a, b in zip(physical, physical[1:]))
    accounting = checkpoint['environment_hand_accounting']
    validate_environment_hand_accounting(accounting)
    assert accounting['prefix_complete'] and accounting['completed_hands'] == physical[-1]
    assert checkpoint['total_hands'] == rows[-1]['hands']
    assert checkpoint['config']['total_environment_hands'] == 1048576
    assert checkpoint['config']['all_policy_heads_only_training']
    assert checkpoint['run_id'] == 'physical_budget_1m_20260830'
    trainable_prefixes = ('policy_head.', 'preflop_policy_head.', 'value_head.')
    frozen = [name for name in source['model'] if not name.startswith(trainable_prefixes)]
    assert all(torch.equal(source['model'][name], checkpoint['model'][name]) for name in frozen)
    changed_heads = [name for name, value in checkpoint['model'].items()
                     if name.startswith(trainable_prefixes) and
                     (name not in source['model'] or not torch.equal(value, source['model'][name]))]
    assert any(name.startswith('policy_head.') for name in changed_heads)
    assert any(name.startswith('preflop_policy_head.') for name in changed_heads)
    assert any(name.startswith('value_head.') for name in changed_heads)
    assert all(torch.isfinite(value).all() for value in checkpoint['model'].values())
    steps = [int(value['step']) for value in checkpoint['optimizer']['state'].values()]
    assert len(steps) == 10 and min(steps) > 0 and min(steps) == max(steps)
    assignments = [json.loads(line) for line in (run / 'opponent_assignments.jsonl').read_text().splitlines()]
    assignments = [r for r in assignments if int(r['applies_to_iteration']) <= iteration]
    config = checkpoint['config']
    pool_ids = [int(r['id']) for r in checkpoint['pool_snapshots']]
    assignment_audit = restore_group_assignment_rng_from_evidence(
        assignments, rows, rng=random.Random(0), seed=int(config['seed']),
        worker_count=int(config['workers']), pool_size=len(pool_ids), pool_snapshot_ids=pool_ids,
        group_count=int(config['opponent_groups']), self_play_fraction=float(config['self_play_fraction']),
        checkpoint_iteration=iteration, checkpoint_total_hands=checkpoint['total_hands'])
    assert assignment_audit['tail_iteration'] == iteration
    assert assignment_audit['pending_assignments'] is None
    assert sha(checkpoint_path) == checkpoint_hash and sha(source_path) == source_hash
    result = dict(status='PASS', scope='immutable_archive_prefix_not_final_session',
                  checkpoint=str(checkpoint_path), checkpoint_sha256=checkpoint_hash,
                  source_sha256=source_hash, iteration=iteration,
                  physical_hands=accounting['completed_hands'], legacy_marker_hands=checkpoint['total_hands'],
                  frozen_tensors_unchanged=len(frozen), changed_head_tensors=changed_heads,
                  optimizer_state_entries=len(steps), optimizer_step=min(steps), assignment_audit=assignment_audit,
                  max_reference_kl=max(r['reference_policy_kl'] for r in rows),
                  kl_stop_count=sum(r.get('kl_early_stop_triggered', False) for r in rows))
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
