import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent


def test_unchanged_recovery_contract():
    spec = importlib.util.spec_from_file_location("parent_kl_recovery", BASE / "run_tail.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.TARGET == 196608 and module.KL_COEF == ".1"
    prior = BASE.parent / "v6-parent-kl-conservative-tail-20260901/experiment.json"
    assert prior.is_file()
    text = (BASE / "preregistration.md").read_text(encoding="utf-8")
    assert "only infrastructure change" in text and "No Slumbot" in text

