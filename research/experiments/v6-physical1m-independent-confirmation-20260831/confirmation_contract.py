"""Fixed six-contrast confirmation; no data-dependent sample or model choices."""
import math
from pathlib import Path
import random
import statistics

PAIRS = 8192
SEED = 20261002
CELLS = tuple([(label, a) for label in ('source', 'final') for a in range(5)]
              + [('mid262', a) for a in (3, 4)])
HANDS = len(CELLS)*PAIRS*2


def decks(seed=SEED, count=PAIRS):
    rng = random.Random(seed)
    result = []
    for _ in range(count):
        deck = list(range(52))
        rng.shuffle(deck)
        result.append(deck)
    return result


def disjoint_decks(current, previous):
    def checked(rows):
        if any(len(d) != 52 or sorted(d) != list(range(52)) for d in rows):
            raise ValueError('Invalid full deck')
        keys = {tuple(d) for d in rows}
        if len(keys) != len(rows): raise ValueError('Duplicate full deck')
        return keys
    if checked(current) & checked(previous): raise ValueError('Reused full deck')


def estimate(values):
    if len(values) < 2 or not all(math.isfinite(x) for x in values):
        raise ValueError('Invalid sample')
    mean = statistics.mean(values)
    se = statistics.stdev(values)/math.sqrt(len(values))
    z = statistics.NormalDist().inv_cdf(1-.05/12)
    return dict(bb_per_100=mean, standard_error=se,
                ci95=[mean-1.96*se, mean+1.96*se],
                ci_adjusted=[mean-z*se, mean+z*se])


def gate(contrasts, growth):
    if [r['anchor'] for r in contrasts] != list(range(5)):
        raise ValueError('Wrong primary family')
    for row in [*contrasts, growth]:
        nums = [row['bb_per_100'], *row['ci_adjusted']]
        if len(nums) != 3 or not all(math.isfinite(v) for v in nums):
            raise ValueError('Invalid gate input')
        if not nums[1] <= nums[0] <= nums[2]: raise ValueError('Invalid interval')
    significant = {r['anchor'] for r in contrasts if r['ci_adjusted'][0] > 0}
    return (all(r['bb_per_100'] > 0 for r in contrasts) and len(significant) >= 3
            and 0 in significant and bool(significant & {3, 4})
            and growth['ci_adjusted'][0] > 0)


def raw_count(path):
    path = Path(path)
    return path.read_bytes().count(b'\n') if path.exists() else 0


def analyze(values):
    if set(values) != set(CELLS): raise ValueError('Wrong fixed matrix')
    if any(len(v) != PAIRS for v in values.values()): raise ValueError('Wrong pair count')
    primary = [dict(anchor=a, **estimate([f-s for f, s in zip(values['final', a], values['source', a])]))
               for a in range(5)]
    growth = estimate([math.fsum(values['final', a][i]-values['mid262', a][i]
                                for a in (3, 4))/2 for i in range(PAIRS)])
    passed = gate(primary, growth)
    return dict(primary_contrasts=primary, heldout_growth=growth,
                confirmation_gate_pass=passed,
                decision='ADMIT_SEPARATE_SLUMBOT_PILOT' if passed else 'INDEPENDENT_CONFIRMATION_NOT_PASSED')
