"""Retained complete-hand PPO routing fixture, never a production continuation."""
import copy
import json
from pathlib import Path
import sys
import time

import torch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from check_parents import module, sha
from observable_critic import attach_encoder, extend_optimizer
from prepare_network import prepare


def main():
    started = time.perf_counter()
    torch.set_num_threads(1)
    runtime = BASE.parent / 'v6-preflop-actor-trunk-route-qualification-20260906/candidate'
    sys.path.insert(0, str(runtime))
    sys.path.insert(0, str(runtime / 'scripts'))
    from alpha_holdem.train_mp3_hybrid_h1 import trinal_clip_ppo_update
    candidate = module('ppo_fixture_network', prepare())
    expected = {1: '52501761b214aafc00caea3cba14e6d51c8f176d33c612914d6916fd939bbcf2',
                3: 'c23b7db58802e67c1bcb94f7418ff980db7ec981cab9ca171bb37cc574514d94'}
    result = []
    for seed, digest in expected.items():
        path = BASE.parent / f'v6-fixed-regimen-two-seed-2m-20260908/seed{seed}_control_stage1/latest.pt'
        assert sha(path) == digest
        parent = torch.load(path, map_location='cpu', weights_only=False)
        model = candidate.AlphaHoldemNet(norm_layer='gn', critic_contract='critic_v2',
            separate_preflop_head=True, preflop_trunk_gradient=True)
        model(torch.zeros(1, 6, 4, 13), torch.zeros(1, 25, 4, 5), torch.zeros(1, 3))
        model.load_state_dict(parent['model'], strict=True)
        optimizer = torch.optim.Adam(model.parameters(), lr=.0003)
        optimizer.load_state_dict(copy.deepcopy(parent['optimizer']))
        attach_encoder(model)
        extend_optimizer(model, optimizer)
        blocks = parent['ppo_replay_entries'][-1]['blocks'][:32]
        assert all(bool(block[-1][8]) for block in blocks)
        transitions = [row for block in blocks for row in block]
        before = {name: p.detach().clone() for name, p in model.named_parameters()}
        torch.manual_seed(2026090830 + seed)
        metrics = trinal_clip_ppo_update(model, optimizer, transitions, torch.device('cpu'),
            epochs=1, mini_batch_size=16384, critic_contract='critic_v2',
            value_coef=1., entropy_coef=.005, entropy_floor=.05,
            policy_advantage_clip=3., policy_advantage_normalization='global')
        changed = [n for n, p in model.named_parameters() if not torch.equal(p, before[n])]
        assert any(n.startswith('observable_value_encoder.') for n in changed)
        assert any(n.startswith('value_head.') for n in changed)
        assert any(not n.startswith(('observable_value_encoder.', 'value_head.')) for n in changed)
        assert all(torch.isfinite(p).all() for p in model.parameters())
        assert all(p in optimizer.state and optimizer.state[p]['step'].item() == 1
                   for p in model.observable_value_encoder.parameters())
        assert sha(path) == digest
        result.append({'seed': seed, 'parent_sha256': digest, 'complete_replay_hands': len(blocks),
                       'replayed_transition_rows': len(transitions), 'changed_parameter_names': changed,
                       'passed': True, 'metric_keys': sorted(metrics)})
        del model, optimizer, parent, before
    report = {'passed': True, 'runs': result, 'training_hands': 0, 'evaluation_hands': 0,
              'wall_seconds': time.perf_counter() - started,
              'contract': 'Diagnostic-only CPU one-epoch existing complete replay blocks; reference KL disabled. No production state saved. Not the registered full PPO recipe or a worker/resume test.'}
    with (BASE / 'ppo_checks.json').open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps({'passed': True, 'rows': sum(r['replayed_transition_rows'] for r in result),
                      'wall_seconds': report['wall_seconds']}))


if __name__ == '__main__':
    main()
