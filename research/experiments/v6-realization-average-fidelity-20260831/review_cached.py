"""Eager metrics loading around the unchanged captured reviewer; no new inference."""
from datetime import datetime,timezone
from pathlib import Path
import json
import shutil
import sys
import time
from unittest.mock import patch
import numpy as np
import psutil
import review_finish as original
run=original.run
ORIGINAL_LOAD=np.load

def cached_load(path,*args,**kwargs):
    result=ORIGINAL_LOAD(path,*args,**kwargs)
    if Path(path).name=='mixture_metrics.npz':
        with result:
            return {name:result[name] for name in result.files}
    return result

def main():
    if sys.argv[1:] or (run.BASE/'cached_review_execution.json').exists() or (run.BASE/'reviewed_analysis.json').exists():
        raise ValueError('Preserve earlier review/cache execution')
    start=time.monotonic()
    execution=dict(status='RUNNING',pid=psutil.Process().pid,create_time=psutil.Process().create_time(),
        started_at=datetime.now(timezone.utc).isoformat(),original_review_sha256=run.sha(run.BASE/'review_finish.py'),
        model_queries=0,new_unique_hands=0)
    run.write('cached_review_execution.json',execution)
    directory=run.BASE/'cached_review_code'
    directory.mkdir()
    relative=Path(__file__).resolve().relative_to(run.ROOT).as_posix()
    run.capture_code_provenance(run.ROOT,directory,[relative])
    target=directory/'source_files'/relative
    target.parent.mkdir(parents=True)
    shutil.copy2(run.ROOT/relative,target)
    run.write('cached_review_code/copy_manifest.json',[dict(original=relative,copy=target.relative_to(run.ROOT).as_posix(),sha256=run.sha(target))])
    run.log('--command',f'python research/experiments/{run.BASE.name}/review_cached.py',
        '--artifact',Path(__file__),*[v for n in ('source_manifest.json','code.patch','copy_manifest.json') for v in ('--artifact',directory/n)])
    success=False
    try:
        with patch.object(original.np,'load',cached_load):
            original.main()
        success=True
    finally:
        execution.update(status='COMPLETED' if success else 'FAILED_PRESERVED',
            finished_at=datetime.now(timezone.utc).isoformat(),wall_time_seconds=time.monotonic()-start)
        run.write('cached_review_execution.json',execution)
        run.log('--artifact',run.BASE/'cached_review_execution.json')
        print(json.dumps(execution),flush=True)

if __name__=='__main__':main()

