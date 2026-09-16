"""Fixed equal-eight-session pilot; budget admission is not significance."""
import math
import statistics

T7 = 2.3646242515927853


def summarize(sessions, hands_per_session=2500):
    if len(sessions) != 8 or any(len(s) != hands_per_session for s in sessions):
        raise ValueError('Require the fixed complete eight equal sessions')
    chips = [v for session in sessions for v in session]
    if len(chips) < 2 or any(type(v) is not int or abs(v) > 20000 for v in chips):
        raise ValueError('Invalid terminal chip sample')
    mean = math.fsum(chips)/len(chips)
    raw_se = statistics.stdev(chips)/math.sqrt(len(chips))
    means = [math.fsum(s)/len(s) for s in sessions]
    group_mean = math.fsum(means)/8
    group_se = statistics.stdev(means)/math.sqrt(8)
    if not math.isclose(mean, group_mean, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError('Unequal session weighting')
    raw_ci = [mean-1.96*raw_se, mean+1.96*raw_se]
    group_ci = [group_mean-T7*group_se, group_mean+T7*group_se]
    return dict(hands=len(chips), sessions=8, bb_per_100=mean, raw_hand_se=raw_se,
                raw_hand_ci95=raw_ci, session_means_bb_per_100=means, session_se=group_se,
                session_t7_ci95=group_ci, supports_separate_100k_confirmation=mean > 0,
                both_pilot_lower_bounds_positive=raw_ci[0] > 0 and group_ci[0] > 0,
                goal_achieved=False, probe_hands_pooled=0, old_baseline_hands_pooled=0,
                qualification_hands=0)
