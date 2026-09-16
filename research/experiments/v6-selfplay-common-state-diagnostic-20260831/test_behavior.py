import math
import socket
from unittest.mock import patch
import pytest
import behavior_stats as stats


@pytest.fixture(autouse=True)
def no_network():
    seen=[]
    def deny(*args,**kwargs): seen.append(1); raise AssertionError('Offline only')
    with patch.object(socket.socket,'connect',deny),patch.object(socket.socket,'connect_ex',deny),patch.object(socket,'create_connection',deny):
        yield
    assert seen==[]


def vector(a,b): return [a,b]+[0.]*7


def test_identical_and_disjoint():
    same=stats.distances(vector(.3,.7),vector(.3,.7))
    assert same['tv']==same['js_bits']==0
    opposed=stats.distances(vector(1,0),vector(0,1))
    assert opposed['tv']==opposed['js_bits']==1
    assert opposed['fold_delta']==-1 and opposed['passive_delta']==1


def test_known_half_mixture():
    result=stats.distances(vector(1,0),vector(.5,.5))
    assert result['tv']==.5
    assert result['js_bits']==pytest.approx(.31127812445913283)


def test_probability_categories_sum_and_allin_subset():
    a=[0,1]+[0.]*7
    b=[0.]*9
    b[8]=1.
    result=stats.distances(a,b)
    assert result['raise_delta']==result['allin_delta']==1
    assert result['fold_delta']+result['passive_delta']+result['raise_delta']==0


@pytest.mark.parametrize('bad',[[1],[-.1,1.1]+[0]*7,[math.nan,1]+[0]*7,[math.inf,0]+[0]*7,[True,0]+[0]*7,[.2,.2]+[0]*7])
def test_bad_probabilities_rejected(bad):
    with pytest.raises(ValueError): stats.distances(bad,vector(1,0))


def test_hand_weighting_not_state_weighting():
    keys=['tv','js_bits','selected_disagreement','fold_delta','passive_delta','raise_delta','allin_delta','control_entropy_bits','treatment_entropy_bits']
    rows=[dict(hand_index=0,**{k:0. for k in keys})]+[dict(hand_index=1,**{k:1. for k in keys}) for _ in range(10)]
    result=stats.aggregate(rows,expected_hands=2)
    assert result['hand_weighted']['tv']['mean']==.5
    assert result['state_weighted']['tv']==pytest.approx(10/11)
    assert result['hand_weighted']['tv']['standard_error']==.5
    with pytest.raises(ValueError): stats.aggregate(rows,expected_hands=3)


def test_symmetry_and_finite_zero_mass():
    a,b=vector(.2,.8),vector(.6,.4)
    forward,back=stats.distances(a,b),stats.distances(b,a)
    assert forward['tv']==back['tv'] and forward['js_bits']==back['js_bits']
    assert forward['fold_delta']==-back['fold_delta']
