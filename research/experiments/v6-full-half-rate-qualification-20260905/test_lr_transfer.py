import copy
from collections import deque
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lr_transfer as t

BINDING = {'path': 'fixture.pt', 'sha256': 'a' * 64}


def parent():
    p = torch.nn.Parameter(torch.tensor([1.0, 2.0]))
    opt = torch.optim.Adam([p], lr=1e-4)
    p.grad = torch.tensor([0.3, -0.2])
    opt.step()
    return {'model': {'weight': p.detach().clone()}, 'optimizer': opt.state_dict(),
            'all_policy_heads_only_training': False, 'iteration': 1992,
            'total_hands': 8123, 'environment_hand_accounting': {'completed_hands': 9445556},
            'ppo_replay_entries': deque([{'values': np.array([1.0, 2.0])}]),
            'main_process_rng_state': {'torch': torch.tensor([1, 2], dtype=torch.uint8)},
            'ppo_replay_rng_state': (3, (1, 2, 3), None),
            'opponent_pool_state': {'history': [0, 1, 2]}}


def test_roundtrip_and_no_source_mutation(tmp_path):
    source = parent()
    before = copy.deepcopy(source)
    derived = t.derive(source, BINDING)
    target = tmp_path / 'derived.pt'
    t.save_exclusive(target, derived)
    t.validate_derived(source, torch.load(target, weights_only=False), BINDING)
    assert t.equal_tree(source, before)
    assert derived['optimizer']['param_groups'][0]['lr'] == 5e-5
    with pytest.raises(FileExistsError):
        t.save_exclusive(target, derived)


@pytest.mark.parametrize('field', ['model', 'iteration', 'total_hands', 'environment_hand_accounting',
    'ppo_replay_entries', 'main_process_rng_state', 'ppo_replay_rng_state', 'opponent_pool_state'])
def test_reject_unintended_field(field):
    source = parent()
    derived = copy.deepcopy(t.derive(source, BINDING))
    derived[field] = None
    with pytest.raises(ValueError, match='unintended checkpoint'):
        t.validate_derived(source, derived, BINDING)


@pytest.mark.parametrize('field', ['step', 'exp_avg', 'exp_avg_sq'])
def test_reject_adam_state_change(field):
    source = parent()
    derived = t.derive(source, BINDING)
    derived['optimizer']['state'][0][field].add_(1)
    with pytest.raises(ValueError, match='moments or clocks'):
        t.validate_derived(source, derived, BINDING)


@pytest.mark.parametrize('field,value', [('lr', 1e-4), ('eps', 1e-7), ('params', [1]), ('betas', (0.8, 0.999))])
def test_reject_group_change(field, value):
    source = parent()
    derived = t.derive(source, BINDING)
    derived['optimizer']['param_groups'][0][field] = value
    with pytest.raises(ValueError, match='group change'):
        t.validate_derived(source, derived, BINDING)


@pytest.mark.parametrize('factor', [0.0, 1.0, 2.0, float('nan'), True])
def test_reject_unregistered_factor(factor):
    with pytest.raises(ValueError, match='preregistered'):
        t.derive(parent(), BINDING, factor)


def test_reject_provenance_change():
    source = parent()
    derived = t.derive(source, BINDING)
    derived[t.PROVENANCE]['source_sha256'] = 'b' * 64
    with pytest.raises(ValueError, match='provenance'):
        t.validate_derived(source, derived, BINDING)


def test_reject_missing_state():
    source = parent()
    source['optimizer']['state'].clear()
    with pytest.raises(ValueError, match='mapping'):
        t.derive(source, BINDING)


def test_reject_second_transfer():
    with pytest.raises(ValueError, match='already transformed'):
        t.derive(t.derive(parent(), BINDING), BINDING)
