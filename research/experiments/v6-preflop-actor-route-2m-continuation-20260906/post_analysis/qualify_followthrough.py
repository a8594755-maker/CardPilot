from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import terminal_review as r


def main():
    out = HERE/'followthrough_qualification.json'
    r.require(not out.exists() and not (HERE/'followthrough_qualification_failure.json').exists(),'preserve qualification')
    r.validate_review_qualification()
    owner = r.read(r.BASE/'ownership.json')
    r.require(owner['pid'] == r.EXPECTED_OWNER['pid'] and owner['create_time'] == r.EXPECTED_OWNER['create_time']
              and r.live(owner['pid'],owner['create_time']),'exact controller must still be live')
    begun = time.monotonic()
    argv = [sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',
            str(HERE/'test_terminal_followthrough.py'),'--junitxml='+str(HERE/'followthrough_tests.xml')]
    result = subprocess.run(argv,cwd=r.ROOT,capture_output=True,text=True,encoding='utf-8')
    paths = [Path(__file__),HERE/'terminal_followthrough.py',HERE/'test_terminal_followthrough.py',
             HERE/'followthrough_tests.xml',HERE/'qualification.json',r.BASE/'ownership.json',
             r.ROOT/'research/experiment_log.py']
    value = {'passed':result.returncode == 0,'exit_code':result.returncode,'command':sys.orig_argv,
             'pytest_command':argv,'created_at':datetime.now(timezone.utc).isoformat(),
             'stdout':result.stdout,'stderr':result.stderr,'wall_seconds':time.monotonic()-begun,
             'input_sha256':{str(p):r.sha(p) for p in paths},'new_hands':0,'current_outcomes_read':False,
             'logger_writes':0,'bound_owner':r.EXPECTED_OWNER}
    with (out if value['passed'] else HERE/'followthrough_qualification_failure.json').open('x',encoding='utf-8') as handle:
        json.dump(value,handle,indent=2,allow_nan=False)
    print(json.dumps({'passed':value['passed'],'stdout':result.stdout,'new_hands':0}))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()

