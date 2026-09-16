import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parent/'summarize_prefix_throughput.py'
spec=importlib.util.spec_from_file_location('v6_prefix_throughput',path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    lines=[f'[{i:5d}] hands={i*100} envhands={i*200} inf_bs=4.0 collect=2.0s ppo=0.5s' for i in range(1,13)]
    metrics=[dict(iteration=i,environment_hand_accounting=dict(completed_hands=i*200)) for i in range(1,13)]
    return lines,metrics


def test_exact_units_and_accounting():
    out=module.summarize(*fixture())
    assert out['physical_hands_per_logged_collect_plus_ppo_second']==80
    assert out['collection_fraction_of_logged_collect_plus_ppo']==.8
    assert out['physical_hands']==2400 and out['legacy_markers']==1200


def test_incomplete_and_counter_mismatch_fail():
    lines,metrics=fixture()
    with pytest.raises(ValueError): module.summarize(lines[:11],metrics[:11])
    metrics[5]['environment_hand_accounting']['completed_hands']=1
    with pytest.raises(ValueError): module.summarize(lines,metrics)


def test_duplicate_iteration_fails():
    lines,metrics=fixture()
    lines[3]=lines[2]
    with pytest.raises(ValueError): module.summarize(lines,metrics)
