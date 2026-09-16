import importlib.util
from pathlib import Path
import sys
import pytest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
spec = importlib.util.spec_from_file_location('sampled_controller_test', BASE / 'run_external.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def summary():
    item = r.p.schedule()[0]
    return item, dict(status='COMPLETED', successful_hands=2500, attempted_hands=2500, target_hands=2500,
        session_id=item['session_id'], policy_seed=item['policy_seed'], model_sha256=r.p.MODEL_HASHES[item['arm']],
        policy_mode='sample', policy_temperature=1, observation_bridge_contract=r.p.BRIDGE,
        frozen_identity_verified=True, closing_event_persisted=True)


def test_summary():
    item, s = summary()
    r.validate_summary(s, item)


@pytest.mark.parametrize('key,value', [('status','FAILED'), ('successful_hands',2499),
    ('policy_mode','greedy'), ('model_sha256','bad'), ('closing_event_persisted',False)])
def test_failed_summary(key, value):
    item, s = summary()
    s[key] = value
    with pytest.raises(ValueError):
        r.validate_summary(s, item)


def test_hash_guard(tmp_path):
    f = tmp_path / 'input'
    f.write_text('one')
    inputs = {str(f):r.sha(f)}
    r.check(inputs)
    f.write_text('two')
    with pytest.raises(ValueError):
        r.check(inputs)


def test_exclusive_evidence(tmp_path):
    f = tmp_path / 'evidence'
    r.write(f, dict(one=1))
    with pytest.raises(FileExistsError):
        r.write(f, dict(one=2))
