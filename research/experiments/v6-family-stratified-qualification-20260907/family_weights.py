"""Pure identity-based conditional-pool allocation; no model/optimizer mutation."""
import math

MASSES = {'original': 0.5, 'added': 0.25, 'recent': 0.25}

def stratify(weights, snapshot_ids, original_ids, added_ids):
    ids = list(snapshot_ids)
    old, added = set(original_ids), set(added_ids)
    if len(ids) != 9 or len(set(ids)) != 9 or len(weights) != 9:
        raise ValueError('requires nine distinct active snapshot IDs')
    if any(type(i) is not int or i < 0 for i in ids):
        raise ValueError('invalid snapshot identity')
    if len(old) != 3 or len(added) != 4 or old & added or not (old | added) <= set(ids):
        raise ValueError('requires three original and four added fixed identities')
    ws = [float(w) for w in weights]
    if any(not math.isfinite(w) or w < 0 for w in ws) or abs(sum(ws) - 1) > 1e-8:
        raise ValueError('invalid normalized weights')
    groups = ['original' if i in old else 'added' if i in added else 'recent' for i in ids]
    totals = {g: sum(w for w, label in zip(ws, groups) if label == g) for g in MASSES}
    if any(v <= 0 for v in totals.values()):
        raise ValueError('zero-support family cannot preserve relative weights')
    return [w * MASSES[g] / totals[g] for w, g in zip(ws, groups)]

def bind_families(snapshots, original_hashes, added_hashes):
    """Resolve fixed identities from predeclared checkpoint hashes, never position."""
    old, added = set(original_hashes), set(added_hashes)
    if len(old) != 3 or len(added) != 4 or old & added:
        raise ValueError('invalid source-hash families')
    found = {}
    for snap in snapshots:
        meta = snap.get('score_components', {})
        if meta.get('kind') != 'initial_external_opponent':
            continue
        digest = meta.get('checkpoint_sha256')
        if digest not in old | added or digest in found:
            raise ValueError('unknown or duplicate fixed source')
        found[digest] = snap['id']
    if set(found) != old | added:
        raise ValueError('missing fixed source')
    return {found[h] for h in old}, {found[h] for h in added}
