import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent


def test_preregistered_intervention_is_single_and_explicit():
    spec = importlib.util.spec_from_file_location("parent_kl", BASE / "run_smoke.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.TARGET == 196608
    assert module.KL_COEF == ".1"
    text = (BASE / "preregistration.md").read_text(encoding="utf-8")
    assert "sole learning intervention" in text
    assert "No Slumbot hands" in text

