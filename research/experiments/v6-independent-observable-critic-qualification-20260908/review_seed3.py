"""Independently reopen first-derivation payload and completed worker evidence."""
import hashlib
import json
import math
from pathlib import Path

import torch

from check_parents import module
from run_smoke import sha, write_new
from derive_capture_check_v2 import verify

BASE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def main():
    folder = BASE / 'seed3_first_capture_v2'
    assert read(folder/'terminal_process.json')['returncode'] == 0
    contract = read(folder/'capture_contract.json')
    for name, digest in contract['sources'].items():
        assert sha(Path(name)) == digest
    transfer = module('seed3_capture_equality', BASE.parent /
        'v6-preflop-actor-trunk-route-qualification-20260906/route_transfer.py')
    parent_path = BASE.parent / 'v6-fixed-regimen-two-seed-2m-20260908/seed3_control_stage1/latest.pt'
    assert sha(parent_path) == contract['parent_sha256']
    capture = read(folder/'initial_capture.json')
    assert sha(folder/'initial_resume.pt') == capture['sha256']
    parent = torch.load(parent_path, map_location='cpu', weights_only=False)
    initial = torch.load(folder/'initial_resume.pt', map_location='cpu', weights_only=False)
    final = torch.load(folder/'latest.pt', map_location='cpu', weights_only=False)
    verify(parent, initial, transfer.equal_tree)
    for name, info in contract['prefixes'].items():
        with (folder/name).open('rb') as handle:
            assert hashlib.sha256(handle.read(info['bytes'])).hexdigest() == info['sha256']
    rows = [json.loads(line) for line in (folder/'h1_training_metrics.jsonl').read_text().splitlines()]
    rows = [r for r in rows if r['iteration'] > parent['iteration']]
    assert [r['iteration'] for r in rows] == list(range(parent['iteration']+1, final['iteration']+1))
    steps = sum(math.ceil(r['policy_rows']/final['config']['mini_batch_size'])*r['ppo_epochs_completed'] for r in rows)
    for key, state in parent['optimizer']['state'].items():
        assert int(final['optimizer']['state'][key]['step'] - state['step']) == steps
    new = set(final['optimizer']['state']) - set(parent['optimizer']['state'])
    assert len(new) == 76 and steps > 0
    assert all(final['optimizer']['state'][k]['step'].item() == steps for k in new)
    assert final['optimizer']['param_groups'] == initial['optimizer']['param_groups']
    assert all(torch.isfinite(v).all() for v in final['model'].values())
    assert any(not torch.equal(v, initial['model'][k]) for k,v in final['model'].items() if k.startswith('observable_value_encoder.'))
    assert final['fixed_deal_attempt']['receipt']['namespace'] == capture['namespace']
    physical = final['environment_hand_accounting']['completed_hands']-contract['initial_physical_hands']
    assert physical >= contract['target_new_hands']
    report = {'passed': True, 'new_physical_hands': physical,
        'new_transition_hands': final['total_hands']-parent['total_hands'],
        'new_replay_rows': sum(r['ppo_replay_rows'] for r in rows),
        'step_delta': steps, 'new_encoder_parameters': 76,
        'checkpoint_sha256': sha(folder/'latest.pt'), 'initial_sha256': capture['sha256'],
        'namespace': capture['namespace'], 'strength_evaluation_hands': 0}
    write_new(folder/'derivation_review.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
