import copy
import math
import socket
import statistics
from unittest.mock import patch
import pytest
from scipy.stats import ttest_ind
import pair_protocol as protocol


@pytest.fixture(autouse=True)
def no_network():
    attempts=[]
    def deny(*args,**kwargs):
        attempts.append(1)
        raise AssertionError('Offline protocol tests prohibit network')
    with patch.object(socket.socket,'connect',deny),patch.object(socket.socket,'connect_ex',deny),patch.object(socket,'create_connection',deny):
        yield
    assert attempts==[]


@pytest.fixture
def groups():
    return dict(control25=[[100+7*g+(i*37)%101-50 for i in range(2500)] for g in range(8)],
                selfplay75=[[125+9*g+(i*19)%303-151 for i in range(2500)] for g in range(8)])


@pytest.fixture
def audits():
    hashes=dict(control25='a'*64,selfplay75='b'*64)
    result={arm:dict(status='PASS',sessions=8,successful_hands=20000,model_sha256=hashes[arm],
                    token_chains_disjoint=True,results=[]) for arm in protocol.ARMS}
    for item in protocol.schedule():
        row=dict(status='PASS',session_id=item['session_id'],policy_seed=item['policy_seed'],model_sha256=hashes[item['arm']],
            successful_hands=2500,attempted_hands=2500,target_hands=2500,decision_replays=8000,policy_draws_verified=8000,
            pending_request_id=None,protocol_failures=[],committed_without_raw=[],partial_journal=False,partial_hands=False,
            token_sha256=[f'{item["launch_index"]+1:064x}'])
        result[item['arm']]['results'].append(row)
    return result,hashes


def test_fixed_balanced_schedule_and_unique_identifiers():
    rows=protocol.schedule()
    assert len(rows)==16 and sum(r['hands'] for r in rows)==40000
    assert [r['launch_index'] for r in rows]==list(range(16))
    assert len({r['session_id'] for r in rows})==len({r['policy_seed'] for r in rows})==16
    for wave,order in [(0,['control25','selfplay75']),(1,['selfplay75','control25'])]:
        members=[r for r in rows if r['wave']==wave]
        assert [r['arm'] for r in members]==order*4
        for arm in protocol.ARMS:
            assert len([r for r in members if r['arm']==arm])==4
    for arm,base in [('control25',2026100700),('selfplay75',2026100800)]:
        assert [r['index'] for r in rows if r['arm']==arm]==list(range(1,9))
        assert [r['policy_seed'] for r in rows if r['arm']==arm]==list(range(base+1,base+9))


@pytest.mark.parametrize('confidence',[.95,1-.05/3])
def test_welch_against_independent_scipy_raw_and_sessions(groups,confidence):
    for values in [{arm:[x for g in groups[arm] for x in g] for arm in protocol.ARMS},
                   {arm:[statistics.mean(g) for g in groups[arm]] for arm in protocol.ARMS}]:
        a,b=values['selfplay75'],values['control25']
        got=protocol.welch(a,b,confidence)
        expected=ttest_ind(a,b,equal_var=False)
        bounds=expected.confidence_interval(confidence_level=confidence)
        assert got['ci']==pytest.approx([bounds.low,bounds.high])
        assert got['degrees_of_freedom']==pytest.approx(expected.df)
        assert got['bb_per_100']==pytest.approx(math.fsum(a)/len(a)-math.fsum(b)/len(b))


def test_not_an_accidental_paired_hand_estimator():
    a=[x+50 for x in range(100)]
    b=list(range(100))
    got=protocol.welch(a,b)
    assert statistics.stdev([x-y for x,y in zip(a,b)])==0
    assert got['standard_error']>0 and got['ci'][0]<50<got['ci'][1]
    assert got==protocol.welch(a,list(reversed(b)))


