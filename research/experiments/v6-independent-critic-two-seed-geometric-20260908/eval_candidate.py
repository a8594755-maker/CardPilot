"""Use unchanged greedy evaluator with explicit training-only critic removal.

No checkpoint file is rewritten. The raw evaluator binds the original complete
checkpoint hash; this adapter's hash is part of the frozen runtime contract.
"""
import importlib.util
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from alpha_holdem.v5_mirror_eval import init_model as original_init


def actor_checkpoint(checkpoint):
    state = checkpoint['model']
    extra = [k for k in state if k.startswith('observable_value_encoder.')]
    enabled = checkpoint.get('config', {}).get('independent_observable_critic', False)
    if bool(extra) != bool(enabled):
        raise ValueError('inconsistent independent critic checkpoint')
    if not extra:
        return checkpoint
    if checkpoint.get('observable_critic_contract') != 'observable_value_encoder.v1':
        raise ValueError('unqualified independent critic version')
    if len(extra) != 76:
        raise ValueError('unexpected critic state layout')
    return {**checkpoint, 'model': type(state)((k,v) for k,v in state.items() if k not in extra)}


def init_model(checkpoint, device):
    return original_init(actor_checkpoint(checkpoint), device)


def main():
    path = ROOT / 'scripts/alpha_holdem/v6_public_opponent_matched_eval.py'
    spec = importlib.util.spec_from_file_location('fixed_observable_evaluator', path)
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    evaluator.init_model = init_model
    evaluator.main()


if __name__ == '__main__':
    main()
