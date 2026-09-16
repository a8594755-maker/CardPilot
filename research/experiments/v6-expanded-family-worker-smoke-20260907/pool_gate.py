"""Only explicitly allowed loader normalization, never ignore tensor differences."""
def normalized_pool(parent, history_limit):
    result=dict(parent)
    result['pool_snapshots']=[{**s,'state_dict':dict(s['state_dict'])} for s in parent['pool_snapshots']]
    result['pool_candidate_history']=parent['pool_candidate_history'][-history_limit:]
    return result
