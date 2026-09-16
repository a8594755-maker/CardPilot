import json
from pathlib import Path
import pytest
import run_probe as probe


def test_exact_two_session_commands():
    commands=[probe.session_command(i) for i in [1,2]]
    assert len(set(cmd[cmd.index('--seed')+1] for cmd in commands))==2
    assert len(set(cmd[cmd.index('--session-id')+1] for cmd in commands))==2
    for i,cmd in enumerate(commands,1):
        assert cmd[cmd.index('--hands')+1]=='8'
        assert cmd[cmd.index('--seed')+1]==str(2026092800+i)
        assert cmd[cmd.index('--device')+1]=='cpu'
        assert cmd[cmd.index('--model')+1]==str(probe.BASE/'frozen/source.pt')
        assert 'execution_code/source_files' in Path(cmd[0]).as_posix()
    with pytest.raises(AssertionError): probe.session_command(3)


def test_only_complete_lines_count(tmp_path):
    path=tmp_path/'hands.jsonl'
    path.write_bytes(b'{}\n{"partial":')
    assert probe.lines(path)==[{}]
    assert probe.lines(tmp_path/'missing')==[]


def test_observed_terminals_not_mistaken_for_valid_raw(tmp_path):
    events=[dict(event='hand_start',hand=1),dict(event='request_intent',request_id=1),
            dict(event='request_response',request_id=1,hand=1,response=dict(winnings=100)),
            dict(event='hand_start',hand=2),dict(event='request_intent',request_id=2),
            dict(event='request_error',request_id=2)]
    (tmp_path/'journal.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in events))
    result=probe.observe(tmp_path)
    assert result['durable_raw_hands']==0 and result['observed_server_terminal_hands']==1
    assert result['ambiguous_request_ids']==[2] and result['attempted_hands']==2


def test_invalid_complete_json_not_silently_skipped(tmp_path):
    path=tmp_path/'hands.jsonl'
    path.write_bytes(b'{bad}\n')
    with pytest.raises(json.JSONDecodeError): probe.lines(path)
