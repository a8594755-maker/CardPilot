import json
import math
import pytest
from pilot_stats import summarize,T7
import run_pilot as run
from review_finish import independent_estimate


def test_chip_units_and_fixed_goal_scope():
    result=summarize([[100,100] for _ in range(8)],hands_per_session=2)
    assert result['bb_per_100']==100 and result['raw_hand_ci95']==[100,100]
    assert result['session_t7_ci95']==[100,100]
    assert result['supports_separate_100k_confirmation'] and result['both_pilot_lower_bounds_positive']
    assert not result['goal_achieved'] and result['qualification_hands']==0


def test_zero_point_not_admitted():
    result=summarize([[-100,100] for _ in range(8)],hands_per_session=2)
    assert result['bb_per_100']==0 and result['session_t7_ci95']==[0,0]
    assert result['raw_hand_se']==pytest.approx(math.sqrt(160000/15)/4)
    assert not result['supports_separate_100k_confirmation']


def test_positive_point_budget_admission_is_not_significance():
    result=summarize([[200]*2500 for _ in range(7)]+[[-1000]*2500])
    assert result['bb_per_100']==50 and result['raw_hand_ci95'][0]>0 and result['session_t7_ci95'][0]<0
    assert result['supports_separate_100k_confirmation'] and not result['both_pilot_lower_bounds_positive']
    assert not result['goal_achieved']
    assert result['session_t7_ci95'][1]==pytest.approx(50+T7*150)


def test_positive_point_with_raw_uncertainty():
    result=summarize([[20000,-19900] for _ in range(8)],hands_per_session=2)
    assert result['bb_per_100']==50 and result['raw_hand_ci95'][0]<0
    assert result['supports_separate_100k_confirmation'] and not result['both_pilot_lower_bounds_positive']


@pytest.mark.parametrize('bad',[20001,True,1.0,float('nan'),float('inf')])
def test_invalid_chip_evidence(bad):
    data=[[0,0] for _ in range(8)]
    data[0][0]=bad
    with pytest.raises(ValueError): summarize(data,hands_per_session=2)


def test_incomplete_session_rejected():
    with pytest.raises(ValueError): summarize([[0]*2500]*7)
    with pytest.raises(ValueError): summarize([[0]*2500]*7+[[0]*2499])


def test_exact_fresh_commands():
    commands=[run.session_command(i) for i in range(1,9)]
    assert len({c[c.index('--seed')+1] for c in commands})==8
    assert len({c[c.index('--session-id')+1] for c in commands})==8
    for i,c in enumerate(commands,1):
        assert c[c.index('--seed')+1]==str(2026101200+i)
        assert c[c.index('--session-id')+1]==f'v6_historical_average_fresh20k_20260831_s{i:02d}'
        assert c[c.index('--hands')+1]=='2500' and c[c.index('--device')+1]=='cpu'
        assert c[c.index('--model')+1]==str(run.BASE/'frozen/final.pt')
        assert 'live-readiness' in c[0] and 'execution_code' in c[0]
    with pytest.raises(AssertionError): run.session_command(True)
    with pytest.raises(AssertionError): run.session_command(9)


def test_complete_lines_and_ambiguous_request_accounting(tmp_path):
    events=[dict(event='hand_start',hand=1),dict(event='request_intent',request_id=1),
            dict(event='request_response',request_id=1,hand=1,response=dict(winnings=100)),
            dict(event='hand_start',hand=2),dict(event='request_intent',request_id=2)]
    (tmp_path/'journal.jsonl').write_bytes(('\n'.join(json.dumps(e) for e in events)+'\n{"partial":').encode())
    (tmp_path/'hands.jsonl').write_bytes(b'{}\n{"partial":')
    assert run.raw_count(tmp_path/'hands.jsonl')==1
    assert run.raw_count(tmp_path/'missing')==0
    result=run.observe(tmp_path)
    assert result['durable_raw_hands']==1 and result['attempted_hands']==2
    assert result['ambiguous_request_ids']==[2] and result['observed_server_terminal_hands']==1


def test_independent_statistic_arithmetic():
    groups=[[((i+hand)%31-15)*100 for hand in range(2500)] for i in range(8)]
    first,second=summarize(groups),independent_estimate(groups)
    for key in ['bb_per_100','raw_hand_se','session_se']:
        assert first[key]==pytest.approx(second[key],rel=1e-12,abs=1e-10)
    for key in ['raw_hand_ci95','session_t7_ci95','session_means_bb_per_100']:
        assert first[key]==pytest.approx(second[key],rel=1e-12,abs=1e-10)
    assert first['both_pilot_lower_bounds_positive']==second['both_pilot_lower_bounds_positive']


def test_readiness_prerequisites_without_network():
    if run.CONFIRM_SHA is None or run.PARITY_SHA is None:
        with pytest.raises(AssertionError, match='not frozen'):
            run.verify()
    else:
        run.verify()
    assert run.excluded_tokens()
    assert run.MODEL_SHA=='cd7ce2b27cf3a86e96141432c92c6f92a3eb923dce519d1f1128af5acbb2364b'


def test_missing_admission_hash_fails_before_any_live_call(monkeypatch):
    monkeypatch.setattr(run, 'CONFIRM_SHA', None)
    with pytest.raises(AssertionError, match='not frozen'):
        run.verify()


def test_all_prior_corrected_v6_cohorts_excluded():
    paths = run.prior_audits()
    assert len(paths) == 5 and len({str(p) for _, p in paths}) == 5
    assert {p.name for _, p in paths} == {'combined_audit.json', 'control25_combined_audit.json', 'selfplay75_combined_audit.json'}
    assert any('v6-physical1m-fresh20k' in str(p) for _, p in paths)
