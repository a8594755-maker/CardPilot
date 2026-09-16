"""Independent provenance for read-only prefix throughput analysis."""
import json
from pathlib import Path
import shutil
import sys

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(ROOT))
from research.experiment_log import capture_code_provenance,sha256_file


def main():
    directory=BASE/'prefix_code'
    directory.mkdir(exist_ok=False)
    paths=[(BASE/name).relative_to(ROOT).as_posix() for name in [
        'summarize_prefix_throughput.py','test_prefix_throughput.py','throughput_context.md','capture_prefix_code.py']]
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
