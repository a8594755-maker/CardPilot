"""Opt-in generic opponent execution mixture; hero and frozen trainer unchanged."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / 'research/experiments/v6-anchor-recent-trainer-integration-20260907/train_candidate.py'
SOURCE_SHA = '4e60dd8c45577c6523f8a6b4696db5a02926c557c3f4e6d3d61d2c84b60cc41c'

def mixture_logits(logits, weight):
    import torch
    if not 0 <= weight <= 1:
        raise ValueError('mixture weight must be finite in [0,1]')
    if weight == 0:
        return logits
    if not torch.isfinite(logits).any(dim=-1).all():
        raise ValueError('no finite legal logit')
    probabilities = logits.softmax(-1)
    greedy = torch.zeros_like(probabilities).scatter_(-1, logits.argmax(-1, keepdim=True), 1)
    mixture = probabilities * (1 - weight) + greedy * weight
    return mixture.log()

class OpponentView:
    def __init__(self, model, weight):
        self.model, self.weight = model, weight

    def __call__(self, *args, **kwargs):
        logits, values = self.model(*args, **kwargs)
        return mixture_logits(logits, self.weight), values

def install(weight):
    if not 0 <= weight <= 1:
        raise ValueError('mixture weight must be finite in [0,1]')
    with SOURCE.open('rb') as handle:
        if hashlib.file_digest(handle, 'sha256').hexdigest() != SOURCE_SHA:
            raise ValueError('frozen integration source changed')
    spec = importlib.util.spec_from_file_location('opponent_mixture_parent', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    trainer, binding = module.install()
    original = trainer.run_inference_v5
    def inference(hero_model, opp_models, *args, **kwargs):
        # Self-play requests use hero_model, never an OpponentView. No new RNG.
        opponents = opp_models if weight == 0 else [OpponentView(m, weight) for m in opp_models]
        return original(hero_model, opponents, *args, **kwargs)
    trainer.run_inference_v5 = inference
    binding['opponent_execution_mixture'] = {
        'greedy_weight': weight, 'scope': 'historical pool opponent requests only',
        'unit': 'per-decision probability mixture, not per-hand mode selection',
        'hero_and_selfplay_unchanged': True, 'additional_rng_draws': 0,
        'source_sha256': SOURCE_SHA}
    return trainer, binding, original

def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--opponent-greedy-mixture', type=float, required=True)
    args, remaining = parser.parse_known_args()
    trainer, binding, _ = install(args.opponent_greedy_mixture)
    sys.argv = [sys.argv[0], *remaining]
    print(json.dumps(binding), flush=True)
    trainer.mp.set_start_method('spawn')
    trainer.main()

if __name__ == '__main__':
    main()
