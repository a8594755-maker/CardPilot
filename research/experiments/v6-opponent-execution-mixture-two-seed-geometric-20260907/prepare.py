"""Freeze matched parent/implementation bindings; does not launch training."""
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
QUAL = ROOT/'research/experiments/v6-opponent-execution-mixture-resume-20260907'
PARENT = ROOT/'research/experiments/v6-anchor-recent-two-seed-geometric-20260907'
EXPECTED = {1:'819bfdd9ea0b9625a2e6e2528cbd7be5d984667a463d1ac14f70a44b4091dd85',
            3:'df2d4c7cdac0aba5c88c03e43922b8b0a55e57341868ea62bfe5adbbe0a2a7b5'}


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def main():
    assert json.loads((QUAL/'experiment.json').read_text())['status'] == 'COMPLETED'
    review = json.loads((QUAL/'terminal_review.json').read_text())
    assert review['passed'] and review['new_training_hands'] == 36079
    for path,digest in review['input_sha256'].items():
        assert sha(Path(path)) == digest, path
    bindings = {str(p):sha(p) for p in (BASE/'protocol.md', Path(__file__),
        BASE/'train_candidate.py', QUAL/'terminal_review.json')}
    parents = {}
    for seed,digest in EXPECTED.items():
        path = PARENT/f'seed{seed}_recent_stage2/latest.pt'
        assert sha(path) == digest
        bindings[str(path)] = digest
        parents[str(seed)] = {'path':str(path),'sha256':digest}
    with (BASE/'preparation.json').open('x',encoding='utf-8') as handle:
        json.dump({'passed':True,'command':sys.orig_argv,'parents':parents,
            'input_sha256':bindings,'additional_physical_doses':[262144,1048576],
            'training_started':False,'controller_qualified':False},handle,indent=2)


if __name__ == '__main__':
    main()
