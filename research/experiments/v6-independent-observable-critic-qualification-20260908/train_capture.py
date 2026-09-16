"""Same trainer, with a separately preserved and checked first resume payload."""
import argparse
import hashlib
import json
from pathlib import Path

import torch

from train_candidate import install
from check_parents import module

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--resume', type=Path, required=True)
    args, _ = parser.parse_known_args()
    contract = json.loads((args.run_dir / 'capture_contract.json').read_text())
    for filename, expected in contract['sources'].items():
        with Path(filename).open('rb') as handle:
            assert hashlib.file_digest(handle, 'sha256').hexdigest() == expected
    with args.resume.open('rb') as handle:
        assert hashlib.file_digest(handle, 'sha256').hexdigest() == contract['parent_sha256']
    trainer, binding = install()
    transfer = module('capture_equal_tree', BASE.parent /
        'v6-preflop-actor-trunk-route-qualification-20260906/route_transfer.py')
    parent = torch.load(args.resume, map_location='cpu', weights_only=False)
    original_save = trainer.atomic_torch_save
    captured = False

    def save(payload, path):
        nonlocal captured, parent
        if not captured:
            keys = ['model', 'optimizer', 'iteration', 'total_hands', 'ppo_replay_entries',
                    'ppo_replay_rng_state', 'ppo_replay_cumulative_rows',
                    'ppo_replay_recovery_boundaries', 'pool_snapshots', 'pool_strategy',
                    'pool_active_metadata', 'pool_candidate_history', 'assignment_replay_origin']
            for key in keys:
                if not transfer.equal_tree(payload[key], parent[key]):
                    raise ValueError('initial payload mismatch: ' + key)
            assert payload['environment_hand_accounting']['completed_hands'] == parent['environment_hand_accounting']['completed_hands']
            assert payload['fixed_deal_attempt']['receipt']['namespace'] != parent['fixed_deal_attempt']['receipt']['namespace']
            initial = args.run_dir / 'initial_resume.pt'
            if initial.exists():
                raise ValueError('initial capture already exists')
            original_save(payload, initial)
            with initial.open('rb') as handle:
                digest = hashlib.file_digest(handle, 'sha256').hexdigest()
            with (args.run_dir / 'initial_capture.json').open('x', encoding='utf-8') as handle:
                json.dump({'passed': True, 'exact_fields': keys, 'sha256': digest,
                           'namespace': payload['fixed_deal_attempt']['receipt']['namespace']}, handle, indent=2)
            captured = True
            parent = None
        return original_save(payload, path)

    trainer.atomic_torch_save = save
    print(json.dumps(binding), flush=True)
    trainer.mp.set_start_method('spawn')
    trainer.main()
    if not captured:
        raise ValueError('initial save was not captured')


if __name__ == '__main__':
    main()
