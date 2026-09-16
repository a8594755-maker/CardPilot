"""Paired native hero-hand fidelity gate; no return or strength inference."""
import math
import numpy as np

def interval(values):
    x=np.asarray(values,dtype=np.float64)
    if x.ndim!=1 or len(x)<2 or not np.isfinite(x).all():raise ValueError('Invalid hand sample')
    mean=math.fsum(x.tolist())/len(x)
    se=math.sqrt(math.fsum((float(v)-mean)**2 for v in x)/(len(x)-1)/len(x))
    return dict(n=len(x),mean=mean,standard_error=se,ci95=[mean-1.96*se,mean+1.96*se])

def hero_tv(probabilities,targets,hands,actors,physical_hands=8192):
    p,q=np.asarray(probabilities),np.asarray(targets)
    h,a=np.asarray(hands),np.asarray(actors)
    if p.shape!=q.shape or p.ndim!=2 or p.shape[1]!=9 or h.shape!=(len(p),) or a.shape!=h.shape:
        raise ValueError('Invalid common-state arrays')
    if not np.isfinite(p).all() or not np.isfinite(q).all() or (p<0).any() or (q<0).any():
        raise ValueError('Invalid probabilities')
    if not np.allclose(p.sum(1),1,rtol=0,atol=1e-10) or not np.allclose(q.sum(1),1,rtol=0,atol=1e-10):
        raise ValueError('Unnormalized probabilities')
    if h.dtype.kind not in 'iu' or a.dtype.kind not in 'iu' or (h<0).any() or (h>=physical_hands).any() or not np.isin(a,[0,1]).all():
        raise ValueError('Invalid hero-hand identity')
    use=a==h%2
    sums=np.bincount(h[use],weights=np.abs(p[use]-q[use]).sum(1)/2,minlength=physical_hands)
    counts=np.bincount(h[use],minlength=physical_hands)
    means=np.full(physical_hands,np.nan)
    means[counts>0]=sums[counts>0]/counts[counts>0]
    return means,counts

def paired_gate(control,candidate):
    old,new=np.asarray(control),np.asarray(candidate)
    if old.shape!=new.shape or old.ndim!=1 or not np.array_equal(np.isnan(old),np.isnan(new)):
        raise ValueError('Mismatched hero-hand coverage')
    valid=np.isfinite(old)&np.isfinite(new)
    if not np.all(np.isnan(old)|valid):raise ValueError('Nonfinite hand outcome')
    c,t,d=interval(old[valid]),interval(new[valid]),interval(old[valid]-new[valid])
    admitted=d['ci95'][0]>0 and t['mean']<=.15
    return dict(control=c,treatment=t,paired_control_minus_treatment=d,
        physical_hands=len(old),hands_with_hero_decisions=int(valid.sum()),hands_without_hero_decisions=int((~valid).sum()),
        decision='ADMIT_SEPARATE_STRATEGIC_ASSESSMENT' if admitted else 'REACH_TARGET_FIDELITY_GATE_NOT_PASSED',
        goal_achieved=False,strength_evaluation_hands=0)

def cross_entropy(probabilities,targets):
    p,q=np.asarray(probabilities),np.asarray(targets)
    if ((p==0)&(q>0)).any():raise ValueError('Positive reference mass on numeric zero student probability')
    logp=np.zeros_like(p,dtype=np.float64)
    np.log(p,out=logp,where=p>0)
    return -(q*logp).sum(1)

