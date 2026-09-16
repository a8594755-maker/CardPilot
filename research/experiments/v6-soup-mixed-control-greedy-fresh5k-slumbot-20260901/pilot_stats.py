"""Raw-hand and equal-session statistics for the exploratory control gate."""

import math
import statistics


T7 = 2.3646242515927853
PARENT_SOUP_FRESH20K_BB100 = -41.8162


def summarize(sessions, hands_per_session=625):
    if len(sessions) != 8 or any(len(row) != hands_per_session for row in sessions):
        raise ValueError("Require eight complete equal sessions")
    chips = [value for session in sessions for value in session]
    if any(type(value) is not int or abs(value) > 20000 for value in chips):
        raise ValueError("Invalid terminal chip sample")
    mean = math.fsum(chips) / len(chips)
    raw_se = statistics.stdev(chips) / math.sqrt(len(chips))
    session_means = [math.fsum(session) / len(session) for session in sessions]
    session_se = statistics.stdev(session_means) / math.sqrt(8)
    if not math.isclose(mean, math.fsum(session_means) / 8, abs_tol=1e-12):
        raise ValueError("Unequal session weighting")
    positive_sessions = sum(value > 0 for value in session_means)
    return {
        "hands": len(chips),
        "sessions": 8,
        "bb_per_100": mean,
        "raw_hand_se": raw_se,
        "raw_hand_ci95": [mean - 1.96 * raw_se, mean + 1.96 * raw_se],
        "session_means_bb_per_100": session_means,
        "positive_sessions": positive_sessions,
        "session_se": session_se,
        "session_t7_ci95": [mean - T7 * session_se, mean + T7 * session_se],
        "parent_soup_fresh20k_bb_per_100": PARENT_SOUP_FRESH20K_BB100,
        "unpaired_point_delta_vs_parent_soup": mean - PARENT_SOUP_FRESH20K_BB100,
        "supports_separate_fresh20k": mean > 0 and positive_sessions >= 4,
        "goal_achieved": False,
        "qualification_hands": 0,
    }
