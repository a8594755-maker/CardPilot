import importlib.util
from pathlib import Path
import subprocess
import sys
import pytest

spec=importlib.util.spec_from_file_location('long_run_10m',Path(__file__).with_name('long_run_10m.py'))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_fresh_and_continuation(tmp_path):
    first=m.training_command(tmp_path,'train10m')
    second=m.training_command(tmp_path,'train20m')
    assert '--resume' not in first
    assert first[first.index('--total-environment-hands')+1]=='10000000'
    assert second[second.index('--total-environment-hands')+1]=='20000000'
    assert '--no-reset-optimizer' in second and '--reset-hand-counter' not in second
    assert '--managed-deal-attempts' in first and '--managed-deal-attempts' in second
    assert int(first[first.index('--worker-seed-base')+1])+12 < 2**32
    assert first[first.index('--total-hands')+1]==second[second.index('--total-hands')+1]


def test_plan_does_not_create_experiment():
    result=subprocess.run([sys.executable,str(Path(m.__file__)),'plan','--run-name','unit_plan_no_execution'],
                          capture_output=True,text=True)
    assert result.returncode==0
    assert not (m.ROOT/'research/experiments/unit_plan_no_execution').exists()


def test_exact_file_exclusion(tmp_path):
    path=tmp_path/'record.json'
    m.write(path,{'one':1})
    with pytest.raises(FileExistsError):
        m.write(path,{'one':2})


def test_trainer_argument_surface():
    # --help exits before model creation, worker startup or directory writes.
    result=subprocess.run([sys.executable,'-B',str(m.ROOT/'scripts/alpha_holdem/train_v5.py'),'--help'],
                          capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    for stage in m.STAGES:
        for arg in m.training_command(Path('unused'),stage):
            if arg.startswith('--'):
                assert arg in result.stdout,arg
