"""Actual initial architecture derivation invariants, reusable by independent review."""
import torch


def verify(parent, initial, equal):
    prefix = 'observable_value_encoder.'
    added = {k:v for k,v in initial['model'].items() if k.startswith(prefix)}
    assert len(added) == 76
    assert equal({k:v for k,v in initial['model'].items() if not k.startswith(prefix)}, parent['model'])
    for name, value in added.items():
        assert torch.equal(value.cpu(), parent['model'][name[len(prefix):]].cpu())
    assert equal(initial['optimizer']['state'], parent['optimizer']['state'])
    old = parent['optimizer']['param_groups'][0]
    new = initial['optimizer']['param_groups'][0]
    assert all(equal(v, new[k]) for k,v in old.items() if k != 'params')
    assert new['params'][:len(old['params'])] == old['params']
    assert len(new['params']) == len(old['params']) + 76
    keys = ['iteration', 'total_hands', 'ppo_replay_entries', 'ppo_replay_rng_state',
            'ppo_replay_cumulative_rows', 'ppo_replay_recovery_boundaries', 'pool_snapshots',
            'pool_strategy', 'pool_active_metadata', 'pool_candidate_history', 'assignment_replay_origin']
    for key in keys:
        assert equal(parent[key], initial[key]), key
    assert parent['environment_hand_accounting']['completed_hands'] == initial['environment_hand_accounting']['completed_hands']
    assert parent['fixed_deal_attempt']['receipt']['namespace'] != initial['fixed_deal_attempt']['receipt']['namespace']
    return keys
