"""Metadata-only treatment derivation; all learned and continuation state retained."""
from collections import deque
import copy
import math
from pathlib import Path
import sys

import numpy as np
import torch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / 'candidate/scripts'))
from alpha_holdem.preflop_gradient_contract import (
    FLAG, ORIGIN, checkpoint_flag, migration_metadata, validate_config, validate_resume,
)


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
        return left.keys() == right.keys() and all(equal_tree(left[k], right[k]) for k in left)
    if isinstance(left, (list, tuple, deque)):
        return len(left) == len(right) and all(equal_tree(a, b) for a, b in zip(left, right))
    if isinstance(left, float) and math.isnan(left):
        return math.isnan(right)
    return bool(left == right)


def validate_derived(parent, derived, binding):
    if checkpoint_flag(parent) or parent.get(ORIGIN) is not None:
        raise ValueError('source is already transformed')
    expected_keys = set(parent) | {FLAG, ORIGIN}
    if set(derived) != expected_keys:
        raise ValueError('unexpected derived fields')
    for key in parent:
        if key not in ('config', FLAG, ORIGIN) and not equal_tree(parent[key], derived[key]):
            raise ValueError('unintended checkpoint change: ' + key)
    config = copy.deepcopy(parent['config'])
    config[FLAG] = True
    if not equal_tree(config, derived['config']) or derived[FLAG] is not True:
        raise ValueError('unexpected configuration changes')
    if derived[ORIGIN] != migration_metadata(binding['path'], binding['sha256']):
        raise ValueError('migration provenance mismatch')
    validate_resume(config, derived)


def derive(parent, binding):
    config = copy.deepcopy(parent['config'])
    config[FLAG] = True
    validate_config(config)
    if parent.get('all_policy_heads_only_training') is not False:
        raise ValueError('requires retained full-scope parent')
    derived = dict(parent)
    derived.update({'config': config, FLAG: True,
                    ORIGIN: migration_metadata(binding['path'], binding['sha256'])})
    validate_derived(parent, derived, binding)
    return derived
