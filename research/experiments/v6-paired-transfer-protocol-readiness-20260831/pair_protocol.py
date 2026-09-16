"""Offline helpers only; no model, filesystem writes, networking or game launcher."""
import math
import statistics
from scipy.stats import t

ARMS=('control25','selfplay75')
HANDS=2500
SESSIONS=8
FAMILY=3


def schedule():
    rows=[]
    for wave in range(2):
        order=ARMS if wave==0 else tuple(reversed(ARMS))
        for slot in range(4):
            index=wave*4+slot+1
            for arm in order:
                rows.append(dict(wave=wave,launch_index=len(rows),arm=arm,index=index,hands=HANDS,
                    policy_seed=(2026100700 if arm=='control25' else 2026100800)+index,
                    session_id=f'v6_selfplay_transfer_20260831_{arm}_s{index:02d}'))
    return rows


def _values(values):
    if len(values)<2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
        raise ValueError('Require finite numeric observations')


def welch(treatment,control,confidence=.95):
    _values(treatment)
    _values(control)
    if not 0<confidence<1: raise ValueError('Invalid confidence')
    nt,nc=len(treatment),len(control)
    difference=statistics.mean(treatment)-statistics.mean(control)
    vt,vc=statistics.variance(treatment)/nt,statistics.variance(control)/nc
    se=math.sqrt(vt+vc)
    df=(vt+vc)**2/(vt**2/(nt-1)+vc**2/(nc-1)) if se else None
    half=float(t.ppf((1+confidence)/2,df))*se if se else 0.
    return dict(bb_per_100=difference,standard_error=se,degrees_of_freedom=df,
                ci=[difference-half,difference+half],confidence=confidence,
                empirical_zero_variance=se==0)


def arm_summary(groups):
    if len(groups)!=SESSIONS or any(len(g)!=HANDS for g in groups):
        raise ValueError('Require eight complete2500-hand sessions')
    values=[v for g in groups for v in g]
    if any(type(v) is not int or abs(v)>20000 for v in values): raise ValueError('Invalid integer terminal chips')
    mean=statistics.mean(values)
    se=statistics.stdev(values)/math.sqrt(len(values))
    means=[statistics.mean(g) for g in groups]
    group_se=statistics.stdev(means)/math.sqrt(SESSIONS)
    if not math.isclose(mean,statistics.mean(means),rel_tol=1e-12,abs_tol=1e-12):
        raise ValueError('Unequal weighting')
    z3=statistics.NormalDist().inv_cdf(1-.05/(2*FAMILY))
    t7=float(t.ppf(.975,7))
    t7_adjusted=float(t.ppf(1-.05/(2*FAMILY),7))
    return dict(hands=len(values),sessions=8,bb_per_100=mean,raw_hand_se=se,
        raw_hand_ci95=[mean-1.96*se,mean+1.96*se],raw_hand_ci_adjusted=[mean-z3*se,mean+z3*se],
        session_means_bb_per_100=means,session_se=group_se,
        session_t7_ci95=[mean-t7*group_se,mean+t7*group_se],
        session_t7_ci_adjusted=[mean-t7_adjusted*group_se,mean+t7_adjusted*group_se],
        empirical_zero_raw_variance=se==0,empirical_zero_session_variance=group_se==0)


def allocation(arm_statistics,*,evidence_valid):
    if evidence_valid is not True or set(arm_statistics)!=set(ARMS): raise ValueError('Both audited arms required')
    points={arm:arm_statistics[arm]['bb_per_100'] for arm in ARMS}
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in points.values()): raise ValueError('Invalid points')
    positives=[arm for arm in ARMS if points[arm]>0]
    return max(positives,key=lambda arm:points[arm]) if positives else None


def summarize_pair(groups,*,evidence_valid):
    if evidence_valid is not True or set(groups)!=set(ARMS): raise ValueError('Both fully audited cohorts required')
    summaries={arm:arm_summary(groups[arm]) for arm in ARMS}
    raw={arm:[x for g in groups[arm] for x in g] for arm in ARMS}
    sessions={arm:summaries[arm]['session_means_bb_per_100'] for arm in ARMS}
    contrasts={}
    for unit,values in [('raw_hand',raw),('session',sessions)]:
        contrasts[unit]=dict(ordinary=welch(values['selfplay75'],values['control25']),
            adjusted=welch(values['selfplay75'],values['control25'],1-.05/FAMILY))
    selected=allocation(summaries,evidence_valid=True)
    return dict(arms=summaries,contrast_selfplay75_minus_control25=contrasts,
        selected_for_separate_fresh100k=selected,qualification_hands=0,goal_achieved=False,
        total_pilot_hands=40000,pilot_hands_pooled_into_qualification=0,
        server_rng_independence_proven=False,internal_scores_used=False)


def validate_combined_audits(audits,model_hashes,excluded_tokens):
    if set(audits)!=set(ARMS) or set(model_hashes)!=set(ARMS): raise ValueError('Missing arm')
    prior=set(excluded_tokens)
    seen=set()
    for arm in ARMS:
        audit=audits[arm]
        expected={r['session_id']:r for r in schedule() if r['arm']==arm}
        if not (audit['status']=='PASS' and audit['sessions']==8 and audit['successful_hands']==20000
                and audit['model_sha256']==model_hashes[arm] and audit['token_chains_disjoint']):
            raise ValueError('Invalid per-model combined audit')
        rows=audit['results']
        if len(rows)!=8 or {r['session_id'] for r in rows}!=set(expected): raise ValueError('Wrong session identities')
        for row in rows:
            registered=expected[row['session_id']]
            if not (row['status']=='PASS' and row['model_sha256']==model_hashes[arm]
                    and row['policy_seed']==registered['policy_seed']
                    and row['successful_hands']==row['attempted_hands']==row['target_hands']==2500):
                raise ValueError('Incomplete or substituted session')
            if any(row[k] for k in ['pending_request_id','protocol_failures','committed_without_raw','partial_journal','partial_hands']):
                raise ValueError('Unresolved session evidence')
            if not (row['decision_replays']==row['policy_draws_verified'] and row['decision_replays']>0):
                raise ValueError('Missing full-model replay')
            tokens=set(row['token_sha256'])
            if not tokens or tokens&seen or tokens&prior: raise ValueError('Reused or absent session token chain')
            seen.update(tokens)
    return dict(status='PASS',sessions=16,hands=40000,cross_arm_token_chains_disjoint=True,
                excluded_token_chains_disjoint=True,server_rng_independence_proven=False)
