import importlib.util
from pathlib import Path
import sys
import pytest

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
spec = importlib.util.spec_from_file_location('post_terminal_review_tests',BASE/'review_external.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def fixtures():
    result = {}
    for arm in r.p.ARMS:
        rows = []
        for item in r.p.schedule():
            if item['arm'] != arm:
                continue
            rows.append(dict(session_id=item['session_id'],status='PASS',model_sha256=r.p.MODEL_HASHES[arm],
                policy_seed=item['policy_seed'],successful_hands=2500,attempted_hands=2500,target_hands=2500,
                pending_request_id=None,protocol_failures=0,committed_without_raw=0,partial_journal=False,
                partial_hands=False,decision_replays=100,policy_draws_verified=100,
                token_sha256=[item['session_id']]))
        result[arm] = dict(status='PASS',sessions=8,successful_hands=20000,results=rows)
    return result


def test_complete_cross_audit():
    assert r.verify_audits(fixtures(),[])['decision_replays'] == 3200


def test_prior_token_rejected():
    with pytest.raises(ValueError):
        r.verify_audits(fixtures(),[r.p.schedule()[0]['session_id']])


@pytest.mark.parametrize('key,value',[('successful_hands',2499),('model_sha256','bad'),
    ('decision_replays',0),('partial_hands',True),('policy_seed',-1)])
def test_bad_replay_rejected(key,value):
    data = fixtures()
    data[r.p.ARMS[0]]['results'][0][key] = value
    with pytest.raises(ValueError):
        r.verify_audits(data,[])


def test_live_controller_blocks_reading(monkeypatch):
    import os
    import psutil
    monkeypatch.setattr(r,'read',lambda path: dict(pid=os.getpid(),create_time=psutil.Process().create_time()))
    with pytest.raises(ValueError,match='Controller still owns evidence'):
        r.terminal_ready()
