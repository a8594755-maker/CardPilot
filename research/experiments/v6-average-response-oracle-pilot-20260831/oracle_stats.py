"""Paired diagnostics for a frozen-opponent response, not equilibrium evidence."""
import math
from pathlib import Path
import statistics


def raw_count(path):
    path = Path(path)
    return path.read_bytes().count(b'\n') if path.exists() else 0


def estimate(values):
    if len(values) < 2 or not all(math.isfinite(v) for v in values):
        raise ValueError('Finite paired observations required')
    mean = statistics.mean(values)
    se = statistics.stdev(values)/math.sqrt(len(values))
    z = statistics.NormalDist().inv_cdf(1-.05/36)
    return dict(bb_per_100=mean, standard_error=se, ci95=[mean-1.96*se, mean+1.96*se],
                family18_ci95=[mean-z*se, mean+z*se])


def decision(primary):
    if not math.isfinite(primary['bb_per_100']) or not all(math.isfinite(v) for v in primary['ci95']):
        raise ValueError('Invalid primary response estimate')
    return 'ADMIT_SEPARATE_AVERAGE_UPDATE' if primary['ci95'][0] > 0 else 'RESPONSE_LEARNING_GATE_NOT_PASSED'


def select_first_actual(archives, threshold):
    if threshold <= 0 or not archives:
        raise ValueError('Nonempty archive and positive threshold required')
    ordered = sorted(archives, key=lambda x: x['iteration'])
    if len({a['iteration'] for a in ordered}) != len(ordered):
        raise ValueError('Ambiguous archive iteration')
    if any(a['actual_hands'] >= b['actual_hands'] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('Nonmonotonic actual archive counters')
    return next(a for a in ordered if a['actual_hands'] >= threshold)


def exposure(rows, iterations):
    if [r['applies_to_iteration'] for r in rows] != list(range(1, iterations+1)):
        raise ValueError('Incomplete assignment evidence')
    for row in rows:
        groups = row['group_metadata']
        assert len(groups) == 8 and all(g['opponent_id'] == 0 for g in groups)
        assert sorted(w for g in groups for w in g['workers']) == list(range(12))
        assert sorted(w['worker_id'] for w in row['workers']) == list(range(12))
        assert all(w['opponent']['kind'] == 'pool_snapshot' for w in row['workers'])
    return dict(selfplay_worker_slots=0, average_worker_slots=12*iterations,
                unit='assigned worker-update slots; physical hands accounted independently')
