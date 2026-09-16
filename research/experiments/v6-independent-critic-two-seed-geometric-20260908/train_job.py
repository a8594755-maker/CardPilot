"""Qualified network/trainer with exact per-job input and initial payload gates."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import torch

BASE = Path(__file__).resolve().parent
QUAL = BASE.parent / 'v6-independent-observable-critic-qualification-20260908'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--resume', type=Path, required=True)
    args, _ = parser.parse_known_args()
    contract = json.loads((args.run_dir/'job_contract.json').read_text())
    for filename, expected in contract['sources'].items():
        with Path(filename).open('rb') as handle:
            assert hashlib.file_digest(handle, 'sha256').hexdigest() == expected
    assert args.resume.resolve() == Path(contract['parent']).resolve()
    with args.resume.open('rb') as handle:
        assert hashlib.file_digest(handle, 'sha256').hexdigest() == contract['parent_sha256']
    sys.path.insert(0, str(QUAL))
    wrapper = load('production_qualified_wrapper', QUAL/'train_candidate.py')
    trainer, binding = wrapper.install()
    equal = load('production_state_equal', BASE.parent/
        'v6-preflop-actor-trunk-route-qualification-20260906/route_transfer.py').equal_tree
    from derive_capture_check_v2 import verify
    parent = torch.load(args.resume, map_location='cpu', weights_only=False)
    original_save = trainer.atomic_torch_save
    captured = False

    def save(payload, path):
        nonlocal parent, captured
        if not captured:
            target = bool(payload['config'].get('independent_observable_critic', False))
            assert target == (contract['arm'] == 'independent')
            prior = bool(parent['config'].get('independent_observable_critic', False))
            if target and not prior:
                verify(parent, payload, equal)
                mode = 'declared-first-derivation'
            else:
                keys = ['model','optimizer','total_hands','iteration','ppo_replay_entries',
                        'ppo_replay_rng_state','ppo_replay_cumulative_rows','ppo_replay_recovery_boundaries',
                        'pool_snapshots','pool_strategy','pool_active_metadata','pool_candidate_history',
                        'assignment_replay_origin']
                for key in keys:
                    assert equal(parent[key], payload[key]), key
                mode = 'exact-existing-state-statistical-worker-resume'
            for key in ('adaptive_opponent_ema_rewards','adaptive_opponent_weights','adaptive_opponent_observations'):
                assert equal(parent.get(key), payload.get(key)), key
            assert parent['environment_hand_accounting']['completed_hands'] == payload['environment_hand_accounting']['completed_hands']
            assert parent['fixed_deal_attempt']['receipt']['namespace'] != payload['fixed_deal_attempt']['receipt']['namespace']
            initial = args.run_dir/'initial_resume.pt'
            assert not initial.exists()
            original_save(payload, initial)
            with initial.open('rb') as handle:
                digest = hashlib.file_digest(handle, 'sha256').hexdigest()
            with (args.run_dir/'initial_gate.json').open('x', encoding='utf-8') as handle:
                json.dump({'passed': True,'mode':mode,'sha256':digest,
                           'namespace':payload['fixed_deal_attempt']['receipt']['namespace']}, handle, indent=2)
            parent = None
            captured = True
        return original_save(payload, path)

    trainer.atomic_torch_save = save
    print(json.dumps(binding), flush=True)
    trainer.mp.set_start_method('spawn')
    trainer.main()
    assert captured


if __name__ == '__main__':
    main()
