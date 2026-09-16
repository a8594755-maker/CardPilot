"""Independent final-state review; explicitly does not claim initial-save audit."""
import hashlib
import json
import math
from pathlib import Path
import sys

import torch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / 'v6-preflop-actor-trunk-route-qualification-20260906/candidate/scripts'))


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    folder = BASE / 'seed1_first_smoke'
    assert read(folder / 'terminal_process.json')['returncode'] == 0
    contract = read(folder / 'input_contract.json')
    for filename, digest in contract['sources'].items():
        assert sha(Path(filename)) == digest
    parent_path = Path(contract['parent'])
    assert sha(parent_path) == contract['parent_sha256']
    for name, info in contract['prefixes'].items():
        with (folder / name).open('rb') as handle:
            assert hashlib.sha256(handle.read(info['bytes'])).hexdigest() == info['sha256']
    parent = torch.load(parent_path, map_location='cpu', weights_only=False)
    final = torch.load(folder / 'latest.pt', map_location='cpu', weights_only=False)
    assert final['config']['independent_observable_critic'] is True
    assert final['observable_critic_contract'] == 'observable_value_encoder.v1'
    assert final['iteration'] == parent['iteration'] + 2
    new_hands = final['environment_hand_accounting']['completed_hands'] - contract['initial_physical_hands']
    assert new_hands >= 8192
    prefix = 'observable_value_encoder.'
    added = [k for k in final['model'] if k.startswith(prefix)]
    assert added and all(torch.isfinite(v).all() for v in final['model'].values())
    assert any(not torch.equal(final['model'][k], parent['model'][k[len(prefix):]]) for k in added)
    old_group = parent['optimizer']['param_groups'][0]
    new_group = final['optimizer']['param_groups'][0]
    assert all(v == new_group[k] for k, v in old_group.items() if k != 'params')
    assert new_group['params'][:len(old_group['params'])] == old_group['params']
    old_steps = {str(k): int(final['optimizer']['state'][k]['step'] - v['step'])
                 for k, v in parent['optimizer']['state'].items()}
    rows = [json.loads(line) for line in (folder / 'h1_training_metrics.jsonl').read_text().splitlines()]
    suffix = [r for r in rows if r['iteration'] > parent['iteration']]
    expected_steps = sum(math.ceil(r['policy_rows'] / final['config']['mini_batch_size'])
                         * r['ppo_epochs_completed'] for r in suffix)
    assert set(old_steps.values()) == {expected_steps}
    new_ids = set(final['optimizer']['state']) - set(parent['optimizer']['state'])
    assert len(new_ids) == len(added)
    assert all(final['optimizer']['state'][k]['step'].item() == expected_steps for k in new_ids)
    assert len(final['ppo_replay_entries']) == 2
    assert [e['iteration'] for e in final['ppo_replay_entries']] == [3808, 3809]
    assert final['fixed_deal_attempt']['receipt']['namespace'] != parent['fixed_deal_attempt']['receipt']['namespace']
    assert [r['iteration'] for r in suffix] == [3808, 3809]
    report = {'passed_final_state_checks': True, 'new_physical_hands': new_hands,
        'new_transition_hands': final['total_hands'] - parent['total_hands'],
        'new_replay_rows': sum(r['ppo_replay_rows'] for r in suffix),
        'checkpoint_sha256': sha(folder / 'latest.pt'), 'new_encoder_parameters': len(added),
        'old_optimizer_step_deltas': old_steps, 'new_optimizer_steps': expected_steps,
        'namespace': final['fixed_deal_attempt']['receipt']['namespace'],
        'limitations': 'Initial resume save was overwritten by later normal saves; no separately retained initial checkpoint. Existing unit/real-parent tests and final steps do not replace an actual initial payload audit. Extended restart must capture initial payload before new updates.'}
    with (folder / 'final_review.json').open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps({k:v for k,v in report.items() if k != 'old_optimizer_step_deltas'}))


if __name__ == '__main__':
    main()
