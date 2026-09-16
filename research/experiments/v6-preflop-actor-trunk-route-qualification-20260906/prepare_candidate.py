"""Preserve the original runtime and stage a default-preserving candidate once."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    assert json.loads((BASE / 'experiment.json').read_text())['status'] == 'RUNNING'
    originals, candidate = BASE / 'original/scripts', BASE / 'candidate/scripts'
    assert not originals.exists() and not candidate.exists(), 'preserve previous preparation'
    pins = {'train_v5.py': '1b4d23abfa3e0a9c675126fd7183d37b134a2a13253563e990e144cc01a90f8b',
            'network_hybrid_h1.py': '95fe31834a3c55bb0ad7a13da7188d74bfb9513da9c10396acad94a7c563b406'}
    for name, expected in pins.items():
        assert sha(ROOT / 'scripts/alpha_holdem' / name) == expected
    rows = {}
    for source in sorted((ROOT / 'scripts/alpha_holdem').rglob('*.py')):
        relative = source.relative_to(ROOT / 'scripts')
        expected = sha(source)
        for destination in (originals / relative, candidate / relative):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            assert sha(destination) == expected
        rows[str(relative)] = expected
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'command': sys.orig_argv,
              'source_sha256': rows, 'files': len(rows), 'new_hands': 0,
              'production_changed': False, 'candidate_initially_byte_identical': True}
    with (BASE / 'preparation.json').open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps({'files': len(rows), 'production_changed': False, 'new_hands': 0}))


if __name__ == '__main__':
    main()
