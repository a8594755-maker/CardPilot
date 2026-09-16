"""Unchanged trainer/I/O implementation, with a bounded45s publication grace."""
from functools import partial
import hashlib
import json
from pathlib import Path
import runpy
import sys

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'recovery_20260905'
ROOT = HERE.parents[3]
PRODUCTION = ROOT / 'scripts/alpha_holdem/train_v5.py'
ORIGINAL_IO = ROOT / 'scripts/alpha_holdem/managed_checkpoint_io.py'
CANDIDATE = PREVIOUS / 'checkpoint_io_candidate.py'
IO_BOUNDS = {'replace_timeout_seconds': 45.0, 'max_replace_attempts': 256}
EXPECTED = {PRODUCTION: '1b4d23abfa3e0a9c675126fd7183d37b134a2a13253563e990e144cc01a90f8b',
            ORIGINAL_IO: 'ac2f02452f2dc482b10d33128608172e111cf937a8c6824311bf20b2ba8aea05',
            CANDIDATE: 'e5b196f021ca3e6be045b6e8980ecff05a051c623472f91072d933330d2188a1'}


def install_io_override():
    for path, expected in EXPECTED.items():
        with path.open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != expected:
                raise ValueError(f'Frozen recovery source changed: {path}')
    sys.path.insert(0, str(ROOT / 'scripts'))
    sys.path.insert(0, str(PREVIOUS))
    import alpha_holdem.managed_checkpoint_io as original
    import checkpoint_io_candidate as candidate
    if Path(original.__file__).resolve() != ORIGINAL_IO or Path(candidate.__file__).resolve() != CANDIDATE:
        raise ValueError('Wrong I/O module binding')
    original.atomic_torch_save = partial(candidate.atomic_torch_save, **IO_BOUNDS)
    return {'schema': 'cardpilot.checkpoint_io_override.bounded45s.v1',
            'input_sha256': {str(p): digest for p, digest in EXPECTED.items()},
            'override': 'alpha_holdem.managed_checkpoint_io.atomic_torch_save', 'bounds': IO_BOUNDS,
            'same_serialized_payload_and_failure_preservation': True, 'learned_update_algorithm_modified': False,
            'permissions_or_security_settings_modified': False}


def main():
    print(json.dumps(install_io_override()), flush=True)
    sys.argv = [str(PRODUCTION), *sys.argv[1:]]
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(PRODUCTION.parent))
    runpy.run_path(str(PRODUCTION), run_name='__main__')


if __name__ == '__main__':
    main()
