"""Isolated independent-critic trainer with retained anchor/recovery bindings."""
import importlib
import importlib.util
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


def install():
    manifest = json.loads((BASE / 'runtime_sources.json').read_text())
    for filename, expected in manifest.items():
        with Path(filename).open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != expected:
                raise ValueError('candidate dependency changed: ' + filename)
    # Reuse the already hash-checked anchor pool and bounded checkpoint I/O.
    source = BASE.parent / 'v6-anchor-recent-trainer-integration-20260907/train_candidate.py'
    spec = importlib.util.spec_from_file_location('observable_anchor_runtime', source)
    wrapper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wrapper)
    original, binding = wrapper.install()
    trainer = importlib.import_module('candidate_train')
    if Path(trainer.__file__).resolve() != BASE / 'candidate_train.py':
        raise ValueError('unexpected independent trainer module')
    trainer.OpponentPool = original.OpponentPool
    trainer.argparse = original.argparse
    binding['independent_critic_candidate'] = str(Path(trainer.__file__).resolve())
    binding['critic_route_unchanged'] = False
    return trainer, binding


def main():
    trainer, binding = install()
    print(json.dumps(binding), flush=True)
    trainer.mp.set_start_method('spawn')
    trainer.main()


if __name__ == '__main__':
    main()
