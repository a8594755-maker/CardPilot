"""One-shot prerequisite chain: exact current owner exit -> qualified raw review.

No Slumbot requests, model changes, training, logger writes, policy selection or
automatic recovery. Existing incomplete/failed executions are preserved, not retried.
"""
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_completed as review

EXPECTED_OWNER = {'pid': 11988, 'create_time': 1788668926.081722}


def owner_matches(execution, expected):
    return execution['pid'] == expected['pid'] and abs(execution['create_time'] - expected['create_time']) < .001


def wait_for_owner(expected, live=None, read_execution=None, pause=None, on_observation_error=None):
    live = live or review.r.live_identity
    read_execution = read_execution or (lambda: review.r.read(review.BASE / 'execution.json'))
    pause = pause or time.sleep
    while True:
        try:
            execution = read_execution()
            review.r.protocol.require(owner_matches(execution, expected), 'bound controller identity replaced')
            if not live(expected):
                return execution
        except (OSError, json.JSONDecodeError, psutil.AccessDenied) as exc:
            # Observation failure is not evidence of owner exit or a new attempt.
            if on_observation_error:
                on_observation_error(exc)
        pause(15)


def review_command():
    return [sys.executable, '-B', str(HERE / 'review_completed.py'),
            '--out', str(review.BASE / 'post_terminal_review.json')]


def validate_qualification():
    r = review.r
    value = r.read(HERE / 'qualification.json')
    r.protocol.require(value['passed'] is True and value['exit_code'] == 0, 'reviewer not qualified')
    r.check_hashes(value['source_sha256'])
    r.protocol.require(r.sha(HERE / 'tests.xml') == value['xml_sha256'], 'review test artifact changed')
    follow = r.read(HERE / 'followthrough_qualification_v2.json')
    r.protocol.require(follow['passed'] is True and follow['exit_code'] == 0, 'followthrough not qualified')
    r.check_hashes(follow['source_sha256'])
    r.protocol.require(r.sha(HERE / 'followthrough_tests_v2.xml') == follow['xml_sha256'], 'followthrough tests changed')


def run():
    r, base = review.r, review.BASE
    path = HERE / 'followthrough_execution.json'
    r.protocol.require(not path.exists() and not (base / 'post_terminal_review.json').exists(),
                       'existing attempt/report; no automatic rerun')
    validate_qualification()
    execution = r.read(base / 'execution.json')
    r.protocol.require(owner_matches(execution, EXPECTED_OWNER) and r.live_identity(EXPECTED_OWNER),
                       'must attach to the exact currently live controller')
    state = {'status': 'WAITING_BOUND_OWNER', 'pid': os.getpid(),
        'create_time': psutil.Process().create_time(), 'bound_owner': EXPECTED_OWNER,
        'started_at': datetime.now(timezone.utc).isoformat(),
        'command': [sys.executable, *sys.orig_argv[1:]], 'review_child': None,
        'observation_errors': [],
        'no_new_poker_requests': True, 'no_logger_writes': True, 'goal_achieved': False}
    r.write_new(path, state)
    started = time.monotonic()
    try:
        def observed_error(exc):
            state['observation_errors'].append({'at': datetime.now(timezone.utc).isoformat(), 'error': repr(exc)})
            r.atomic_json(path, state)
        wait_for_owner(EXPECTED_OWNER, on_observation_error=observed_error)
        validate_qualification()
        r.protocol.require(review.readiness()['ready'], 'controller terminal but fixed-budget evidence incomplete')
        r.protocol.require(not (base / 'post_terminal_review.json').exists(), 'another review appeared; preserve')
        argv = review_command()
        with (HERE / 'terminal_review.stdout.log').open('x', encoding='utf-8') as output, \
             (HERE / 'terminal_review.stderr.log').open('x', encoding='utf-8') as error:
            child = subprocess.Popen(argv, cwd=review.ROOT, stdout=output, stderr=error,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            state['review_child'] = {'pid': child.pid, 'create_time': psutil.Process(child.pid).create_time(),
                                    'command': argv, 'exit_code': None}
            state['status'] = 'REVIEW_RUNNING'
            r.atomic_json(path, state)
            state['review_child']['exit_code'] = child.wait()
        r.protocol.require(state['review_child']['exit_code'] == 0, 'qualified review failed; no retry')
        report_path = base / 'post_terminal_review.json'
        report = r.read(report_path)
        r.protocol.require(report['passed'] is True and report['evaluation_hands'] == 80000 and
                           report['final_qualification_hands'] == 0 and report['goal_achieved'] is False,
                           'completed review scope invalid')
        state.update(status='REVIEW_COMPLETE_NEEDS_RESEARCH_DECISION', review_sha256=r.sha(report_path))
    except BaseException as exc:
        state.update(status='STOPPED_PRESERVED_NO_RETRY', error=repr(exc))
    finally:
        state.update(ended_at=datetime.now(timezone.utc).isoformat(), wall_seconds=time.monotonic() - started)
        r.atomic_json(path, state)
        print(json.dumps({'status': state['status'], 'new_hands': 0, 'goal_achieved': False}), flush=True)
    if state['status'] != 'REVIEW_COMPLETE_NEEDS_RESEARCH_DECISION':
        raise SystemExit(1)


if __name__ == '__main__':
    run()
