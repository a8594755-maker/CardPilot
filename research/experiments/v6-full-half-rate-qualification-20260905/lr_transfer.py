"""Narrow auditable LR-only transformation; no environment execution."""
import copy
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SCOPE = ROOT / 'research/experiments/v6-current-kl-scope-transfer-20260905'
sys.path.insert(0, str(SCOPE))
from inspect_parents import require
from scope_transfer import equal_tree, save_exclusive

PROVENANCE = 'optimizer_learning_rate_transfer'


def validate_source(parent):
    require(parent.get('all_policy_heads_only_training') is False, 'not full-network source')
    require(PROVENANCE not in parent, 'already transformed')
    opt = parent['optimizer']
    require(set(opt) == {'state', 'param_groups'} and len(opt['param_groups']) == 1,
            'single-group optimizer required')
    group = opt['param_groups'][0]
    ids = group['params']
    require(ids and all(type(value) is int for value in ids)
            and ids == list(range(len(ids))) and set(ids) == set(opt['state']),
            'missing or ambiguous optimizer parameter/state mapping')
    lr = group['lr']
    require(type(lr) is float and math.isfinite(lr) and lr > 0, 'invalid actual LR')
    require(all(group.get(key) is False for key in
            ('amsgrad', 'capturable', 'differentiable', 'maximize')),
            'unsupported Adam mode')


def provenance(binding, old_lr):
    return {'schema': 'cardpilot.lr_only_adam_transfer.v1',
            'source_checkpoint': binding['path'], 'source_sha256': binding['sha256'],
            'source_actual_lr': old_lr, 'target_actual_lr': old_lr * 0.5,
            'factor': 0.5, 'all_other_checkpoint_fields_preserved': True,
            'optimizer_state_reset': False, 'fixture_updated_weights_saved': False,
            'actual_worker_resume_still_requires_audit': True}


def validate_derived(parent, derived, binding):
    validate_source(parent)
    require(set(derived) == set(parent) | {PROVENANCE}, 'unexpected checkpoint fields')
    for key in parent:
        if key != 'optimizer':
            require(equal_tree(parent[key], derived[key]), f'unintended checkpoint change: {key}')
    require(set(derived['optimizer']) == set(parent['optimizer']), 'optimizer fields changed')
    require(equal_tree(parent['optimizer']['state'], derived['optimizer']['state']),
            'optimizer moments or clocks changed')
    group = copy.deepcopy(parent['optimizer']['param_groups'][0])
    old_lr = group['lr']
    group['lr'] = old_lr * 0.5
    require(equal_tree(derived['optimizer']['param_groups'], [group]), 'unintended optimizer group change')
    require(equal_tree(derived[PROVENANCE], provenance(binding, old_lr)), 'transfer provenance mismatch')


def derive(parent, binding, factor=0.5):
    require(type(factor) is float and factor == 0.5, 'only preregistered half rate admitted')
    validate_source(parent)
    derived = dict(parent)
    group = copy.deepcopy(parent['optimizer']['param_groups'][0])
    old_lr = group['lr']
    group['lr'] *= factor
    derived['optimizer'] = {'state': copy.deepcopy(parent['optimizer']['state']), 'param_groups': [group]}
    derived[PROVENANCE] = provenance(binding, old_lr)
    validate_derived(parent, derived, binding)
    return derived
