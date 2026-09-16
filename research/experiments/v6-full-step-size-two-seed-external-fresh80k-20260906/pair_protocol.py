"""Four frozen policies: 20k each, balanced waves, six primary quantities; no network."""
import math
from pathlib import Path
import statistics

from scipy.stats import t

ARMS = ('seed1_full', 'seed1_half', 'seed3_full', 'seed3_half')
HANDS_PER_SESSION = 2500
SESSIONS_PER_ARM = 8
HANDS_PER_ARM = HANDS_PER_SESSION * SESSIONS_PER_ARM
WAVES = 4
SESSIONS_PER_ARM_PER_WAVE = 2
PRIMARY_FAMILY_SIZE = 6
BRIDGE = 'hunl_v6_physical_legacy_v4_observation_bridge_v1'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def schedule():
    rows = []
    for wave in range(WAVES):
        order = ARMS[wave:] + ARMS[:wave]
        for slot in range(SESSIONS_PER_ARM_PER_WAVE):
            index = wave * SESSIONS_PER_ARM_PER_WAVE + slot + 1
            for arm in order:
                rows.append({'wave': wave, 'launch_index': len(rows), 'arm': arm, 'index': index,
                    'hands': HANDS_PER_SESSION,
                    'policy_seed': {'seed1_full': 2026401100, 'seed1_half': 2026401200,
                                    'seed3_full': 2026403100, 'seed3_half': 2026403200}[arm] + index,
                    'session_id': f'v6_full_step_size_external_20260906_{arm}_s{index:02d}'})
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
            'exactly8 complete2500-hand sessions required')
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
        'session_means_bb_per_100': means, 'session_t7': mean_t(means),
        'session_t7_family_adjusted': mean_t(means, adjusted),
        'wave_means_bb_per_100': [statistics.mean(means[2 * wave:2 * (wave + 1)]) for wave in range(WAVES)],
        'positive_sessions': sum(value > 0 for value in means), 'empirical_zero_raw_variance': se == 0}


def summarize_four(groups, *, evidence_valid):
    require(evidence_valid is True and set(groups) == set(ARMS), 'four fully audited arms required')
    summaries = {arm: arm_summary(groups[arm]) for arm in ARMS}
    adjusted = 1 - .05 / PRIMARY_FAMILY_SIZE
    raw = {arm: [value for group in groups[arm] for value in group] for arm in ARMS}
    sessions = {arm: summaries[arm]['session_means_bb_per_100'] for arm in ARMS}
    contrasts = {}
    for seed in (1, 3):
        full, half = f'seed{seed}_full', f'seed{seed}_half'
        contrast = {unit: {'ordinary': welch(values[half], values[full]),
                          'family_adjusted': welch(values[half], values[full], adjusted)}
                    for unit, values in (('independent_raw_hands', raw), ('independent_sessions', sessions))}
        differences = [summaries[half]['wave_means_bb_per_100'][wave] -
                       summaries[full]['wave_means_bb_per_100'][wave] for wave in range(WAVES)]
        contrast['balanced_wave_sensitivity'] = {'wave_differences_bb_per_100': differences,
            't3': mean_t(differences), 'family_adjusted_t3': mean_t(differences, adjusted),
            'not_paired_server_deals': True}
        contrasts[str(seed)] = contrast
    return {'arms': summaries, 'half_minus_full_by_seed': contrasts,
        'development_hands': 80000, 'final_qualification_hands': 0,
        'primary_family': [arm + '_absolute' for arm in ARMS] +
                          ['seed1_half_minus_full', 'seed3_half_minus_full'],
        'family_adjustment': 'Bonferroni over six primary quantities; seat/wave detail remains descriptive',
        'interval_assumptions': 'Raw independent hand noise; session/Welch and four-wave t intervals are limited sensitivity checks, not proof of arbitrary temporal independence.',
        'server_rng_independence_proven': False,
        'training_seeds': [1, 3], 'training_seed_population_inference': False,
        'automatic_model_selection': False, 'automatic_final_test_authorized': False, 'goal_achieved': False}
