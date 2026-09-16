import math
import pytest
from baseline_stats import summarize,T7


def test_chip_units_and_identical_sessions():
    r=summarize([[100,100] for _ in range(8)],hands_per_session=2)
    assert r['bb_per_100']==100 and r['raw_hand_ci95']==[100,100] and r['session_t7_ci95']==[100,100]
    assert r['supports_separate_100k_confirmation'] and not r['goal_achieved']


def test_raw_and_session_variance_differ():
    r=summarize([[-100,100] for _ in range(8)],hands_per_session=2)
    assert r['bb_per_100']==0 and r['session_t7_ci95']==[0,0]
    assert r['raw_hand_se']==pytest.approx(math.sqrt(160000/15)/4)
    assert not r['supports_separate_100k_confirmation']


def test_session_cluster_check_blocks_pseudoreplication():
    r=summarize([[200]*2500 for _ in range(7)]+[[-1000]*2500])
    assert r['bb_per_100']==50 and r['raw_hand_ci95'][0]>0 and r['session_t7_ci95'][0]<0
    assert not r['supports_separate_100k_confirmation']
    assert r['session_t7_ci95'][1]==pytest.approx(50+T7*150)


@pytest.mark.parametrize('bad',[20001,True,1.0,float('nan'),float('inf')])
def test_invalid_chip_evidence_fails(bad):
    data=[[0,0] for _ in range(8)]
    data[0][0]=bad
    with pytest.raises(ValueError): summarize(data,hands_per_session=2)


def test_incomplete_or_unequal_sessions_fail():
    with pytest.raises(ValueError): summarize([[0]*2500]*7)
    with pytest.raises(ValueError): summarize([[0]*2500]*7+[[0]*2499])


def test_exact_eight_new_sessions_and_source():
    import run_baseline as run
    commands=[run.session_command(i) for i in range(1,9)]
    assert len({c[c.index('--seed')+1] for c in commands})==8
    assert len({c[c.index('--session-id')+1] for c in commands})==8
    for i,c in enumerate(commands,1):
        assert c[c.index('--seed')+1]==str(2026092900+i)
        assert c[c.index('--hands')+1]=='2500' and c[c.index('--device')+1]=='cpu'
        assert c[c.index('--model')+1]==str(run.BASE/'frozen/source.pt')
        assert 'live-readiness' in c[0] and 'execution_code' in c[0]
    with pytest.raises(AssertionError): run.session_command(9)
    with pytest.raises(AssertionError): run.session_command(True)


def test_complete_raw_count_only(tmp_path):
    import run_baseline as run
    p=tmp_path/'hands.jsonl'
    p.write_bytes(b'{}\n{}\n{"unfinished":')
    assert run.raw_count(p)==2 and run.raw_count(tmp_path/'missing')==0
