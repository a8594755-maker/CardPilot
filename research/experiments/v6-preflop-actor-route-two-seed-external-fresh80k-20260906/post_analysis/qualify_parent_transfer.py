"""Offline comparison qualification, never current outcome reads or logger writes."""
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import time
import compare_parent_transfer as c


def main():
    output, xml = c.HERE/'parent_transfer_qualification.json', c.HERE/'parent_transfer_tests.xml'
    c.r.protocol.require(not output.exists() and not xml.exists(), 'preserve earlier qualification')
    paths = [Path(__file__), c.HERE/'compare_parent_transfer.py', c.HERE/'test_parent_transfer.py',
        c.HERE/'review_completed.py', c.BASE/'run_pair.py', c.BASE/'pair_protocol.py']
    hashes = {str(p):c.r.sha(p) for p in paths}
    argv = [sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',
        str(c.HERE/'test_parent_transfer.py'),f'--junitxml={xml}']
    started = time.monotonic()
    result = subprocess.run(argv,cwd=c.ROOT,capture_output=True,text=True,timeout=45)
    c.r.check_hashes(hashes)
    hashes[str(xml)] = c.r.sha(xml)
    report = dict(passed=result.returncode==0,created_at=datetime.now(timezone.utc).isoformat(),
        command=sys.orig_argv,pytest_argv=argv,exit_code=result.returncode,stdout=result.stdout,
        stderr=result.stderr,wall_seconds=time.monotonic()-started,input_sha256=hashes,
        new_hands=0,new_model_queries=0,current_outcomes_read=False,
        logger_deferred_until_both_exact_owners_terminal=True)
    c.r.write_new(output,report)
    print(report)
    raise SystemExit(result.returncode)


if __name__ == '__main__': main()
