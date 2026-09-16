"""Describe the current frozen architecture's direct gradient routes, not strength.

Part of this experiment's independent post-analysis. CPU only; synthetic network
inputs, no poker hands, PPO updates, optimizer creation or checkpoint mutation.
Register this executed command and its artifacts after the live owner exits.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[2]
SCOPE = ROOT / 'research/experiments/v6-current-kl-scope-transfer-20260905'
sys.path.insert(0, str(SCOPE))
from inspect_parents import make_model, require, sha
import torch

SOURCE_HASHES = {
    str(ROOT / 'scripts/alpha_holdem/network_hybrid_h1.py'):
        '95fe31834a3c55bb0ad7a13da7188d74bfb9513da9c10396acad94a7c563b406',
    str(SCOPE / 'inspect_parents.py'):
        '2a5c73fcc130ddd475e7d2eb85289fc9dd6660682ac3107c117b75dac8fe702e',
}
CHECKPOINTS = {
    1: 'dd594114975c7a38ec34acea9caef9b77ead54afe13ccdde0acf9d98a82822e6',
    3: 'bb7841a2ea4be1cc6aa1c9d1fefa8c3f3dda960400d1b37e0d63e4f4681e1688',
}


def group(name):
    for prefix in ('preflop_policy_head', 'policy_head', 'value_head'):
        if name.startswith(prefix + '.'):
            return prefix
    return 'shared_representation'


def tensor_digest(model):
    digest = hashlib.sha256()
    for name, tensor in model.state_dict().items():
        digest.update(name.encode())
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def direct_routes(model, cards, actions, extras, mask, objective):
    named = list(model.named_parameters())
    logits, value = model(cards, actions, extras, mask)
    # Contrasting two logits avoids the zero derivative of a constant sum of
    # normalized probabilities. This is a connectivity probe, NOT a poker loss.
    loss = (logits[:, 1] - logits[:, 2]).sum() if objective == 'policy' else value.sum()
    gradients = torch.autograd.grad(loss, [parameter for _, parameter in named], allow_unused=True)
    result = {key: {'l2': 0., 'nonzero_parameter_tensors': 0, 'total_parameter_tensors': 0}
              for key in ('shared_representation', 'policy_head', 'preflop_policy_head', 'value_head')}
    for (name, _), gradient in zip(named, gradients):
        row = result[group(name)]
        row['total_parameter_tensors'] += 1
        if gradient is not None:
            require(torch.isfinite(gradient).all().item(), 'nonfinite direct gradient')
            squared = gradient.detach().double().square().sum().item()
            row['l2'] += squared
            row['nonzero_parameter_tensors'] += int(squared > 0.)
    for row in result.values():
        row['l2'] = row['l2'] ** .5
    return result


def main():
    output = BASE / 'post_analysis/gradient_route_observation.json'
    require(not output.exists(), 'preserve previous route observation')
    require(all(sha(path) == expected for path, expected in SOURCE_HASHES.items()), 'frozen architecture changed')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(20263906)
    started = time.monotonic()
    hashes = {**SOURCE_HASHES, str(Path(__file__)): sha(__file__)}
    results = {}
    for seed, expected in CHECKPOINTS.items():
        run = BASE / f'seed{seed}_full_stage1'
        checkpoint_path = run / 'latest.pt'
        require(sha(checkpoint_path) == expected, 'closed checkpoint changed')
        verification = json.loads((run / 'verification.json').read_text(encoding='utf-8'))
        require(verification['passed'] and verification['checkpoint_sha256'] == expected, 'closed cell unverified')
        checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
        require(checkpoint['all_policy_heads_only_training'] is False, 'not the current full trainable scope')
        model = make_model(checkpoint).eval()
        require(len(list(model.parameters())) == 86 and all(p.requires_grad for p in model.parameters()), 'wrong trainable scope')
        before = tensor_digest(model)
        cards = torch.randn(2, 6, 4, 13)
        actions, extras, mask = torch.randn(2, 25, 4, 5), torch.zeros(2, 3), torch.ones(2, 9)
        probe_results = {}
        for street in ('preflop', 'postflop'):
            cards[:, 4] = 0.
            if street == 'postflop':
                cards[:, 4, 0, :3] = 1.
            for objective in ('policy', 'value'):
                route = direct_routes(model, cards, actions, extras, mask, objective)
                expected_groups = ({'preflop_policy_head'} if street == 'preflop'
                                   else {'shared_representation', 'policy_head'}) if objective == 'policy' else {'value_head'}
                require({name for name, row in route.items() if row['l2'] > 0.} == expected_groups,
                        f'unexpected route:{seed}/{street}/{objective}')
                probe_results[f'{street}_{objective}'] = route
        require(tensor_digest(model) == before and all(p.grad is None for p in model.parameters()), 'probe mutated model')
        results[str(seed)] = {'routes': probe_results, 'model_parameters_unchanged': True,
                              'synthetic_input_batch_size': 2, 'actual_checkpoint_sha256': expected}
        hashes[str(checkpoint_path)] = expected
        hashes[str(run / 'verification.json')] = sha(run / 'verification.json')
        del model, checkpoint
    require(all(sha(path) == expected for path, expected in hashes.items()), 'source/evidence changed during check')
    report = {
        'passed': True, 'created_at': datetime.now(timezone.utc).isoformat(), 'command': sys.orig_argv,
        'input_sha256': hashes, 'seeds': results, 'wall_seconds': time.monotonic() - started,
        'environment_hands': 0, 'slumbot_hands': 0, 'optimizer_updates': 0, 'allocation_changed': False,
        'scope': 'Synthetic-input direct network gradient connectivity under the existing separate-preflop-head '
                 'and critic_v2 contracts. Not a full PPO loss audit, actual rollout gradient dose, '
                 'poker quality, causal explanation of seat imbalance or a recommendation to remove detach.',
    }
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
