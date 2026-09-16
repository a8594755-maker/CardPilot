import importlib.util
from pathlib import Path

BASE = Path(__file__).resolve().parent


def test_allocation_identity():
    spec = importlib.util.spec_from_file_location("pilot", BASE / "run_pilot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.SOURCE_SHA == "1c050edb088eaaf4bdc653a7b7b4708191854a7ca216f913ca2b7c1c6cd412c4"
    assert [module.session_seed(i) for i in range(1, 9)] == list(range(2026110301, 2026110309))
    assert len({module.session_id(i) for i in range(1, 9)}) == 8
    assert "cannot be pooled" in (BASE / "preregistration.md").read_text(encoding="utf-8")

