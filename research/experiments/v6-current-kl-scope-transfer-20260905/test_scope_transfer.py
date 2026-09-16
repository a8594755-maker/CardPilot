import copy
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scope_transfer as s


class Tiny(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.body = torch.nn.Linear(3, 3)
        self.policy_head = torch.nn.Linear(3, 2)
        self.preflop_policy_head = torch.nn.Linear(3, 2)
        self.value_head = torch.nn.Linear(3, 1)


def fixture():
    torch.manual_seed(61)
    model = Tiny()
    selected = [(name, p) for name, p in model.named_parameters() if name.startswith(s.HEAD_PREFIXES)]
    optimizer = torch.optim.Adam([p for _, p in selected], lr=1e-4)
    for index, (_, parameter) in enumerate(selected):
        parameter.grad = torch.full_like(parameter, (index + 1) / 100)
    optimizer.step()
    optimizer.zero_grad(set_to_none=True)
    parent = {'model': copy.deepcopy(model.state_dict()), 'optimizer': copy.deepcopy(optimizer.state_dict()),
        'all_policy_heads_only_training': True, 'iteration': 17, 'total_hands': 65000,
        'ppo_replay_entries': [{'obs': np.arange(9, dtype=np.float32), 'actions': torch.tensor([1, 3])}],
        'main_process_rng_state': {'torch': torch.get_rng_state(), 'numpy': (1, np.arange(4, dtype=np.uint32))}}
    group = parent['optimizer']['param_groups'][0]
    binding = {'path': 'fixture.pt', 'sha256': 'fixture-sha', 'all_parameters': s.parameter_description(model),
        'head_parameter_mapping': [{'id': index, 'name': name, 'shape': list(parameter.shape),
            'step': float(parent['optimizer']['state'][index]['step']), 'dtype': str(parameter.dtype)}
            for index, (name, parameter) in zip(group['params'], selected)],
        'optimizer_group_hyperparameters': {key: value for key, value in group.items() if key != 'params'}}
    return model, parent, binding


def test_name_mapping_preserves_complete_state_without_inventing_body_history():
    model, parent, binding = fixture()
    original = copy.deepcopy(parent)
    derived = s.expand_scope(parent, model, binding)
    assert s.equal_tree(parent, original)
    assert set(derived['optimizer']['state']) == set(range(2, 8))
    assert len(derived['optimizer']['param_groups'][0]['params']) == 8
    for key in ('model', 'iteration', 'total_hands', 'ppo_replay_entries', 'main_process_rng_state'):
        assert s.equal_tree(parent[key], derived[key])
    derived['optimizer']['state'][2]['exp_avg'].zero_()
    assert s.equal_tree(parent, original)


def test_actual_adam_common_parameter_step_equivalence_and_new_body_state():
    model, parent, binding = fixture()
    derived = s.expand_scope(parent, model, binding)
    control, full = Tiny(), Tiny()
    control.load_state_dict(parent['model'])
    full.load_state_dict(derived['model'])
    c_named, f_named = dict(control.named_parameters()), dict(full.named_parameters())
    head_names = [row['name'] for row in binding['head_parameter_mapping']]
    c_opt = torch.optim.Adam([c_named[name] for name in head_names])
    f_opt = torch.optim.Adam(full.parameters())
    c_opt.load_state_dict(copy.deepcopy(parent['optimizer']))
    f_opt.load_state_dict(copy.deepcopy(derived['optimizer']))
    for index, name in enumerate(f_named):
        f_named[name].grad = torch.full_like(f_named[name], (index + 1) / 1000)
        if name in head_names:
            c_named[name].grad = f_named[name].grad.clone()
    c_opt.step()
    f_opt.step()
    for name in head_names:
        assert torch.equal(c_named[name], f_named[name])
        assert s.equal_tree(c_opt.state[c_named[name]], f_opt.state[f_named[name]])
    for name in ('body.weight', 'body.bias'):
        assert float(f_opt.state[f_named[name]]['step']) == 1
        assert not torch.equal(f_named[name], parent['model'][name])


@pytest.mark.parametrize('bad', ['scope', 'model', 'order', 'names', 'groups', 'duplicate_id',
    'missing_state', 'hyperparameters', 'shape', 'dtype', 'nan', 'negative_square', 'step', 'unknown_state'])
def test_invalid_source_rejected(bad):
    model, parent, binding = fixture()
    if bad == 'scope': parent['all_policy_heads_only_training'] = False
    elif bad == 'model': parent['model']['body.weight'].add_(1)
    elif bad == 'order': binding['all_parameters'].reverse()
    elif bad == 'names': binding['head_parameter_mapping'][0]['name'] = 'preflop_policy_head.weight'
    elif bad == 'groups': parent['optimizer']['param_groups'].append(copy.deepcopy(parent['optimizer']['param_groups'][0]))
    elif bad == 'duplicate_id': parent['optimizer']['param_groups'][0]['params'][1] = 0
    elif bad == 'missing_state': del parent['optimizer']['state'][0]
    elif bad == 'hyperparameters': parent['optimizer']['param_groups'][0]['lr'] *= 2
    elif bad == 'shape': parent['optimizer']['state'][0]['exp_avg'] = torch.zeros(1)
    elif bad == 'dtype': parent['optimizer']['state'][0]['exp_avg'] = parent['optimizer']['state'][0]['exp_avg'].double()
    elif bad == 'nan': parent['optimizer']['state'][0]['exp_avg'].fill_(float('nan'))
    elif bad == 'negative_square': parent['optimizer']['state'][0]['exp_avg_sq'].fill_(-1)
    elif bad == 'step': parent['optimizer']['state'][0]['step'].fill_(float('inf'))
    else: parent['optimizer']['state'][0]['ignored'] = 1
    with pytest.raises(ValueError):
        s.expand_scope(parent, model, binding)


@pytest.mark.parametrize('bad', ['replay', 'rng', 'hands', 'extra', 'moment', 'invented_state', 'group', 'mapping'])
def test_derived_corruption_rejected(bad):
    model, parent, binding = fixture()
    derived = copy.deepcopy(s.expand_scope(parent, model, binding))
    if bad == 'replay': derived['ppo_replay_entries'][0]['obs'][0] = 999
    elif bad == 'rng': derived['main_process_rng_state']['torch'][0] ^= 1
    elif bad == 'hands': derived['total_hands'] = 0
    elif bad == 'extra': derived['new_unrelated_change'] = True
    elif bad == 'moment': derived['optimizer']['state'][2]['exp_avg'].add_(1)
    elif bad == 'invented_state': derived['optimizer']['state'][0] = copy.deepcopy(derived['optimizer']['state'][2])
    elif bad == 'group': derived['optimizer']['param_groups'][0]['lr'] = .5
    else: derived['optimizer_scope_transfer']['preserved_parameter_mapping'][0]['destination_id'] = 0
    with pytest.raises(ValueError):
        s.validate_derived(parent, derived, binding)


def test_exclusive_serialization_and_roundtrip(tmp_path):
    model, parent, binding = fixture()
    derived = s.expand_scope(parent, model, binding)
    path = tmp_path / 'derived.pt'
    s.save_exclusive(path, derived)
    before = path.read_bytes()
    loaded = torch.load(path, map_location='cpu', weights_only=False)
    s.validate_derived(parent, loaded, binding)
    with pytest.raises(FileExistsError):
        s.save_exclusive(path, derived)
    assert path.read_bytes() == before
