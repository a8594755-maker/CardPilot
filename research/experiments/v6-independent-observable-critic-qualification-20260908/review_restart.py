"""Reopen initial payload independently, then review extended worker result."""
import hashlib
import json
import math
from pathlib import Path
import sys

import torch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from check_parents import module
from run_smoke import sha, write_new


def read(path):
    return json.loads(path.read_text())


def main():
    folder = BASE / 'seed1_extended_restart'
    assert read(folder / 'terminal_process.json')['returncode'] == 0
    contract = read(folder / 'capture_contract.json')
    for filename, expected in contract['sources'].items():
        assert sha(Path(filename)) == expected
    capture = read(folder / 'initial_capture.json')
    assert sha(folder / 'initial_resume.pt') == capture['sha256']
    transfer = module('restart_tree_equality', BASE.parent /
        'v6-preflop-actor-trunk-route-qualification-20260906/route_transfer.py')
    parent_path = BASE / 'seed1_first_smoke/latest.pt'
    assert sha(parent_path) == contract['parent_sha256']
    parent = torch.load(parent_path, map_location='cpu', weights_only=False)
    initial = torch.load(folder / 'initial_resume.pt', map_location='cpu', weights_only=False)
    final = torch.load(folder / 'latest.pt', map_location='cpu', weights_only=False)
    for key in capture['exact_fields']:
        assert transfer.equal_tree(initial[key], parent[key]), key
    for name, info in contract['prefixes'].items():
        with (folder / name).open('rb') as handle:
            assert hashlib.sha256(handle.read(info['bytes'])).hexdigest() == info['sha256']
    rows = [json.loads(line) for line in (folder / 'h1_training_metrics.jsonl').read_text().splitlines()]
    rows = [r for r in rows if r['iteration'] > parent['iteration']]
    assert [r['iteration'] for r in rows] == list(range(parent['iteration']+1, final['iteration']+1))
    steps = sum(math.ceil(r['policy_rows']/final['config']['mini_batch_size'])*r['ppo_epochs_completed'] for r in rows)
    assert steps > 0
    assert final['optimizer']['state'].keys() == parent['optimizer']['state'].keys()
    for key, state in parent['optimizer']['state'].items():
        assert int(final['optimizer']['state'][key]['step']-state['step']) == steps
    assert final['optimizer']['param_groups'] == parent['optimizer']['param_groups']
    assert all(torch.isfinite(v).all() for v in final['model'].values())
    assert any(not torch.equal(v, parent['model'][k]) for k,v in final['model'].items() if k.startswith('observable_value_encoder.'))
    namespace = final['fixed_deal_attempt']['receipt']['namespace']
    assert namespace == capture['namespace'] != parent['fixed_deal_attempt']['receipt']['namespace']
    new_hands = final['environment_hand_accounting']['completed_hands']-contract['initial_physical_hands']
    assert new_hands >= contract['target_new_hands']
    assert initial['environment_hand_accounting']['completed_hands'] == contract['initial_physical_hands']
    report = {'passed': True, 'new_physical_hands': new_hands,
        'new_transition_hands': final['total_hands']-parent['total_hands'],
        'new_replay_rows': sum(r['ppo_replay_rows'] for r in rows),
        'retained_optimizer_states': len(parent['optimizer']['state']), 'step_delta': steps,
        'exact_initial_fields': capture['exact_fields'], 'namespace': namespace,
        'checkpoint_sha256': sha(folder / 'latest.pt'), 'initial_sha256': capture['sha256'],
        'limitations': 'Statistical managed continuation, not bitwise worker RNG equivalence. No strength evaluation.'}
    write_new(folder / 'restart_review.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
