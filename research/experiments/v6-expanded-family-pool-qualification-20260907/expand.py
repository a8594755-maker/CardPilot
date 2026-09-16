"""Pure explicit nine-slot pool derivation. Never mutates a source checkpoint."""
import copy
import math

FIELDS={'pool_snapshots','pool_active_metadata','pool_candidate_history',
        'adaptive_opponent_ema_rewards','adaptive_opponent_weights','adaptive_opponent_observations',
        'expanded_family_pool_contract'}
def expand(parent, additions):
    if parent.get('expanded_family_pool_contract') is not None:
        raise ValueError('expansion already applied')
    if parent.get('pool_strategy')!='anchor-latest' or len(parent['pool_snapshots'])!=5 or len(additions)!=4:
        raise ValueError('requires five-slot anchor-latest and four additions')
    snaps=parent['pool_snapshots']; history=parent['pool_candidate_history']
    if sum(s.get('score_components',{}).get('kind')=='initial_external_opponent' for s in snaps)!=3:
        raise ValueError('requires three preserved external anchors')
    ids=[s['id'] for s in snaps]
    if len(set(ids))!=5 or any(type(i) is not int or i<0 for i in ids): raise ValueError('invalid IDs')
    for k in ('adaptive_opponent_ema_rewards','adaptive_opponent_weights','adaptive_opponent_observations'):
        if len(parent[k])!=5: raise ValueError('adaptive length mismatch')
    ws=parent['adaptive_opponent_weights']
    if not all(math.isfinite(w) and w>=0 for w in ws) or abs(sum(ws)-1)>1e-6: raise ValueError('invalid weights')
    hashes=[a['sha256'] for a in additions]
    known={s.get('score_components',{}).get('checkpoint_sha256') for s in snaps+history}
    if len(set(hashes))!=4 or any(h in known for h in hashes): raise ValueError('duplicate source')
    if any(len(h)!=64 for h in hashes): raise ValueError('invalid SHA')
    out=copy.deepcopy(parent)
    next_id=max(ids+[h['id'] for h in history])+1
    for j,a in enumerate(additions):
        c=a['checkpoint']
        components={'kind':'initial_external_opponent','checkpoint':a['path'],'checkpoint_sha256':a['sha256'],
           'norm_layer':c.get('norm_layer','bn'),'position_adapter_postflop_only':bool(c.get('position_adapter_postflop_only',False)),
           'position_adapter_min_street':int(c.get('position_adapter_min_street',1)),
           'position_adapter_max_street':int(c.get('position_adapter_max_street',3)),
           'admission_kind':'explicit_family_expansion','source_family':a['family']}
        snap={'id':next_id+j,'hands':c['total_hands'],'iteration':c['iteration'],'pool_strategy':'anchor-latest',
           'selection_loss':0.0,'selection_score':0.0,'score_components':components,'state_dict':copy.deepcopy(c['model'])}
        out['pool_snapshots'].append(snap)
        metadata={k:copy.deepcopy(v) for k,v in snap.items() if k!='state_dict'}
        out['pool_active_metadata'].append(metadata)
        out['pool_candidate_history'].append({**metadata,'selected':True,'active_ids_after':[s['id'] for s in out['pool_snapshots']]})
    out['adaptive_opponent_ema_rewards']+= [0.0]*4
    out['adaptive_opponent_observations']+= [0]*4
    out['adaptive_opponent_weights']=[w*5/9 for w in ws]+[1/9]*4
    out['expanded_family_pool_contract']={'capacity':9,'preserved_slots':5,'new_ids':list(range(next_id,next_id+4)),
        'source_sha256':hashes,'new_initial_mass':4/9,'old_relative_weights_preserved':True,
        'requires_new_assignment_boundary':True,'statistical_not_bitwise_continuation':True}
    return out
