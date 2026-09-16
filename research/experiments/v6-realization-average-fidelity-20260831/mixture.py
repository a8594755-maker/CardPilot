"""Full-own-history realization mixture arithmetic; no game or model calls."""
import math
import numpy as np
T7=2.3646242515927853

def probabilities(values,ndim):
    p=np.asarray(values,dtype=np.float64)
    if p.ndim!=ndim or p.shape[-1]!=9 or not np.isfinite(p).all() or (p<0).any() or not np.allclose(p.sum(-1),1.,rtol=0,atol=1e-10):
        raise ValueError('Invalid action probabilities')
    return p

class Posterior:
    def __init__(self,count=3):
        if type(count) is not int or count<1:raise ValueError('Invalid teacher count')
        self.log_weights=np.full(count,-math.log(count))
    def weights(self):
        scaled=np.exp(self.log_weights-np.max(self.log_weights))
        return scaled/scaled.sum()
    def before(self,teacher_probs):
        p=probabilities(teacher_probs,2)
        if len(p)!=len(self.log_weights):raise ValueError('Teacher count mismatch')
        w=self.weights()
        return w@p,w
    def observe_own_action(self,teacher_probs,slot):
        p=probabilities(teacher_probs,2)
        if type(slot) is not int or not 0<=slot<9:raise ValueError('Invalid own action slot')
        selected=p[:,slot]
        likelihood=np.full_like(selected,-np.inf)
        np.log(selected,out=likelihood,where=selected>0)
        updated=self.log_weights+likelihood
        if not np.isfinite(updated).any():raise ValueError('Unreachable own-action prefix')
        maximum=np.max(updated)
        self.log_weights=updated-(maximum+np.log(np.exp(updated-maximum).sum()))

def distances(q,student):
    q,student=probabilities(q,1),probabilities(student,1)
    midpoint=(q+student)/2
    js=0.
    for p in (q,student):
        active=p>0
        js+=.5*float((p[active]*np.log(p[active]/midpoint[active])).sum())
    return float(np.abs(q-student).sum()/2),js

def estimate(values,critical=1.96):
    x=np.asarray(values,dtype=np.float64)
    if x.ndim!=1 or len(x)<2 or not np.isfinite(x).all():raise ValueError('Invalid scalar sample')
    mean=math.fsum(x.tolist())/len(x)
    se=math.sqrt(math.fsum((float(v)-mean)**2 for v in x)/(len(x)-1)/len(x))
    return dict(n=len(x),mean=mean,standard_error=se,ci95=[mean-critical*se,mean+critical*se])

def hand_summary(metadata,tvs):
    by_hand={}
    for row,tv in zip(metadata,tvs,strict=True):
        key=(row['cohort'],row['hand'])
        by_hand.setdefault(key,[]).append(float(tv))
    result={}
    for cohort,total in [('native',8192),('slumbot',20000)]:
        means=[math.fsum(v)/len(v) for (c,_),v in by_hand.items() if c==cohort]
        result[cohort]=dict(estimate(means),physical_hands=total,
            hands_with_decisions=len(means),hands_without_decisions=total-len(means))
    session_means=[]
    for session in range(8):
        values=[math.fsum(v)/len(v) for (c,h),v in by_hand.items() if c=='slumbot' and h//2500==session]
        if not values:raise ValueError('Empty external session')
        session_means.append(math.fsum(values)/len(values))
    result['slumbot_session_means']=session_means
    result['slumbot_session_t7']=estimate(session_means,T7)
    shift=result['slumbot_session_t7']['mean']-result['native']['mean']
    shift_se=math.hypot(result['slumbot_session_t7']['standard_error'],result['native']['standard_error'])
    result['descriptive_shift']=dict(mean=shift,standard_error=shift_se,conservative_t7_ci95=[shift-T7*shift_se,shift+T7*shift_se])
    result['decision']=('EXTERNAL_DISTRIBUTION_FIDELITY_GAP' if shift-T7*shift_se>.05 else
        'LARGE_AVERAGING_FIDELITY_GAP' if result['slumbot_session_t7']['ci95'][0]>.10 else
        'NO_LARGE_FIDELITY_GAP_CONFIRMED')
    return result

