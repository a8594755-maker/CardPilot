"""Fixed fresh100k analysis contract. Statistics alone never prove evidence validity."""
import math
import statistics

SESSIONS=8
HANDS_PER_SESSION=12500
TOTAL_HANDS=100000
T7=2.3646242515927853

def admission(record,review,digest):
    return (record.get('status')=='COMPLETED' and review.get('status')=='PASS'
        and review.get('decision')=='ADMIT_SEPARATE_FRESH100K_CONFIRMATION'
        and review.get('model_sha256')==digest and review.get('evaluation_hands')==20000
        and review.get('slumbot_hands')==20000 and review.get('new_training_hands')==0
        and review.get('supports_separate_100k_confirmation') is True
        and math.isfinite(review.get('statistics',{}).get('bb_per_100',math.nan))
        and review['statistics']['bb_per_100']>0 and review.get('goal_achieved') is False)

def summarize(groups):
    if len(groups)!=SESSIONS or any(len(g)!=HANDS_PER_SESSION for g in groups):
        raise ValueError('Require exactly8complete12500hand sessions; no pooling or extension')
    data=[x for g in groups for x in g]
    if any(type(x) is not int or abs(x)>20000 for x in data):
        raise ValueError('Invalid200bb terminal chip sample')
    mean=math.fsum(data)/TOTAL_HANDS
    raw_se=statistics.stdev(data)/math.sqrt(TOTAL_HANDS)
    means=[math.fsum(g)/HANDS_PER_SESSION for g in groups]
    session_se=statistics.stdev(means)/math.sqrt(SESSIONS)
    raw=[mean-1.96*raw_se,mean+1.96*raw_se]
    cluster=[mean-T7*session_se,mean+T7*session_se]
    return dict(hands=TOTAL_HANDS,sessions=SESSIONS,bb_per_100=mean,
        raw_hand_se=raw_se,raw_hand_ci95=raw,session_se=session_se,
        session_means_bb_per_100=means,session_t7_ci95=cluster,
        primary_raw_gate=mean>0 and raw[0]>0,
        conservative_statistical_gate=mean>0 and raw[0]>0 and cluster[0]>0,
        goal_achieved=False,
        evidence_validation_required=True,pilot_hands_pooled=0,old_hands_pooled=0)

