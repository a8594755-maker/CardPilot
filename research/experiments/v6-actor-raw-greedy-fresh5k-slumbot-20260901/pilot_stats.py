"""Raw-hand and equal-eight-session statistics for greedy fresh5k."""
import math
import statistics

T7 = 2.3646242515927853
SAMPLED_BB_PER_100 = -79.2126


def summarize(sessions, hands_per_session=625):
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
    delta = mean - SAMPLED_BB_PER_100
    return {"hands": len(chips), "sessions": 8, "bb_per_100": mean,
            "raw_hand_se": raw_se, "raw_hand_ci95": raw_ci,
            "session_means_bb_per_100": means, "positive_sessions": positive_sessions,
            "session_se": session_se, "session_t7_ci95": session_ci,
            "sampled_pilot_bb_per_100": SAMPLED_BB_PER_100,
            "point_delta_vs_sampled": delta,
            "supports_separate_fresh20k": mean > 0 and positive_sessions >= 4 and delta >= 20,
            "goal_achieved": False, "qualification_hands": 0}
