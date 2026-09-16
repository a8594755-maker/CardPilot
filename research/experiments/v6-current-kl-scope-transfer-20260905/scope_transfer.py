"""Explicit, narrowly qualified Adam scope expansion; no simulator or network."""
from collections import deque
import copy
import json
import math
import os
from pathlib import Path

import numpy as np
import torch

from inspect_parents import HEAD_PREFIXES, require


def equal_tree(left, right):
    if isinstance(left, torch.Tensor) or isinstance(right, torch.Tensor):
        return (isinstance(left, torch.Tensor) and isinstance(right, torch.Tensor)
            and left.dtype == right.dtype and left.shape == right.shape
            and torch.equal(left.detach().cpu(), right.detach().cpu()))
    if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
        return (isinstance(left, np.ndarray) and isinstance(right, np.ndarray)
            and left.dtype == right.dtype and left.shape == right.shape
            and np.array_equal(left, right, equal_nan=True))
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equal_tree(left[key], right[key]) for key in left)
    if isinstance(left, (tuple, list, deque)):
        return len(left) == len(right) and all(equal_tree(a, b) for a, b in zip(left, right))
    if isinstance(left, float) and math.isnan(left):
        return math.isnan(right)
    return bool(left == right)


def parameter_description(model):
    return [{'name': name, 'shape': list(parameter.shape), 'dtype': str(parameter.dtype)}
        for name, parameter in model.named_parameters()]


def expand_scope(parent, model, binding):
    require(parent.get('all_policy_heads_only_training') is True and
        'optimizer_scope_transfer' not in parent, 'not a pristine heads-only source')
    require(equal_tree(parent['model'], model.state_dict()), 'loaded model differs from parent')
    require(parameter_description(model) == binding['all_parameters'], 'qualified model parameter order changed')
    named = dict(model.named_parameters())
    names = list(named)
    source_names = [name for name in names if name.startswith(HEAD_PREFIXES)]
    mapping = binding['head_parameter_mapping']
    require(source_names and [row['name'] for row in mapping] == source_names,
        'qualified producer name order changed')
    optimizer = parent['optimizer']
    require(set(optimizer) == {'state', 'param_groups'} and len(optimizer['param_groups']) == 1,
        'only the qualified single-group Adam is supported')
    group = optimizer['param_groups'][0]
    ids = group['params']
    require(all(type(index) is int for index in ids) and len(ids) == len(set(ids)) == len(source_names)
        and ids == [row['id'] for row in mapping] and set(ids) == set(optimizer['state']),
        'source Adam IDs/state incomplete or ambiguous')
    hyperparameters = {key: value for key, value in group.items() if key != 'params'}
    require(json.dumps(hyperparameters, sort_keys=True) == json.dumps(binding['optimizer_group_hyperparameters'], sort_keys=True),
        'source optimizer hyperparameters changed')
    require(math.isfinite(group['lr']) and group['lr'] > 0 and group['amsgrad'] is False
        and not group['capturable'] and not group['differentiable'] and not group['maximize'],
        'unsupported Adam mode or learning rate')
    destination = {name: index for index, name in enumerate(names)}
    states, preserved = {}, []
    for row in mapping:
        index, name = row['id'], row['name']
        parameter, state = named[name], optimizer['state'][index]
        require(row['shape'] == list(parameter.shape) and row['dtype'] == str(parameter.dtype), 'binding shape/dtype mismatch')
        require(set(state) == {'step', 'exp_avg', 'exp_avg_sq'}, 'unsupported Adam state fields')
        step = state['step']
        require(isinstance(step, torch.Tensor) and step.numel() == 1 and torch.isfinite(step).all().item()
            and float(step) == row['step'] and float(step) > 0 and float(step).is_integer(), 'invalid retained Adam step')
        for key in ('exp_avg', 'exp_avg_sq'):
            value = state[key]
            require(isinstance(value, torch.Tensor) and value.shape == parameter.shape and value.dtype == parameter.dtype
                and torch.isfinite(value).all().item(), 'invalid Adam moment shape/dtype/value')
        require(torch.all(state['exp_avg_sq'] >= 0).item(), 'negative Adam second moment')
        states[destination[name]] = copy.deepcopy(state)
        preserved.append({'name': name, 'source_id': index, 'destination_id': destination[name]})
    new_names = [name for name in names if name not in source_names]
    require(new_names, 'scope did not expand')
    new_group = copy.deepcopy(group)
    new_group['params'] = list(range(len(names)))
    derived = dict(parent)
    derived['optimizer'] = {'state': states, 'param_groups': [new_group]}
    derived['all_policy_heads_only_training'] = False
    derived['optimizer_scope_transfer'] = {'schema': 'cardpilot.named_adam_heads_to_full.v1',
        'source_checkpoint': binding['path'], 'source_sha256': binding['sha256'],
        'source_scope': 'all_policy_heads_and_public_critic', 'target_scope': 'full_existing_network',
        'preserved_parameter_mapping': preserved, 'new_parameter_names': new_names,
        'new_parameter_state': 'Absent until first gradient; no fabricated history',
        'existing_optimizer_state_reset': False, 'optimizer_hyperparameters_changed': False,
        'rollout_resume_integrity_not_certified_by_this_transfer': True}
    validate_derived(parent, derived, binding)
    return derived


def validate_derived(parent, derived, binding):
    require(set(derived) == set(parent) | {'optimizer_scope_transfer'}, 'unexpected checkpoint fields')
    require(derived['all_policy_heads_only_training'] is False, 'full scope not declared')
    for key in parent:
        if key not in ('optimizer', 'all_policy_heads_only_training'):
            require(equal_tree(parent[key], derived[key]), f'unintended checkpoint change: {key}')
    provenance = derived['optimizer_scope_transfer']
    require(provenance['source_sha256'] == binding['sha256'] and provenance['source_checkpoint'] == binding['path'],
        'source provenance mismatch')
    names = [row['name'] for row in binding['all_parameters']]
    require(len(names) == len(set(names)), 'duplicate qualified parameter names')
    positions = {name: index for index, name in enumerate(names)}
    expected = [{'name': row['name'], 'source_id': row['id'], 'destination_id': positions[row['name']]}
        for row in binding['head_parameter_mapping']]
    require(provenance['preserved_parameter_mapping'] == expected, 'provenance mapping changed')
    require(provenance['new_parameter_names'] == [name for name in names if name not in {row['name'] for row in expected}],
        'new parameter names changed')
    expected_group = copy.deepcopy(parent['optimizer']['param_groups'][0])
    expected_group['params'] = list(range(len(names)))
    require(equal_tree(derived['optimizer']['param_groups'], [expected_group]), 'optimizer group/hyperparameters changed')
    require(set(derived['optimizer']['state']) == {row['destination_id'] for row in expected},
        'missing existing state or invented new state')
    for row in expected:
        require(equal_tree(parent['optimizer']['state'][row['source_id']], derived['optimizer']['state'][row['destination_id']]),
            f'Adam state changed: {row["name"]}')


def save_exclusive(path, checkpoint):
    """Unqualified/partial outputs are never consumed; preserve failures, never overwrite."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as handle:
        torch.save(checkpoint, handle)
        handle.flush()
        os.fsync(handle.fileno())
