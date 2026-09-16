"""Run the frozen actor-route candidate with the previously qualified45s I/O bound."""
from functools import partial
import hashlib
import json
from pathlib import Path
import runpy
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
QUAL = ROOT / 'research/experiments/v6-preflop-actor-trunk-route-qualification-20260906'
RUNTIME = QUAL / 'candidate'
TRAINER = RUNTIME / 'scripts/alpha_holdem/train_v5.py'
IO_MODULE = RUNTIME / 'scripts/alpha_holdem/managed_checkpoint_io.py'
IO_CANDIDATE = ROOT / 'research/experiments/v6-phase-held-reference-seed3-replication-20260905/recovery_20260905/checkpoint_io_candidate.py'
EXPECTED = {
    QUAL / 'qualification_v2.json':'a5f6cfce6bc32535cc4f43231b69f30cd1d7e2ab748da175af4f65f7d88a705c',
    TRAINER:'bcce947477fdcf6593b7a88ce6845bf5638ce6698b9462deeecf4133b05472e6',
    IO_MODULE:'ac2f02452f2dc482b10d33128608172e111cf937a8c6824311bf20b2ba8aea05',
    IO_CANDIDATE:'e5b196f021ca3e6be045b6e8980ecff05a051c623472f91072d933330d2188a1',
}
BOUNDS = {'replace_timeout_seconds':45.0,'max_replace_attempts':256}


def install():
    for path,digest in EXPECTED.items():
        with path.open('rb') as handle:
            if hashlib.file_digest(handle,'sha256').hexdigest()!=digest:
                raise ValueError('frozen wrapper input changed: '+str(path))
    report = json.loads((QUAL/'qualification_v2.json').read_text(encoding='utf-8'))
    for path,digest in report['input_sha256'].items():
        source = Path(path)
        if source.is_relative_to(RUNTIME):
            with source.open('rb') as handle:
                if hashlib.file_digest(handle,'sha256').hexdigest()!=digest:
                    raise ValueError('qualified runtime changed: '+path)
    sys.path.insert(0,str(RUNTIME))
    sys.path.insert(0,str(RUNTIME/'scripts'))
    sys.path.insert(0,str(IO_CANDIDATE.parent))
    import alpha_holdem.managed_checkpoint_io as original
    import checkpoint_io_candidate as candidate
    if Path(original.__file__).resolve()!=IO_MODULE or Path(candidate.__file__).resolve()!=IO_CANDIDATE:
        raise ValueError('wrong checkpoint I/O binding')
    original.atomic_torch_save = partial(candidate.atomic_torch_save,**BOUNDS)
    return {'input_sha256':{str(p):s for p,s in EXPECTED.items()}, 'io_bounds':BOUNDS,
            'runtime':str(RUNTIME),'critic_route_unchanged':True,'payload_preserved':True}


def main():
    print(json.dumps(install()),flush=True)
    sys.argv = [str(TRAINER),*sys.argv[1:]]
    sys.path.insert(0,str(TRAINER.parent))
    runpy.run_path(str(TRAINER),run_name='__main__')


if __name__=='__main__':
    main()
