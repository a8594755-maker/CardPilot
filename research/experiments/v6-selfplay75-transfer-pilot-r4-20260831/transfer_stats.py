"""Internal diagnostic statistics, never a strength-based external selector."""
import math
from pathlib import Path
import statistics


def raw_count(path):
    path=Path(path)
    return path.read_bytes().count(b'\n') if path.exists() else 0


def estimate(values):
    if len(values)<2 or not all(math.isfinite(v) for v in values): raise ValueError('Invalid paired data')
    mean=statistics.mean(values)
    se=statistics.stdev(values)/math.sqrt(len(values))
    z=statistics.NormalDist().inv_cdf(1-.05/12)
    return dict(bb_per_100=mean,standard_error=se,ci95=[mean-1.96*se,mean+1.96*se],
                ci_adjusted=[mean-z*se,mean+z*se])


def external_pair_admission(health):
    if set(health)!={'control25','selfplay75'}: raise ValueError('Require both arms')
    return all(row['status']=='PASS' and row['new_training_hands']>=1048576 for row in health.values())


def exposure(records, iterations, expected_groups):
    """Assigned worker-update slots, NOT measured self-play terminal hands."""
    used=[r for r in records if r['applies_to_iteration']<=iterations]
    assert [r['applies_to_iteration'] for r in used]==list(range(1,iterations+1))
    counts=[]
    for row in used:
        groups=row['group_metadata']
        assert len(groups)==8 and sum(g['opponent_id']==-1 for g in groups)==expected_groups
        assert sorted(w for g in groups for w in g['workers'])==list(range(12))
        workers=row['workers']
        assert sorted(w['worker_id'] for w in workers)==list(range(12))
        by_group={w for g in groups if g['opponent_id']==-1 for w in g['workers']}
        by_worker={w['worker_id'] for w in workers if w['opponent']['kind']=='self_play'}
        assert by_group==by_worker
        counts.append(len(by_worker))
    return dict(unit='assigned worker-update slots, not completed hands',
                selfplay_worker_slots=sum(counts),all_worker_slots=12*iterations,
                selfplay_worker_fraction=sum(counts)/(12*iterations),
                selfplay_workers_per_update=counts,terminal_hand_fraction=None)
