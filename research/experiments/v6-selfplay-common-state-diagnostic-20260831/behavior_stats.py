"""Read-only distribution distances and explicit exogenous hand-block weighting."""
from collections import defaultdict
import math
import statistics


def probability_vector(values):
    if len(values)!=9 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in values):
        raise ValueError('Invalid nine-slot probability vector')
    if not math.isclose(math.fsum(values),1.,abs_tol=1e-12,rel_tol=0): raise ValueError('Unnormalized probabilities')


def distances(control,treatment):
    probability_vector(control)
    probability_vector(treatment)
    midpoint=[(a+b)/2 for a,b in zip(control,treatment)]
    entropy=lambda p:-math.fsum(x*math.log2(x) for x in p if x)
    js=entropy(midpoint)-(entropy(control)+entropy(treatment))/2
    if js < -1e-12: raise ValueError('Negative JS divergence')
    return dict(tv=.5*math.fsum(abs(a-b) for a,b in zip(control,treatment)),js_bits=max(0.,js),
        fold_delta=treatment[0]-control[0],passive_delta=treatment[1]-control[1],
        raise_delta=math.fsum(treatment[2:])-math.fsum(control[2:]),allin_delta=treatment[8]-control[8],
        control_entropy_bits=entropy(control),treatment_entropy_bits=entropy(treatment))


def interval(values):
    if len(values)<2 or any(not math.isfinite(v) for v in values): raise ValueError('Insufficient finite blocks')
    mean=statistics.mean(values)
    se=statistics.stdev(values)/math.sqrt(len(values))
    return dict(mean=mean,standard_error=se,ci95=[mean-1.96*se,mean+1.96*se],blocks=len(values))


def aggregate(rows,expected_hands=512):
    grouped=defaultdict(list)
    for row in rows: grouped[row['hand_index']].append(row)
    if set(grouped)!=set(range(expected_hands)): raise ValueError('Wrong hand block prefix')
    keys=['tv','js_bits','selected_disagreement','fold_delta','passive_delta','raise_delta','allin_delta',
          'control_entropy_bits','treatment_entropy_bits']
    blocks=[dict(hand_index=i,states=len(grouped[i]),**{k:statistics.mean(r[k] for r in grouped[i]) for k in keys})
            for i in range(expected_hands)]
    return dict(hand_weighted={k:interval([r[k] for r in blocks]) for k in keys},
                state_weighted={k:statistics.mean(r[k] for r in rows) for k in keys},blocks=blocks)
