"""Descriptive distribution geometry; no outcome/admission statistics."""
from collections import defaultdict
import math

FLOOR = 1e-12


def distribution_metrics(source, candidate, mask):
    if not len(source) == len(candidate) == len(mask) == 9: raise ValueError('Expected9slots')
    legal = [i for i, v in enumerate(mask) if v]
    if not legal: raise ValueError('No legal slots')
    for values in (source, candidate):
        if (not all(math.isfinite(x) and 0 <= x <= 1 for x in values)
                or abs(math.fsum(values)-1) > 1e-12 or any(values[i] != 0 for i in range(9) if i not in legal)):
            raise ValueError('Invalid legal distribution')
    p, q = [source[i] for i in legal], [candidate[i] for i in legal]
    midpoint = [(a+b)/2 for a, b in zip(p, q)]
    def entropy(values): return -math.fsum(x*math.log(x) for x in values if x)
    def smooth(values):
        values = [max(FLOOR, x) for x in values]
        total = math.fsum(values)
        return [x/total for x in values]
    sp, sq = smooth(p), smooth(q)
    return dict(total_variation=.5*math.fsum(abs(a-b) for a, b in zip(p, q)),
                source_to_candidate_kl_floor=math.fsum(a*math.log(a/b) for a, b in zip(sp, sq)),
                candidate_to_source_kl_floor=math.fsum(b*math.log(b/a) for a, b in zip(sp, sq)),
                jensen_shannon=max(0.0, entropy(midpoint)-(entropy(p)+entropy(q))/2),
                entropy_nats=entropy(q), fold_probability=candidate[0], allin_probability=candidate[8],
                argmax_disagreement=float(max(legal, key=lambda i:source[i]) != max(legal, key=lambda i:candidate[i])),
                source_clipped_entries=sum(x < FLOOR for x in p), candidate_clipped_entries=sum(x < FLOOR for x in q))


def summarize(rows):
    if not rows: raise ValueError('No diagnostic rows')
    labels, by_hand = list(rows[0]['metrics']), defaultdict(list)
    for row in rows: by_hand[row['hand_index']].append(row)
    result = dict(states=len(rows), hands=len(by_hand), state_weighted={}, hand_weighted={})
    for label in labels:
        keys = list(rows[0]['metrics'][label])
        result['state_weighted'][label] = {k:math.fsum(r['metrics'][label][k] for r in rows)/len(rows) for k in keys}
        means = [{k:math.fsum(r['metrics'][label][k] for r in group)/len(group) for k in keys} for group in by_hand.values()]
        result['hand_weighted'][label] = {k:math.fsum(m[k] for m in means)/len(means) for k in keys}
    return result
