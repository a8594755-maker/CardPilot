import copy
import json
from pathlib import Path
import sys

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import terminal_followthrough as f


def test_waits_until_exact_owner_absent():
    calls,pauses = [],[]
    def live(owner):
        calls.append(owner)
        return len(calls) < 3
    f.wait_owner(read_owner=lambda:copy.deepcopy(f.r.EXPECTED_OWNER),live=live,pause=pauses.append)
    assert len(calls) == 3 and pauses == [15,15]


@pytest.mark.parametrize('error',[OSError('temporary'),json.JSONDecodeError('partial','',0)])
def test_observation_failure_does_not_signal_exit(error):
    reads,errors,pauses = [],[],[]
    def read():
        reads.append(1)
        if len(reads) == 1:
            raise error
        return copy.deepcopy(f.r.EXPECTED_OWNER)
    f.wait_owner(read_owner=read,live=lambda owner:False,pause=pauses.append,on_error=errors.append)
    assert len(reads) == 2 and errors == [error] and pauses == [15]


@pytest.mark.parametrize('change',[{'pid':1},{'create_time':1.}])
def test_replaced_identity_is_not_a_resume(change):
    value = dict(f.r.EXPECTED_OWNER,**change)
    with pytest.raises(ValueError,match='replaced'):
        f.wait_owner(read_owner=lambda:value,live=lambda _:False,pause=lambda _:None)


def test_existing_report_prevents_any_new_launch(tmp_path,monkeypatch):
    (tmp_path/'post_terminal_review.json').write_text('{}',encoding='utf-8')
    monkeypatch.setattr(f.r,'BASE',tmp_path)
    with pytest.raises(ValueError,match='preserve'):
        f.run()


def test_failed_qualification_prevents_launch(monkeypatch):
    monkeypatch.setattr(f.r,'validate_review_qualification',lambda:None)
    monkeypatch.setattr(f.r,'read',lambda path:{'passed':False,'exit_code':1})
    with pytest.raises(ValueError,match='qualified'):
        f.validate()

