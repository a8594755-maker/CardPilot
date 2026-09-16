"""Match actual endpoint rewards, not noisy summaries or pseudo-observations."""
import copy


def join(control, treatment):
    def mapping(rows):
        result = {}
        for row in rows:
            key = (row['anchor'],row['pair_index'])
            if key in result: raise ValueError('duplicate paired identity')
            result[key] = row
        return result
    left,right = mapping(control),mapping(treatment)
    if left.keys() != right.keys(): raise ValueError('unmatched paired identities')
    rows = []
    for key,a in left.items():
        b = right[key]
        if a['deck'] != b['deck'] or a['control_rewards_bb'] != b['control_rewards_bb']:
            raise ValueError('deck/root outcomes differ across arms')
        row = copy.deepcopy(a)
        row['control_rewards_bb'] = a['treatment_rewards_bb']
        row['treatment_rewards_bb'] = b['treatment_rewards_bb']
        delta = [r-l for l,r in zip(row['control_rewards_bb'],row['treatment_rewards_bb'])]
        if len(delta) != 2: raise ValueError('expected both seats')
        row['treatment_minus_control_rewards_bb'] = delta
        row['treatment_minus_control_pair_mean_bb'] = sum(delta)/2
        rows.append(row)
    return rows
