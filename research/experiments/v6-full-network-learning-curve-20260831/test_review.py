import importlib.util
import math
from pathlib import Path
import pytest

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('v6_curve_independent_review',BASE/'review_completed_curve.py')
review=importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def fixture():
    return [dict(pair_index=i,deck=list(range(52)),rewards_bb=[i,-i/2],decisions=[4,3]) for i in range(4)]


def test_raw_pair_validation_and_units():
    assert review.verify_rows(fixture(),4)==[0,25,50,75]
    rows=fixture()
    rows[2]['pair_index']=1
    with pytest.raises(ValueError): review.verify_rows(rows,4)
    with pytest.raises(ValueError): review.verify_rows(fixture(),5)


@pytest.mark.parametrize('field,value',[('deck',[0]*52),('rewards_bb',[201,0]),
    ('rewards_bb',[float('nan'),0]),('decisions',[0,1])])
def test_invalid_evidence_rejected(field,value):
    rows=fixture()
    rows[0][field]=value
    with pytest.raises(ValueError): review.verify_rows(rows,4)


def test_independent_interval_arithmetic():
    out=review.interval([1,2,3])
    assert out['bb_per_100']==2
    assert abs(out['standard_error']-1/math.sqrt(3))<1e-12
    assert review.interval([4,4,4],.99)['ci']==[4,4]
    with pytest.raises(ValueError): review.interval([1])


def test_gate_needs_standard_and_holdout_breadth():
    good=[dict(anchor=i,bb_per_100=1,ci99=[.1,2]) for i in range(5)]
    assert review.raw_gate(good)
    good[0]['ci99']=[-.1,2]
    assert not review.raw_gate(good)
    with pytest.raises(ValueError): review.raw_gate(good[:-1])
