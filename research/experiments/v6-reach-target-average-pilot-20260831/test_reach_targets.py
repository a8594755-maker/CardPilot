import numpy as np
import pytest
from reach_targets import relabel_hand,reservoir_index,scatter_hand

def fixture(n=3):
    p=np.zeros((3,n,9))
    for teacher,value in enumerate((.9,.5,.1)):
        p[teacher,:,0]=value;p[teacher,:,1]=1-value
    return p

def test_separate_own_reach_per_seat_no_current_action_leak():
    q,w=relabel_hand(fixture(),[0,1,0],[1,0,1])
    assert np.allclose(w[0],[1/3]*3) and np.allclose(w[1],[1/3]*3)
    assert np.allclose(w[2],[.1,.5,.9]/np.array([1.5]*3))
    assert np.allclose(q[:2,0],[.5,.5])
    assert q[2,0]==pytest.approx((.1*.9+.5*.5+.9*.1)/1.5)

def test_opponent_action_change_does_not_change_hero_posterior():
    first=relabel_hand(fixture(),[0,1,0],[1,0,1])[0]
    second=relabel_hand(fixture(),[0,1,0],[1,1,1])[0]
    assert np.array_equal(first[2],second[2])

def test_reset_at_every_hand():
    q,w=relabel_hand(fixture(),[0,0,0],[1,1,1])
    fresh,freshw=relabel_hand(fixture(1),[0],[1])
    assert np.allclose(freshw,[np.ones(3)/3])
    assert not np.allclose(w[-1],freshw[0])

def test_q_is_posterior_expectation_not_observed_teacher():
    p=fixture()
    q,w=relabel_hand(p,[0,0,0],[0,1,0])
    assert np.allclose(q,np.einsum('ti,itj->tj',w,p))
    assert not np.array_equal(q,p[0]) and not np.array_equal(q,p[2])

@pytest.mark.parametrize('actors,slots',[([True],[1]),([2],[1]),([0],[9]),([0.],[1]),([0],[True])])
def test_invalid_sequences(actors,slots):
    with pytest.raises(ValueError):relabel_hand(fixture(1),actors,slots)

def test_scatter_retains_exact_reservoir_order_and_rejects_replay():
    ids=np.array([[1,1],[0,0],[1,0]])
    index=reservoir_index(ids)
    output=np.full((3,9),np.nan);seen=np.zeros(3,dtype=bool)
    q,_=relabel_hand(fixture(2),[0,0],[1,1])
    assert scatter_hand(0,q,index,output,seen)==1
    assert scatter_hand(1,q,index,output,seen)==2 and seen.all()
    assert np.array_equal(output[0],q[1]) and np.array_equal(output[1],q[0]) and np.array_equal(output[2],q[0])
    with pytest.raises(ValueError,match='twice'):scatter_hand(1,q,index,output,seen)

def test_duplicate_ids_rejected():
    with pytest.raises(ValueError):reservoir_index(np.array([[1,0],[1,0]]))

