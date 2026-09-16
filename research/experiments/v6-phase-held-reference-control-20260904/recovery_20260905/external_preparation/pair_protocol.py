"""Offline-only draft for two fixed40k greedy cohorts; cannot launch sessions."""
import math
from pathlib import Path
import statistics

from scipy.stats import t

ARMS = ('static', 'moving256')
HANDS_PER_SESSION = 2500
SESSIONS_PER_ARM = 16
WAVES = 4
SESSIONS_PER_ARM_PER_WAVE = 4
PRIMARY_FAMILY_SIZE = 3
BRIDGE = 'hunl_v6_physical_legacy_v4_observation_bridge_v1'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def schedule():
    rows = []
    for wave in range(WAVES):
        order = ARMS if wave % 2 == 0 else tuple(reversed(ARMS))
        for slot in range(SESSIONS_PER_ARM_PER_WAVE):
            index = wave * SESSIONS_PER_ARM_PER_WAVE + slot + 1
            for arm in order:
                rows.append({'wave': wave, 'launch_index': len(rows), 'arm': arm, 'index': index,
                    'hands': HANDS_PER_SESSION,
                    'policy_seed': (2026345100 if arm == 'static' else 2026345200) + index,
                    'session_id': f'v6_phase_reference_external_20260905_{arm}_s{index:02d}'})
    return rows


def session_command(item, base, runtime):
    require(item in schedule(), 'unregistered session')
    base, runtime = Path(base), Path(runtime)
    return [str(runtime / 'alpha_holdem/play_slumbot_v6_journaled.py'),
        '--model', str(base / 'frozen' / f'{item["arm"]}.pt'),
        '--hands', str(item['hands']), '--seed', str(item['policy_seed']),
        '--session-id', item['session_id'],
        '--out-dir', str(base / 'sessions' / item['arm'] / f's{item["index"]:02d}'),
        '--device', 'cpu', '--policy-mode', 'greedy', '--observation-bridge', 'legacy-v4']


def values_ok(values):
    require(len(values) > 1 and all(type(v) in (int, float) and math.isfinite(v) for v in values),
            'finite observations required')


def mean_t(values, confidence=.95):
    values_ok(values)
    require(0 < confidence < 1, 'invalid confidence')
    mean = statistics.mean(values)
    se = statistics.stdev(values) / math.sqrt(len(values))
    half = float(t.ppf((1 + confidence) / 2, len(values) - 1)) * se
    return {'bb_per_100': mean, 'standard_error': se, 'ci': [mean - half, mean + half],
            'confidence': confidence, 'samples': len(values), 'degrees_of_freedom': len(values) - 1,
            'empirical_zero_variance': se == 0}


def welch(treatment, control, confidence=.95):
    values_ok(treatment)
    values_ok(control)
    require(0 < confidence < 1, 'invalid confidence')
    nt, nc = len(treatment), len(control)
    vt, vc = statistics.variance(treatment) / nt, statistics.variance(control) / nc
    difference = statistics.mean(treatment) - statistics.mean(control)
    se = math.sqrt(vt + vc)
    df = (vt + vc) ** 2 / (vt ** 2 / (nt - 1) + vc ** 2 / (nc - 1)) if se else None
    half = float(t.ppf((1 + confidence) / 2, df)) * se if se else 0.
    return {'bb_per_100': difference, 'standard_error': se, 'ci': [difference - half, difference + half],
            'confidence': confidence, 'degrees_of_freedom': df, 'empirical_zero_variance': se == 0}


def arm_summary(groups):
    require(len(groups) == SESSIONS_PER_ARM and all(len(g) == HANDS_PER_SESSION for g in groups),
            'exactly16 complete2500-hand sessions required')
    values = [value for group in groups for value in group]
    require(all(type(value) is int and abs(value) <= 20000 for value in values), 'invalid physical200bb terminal chips')
    # 100 chips/bb and100 hands/100 hands cancel: mean terminal chips equals bb/100.
    means = [statistics.mean(group) for group in groups]
    mean, se = statistics.mean(values), statistics.stdev(values) / math.sqrt(len(values))
    adjusted = 1 - .05 / PRIMARY_FAMILY_SIZE
    z = statistics.NormalDist().inv_cdf((1 + adjusted) / 2)
    return {'hands': len(values), 'sessions': len(groups), 'bb_per_100': mean,
        'raw_hand_standard_error': se, 'raw_hand_ci95': [mean - 1.96 * se, mean + 1.96 * se],
        'raw_hand_ci_family_adjusted': [mean - z * se, mean + z * se],
        'session_means_bb_per_100': means, 'session_t15': mean_t(means),
        'session_t15_family_adjusted': mean_t(means, adjusted),
        'wave_means_bb_per_100': [statistics.mean(means[4 * wave:4 * (wave + 1)]) for wave in range(WAVES)],
        'positive_sessions': sum(value > 0 for value in means), 'empirical_zero_raw_variance': se == 0}


def summarize_pair(groups, *, evidence_valid):
    require(evidence_valid is True and set(groups) == set(ARMS), 'both fully audited arms required')
    summaries = {arm: arm_summary(groups[arm]) for arm in ARMS}
    adjusted = 1 - .05 / PRIMARY_FAMILY_SIZE
    raw = {arm: [value for group in groups[arm] for value in group] for arm in ARMS}
    sessions = {arm: summaries[arm]['session_means_bb_per_100'] for arm in ARMS}
    contrasts = {unit: {'ordinary': welch(values['moving256'], values['static']),
                        'family_adjusted': welch(values['moving256'], values['static'], adjusted)}
                 for unit, values in (('independent_raw_hands', raw), ('independent_sessions', sessions))}
    wave_differences = [summaries['moving256']['wave_means_bb_per_100'][wave] -
                        summaries['static']['wave_means_bb_per_100'][wave] for wave in range(WAVES)]
    contrasts['balanced_wave_sensitivity'] = {'wave_differences_bb_per_100': wave_differences,
        't3': mean_t(wave_differences), 'family_adjusted_t3': mean_t(wave_differences, adjusted),
        'not_paired_server_deals': True}
    return {'arms': summaries, 'moving_minus_static': contrasts,
        'development_hands': 80000, 'final_qualification_hands': 0,
        'primary_family': ['static_absolute', 'moving256_absolute', 'moving_minus_static'],
        'family_adjustment': 'Bonferroni over three primary quantities; seat/wave detail remains descriptive',
        'interval_assumptions': 'Raw independent hand noise; session/Welch and four-wave t intervals are limited sensitivity checks, not proof of arbitrary temporal independence.',
        'server_rng_independence_proven': False, 'training_seed_replication': False,
        'automatic_model_selection': False, 'automatic_final_test_authorized': False, 'goal_achieved': False}
