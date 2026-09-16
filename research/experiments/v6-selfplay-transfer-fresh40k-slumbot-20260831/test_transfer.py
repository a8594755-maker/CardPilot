import json
import pytest
import run_transfer as run
import review_finish as review


def test_all_exact_commands_match_reserved_schedule():
    commands=[run.session_command(item) for item in run.PLAN]
    assert len(commands)==16
    assert len({c[c.index('--seed')+1] for c in commands})==len({c[c.index('--session-id')+1] for c in commands})==16
    for item,cmd in zip(run.PLAN,commands):
        assert cmd[0]==str(run.READY/'execution_code/source_files/scripts/alpha_holdem/play_slumbot_v6_journaled.py')
        for key,value in [('--model',str(run.BASE/'frozen'/f'{item["arm"]}.pt')),('--hands','2500'),
                          ('--seed',str(item['policy_seed'])),('--session-id',item['session_id']),
                          ('--out-dir',str(run.session_dir(item))),('--device','cpu')]:
            assert cmd[cmd.index(key)+1]==value
        assert len(cmd)==13 and not any(v in cmd for v in ['--resume','--greedy','--overwrite'])


def test_no_unregistered_session_command():
    with pytest.raises(AssertionError): run.session_command(dict(run.PLAN[0],policy_seed=1))


def test_durable_prefix_and_ambiguous_request_accounting(tmp_path):
    events=[dict(event='hand_start',hand=1),dict(event='request_intent',request_id=1),
        dict(event='request_response',request_id=1,hand=1,response=dict(winnings=100)),
        dict(event='hand_start',hand=2),dict(event='request_intent',request_id=2)]
    (tmp_path/'journal.jsonl').write_bytes(('\n'.join(json.dumps(e) for e in events)+'\n{').encode())
    (tmp_path/'hands.jsonl').write_bytes(b'{}\n{')
    assert run.raw_count(tmp_path/'hands.jsonl')==1 and run.raw_count(tmp_path/'missing')==0
    report=run.observe(tmp_path)
    assert report['durable_raw_hands']==1 and report['attempted_hands']==2
    assert report['ambiguous_request_ids']==[2] and report['observed_server_terminal_hands']==1


def test_independent_raw_session_and_contrast_arithmetic():
    groups={arm:[[((i+h*scale)%257-120)*10 for h in range(2500)] for i in range(8)]
        for arm,scale in [('control25',1),('selfplay75',7)]}
    result=run.protocol.summarize_pair(groups,evidence_valid=True)
    for arm in run.ARMS:
        for key,value in review.interval_arm(groups[arm]).items():
            assert value==pytest.approx(result['arms'][arm][key])
    raw={arm:[v for g in groups[arm] for v in g] for arm in run.ARMS}
    sessions={arm:result['arms'][arm]['session_means_bb_per_100'] for arm in run.ARMS}
    for unit,values in [('raw_hand',raw),('session',sessions)]:
        for label,confidence in [('ordinary',.95),('adjusted',1-.05/3)]:
            observed=review.contrast(values['selfplay75'],values['control25'],confidence)
            for key,value in observed.items(): assert value==pytest.approx(result['contrast_selfplay75_minus_control25'][unit][label][key])


def test_both_bad_points_never_allocate_qualification():
    groups={arm:[[-100]*2500 for _ in range(8)] for arm in run.ARMS}
    result=run.protocol.summarize_pair(groups,evidence_valid=True)
    assert result['selected_for_separate_fresh100k'] is None and result['qualification_hands']==0 and not result['goal_achieved']
    with pytest.raises(ValueError): run.protocol.summarize_pair(groups,evidence_valid=False)


def test_captured_protocol_identity():
    assert run.sha(run.helper)==run.PROTOCOL_SHA
    assert run.sha(run.PROTOCOL/'analysis.json')==run.PROTOCOL_REVIEW_SHA
    assert run.read(run.PROTOCOL/'analysis.json')['tests_passed']==34
