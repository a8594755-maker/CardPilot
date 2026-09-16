"""Read-only real-parent checks; no checkpoint derivation or poker execution."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import torch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from observable_critic import attach_encoder, extend_optimizer
from prepare_network import prepare


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    started = time.perf_counter()
    torch.set_num_threads(1)
    prior = module('retained_route_qualification', BASE.parent /
        'v6-preflop-actor-trunk-route-qualification-20260906/qualify_v2.py')
    candidate = module('observable_candidate', prepare())
    expected = {1: '52501761b214aafc00caea3cba14e6d51c8f176d33c612914d6916fd939bbcf2',
                3: 'c23b7db58802e67c1bcb94f7418ff980db7ec981cab9ca171bb37cc574514d94'}
    results = []
    for seed, digest in expected.items():
        path = BASE.parent / f'v6-fixed-regimen-two-seed-2m-20260908/seed{seed}_control_stage1/latest.pt'
        assert sha(path) == digest
        parent = torch.load(path, map_location='cpu', weights_only=False)
        inputs, identities = prior.replay_inputs(parent)
        model = candidate.AlphaHoldemNet(norm_layer='gn', critic_contract='critic_v2',
            separate_preflop_head=True, preflop_trunk_gradient=True).eval()
        with torch.no_grad():
            model(*inputs[0][:4])
        model.load_state_dict(parent['model'], strict=True)
        optimizer = torch.optim.Adam(model.parameters(), lr=.0003)
        optimizer.load_state_dict(copy.deepcopy(parent['optimizer']))
        assert prior.transfer.equal_tree(optimizer.state_dict(), parent['optimizer'])
        with torch.no_grad():
            before = {street: model(*args[:4]) for street, args in inputs.items()}
        attach_encoder(model)
        receipt = extend_optimizer(model, optimizer)
        extended = optimizer.state_dict()
        assert prior.transfer.equal_tree(extended['state'], parent['optimizer']['state'])
        old_group = parent['optimizer']['param_groups'][0]
        assert all(prior.transfer.equal_tree(extended['param_groups'][0][k], v)
                   for k, v in old_group.items() if k != 'params')
        with torch.no_grad():
            for street, args in inputs.items():
                after = model(*args[:4])
                assert all(torch.equal(a, b) for a, b in zip(before[street], after))
        # This fixture uses actual model.forward and actual retained states.
        # It is not yet the PPO minibatch routine or a worker smoke.
        optimizer.zero_grad(set_to_none=True)
        _, value = model(*inputs[5][:4])
        (value - .2).square().mean().backward()
        assert any(p.grad is not None and p.grad.abs().sum() > 0
                   for p in model.observable_value_encoder.parameters())
        assert all(p.grad is None for n, p in model.named_parameters()
                   if not n.startswith(('observable_value_encoder.', 'value_head.')))
        assert sha(path) == digest
        results.append({'seed': seed, 'parent_sha256': digest, 'passed': True,
                        'retained_state_identities': identities, 'optimizer': receipt,
                        'initial_forward_states': sum(len(x[0]) for x in inputs.values())})
        del model, optimizer, parent, extended, before, inputs
    report = {'passed': True, 'runs': results, 'wall_seconds': time.perf_counter()-started,
              'training_hands': 0, 'evaluation_hands': 0,
              'limitations': 'No PPO/worker integration or replay/counter checkpoint derivation yet.'}
    with (BASE / 'real_parent_checks.json').open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps({'passed': True, 'seeds': list(expected), 'wall_seconds': report['wall_seconds']}))


if __name__ == '__main__':
    main()
