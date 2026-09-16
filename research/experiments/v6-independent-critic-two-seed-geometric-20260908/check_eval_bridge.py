"""Verify actor-only evaluation bridge on real trained independent checkpoints."""
import importlib.util
import json
from pathlib import Path
import sys

import torch
import numpy as np

BASE = Path(__file__).resolve().parent
QUAL = BASE.parent / 'v6-independent-observable-critic-qualification-20260908'
sys.path.insert(0, str(BASE))
from eval_candidate import init_model
sys.path.insert(0, str(QUAL))
from check_parents import module, sha
from observable_critic import attach_encoder


def main():
    torch.set_num_threads(1)
    candidate = module('eval_trained_critic_network', QUAL / 'candidate_network.py')
    results = []
    for name in ('seed1_extended_restart', 'seed3_first_capture_v2'):
        path = QUAL / name / 'latest.pt'
        digest = sha(path)
        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        selected = {n: [] for n in (0, 3, 4, 5)}
        identities = {n: [] for n in selected}
        for entry in checkpoint['ppo_replay_entries']:
            for bi, block in enumerate(entry['blocks']):
                for ri, row in enumerate(block):
                    street = int(row[0].reshape(6,4,13)[4].sum())
                    if len(selected[street]) < 16:
                        selected[street].append(row)
                        identities[street].append([entry['iteration'],bi,ri])
        assert all(len(rows) == 16 for rows in selected.values())
        inputs = {street: tuple(torch.from_numpy(np.stack([row[i] for row in rows])) for i in range(4))
                  for street, rows in selected.items()}
        inputs = {street: (args[0].reshape(-1,6,4,13), args[1].reshape(-1,25,4,5), *args[2:])
                  for street, args in inputs.items()}
        model = candidate.AlphaHoldemNet(norm_layer='gn', critic_contract='critic_v2',
            separate_preflop_head=True, preflop_trunk_gradient=True).eval()
        with torch.no_grad():
            model(*inputs[0][:4])
        attach_encoder(model)
        model.load_state_dict(checkpoint['model'], strict=True)
        actor = init_model(checkpoint, 'cpu').eval()
        for key, tensor in actor.state_dict().items():
            assert torch.equal(tensor, checkpoint['model'][key])
        with torch.no_grad():
            for street, args in inputs.items():
                expected = model(*args[:4])[0]
                actual = actor(*args[:4])[0]
                assert torch.equal(expected, actual), street
        assert sha(path) == digest
        results.append({'checkpoint_sha256': digest, 'states': 64, 'identities': identities,
                        'logits_bitwise_equal': True, 'scope': 'Logits only; unused value route differs.'})
    with (BASE/'eval_bridge_checks.json').open('x', encoding='utf-8') as handle:
        json.dump({'passed': True, 'runs': results, 'new_hands': 0}, handle, indent=2)
    print('Both trained-checkpoint actor bridges passed128 retained states; no new hands.')


if __name__ == '__main__':
    main()
