import importlib.util
from pathlib import Path
import sys
import pytest

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('v6_smoke_runner',BASE/'run_smoke.py')
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_fixed_training_command():
    cmd=runner.command()
    for key,value in {'--env-version':'v6','--total-environment-hands':'8192','--workers':'12',
        '--seed':'20260916','--worker-seed-base':'2026091600','--archive-checkpoint-every':'1',
        '--ppo-epochs':'2','--source-policy-kl-coef':'.01','--max-runtime-seconds':'600'}.items():
        assert cmd[cmd.index(key)+1]==value
    for flag in ['--v6-rebind-legacy-weights','--reset-hand-counter','--reset-optimizer','--allow-resume']:
        assert flag in cmd
    assert '--all-policy-heads-only-training' not in cmd
    assert '--overwrite' not in cmd


def test_exact_source_identity():
    for path,digest in zip(runner.ANCHORS,runner.DIGESTS):
        assert runner.sha256_file(path)==digest


def test_v6_source_requires_explicit_binding():
    from alpha_holdem.policy_contract_v6 import validate_metadata
    with pytest.raises(ValueError): validate_metadata({'env_version':'v55preflopv2v4obs'})
