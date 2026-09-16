import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from paired_contrast import join


def rows():
    a = {'anchor':'test','pair_index':0,'deck':list(range(52)),
         'control_rewards_bb':[1.,-2.],'treatment_rewards_bb':[5.,7.]}
    b = copy.deepcopy(a); b['treatment_rewards_bb'] = [9.,3.]
    return [a],[b]


def test_actual_endpoint_difference():
    a,b = rows(); result = join(a,b)[0]
    assert result['control_rewards_bb'] == [5.,7.]
    assert result['treatment_minus_control_rewards_bb'] == [4.,-4.]
    assert result['treatment_minus_control_pair_mean_bb'] == 0
    assert a[0]['control_rewards_bb'] == [1.,-2.]


@pytest.mark.parametrize('change',['root','deck','missing','duplicate'])
def test_reject_invalid_pairing(change):
    a,b = rows()
    if change == 'root': b[0]['control_rewards_bb'][0] = 2.
    if change == 'deck': b[0]['deck'].reverse()
    if change == 'missing': b = []
    if change == 'duplicate': b = b*2
    with pytest.raises(ValueError): join(a,b)
