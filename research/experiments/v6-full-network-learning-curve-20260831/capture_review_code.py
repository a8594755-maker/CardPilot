"""Separate provenance for outcome-blind helpers added after production launch."""
import json
from pathlib import Path
import shutil
import sys

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(ROOT))
from research.experiment_log import capture_code_provenance,sha256_file


def main():
    directory=BASE/'review_code'
    directory.mkdir(exist_ok=False)
    paths=[(BASE/name).relative_to(ROOT).as_posix() for name in [
        'review_completed_curve.py','test_review.py','inspect_archive.py','capture_review_code.py']]
    capture_code_provenance(ROOT,directory,paths)
    copies=[]
    for relative in paths:
        target=directory/'source_files'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target)
        copies.append(dict(original=relative,copy=target.relative_to(ROOT).as_posix(),sha256=sha256_file(target)))
    (directory/'copy_manifest.json').write_text(json.dumps(copies,indent=2)+'\n')
    print(json.dumps(dict(captured_files=len(copies))))


if __name__=='__main__': main()
