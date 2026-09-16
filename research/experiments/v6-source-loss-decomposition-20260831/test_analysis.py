import copy
import math
import pytest
import analyze


def row(chips=-200,seat=0,kind='fold',folded=0):
    return dict(winnings_chips=chips,terminal_response=dict(client_pos=seat,board=['a','b','c']),
                terminal_validation=dict(status='PASS',terminal_kind=kind,folded_player=folded))


def test_chip_units_and_additive_contributions():
    left,right=analyze.summarize([-100,300],4),analyze.summarize([-200,400],4)
    assert left['conditional_bb_per_100']==100 and left['contribution_bb_per_100']==50
    assert left['contribution_bb_per_100']+right['contribution_bb_per_100']==100


def test_exhaustive_boundaries_and_seats():
    for chips,label in [(0,'0'),(100,'1..100'),(101,'101..500'),(500,'101..500'),(501,'501..2000'),
                        (2000,'501..2000'),(2001,'2001..5000'),(5001,'5001..10000'),(10001,'10001..20000'),(20000,'10001..20000')]:
        for sign in [-1,1]: assert analyze.categories(row(chips*sign))['absolute_payoff_chips']==label
    assert analyze.categories(row())['terminal_kind']=='hero_fold'
    assert analyze.categories(row(seat=1))['terminal_kind']=='opponent_fold'
    assert analyze.categories(row(kind='showdown',folded=None))['terminal_kind']=='showdown'


@pytest.mark.parametrize('bad',[row(chips=1.5),row(chips=20001),row(seat=3),row(kind='unknown'),row(folded=None)])
def test_bad_evidence_rejected(bad):
    with pytest.raises(ValueError): analyze.categories(bad)


def decision():
    return dict(response=dict(client_pos=0,board=[]),behavior_probs=[.25,.75]+[0]*7,
                action_table=['f','c']+[None]*7,legal_mask=[1,1]+[0]*7,selected_action_slot=1,
                direct_increment='c',behavior_action_probability=.75,policy_mode='sample',temperature=1)


def test_decision_summary_is_saved_actions_not_model_queries():
    d=decision()
    assert analyze.decision_bucket(d)==('BB/preflop','call')
    for field,value in [('behavior_action_probability',.1),('direct_increment','b100'),('temperature',.5),
                         ('behavior_probs',[math.nan]+[0]*8),('selected_action_slot',9)]:
        bad=copy.deepcopy(d)
        bad[field]=value
        with pytest.raises(ValueError): analyze.decision_bucket(bad)