def test_chip_units_cluster_offsets_and_family_intervals(groups):
    result=protocol.summarize_pair(groups,evidence_valid=True)
    assert result['total_pilot_hands']==40000 and not result['goal_achieved'] and not result['internal_scores_used']
    assert result['qualification_hands']==result['pilot_hands_pooled_into_qualification']==0
    for arm in protocol.ARMS:
        got=result['arms'][arm]
        flat=[x for g in groups[arm] for x in g]
        mean=math.fsum(flat)/20000
        assert got['bb_per_100']==pytest.approx(mean)
        se=math.sqrt(math.fsum((x-mean)**2 for x in flat)/19999/20000)
        assert got['raw_hand_se']==pytest.approx(se)
        for normal,adjusted in [('raw_hand_ci95','raw_hand_ci_adjusted'),('session_t7_ci95','session_t7_ci_adjusted')]:
            assert got[adjusted][0]<got[normal][0]<got[normal][1]<got[adjusted][1]
    constant=[[100]*2500 for _ in range(8)]
    assert protocol.arm_summary(constant)['bb_per_100']==100 #1bb/hand=100bb/100


@pytest.mark.parametrize('mutation',['missing_arm','missing_session','short_session','bool','float','overflow'])
def test_incomplete_or_malformed_fixed_sample_rejected(groups,mutation):
    if mutation=='missing_arm': groups.pop('control25')
    elif mutation=='missing_session': groups['control25'].pop()
    elif mutation=='short_session': groups['control25'][0].pop()
    else: groups['control25'][0][0]={'bool':True,'float':1.,'overflow':20001}[mutation]
    with pytest.raises(ValueError): protocol.summarize_pair(groups,evidence_valid=True)


@pytest.mark.parametrize('bad',[[],[1],[1,math.inf],[0,math.nan],[True,1]])
def test_invalid_welch_inputs(bad):
    with pytest.raises(ValueError): protocol.welch(bad,[1,2])


def test_zero_variance_explicitly_flagged_not_goal_success():
    result=protocol.welch([2]*8,[1]*8)
    assert result['empirical_zero_variance'] and result['degrees_of_freedom'] is None and result['ci']==[1,1]


@pytest.mark.parametrize('points,selected',[((-2,-1),None),((0,0),None),((1,-1),'control25'),((-1,1),'selfplay75'),((2,3),'selfplay75'),((3,2),'control25'),((2,2),'control25')])
def test_fixed_positive_point_allocation(points,selected):
    summaries={arm:dict(bb_per_100=value) for arm,value in zip(protocol.ARMS,points)}
    assert protocol.allocation(summaries,evidence_valid=True)==selected
    with pytest.raises(ValueError): protocol.allocation(summaries,evidence_valid=False)


def test_cross_arm_audit_valid(audits):
    data,hashes=audits
    got=protocol.validate_combined_audits(data,hashes,{'f'*64})
    assert got['status']=='PASS' and got['hands']==40000 and not got['server_rng_independence_proven']


@pytest.mark.parametrize('mutation',['cross_token','prior_token','seed','id','model','partial','replay','missing_arm','short_arm'])
def test_cross_arm_audit_fails_closed(audits,mutation):
    data,hashes=audits
    row=data['selfplay75']['results'][0]
    prior={'f'*64}
    if mutation=='cross_token': row['token_sha256']=data['control25']['results'][0]['token_sha256']
    elif mutation=='prior_token': prior=set(row['token_sha256'])
    elif mutation=='seed': row['policy_seed']+=1
    elif mutation=='id': row['session_id']=data['control25']['results'][0]['session_id']
    elif mutation=='model': row['model_sha256']=hashes['control25']
    elif mutation=='partial': row['partial_hands']=True
    elif mutation=='replay': row['decision_replays']-=1
    elif mutation=='missing_arm': data.pop('selfplay75')
    elif mutation=='short_arm': row['successful_hands']=2499
    with pytest.raises(ValueError): protocol.validate_combined_audits(data,hashes,prior)
