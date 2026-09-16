import numpy as np
from run_diagnostic import metrics,hero,interval,stratum_summary

def test_metrics_units():
 p=np.array([[.5,.5,0],[1,0,0.]])
 q=np.array([[.25,.75,0],[1,0,0.]])
 tv,ce,js=metrics(p,q)
 assert np.allclose(tv,[.25,0]) and np.isfinite(ce).all() and np.isfinite(js).all()
 assert (js>=0).all()

def test_hero_grouping_no_zero_imputation():
 p=np.tile([.5,.5],(4,1));q=np.tile([1.,0],(4,1))
 h=hero(p,q,np.array([0,0,1,1]),np.array([0,1,1,0]))
 assert h[0]==.5 and h[1]==.5 and np.isnan(h[2:]).all()

def test_interval_direction_and_strata():
 x=interval([.1,.2,.3]);assert x['n']==3 and x['ci95'][0]<x['mean']<x['ci95'][1]
 p=np.tile([.5,.5],(8,1));q=np.tile([1.,0],(8,1))
 meta=dict(street=np.array([0,0,1,1,2,2,3,3]),truncated=np.array([0,1,0,1,0,1,0,1],dtype=bool),
  posterior_max=np.arange(8),teacher_disagreement=np.arange(8),target_entropy=np.arange(8))
 out=stratum_summary(p,q,meta)
 assert [r['n'] for r in out['street']]==[2,2,2,2] and [r['n'] for r in out['truncated']]==[4,4]




