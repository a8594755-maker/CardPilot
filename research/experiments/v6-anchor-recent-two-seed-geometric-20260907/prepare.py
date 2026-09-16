"""Freeze matched parent/implementation bindings; does not launch training."""
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
QUAL = ROOT/'research/experiments/v6-anchor-recent-trainer-integration-20260907'
PARENT = ROOT/'research/experiments/v6-preflop-actor-route-2m-continuation-20260906'
EXPECTED = {1:'c9459d471dbaea0662533633631fb3b86a8e7d164238a887098aabe72d1c29e3',
            3:'d2c7acdde6e97eec6290c07904943fbcda734d5acec57bb7e89cd12843136e23'}


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def main():
    assert json.loads((QUAL/'experiment.json').read_text())['status'] == 'COMPLETED'
    review = json.loads((QUAL/'terminal_review.json').read_text())
    assert review['passed'] and review['new_training_hands'] == 40399
    for path,digest in review['input_sha256'].items():
        assert sha(Path(path)) == digest, path
    bindings = {str(p):sha(p) for p in (BASE/'protocol.md', Path(__file__),
        QUAL/'train_candidate.py', QUAL/'terminal_review.json')}
    parents = {}
    for seed,digest in EXPECTED.items():
        path = PARENT/f'seed{seed}_connected_stage3/latest.pt'
        assert sha(path) == digest
        bindings[str(path)] = digest
        parents[str(seed)] = {'path':str(path),'sha256':digest}
    with (BASE/'preparation.json').open('x',encoding='utf-8') as handle:
        json.dump({'passed':True,'command':sys.orig_argv,'parents':parents,
            'input_sha256':bindings,'additional_physical_doses':[262144,1048576],
            'training_started':False,'controller_qualified':False},handle,indent=2)


if __name__ == '__main__':
    main()
