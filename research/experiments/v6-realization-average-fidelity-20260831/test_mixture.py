import math
import numpy as np
import pytest
from mixture import Posterior,distances,estimate,hand_summary

def pair(a,b):
    return np.asarray([[a,1-a]+[0.]*7,[b,1-b]+[0.]*7])

def test_reach_weighting_not_statewise_mean():
    p=Posterior(2)
    first=pair(.9,.1)
    q,w=p.before(first)
    assert np.allclose(q[:2],[.5,.5]) and np.allclose(w,[.5,.5])
    p.observe_own_action(first,0)
    q,w=p.before(pair(.8,.1))
    assert np.allclose(w,[.9,.1]) and np.allclose(q[:2],[.73,.27])
    assert not np.allclose(q,pair(.8,.1).mean(0))

def test_current_action_not_used_before_prediction():
    p=Posterior(2)
    q_before,_=p.before(pair(.99,.01))
    p.observe_own_action(pair(.99,.01),0)
    q_after,_=p.before(pair(.99,.01))
    assert q_before[0]==pytest.approx(.5) and q_after[0]>.98

def test_no_opponent_or_chance_update_and_reset():
    p=Posterior()
    before=p.weights().copy()
    assert np.array_equal(before,p.weights())
    p.observe_own_action(np.asarray([[.9,.1]+[0.]*7,[.5,.5]+[0.]*7,[.1,.9]+[0.]*7]),0)
    assert not np.allclose(before,p.weights())
    assert np.allclose(Posterior().weights(),[1/3]*3)

def test_zero_reach_and_impossible_prefix():
    p=Posterior(2)
    p.observe_own_action(pair(1.,0.),0)
    assert np.allclose(p.weights(),[1.,0.])
    with pytest.raises(ValueError,match='Unreachable'):p.observe_own_action(pair(0.,1.),0)

def test_long_sequence_stable_without_reset():
    p=Posterior(2)
    for _ in range(2000):p.observe_own_action(pair(.001,.002),0)
    assert np.isfinite(p.weights()).all() and p.weights()[1]>1-1e-12

@pytest.mark.parametrize('bad',[True,-1,9,.1])
def test_invalid_action(bad):
    with pytest.raises(ValueError):Posterior(2).observe_own_action(pair(.5,.5),bad)

@pytest.mark.parametrize('bad',[float('nan'),-.1,1.1])
def test_bad_probabilities(bad):
    p=pair(.5,.5);p[0,0]=bad
    with pytest.raises(ValueError):Posterior(2).before(p)

def test_distances_exact_and_disjoint():
    a=np.array([1.]+[0.]*8);b=np.array([0.,1.]+[0.]*7)
    assert distances(a,a)==(0.,0.)
    tv,js=distances(a,b)
    assert tv==1 and js==pytest.approx(math.log(2))

def test_ci_arithmetic():
    e=estimate([1.,2.,3.])
    assert e['mean']==2 and e['standard_error']==pytest.approx(1/math.sqrt(3))

def test_no_decision_hands_not_imputed_zero():
    rows=[dict(cohort='native',hand=0),dict(cohort='native',hand=1)]
    rows += [dict(cohort='slumbot',hand=s*2500+j) for s in range(8) for j in (0,1)]
    report=hand_summary(rows,[.2]*len(rows))
    assert report['native']['hands_without_decisions']==8190 and report['native']['mean']==pytest.approx(.2)
    assert report['slumbot']['hands_without_decisions']==19984
    assert report['decision']=='LARGE_AVERAGING_FIDELITY_GAP'

def test_shift_threshold_is_prespecified_not_return_gate():
    rows=[dict(cohort='native',hand=h) for h in (0,1)]
    rows += [dict(cohort='slumbot',hand=s*2500+j) for s in range(8) for j in (0,1)]
    report=hand_summary(rows,[.02]*2+[.2]*16)
    assert report['decision']=='EXTERNAL_DISTRIBUTION_FIDELITY_GAP'

def test_real_frozen_parent_admission_without_model_calls():
    import run_diagnostic as run
    run.require_parents()

def test_production_analysis_uses_prior_then_own_history_and_resets():
    import run_diagnostic as run
    rows=[]
    for cohort,hands in [('native',[0,1]),('slumbot',[s*2500 for s in range(8)])]:
        for hand in hands:
            for di in range(2):
                rows.append(dict(cohort=cohort,hand=hand,seat=hand%2,street=0,decision=di,action_slot=1))
    n=len(rows)
    p=np.zeros((4,n,9))
    for model,value in enumerate((.9,.5,.1,.5)):
        p[model,:,0]=value;p[model,:,1]=1-value
    result,_=run.analyze(rows,p)
    assert np.allclose(result['posterior'][::2],[1/3]*3)
    assert np.allclose(result['mixture'][::2,0],.5)
    assert np.allclose(result['mixture'][1::2,0],(.9*.1+.5*.5+.1*.9)/1.5)

