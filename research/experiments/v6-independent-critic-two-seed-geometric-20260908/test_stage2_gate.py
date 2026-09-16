import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('unlaunched_stage2',Path(__file__).with_name('run_stage2.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize('decision',[
    {'passed_evidence_checks':False,'decision':'CONTINUE_PREREGISTERED_1M_DOSE'},
    {'passed_evidence_checks':True,'decision':'STOP_FOR_COLLAPSE_REVIEW'},
])
def test_bad_gate_prevents_any_launch(monkeypatch,decision):
    monkeypatch.setattr(runner.torch,'set_num_threads',lambda _:None)
    monkeypatch.setattr(runner,'read',lambda p: {} if p.name=='input_contract.json' else decision)
    monkeypatch.setattr(runner.subprocess,'Popen',lambda *a,**k: pytest.fail('must not launch'))
    with pytest.raises(AssertionError): runner.main()


def test_missing_gate_prevents_any_launch(monkeypatch):
    monkeypatch.setattr(runner.torch,'set_num_threads',lambda _:None)
    def read(path):
        if path.name=='input_contract.json': return {}
        raise FileNotFoundError(path)
    monkeypatch.setattr(runner,'read',read)
    monkeypatch.setattr(runner.subprocess,'Popen',lambda *a,**k: pytest.fail('must not launch'))
    with pytest.raises(FileNotFoundError): runner.main()
