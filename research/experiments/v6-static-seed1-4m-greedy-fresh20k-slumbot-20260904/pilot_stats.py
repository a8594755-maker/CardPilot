"""Fixed-budget descriptive statistics; never grant formal qualification."""
import math
import statistics

T7 = 2.3646242515927853
MATCHED_STANDARD10 = -24.5683
HISTORICAL_STANDARD10 = -11.4275


def summarize(sessions, hands_per_session=2500):
    if len(sessions) != 8 or any(len(row) != hands_per_session for row in sessions):
        raise ValueError('Require eight complete fixed-budget sessions')
    chips = [value for row in sessions for value in row]
    if any(type(value) is not int or abs(value) > 20000 for value in chips):
        raise ValueError('Invalid terminal chip sample')
    # One big blind is100chips: mean chips/hand equals bb/100 numerically.
    mean = math.fsum(chips) / len(chips)
    raw_se = statistics.stdev(chips) / math.sqrt(len(chips))
    session_means = [math.fsum(row) / len(row) for row in sessions]
    session_se = statistics.stdev(session_means) / math.sqrt(8)
    return {
        'hands': len(chips), 'sessions': 8, 'bb_per_100': mean,
        'raw_hand_se': raw_se, 'raw_hand_ci95': [mean - 1.96 * raw_se, mean + 1.96 * raw_se],
        'session_means_bb_per_100': session_means,
        'session_se': session_se, 'session_t7_ci95': [mean - T7 * session_se, mean + T7 * session_se],
        'positive_sessions': sum(value > 0 for value in session_means),
        'same_contract_standard10_bb_per_100': MATCHED_STANDARD10,
        'historical_standard10_greedy_bb_per_100': HISTORICAL_STANDARD10,
        'point_delta_vs_same_contract_standard10': mean - MATCHED_STANDARD10,
        'point_delta_vs_historical_standard10': mean - HISTORICAL_STANDARD10,
        'supports_separate_fresh100k': False,
        'automatic_formal_test_authorized': False,
        'research_review_required': True,
        'goal_achieved': False, 'qualification_hands': 0,
    }
