"""Isolated explicit anchor-latest integration; frozen trainer stays untouched."""
import argparse
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import types

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
WRAPPER = ROOT / 'research/experiments/v6-preflop-actor-trunk-two-seed-geometric-20260906/train_candidate.py'
SELECTOR = ROOT / 'research/experiments/v6-anchor-recent-pool-qualification-20260907/anchor_recent.py'
EXPECTED = {
    WRAPPER: '04aa0bb51fead487ba815fba9794d34b27f48067320097663503a70738e34a36',
    SELECTOR: 'b9fa9c571ded0ff2554688272236c8e0a0fce7779bfa76d782a245aef1e65d86',
}


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def install():
    for path, digest in EXPECTED.items():
        with path.open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != digest:
                raise ValueError('integration input changed: ' + str(path))
    frozen = load_file('anchor_frozen_wrapper', WRAPPER)
    binding = frozen.install()
    sys.path.insert(0, str(frozen.TRAINER.parent))
    # Canonical import keeps worker functions importable under Windows spawn.
    trainer = importlib.import_module('alpha_holdem.train_v5')
    if Path(trainer.__file__).resolve() != frozen.TRAINER:
        raise ValueError('unexpected trainer module')
    if getattr(trainer, '_anchor_latest_installed', False):
        raise ValueError('integration already installed')
    selector = load_file('anchor_recent_selector', SELECTOR)
    original_pool = trainer.OpponentPool

    class IntegratedPool(original_pool):
        def __init__(self, k=5, strategy='loss-kbest', history_limit=200):
            if strategy == selector.STRATEGY:
                if type(k) is not int or k <= 0:
                    raise ValueError('anchor-latest requires positive integer capacity')
                original_pool.__init__(self, k, 'latest', history_limit)
                self.strategy = strategy
            else:
                original_pool.__init__(self, k, strategy, history_limit)

        def _prune(self):
            if self.strategy == selector.STRATEGY:
                self.snapshots = selector.retained_snapshots(self.snapshots, self.k)
            else:
                original_pool._prune(self)

        def description(self):
            if self.strategy == selector.STRATEGY:
                return f'anchor-preserving recent learned snapshots (K={self.k})'
            return original_pool.description(self)

    class Parser(argparse.ArgumentParser):
        def add_argument(self, *args, **kwargs):
            if '--pool-strategy' in args:
                if kwargs.get('choices') != ('latest', 'loss-kbest', 'elo-kbest'):
                    raise ValueError('unexpected frozen parser contract')
                kwargs['choices'] = (*kwargs['choices'], selector.STRATEGY)
                kwargs['help'] += ' anchor-latest preserves external anchors and retains recent learned snapshots.'
            return super().add_argument(*args, **kwargs)

    trainer.OpponentPool = IntegratedPool
    # Do not mutate global argparse used by other modules.
    trainer.argparse = types.SimpleNamespace(**{**vars(argparse), 'ArgumentParser': Parser})
    trainer._anchor_latest_installed = True
    binding['integration_inputs'] = {str(p): d for p, d in EXPECTED.items()}
    binding['opt_in_strategy'] = selector.STRATEGY
    return trainer, binding


def main():
    trainer, binding = install()
    print(json.dumps(binding), flush=True)
    trainer.mp.set_start_method('spawn')
    trainer.main()


if __name__ == '__main__':
    main()
