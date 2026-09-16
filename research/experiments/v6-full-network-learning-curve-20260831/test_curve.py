import importlib.util
from pathlib import Path
import statistics
import pytest

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('v6_curve_protocol',BASE/'run_curve.py')
curve=importlib.util.module_from_spec(spec)
spec.loader.exec_module(curve)


def test_command_and_heldout_exclusion():
    cmd=curve.training_command()
    for key,value in {'--total-environment-hands':'262144','--env-version':'v6','--seed':'20260918',
                     '--worker-seed-base':'2026091800','--archive-checkpoint-every':'4',
                     '--max-runtime-seconds':'6000','--run-id':'v6_full_curve_20260831'}.items():
        assert cmd[cmd.index(key)+1]==value
    assert '--v6-rebind-legacy-weights' in cmd and '--reset-optimizer' in cmd and '--reset-hand-counter' in cmd
    assert str(BASE/'frozen/anchor3.pt') not in cmd and str(BASE/'frozen/anchor4.pt') not in cmd
    assert '--overwrite' not in cmd


def test_hash_accepts_manifest_strings():
    assert curve.sha(str(BASE/'run_curve.py'))==curve.sha(BASE/'run_curve.py')


def test_counter_selection_not_outcome():
    rows=[dict(iteration=i,environment_hand_accounting=dict(completed_hands=i*10000)) for i in range(1,29)]
    archives={i:None for i in range(4,29,4)}
    selected=curve.choose_curve(rows,archives)
    assert selected['mid65']['iteration']==8 and selected['mid131']['iteration']==16
    with pytest.raises(ValueError): curve.choose_curve(rows,{4:None})
    with pytest.raises(ValueError): curve.choose_curve(rows[1:],archives)


def test_statistics_and_family_gate():
    assert curve.stats([1,2,3])['bb_per_100']==2
    half=1.96*statistics.stdev([1,2,3])/(3**.5)
    assert curve.stats([1,2,3])['ci']==[2-half,2+half]
    good=[dict(bb_per_100=1,ci99=[.1,2]) for _ in range(5)]
    assert curve.admit(good)
    bad=[dict(x) for x in good]
    bad[0]['ci99']=[-.1,2]
    assert not curve.admit(bad)
    bad=[dict(x) for x in good]
    bad[3]['ci99']=bad[4]['ci99']=[-.1,2]
    assert not curve.admit(bad)
    bad=[dict(x) for x in good]
    bad[2]['bb_per_100']=0
    assert not curve.admit(bad)
    with pytest.raises(ValueError): curve.admit(good[:4])


def test_raw_pair_accounting_ignores_partial_line(tmp_path):
    path=tmp_path/'rows.jsonl'
    path.write_bytes(b'{"pair_index":0}\n{"pair_index":1}\n{"pair_')
    assert curve.raw_pair_count(path)==2
    assert curve.raw_pair_count(tmp_path/'missing')==0
