"""Explicit panel contract; never fabricate absent anchor observations."""
import math
import statistics

def require(ok, message):
    if not ok: raise ValueError(message)

def stats(values):
    require(len(values)>=2 and all(math.isfinite(x) for x in values), 'insufficient/nonfinite samples')
    point = statistics.mean(values)*100
    half = 1.96*statistics.stdev(values)*100/math.sqrt(len(values))
    return dict(bb100=point,ci95_low_bb100=point-half,ci95_high_bb100=point+half,samples=len(values))

def summarize(rows, *, anchors, pairs_per_anchor):
    anchors = tuple(anchors)
    require(anchors and len(set(anchors))==len(anchors) and all(isinstance(a,str) and a for a in anchors), 'invalid anchor contract')
    require(type(pairs_per_anchor) is int and pairs_per_anchor>=2, 'insufficient pair target')
    groups = {a:[] for a in anchors}; seats = [[],[]]; pooled=[]; keys=set(); decks=set()
    indices = {a:set() for a in anchors}
    for r in rows:
        a,i = r['anchor'],r['pair_index']
        require(a in groups and type(i) is int and 0<=i<pairs_per_anchor, 'unexpected anchor/index')
        key=(a,i); deck=tuple(r['deck'])
        require(key not in keys and deck not in decks and sorted(deck)==list(range(52)), 'duplicate/invalid pair')
        keys.add(key); decks.add(deck); indices[a].add(i)
        left,right = r['control_rewards_bb'],r['treatment_rewards_bb']
        require(len(left)==len(right)==2 and all(math.isfinite(x) and abs(x)<=200 for x in left+right), 'invalid rewards')
        delta=[right[s]-left[s] for s in (0,1)]
        expected=r['treatment_minus_control_rewards_bb']
        require(len(expected)==2 and all(math.isclose(x,y,abs_tol=1e-9) for x,y in zip(delta,expected)), 'seat arithmetic')
        mean=statistics.mean(delta)
        require(math.isclose(mean,r['treatment_minus_control_pair_mean_bb'],abs_tol=1e-9), 'pair arithmetic')
        groups[a].append(mean); pooled.append(mean)
        for s in (0,1): seats[s].append(delta[s])
    require(all(indices[a]==set(range(pairs_per_anchor)) for a in anchors), 'missing anchor/pairs')
    result=dict(pooled=stats(pooled),by_anchor={a:stats(groups[a]) for a in anchors},by_seat={str(s):stats(seats[s]) for s in (0,1)})
    result['positive_anchor_count']=sum(v['bb100']>=0 for v in result['by_anchor'].values())
    result['both_seats_nonnegative']=all(v['bb100']>=0 for v in result['by_seat'].values())
    return result

def severe(summary, *, minimum_bad_anchors, margin_bb100=25):
    require(type(minimum_bad_anchors) is int and 1<=minimum_bad_anchors<=len(summary['by_anchor']), 'invalid gate contract')
    require(math.isfinite(margin_bb100) and margin_bb100>=0, 'invalid margin')
    require(all(v['samples']>=2 for v in summary['by_anchor'].values()), 'empty anchor gate')
    return sum(v['ci95_high_bb100'] < -margin_bb100 for v in summary['by_anchor'].values())>=minimum_bad_anchors and all(v['ci95_high_bb100']<0 for v in summary['by_seat'].values())
