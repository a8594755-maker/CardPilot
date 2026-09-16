"""Preregistered raw-hand and equal-session statistics for fresh5k."""
import math
import statistics


T7 = 2.3646242515927853
HISTORICAL_STANDARD10_GREEDY_BB100 = -11.4275
ADMISSION_FLOOR_BB100 = -40.0


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
    raw_ci = [mean - 1.96 * raw_se, mean + 1.96 * raw_se]
    session_ci = [mean - T7 * session_se, mean + T7 * session_se]
    return {
        "hands": len(chips),
        "sessions": 8,
        "bb_per_100": mean,
        "raw_hand_se": raw_se,
        "raw_hand_ci95": raw_ci,
        "session_means_bb_per_100": session_means,
        "positive_sessions": sum(value > 0 for value in session_means),
        "session_se": session_se,
        "session_t7_ci95": session_ci,
        "historical_standard10_greedy_bb_per_100": HISTORICAL_STANDARD10_GREEDY_BB100,
        "point_delta_vs_historical_standard10": mean - HISTORICAL_STANDARD10_GREEDY_BB100,
        "admission_floor_bb_per_100": ADMISSION_FLOOR_BB100,
        "supports_separate_fresh20k": mean > ADMISSION_FLOOR_BB100 and raw_ci[1] > 0.0,
        "goal_achieved": False,
        "qualification_hands": 0,
    }
