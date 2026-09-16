import ast
import copy
import importlib.util
from pathlib import Path
import sys

import pytest
import torch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / 'candidate/scripts'))
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet
from alpha_holdem.preflop_gradient_contract import (
    FLAG, ORIGIN, checkpoint_flag, validate_config, validate_resume,
)
from route_transfer import derive, equal_tree, validate_derived


def config(**extra):
    return {FLAG: True, 'separate_preflop_head': True, 'hero_preflop_strategy': 'model',
            'preflop_teacher_coef': 0., 'all_policy_heads_only_training': False, **extra}


@pytest.fixture(scope='module')
def models():
    torch.set_num_threads(1)
    torch.manual_seed(2026410601)
    spec = importlib.util.spec_from_file_location('original_route_network',
              BASE / 'original/scripts/alpha_holdem/network_hybrid_h1.py')
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    args = dict(norm_layer='gn', critic_contract='critic_v2', separate_preflop_head=True)
    networks = [old.AlphaHoldemNet(**args), AlphaHoldemNet(**args),
                AlphaHoldemNet(**args, preflop_trunk_gradient=True)]
    with torch.no_grad():
        for model in networks:
            model(torch.zeros(1,6,4,13), torch.zeros(1,25,4,5), torch.zeros(1,3))
            model.eval()
        for model in networks[1:]:
            model.load_state_dict(networks[0].state_dict(), strict=True)
    return networks


def inputs(street):
    generator = torch.Generator().manual_seed(20264106 + street)
    cards = torch.rand(2,6,4,13, generator=generator)
    cards[:,4] = 0.
    if street:
        cards[:,4,0,:street+2] = 1.
    return cards, torch.rand(2,25,4,5, generator=generator), torch.rand(2,3,generator=generator)


@pytest.mark.parametrize('street', range(4))
def test_default_and_connected_forward_exact(models, street):
    args = inputs(street)
    with torch.no_grad():
        original = models[0](*args)
        for model in models[1:]:
            assert all(torch.equal(a,b) for a,b in zip(original, model(*args)))
            assert equal_tree(model.state_dict(), models[0].state_dict())


@pytest.mark.parametrize('street', range(4))
@pytest.mark.parametrize('connected', [False, True])
@pytest.mark.parametrize('objective', ['actor', 'critic'])
def test_direct_gradient_routes(models, street, connected, objective):
    model = models[2 if connected else 1]
    logits, value = model(*inputs(street))
    loss = (logits[:,1]-logits[:,2]).sum() if objective == 'actor' else value.sum()
    named = list(model.named_parameters())
    gradients = torch.autograd.grad(loss, [p for _,p in named], allow_unused=True)
    nonzero = set()
    for (name,_), grad in zip(named, gradients):
        if grad is not None:
            assert torch.isfinite(grad).all()
            if torch.any(grad != 0):
                nonzero.add(name.split('.')[0] if name.startswith(('policy_head.', 'preflop_policy_head.', 'value_head.')) else 'body')
    expected = {'value_head'} if objective == 'critic' else (
        {'policy_head', 'body'} if street else
        ({'preflop_policy_head', 'body'} if connected else {'preflop_policy_head'}))
    assert nonzero == expected


@pytest.mark.parametrize('change', [
    {'separate_preflop_head':False}, {'preflop_teacher_coef':1.},
    {'hero_preflop_strategy':'heuristic-v4'}, {'policy_postflop_only':True},
    {'all_policy_heads_only_training':True}, {'adapter_only_training':True},
    {'preflop_head_only_training':True}, {FLAG:1}, {FLAG:'true'}, {FLAG:None},
])
def test_invalid_admission(change):
    with pytest.raises(ValueError):
        validate_config(config(**change))


@pytest.mark.parametrize('value', [False, True])
def test_resume_route_must_match(value):
    parent = {'config': config(**{FLAG:value}), FLAG:value}
    validate_resume(config(**{FLAG:value}), parent)
    with pytest.raises(ValueError, match='changed on resume'):
        validate_resume(config(**{FLAG:not value}), parent)


def test_legacy_missing_flag_is_detached():
    assert checkpoint_flag({'config':{}}) is False
    validate_config({})
    validate_resume({}, {'config':{}})


def test_torn_metadata_refused():
    with pytest.raises(ValueError, match='disagree'):
        checkpoint_flag({'config':{FLAG:True}, FLAG:False})


@pytest.mark.parametrize('kwargs', [{'preflop_trunk_gradient':True},
                                   {'separate_preflop_head':True,'preflop_trunk_gradient':'true'}])
def test_invalid_constructor(kwargs):
    with pytest.raises(ValueError):
        AlphaHoldemNet(**kwargs)


def fake_parent():
    return {'config':config(**{FLAG:False}), 'all_policy_heads_only_training':False,
            'model':{'a':torch.ones(2)}, 'optimizer':{'step':torch.tensor(21.)},
            'ppo_replay_entries':[{'a':float('nan')}], 'total_hands':65536,
            'environment_hand_accounting':{'completed_hands':70000}}


def test_metadata_only_derivation():
    parent = fake_parent()
    before = copy.deepcopy(parent)
    binding = {'path':'frozen.pt','sha256':'0'*64}
    result = derive(parent, binding)
    assert equal_tree(parent, before)
    validate_derived(parent, result, binding)
    assert result[ORIGIN]['new_environment_hands'] == 0
    with pytest.raises(ValueError):
        derive(result, binding)


@pytest.mark.parametrize('key', ['model','optimizer','ppo_replay_entries','total_hands','environment_hand_accounting'])
def test_unintended_state_mutation_rejected(key):
    parent = fake_parent()
    binding = {'path':'frozen.pt','sha256':'0'*64}
    result = copy.deepcopy(derive(parent,binding))
    result[key] = None
    with pytest.raises(ValueError, match='unintended'):
        validate_derived(parent,result,binding)


def test_trainer_integration_and_unchanged_optimizer_load():
    path = BASE / 'candidate/scripts/alpha_holdem/train_v5.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    calls = [n for n in ast.walk(tree) if isinstance(n,ast.Call)]
    loads = [n for n in calls if ast.unparse(n.func)=='optimizer.load_state_dict']
    assert len(loads)==1 and ast.unparse(loads[0].args[0])=="ckpt['optimizer']"
    routes = [n for n in calls if ast.unparse(n.func)=='validate_preflop_gradient_resume']
    assert len(routes)==1 and routes[0].lineno < loads[0].lineno
    constructors = [n for n in calls if ast.unparse(n.func)=='AlphaHoldemNet' and
                    any(k.arg=='preflop_trunk_gradient' for k in n.keywords)]
    assert len(constructors)==1
    configs = [n for n in calls if ast.unparse(n.func)=='validate_preflop_gradient_config']
    assert len(configs)==1
    payload = next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='checkpoint_payload')
    strings = [n.value for n in ast.walk(payload) if isinstance(n,ast.Constant)]
    assert FLAG in strings and ORIGIN in strings
