"""Raw-hand and equal-session statistics for bridge fresh20k confirmation."""
import math
import statistics

T7 = 2.3646242515927853
PRIOR_FRESH5K_BB_PER_100 = -15.79
HISTORICAL_OLD_CONTRACT_BB_PER_100 = -11.4275


def summarize(sessions, hands_per_session=2500):
    if len(sessions) != 8 or any(len(session) != hands_per_session for session in sessions):
        raise ValueError("Require eight complete equal sessions")
    chips = [value for session in sessions for value in session]
    if any(type(value) is not int or abs(value) > 20000 for value in chips):
        raise ValueError("Invalid terminal chip sample")
    mean = math.fsum(chips) / len(chips)
    raw_se = statistics.stdev(chips) / math.sqrt(len(chips))
    means = [math.fsum(session) / len(session) for session in sessions]
    session_se = statistics.stdev(means) / math.sqrt(8)
    if not math.isclose(mean, math.fsum(means) / 8, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("Unequal session weighting")
    raw_ci = [mean - 1.96 * raw_se, mean + 1.96 * raw_se]
    session_ci = [mean - T7 * session_se, mean + T7 * session_se]
    positive_sessions = sum(value > 0 for value in means)
    supports = mean > 0 and positive_sessions >= 4
    return {
        "hands": len(chips), "sessions": 8, "bb_per_100": mean,
        "raw_hand_se": raw_se, "raw_hand_ci95": raw_ci,
        "session_means_bb_per_100": means, "positive_sessions": positive_sessions,
        "session_se": session_se, "session_t7_ci95": session_ci,
        "prior_bridge_fresh5k_bb_per_100": PRIOR_FRESH5K_BB_PER_100,
        "historical_old_contract_bb_per_100": HISTORICAL_OLD_CONTRACT_BB_PER_100,
        "point_delta_vs_bridge_fresh5k": mean - PRIOR_FRESH5K_BB_PER_100,
        "point_delta_vs_historical_old_contract": mean - HISTORICAL_OLD_CONTRACT_BB_PER_100,
        "supports_separate_fresh100k": supports,
        "goal_achieved": False, "qualification_hands": 0,
    }
