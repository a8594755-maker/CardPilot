"""One-shot exact-owner exit -> independent terminal review; no logger or poker writes."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import terminal_review as r
sys.path.insert(0,str(r.ROOT))
from research.experiment_log import atomic_json


def wait_owner(read_owner=None, live=None, pause=None, on_error=None):
    read_owner = read_owner or (lambda:r.read(r.BASE/'ownership.json'))
    live = live or (lambda owner:r.live(owner['pid'],owner['create_time']))
    pause = pause or time.sleep
    while True:
        try:
            owner = read_owner()
            r.require(owner['pid'] == r.EXPECTED_OWNER['pid'] and
                abs(owner['create_time']-r.EXPECTED_OWNER['create_time']) < .001,'owner replaced')
            if not live(owner):
                return
        except (OSError,json.JSONDecodeError,psutil.AccessDenied) as exc:
            if on_error:
                on_error(exc)
        pause(15)


def validate():
    r.validate_review_qualification()
    q = r.read(HERE/'followthrough_qualification.json')
    r.require(q['passed'] and q['exit_code'] == 0,'followthrough not qualified')
    r.require(all(r.sha(p) == h for p,h in q['input_sha256'].items()),'followthrough input changed')


def run():
    path = HERE/'followthrough_execution.json'
    output = r.BASE/'post_terminal_review.json'
    r.require(not path.exists() and not output.exists(),'preserve earlier attempt/report')
    validate()
    owner = r.read(r.BASE/'ownership.json')
    r.require(owner['pid'] == r.EXPECTED_OWNER['pid'] and
        abs(owner['create_time']-r.EXPECTED_OWNER['create_time']) < .001 and
        r.live(owner['pid'],owner['create_time']),'attach only to exact live owner')
    state = {'status':'WAITING_BOUND_OWNER','pid':os.getpid(),'create_time':psutil.Process().create_time(),
        'bound_owner':r.EXPECTED_OWNER,'command':sys.orig_argv,'review_child':None,
        'started_at':datetime.now(timezone.utc).isoformat(),'observation_errors':[],
        'no_poker_requests':True,'no_logger_writes':True,'goal_achieved':False}
    with path.open('x',encoding='utf-8') as handle:
        json.dump(state,handle,indent=2)
    begun = time.monotonic()
    try:
        def on_error(exc):
            state['observation_errors'].append({'at':datetime.now(timezone.utc).isoformat(),'error':repr(exc)})
            atomic_json(path,state)
        wait_owner(on_error=on_error)
        validate()
        r.terminal_guard()
        r.require(not output.exists(),'review appeared; preserve')
        argv = [sys.executable,'-B',str(HERE/'terminal_review.py')]
        with (HERE/'terminal_review.stdout.log').open('x',encoding='utf-8') as stdout, \
             (HERE/'terminal_review.stderr.log').open('x',encoding='utf-8') as stderr:
            child = subprocess.Popen(argv,cwd=r.ROOT,stdout=stdout,stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            state['review_child'] = {'pid':child.pid,'create_time':psutil.Process(child.pid).create_time(),
                                    'command':argv,'exit_code':None}
            state['status'] = 'REVIEW_RUNNING'
            atomic_json(path,state)
            state['review_child']['exit_code'] = child.wait()
        r.require(state['review_child']['exit_code'] == 0,'review failed; no retry')
        report = r.read(output)
        r.require(report['passed'] and report['accounting']['evaluation_hands'] == 32768 and
                  report['accounting']['final_qualification_hands'] == 0 and not report['goal_achieved'],
                  'wrong review scope')
        state.update(status='REVIEW_COMPLETE_NEEDS_RESEARCH_DECISION',review_sha256=r.sha(output))
    except BaseException as exc:
        state.update(status='STOPPED_PRESERVED_NO_RETRY',error=repr(exc))
    finally:
        state.update(ended_at=datetime.now(timezone.utc).isoformat(),wall_seconds=time.monotonic()-begun)
        atomic_json(path,state)
        print(json.dumps({'status':state['status'],'new_hands':0,'goal_achieved':False}),flush=True)
    if state['status'] != 'REVIEW_COMPLETE_NEEDS_RESEARCH_DECISION':
        raise SystemExit(1)


if __name__ == '__main__':
    run()

