"""Opt-in pool selection; retain external anchors, fill remaining slots by recency.

This module does not change trainer defaults or touch saved checkpoints. Binding
it into a trainer requires a separate explicit strategy and retained-state gate.
"""

STRATEGY = 'anchor-latest'

def retained_snapshots(snapshots, k):
    if not isinstance(k, int) or k <= 0:
        raise ValueError('anchor-latest requires positive integer capacity')
    ids = [s['id'] for s in snapshots]
    if len(ids) != len(set(ids)) or any(type(i) is not int or i < 0 for i in ids):
        raise ValueError('unique nonnegative snapshot IDs required')
    anchors = [s for s in snapshots if s.get('score_components', {}).get('kind') == 'initial_external_opponent']
    if len(anchors) > k:
        raise ValueError('capacity would discard an external anchor')
    # Critical for initial restored pool-slot/EMA semantics: do not reorder a
    # complete retained pool merely on load. Replacement happens on admission.
    if len(snapshots) <= k:
        return list(snapshots)
    anchor_ids = {s['id'] for s in anchors}
    candidates = [s for s in snapshots if s['id'] not in anchor_ids]
    candidates.sort(key=lambda s: s['id'], reverse=True)
    return anchors + candidates[:k-len(anchors)]

def pool_class(original):
    class AnchorRecentPool(original):
        def __init__(self, k=5, strategy=STRATEGY, history_limit=200):
            if strategy != STRATEGY:
                raise ValueError('explicit anchor-latest strategy required')
            super().__init__(k=k, strategy='latest', history_limit=history_limit)
            self.strategy = STRATEGY
        def _prune(self):
            self.snapshots = retained_snapshots(self.snapshots, self.k)
    return AnchorRecentPool
