"""Qualify only the changed stage3 terminal-review bindings; no live outcomes."""
from datetime import datetime,timezone
from pathlib import Path
import json
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import terminal_review as r


def main():
    output = HERE/'qualification.json'
    r.require(not output.exists() and not (HERE/'qualification_failure.json').exists(),'preserve prior qualification')
    begun = time.perf_counter()
    owner = r.read(r.BASE/'ownership.json')
    r.require(owner['pid'] == r.EXPECTED_OWNER['pid'] and owner['create_time'] == r.EXPECTED_OWNER['create_time']
              and r.live(owner['pid'],owner['create_time']),'qualify while exact original owner is live')
    argv = [sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',
            str(HERE/'test_terminal_review.py'),'--junitxml='+str(HERE/'tests.xml')]
    result = subprocess.run(argv,cwd=r.ROOT,capture_output=True,text=True,encoding='utf-8')
    paths = [Path(__file__),HERE/'terminal_review.py',HERE/'test_terminal_review.py',HERE/'tests.xml',
             r.SOURCE,r.old.SOURCE,r.BASE/'ownership.json',r.BASE/'qualification.json',r.BASE/'preregistration.md',
             r.ROOT/'research/experiments/v6-preflop-actor-trunk-two-seed-geometric-20260906/recovery_20260906/post_analysis/qualification.json']
    r.require(r.sha(r.SOURCE) == '08ec295a658e14252c2725ef4d9c8de3b4c78c732961588145ff63a848ee29af',
              'old actor reviewer changed')
    r.require(r.sha(r.old.SOURCE) == '1e1133c2b7c506a2ffcff7ae6906573ac28e264ef7506a94925abdb214155e56',
              'independent statistical parser changed')
    report = {'passed':result.returncode == 0,'exit_code':result.returncode,
              'created_at':datetime.now(timezone.utc).isoformat(),'command':sys.orig_argv,'pytest_command':argv,
              'stdout':result.stdout,'stderr':result.stderr,'input_sha256':{str(p):r.sha(p) for p in paths},
              'wall_seconds':time.perf_counter()-begun,'new_training_hands':0,'new_evaluation_hands':0,
              'current_outcomes_read':False,'logger_writes':0,'bound_owner':r.EXPECTED_OWNER,
              'deferred_attachment_after_owner_exit':True}
    path = output if report['passed'] else HERE/'qualification_failure.json'
    with path.open('x',encoding='utf-8') as out:
        json.dump(report,out,indent=2,allow_nan=False)
    print(json.dumps({'passed':report['passed'],'stdout':result.stdout,'stderr':result.stderr,
                      'new_hands':0,'current_outcomes_read':False}))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()

