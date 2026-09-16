import copy
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from summarize_throughput import estimate


def rows():
    return [dict(iteration=i+1,recorded_at=f'2026-08-31T02:00:{i*10:02d}+00:00',
        environment_hand_accounting=dict(completed_hands=(i+1)*1000)) for i in range(3)]


def test_physical_rate_excludes_unknown_startup():
    result=estimate(rows())
    assert result['measured_physical_hands_between_saved_updates']==2000
    assert result['elapsed_seconds_between_saved_updates']==20
    assert result['physical_hands_per_second']==100
    assert result['days_for_2_7b_at_unchanged_rate']==pytest.approx(312.5)


@pytest.mark.parametrize('kind',['time','count','iteration','missing'])
def test_bad_prefix_rejected(kind):
    data=copy.deepcopy(rows())
    if kind=='time': data[2]['recorded_at']=data[0]['recorded_at']
    if kind=='count': data[2]['environment_hand_accounting']['completed_hands']=1
    if kind=='iteration': data[2]['iteration']=7
    if kind=='missing': data=data[:1]
    with pytest.raises(ValueError): estimate(data)
