"""Complete isolated runtime packaging after the preserved collection failure."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
from prepare_candidate import BASE, ROOT, sha


def main():
    output = BASE / 'dependency_preparation.json'
    assert not output.exists()
    assert (BASE / 'regression_tests.xml').exists(), 'retain initial collection evidence'
    rows = {}
    for source in sorted((ROOT / 'scripts/deep_cfr').rglob('*.py')):
        relative = source.relative_to(ROOT / 'scripts')
        expected = sha(source)
        for kind in ('original', 'candidate'):
            target = BASE / kind / 'scripts' / relative
            assert not target.exists(), 'preserve earlier dependency staging'
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
            assert sha(target)==expected
        rows[str(relative)]=expected
    with output.open('x',encoding='utf-8') as handle:
        json.dump({'created_at':datetime.now(timezone.utc).isoformat(), 'command':sys.orig_argv,
                   'source_sha256':rows,'new_hands':0,'algorithm_changes':False,
                   'reason':'Initial isolated test collection omitted deep_cfr runtime dependency; 73 collection errors retained.'},handle,indent=2)
    print(json.dumps({'dependency_files':len(rows),'new_hands':0}))


if __name__ == '__main__':
    main()
