"""Counter-only curve selection and preregistered family-six statistics."""
import math
from pathlib import Path
import statistics

TARGET = 1048576
PAIRS = 8192
EVAL_SEED = 20261001
EVAL_HANDS = 4 * 5 * PAIRS * 2
THRESHOLDS = {'mid262': 262144, 'mid524': 524288}


def choose_curve(rows, archives):
    if not rows or [r['iteration'] for r in rows] != list(range(1, len(rows)+1)):
        raise ValueError('Incomplete metric prefix')
    counts = [r['environment_hand_accounting']['completed_hands'] for r in rows]
    if any(type(v) is not int or v <= 0 for v in counts) or any(a >= b for a, b in zip(counts, counts[1:])):
        raise ValueError('Invalid physical counters')
    scheduled = [r for r in rows if r['iteration'] % 4 == 0]
    if {r['iteration'] for r in scheduled} != set(archives):
        raise ValueError('Unexpected or missing scheduled archives')
    result = {}
    for label, threshold in THRESHOLDS.items():
        eligible = [r for r in scheduled if r['environment_hand_accounting']['completed_hands'] >= threshold]
        if not eligible: raise ValueError('Missing threshold crossing')
        result[label] = eligible[0]
    if result['mid262']['iteration'] >= result['mid524']['iteration']:
        raise ValueError('Curve points are not distinct')
    return result


def estimate(values):
    if len(values) < 2 or not all(math.isfinite(x) for x in values): raise ValueError('Invalid sample')
    mean = statistics.mean(values)
    se = statistics.stdev(values)/math.sqrt(len(values))
    z = statistics.NormalDist().inv_cdf(1-.05/12)
    return dict(bb_per_100=mean, standard_error=se, ci95=[mean-1.96*se, mean+1.96*se],
                ci_adjusted=[mean-z*se, mean+z*se])


def gate(contrasts, growth):
    if [r['anchor'] for r in contrasts] != list(range(5)): raise ValueError('Wrong primary family')
    for row in [*contrasts, growth]:
        if not all(math.isfinite(v) for v in [row['bb_per_100'], *row['ci_adjusted']]):
            raise ValueError('Nonfinite gate input')
    significant = {r['anchor'] for r in contrasts if r['ci_adjusted'][0] > 0}
    return (all(r['bb_per_100'] > 0 for r in contrasts) and len(significant) >= 3
            and 0 in significant and bool(significant & {3, 4}) and growth['ci_adjusted'][0] > 0)


def raw_count(path):
    path = Path(path)
    if not path.exists(): return 0
    # Count only complete durable lines. An incomplete writer tail is not a hand.
    return path.read_bytes().count(b'\n')
