"""Exclusive source-bound parent inspection; zero poker hands or gradient updates."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import platform
import sys
import time

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))
import torch
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet
from research.experiment_log import atomic_json

TRAINER_SHA = '1b4d23abfa3e0a9c675126fd7183d37b134a2a13253563e990e144cc01a90f8b'
PARENTS = {
    'seed1': (ROOT / 'research/experiments/v6-phase-held-reference-control-20260904/recovery_20260905/static_stage2_remainder/latest.pt',
        '41ff38496167424fa71373028e9291a0d8bd595315f7121d8fa303e6b15a3372'),
    'seed3': (ROOT / 'research/experiments/v6-phase-held-reference-seed3-replication-20260905/static_stage2/latest.pt',
        '36aa1d935179570e76499a0a0c1c81ccd75384b0411b9c7d9cca56c9a2c14b69'),
}
HEAD_PREFIXES = ('policy_head.', 'preflop_policy_head.', 'value_head.')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def make_model(checkpoint):
    require(checkpoint['norm_layer'] == 'gn' and checkpoint['critic_contract'] == 'critic_v2'
        and checkpoint['separate_preflop_head'] is True and not checkpoint['centralized_critic'],
        'unexpected parent architecture')
    for key in ('postflop_adapter_hidden', 'position_adapter_hidden', 'flat_sequence_policy_adapter_hidden',
        'causal_sequence_policy_adapter_hidden', 'centralized_critic_hidden', 'position_value_adapter_hidden'):
        require(checkpoint[key] == 0, 'unsupported adapter architecture')
    model = AlphaHoldemNet(num_actions=9, norm_layer='gn', critic_contract='critic_v2', separate_preflop_head=True)
    with torch.no_grad():
        model(torch.zeros(1, 6, 4, 13), torch.zeros(1, 25, 4, 5), torch.zeros(1, 3))
    model.load_state_dict(checkpoint['model'], strict=True)
    return model


def main():
    output = BASE / 'parent_inspection.json'
    require(not output.exists(), 'preserve prior inspection')
    require(json.loads((BASE / 'experiment.json').read_text(encoding='utf-8'))['status'] == 'RUNNING',
        'inspection must be preregistered')
    start = time.monotonic()
    torch.set_num_threads(1)
    torch.manual_seed(20263705)
    sources = [Path(__file__), BASE / 'protocol.md', ROOT / 'scripts/alpha_holdem/train_v5.py',
        ROOT / 'scripts/alpha_holdem/network_hybrid_h1.py']
    bindings = {str(path): sha(path) for path in sources}
    require(bindings[str(ROOT / 'scripts/alpha_holdem/train_v5.py')] == TRAINER_SHA, 'producer changed')
    result = {}
    for seed, (path, expected) in PARENTS.items():
        require(sha(path) == expected, 'frozen parent changed')
        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        require(checkpoint['all_policy_heads_only_training'] is True, 'not qualified heads-only parent')
        model = make_model(checkpoint)
        named = list(model.named_parameters())
        selected = [(name, parameter) for name, parameter in named if name.startswith(HEAD_PREFIXES)]
        optimizer = checkpoint['optimizer']
        require(len(optimizer['param_groups']) == 1, 'expected single-group Adam')
        group = optimizer['param_groups'][0]
        ids = group['params']
        require(len(ids) == len(set(ids)) == len(selected) and set(ids) == set(optimizer['state']),
            'producer-order Adam mapping incomplete')
        mapping = []
        for index, (name, parameter) in zip(ids, selected):
            state = optimizer['state'][index]
            require(state['exp_avg'].shape == state['exp_avg_sq'].shape == parameter.shape, 'Adam shape mismatch')
            require(all(torch.isfinite(state[key]).all().item() for key in ('step', 'exp_avg', 'exp_avg_sq')),
                'nonfinite Adam state')
            mapping.append({'id': index, 'name': name, 'shape': list(parameter.shape),
                'step': float(state['step']), 'dtype': str(parameter.dtype)})
        metadata = {key: value for key, value in checkpoint.items()
            if type(value) in (str, int, float, bool, type(None))}
        result[seed] = {'path': str(path), 'sha256': expected, 'bytes': path.stat().st_size,
            'metadata': metadata, 'checkpoint_keys': sorted(checkpoint),
            'all_parameters': [{'name': name, 'shape': list(parameter.shape), 'dtype': str(parameter.dtype)}
                for name, parameter in named], 'head_parameter_mapping': mapping,
            'optimizer_group_hyperparameters': {key: value for key, value in group.items() if key != 'params'},
            'environment_hand_accounting': checkpoint['environment_hand_accounting'],
            'has_main_rng': checkpoint.get('main_process_rng_state') is not None,
            'replay_entries': len(checkpoint['ppo_replay_entries']),
            'new_representation_parameters': len(named) - len(selected)}
        require(sha(path) == expected, 'parent changed during inspection')
        del model, checkpoint
    require(all(sha(Path(path)) == digest for path, digest in bindings.items()), 'inspection source changed')
    report = {'schema': 'cardpilot.scope_transfer.parent_inspection.v1', 'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'outer_argv': sys.orig_argv,
        'wall_seconds': time.monotonic() - start, 'source_sha256': bindings,
        'python': platform.python_version(), 'torch': str(torch.__version__), 'parents': result,
        'model_initialization_only': True, 'gradient_updates': 0, 'environment_hands': 0, 'slumbot_hands': 0}
    atomic_json(output, report)
    print(json.dumps({'passed': True, 'parents': {seed: {'existing_states': len(row['head_parameter_mapping']),
        'new_representation_parameters': row['new_representation_parameters'], 'lr': row['optimizer_group_hyperparameters']['lr']}
        for seed, row in result.items()}, 'new_hands': 0}))


if __name__ == '__main__':
    main()
