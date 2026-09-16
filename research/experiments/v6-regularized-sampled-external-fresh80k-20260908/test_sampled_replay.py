import copy
import importlib.util
from pathlib import Path
import random
import sys
import pytest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parents[2] / 'scripts'))
spec = importlib.util.spec_from_file_location('qualified_sampled_audit', BASE / 'audit_sampled.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
from alpha_holdem.legacy_observation_bridge_v6 import load_policy, external_decision


@pytest.fixture(scope='module')
def policy():
    import torch
    torch.set_num_threads(1)
    return load_policy(BASE.parent / 'v6-regularized-sampled-export-qualification-20260908/seed1_regularized.pt', 'cpu')


def evidence(policy, seed):
    response = dict(action='', hole_cards=['As','Kd'], board=[], client_pos=1)
    _, row = external_decision(policy, response, uniform=random.Random(seed).random(), policy_mode='sample')
    return response, dict(row, response=response)


def test_actual_model_replay(policy):
    for seed in range(32):
        response, row = evidence(policy, seed)
        a.validate_decision(row, response, random.Random(seed), policy, 'sample', external_decision)


@pytest.mark.parametrize('key', ['uniform', 'behavior_action_probability', 'legacy_selected_action_slot',
                                'selected_action_slot', 'source_checkpoint_sha256', 'policy_mode'])
def test_replay_rejects_mutations(policy, key):
    response, row = evidence(policy, 12)
    row = copy.deepcopy(row)
    row[key] = 'corrupt'
    with pytest.raises(ValueError):
        a.validate_decision(row, response, random.Random(12), policy, 'sample', external_decision)


def test_model_required(policy):
    response, row = evidence(policy, 12)
    with pytest.raises(ValueError):
        a.validate_decision(row, response, random.Random(12), None, 'sample', external_decision)
