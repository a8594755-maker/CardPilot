import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent


def test_fixed_identity_and_allocation():
    spec = importlib.util.spec_from_file_location("soup_external", BASE / "run_pilot.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.SOURCE_SHA == "914c8d186d4cdb4f2139ff64d2b32b7558eb1c5761b553c09457bd756aaec8e5"
    assert [module.session_seed(index) for index in range(1, 9)] == list(range(2026110501, 2026110509))
    assert len({module.session_id(index) for index in range(1, 9)}) == 8
    assert "cannot be pooled" in (BASE / "preregistration.md").read_text(encoding="utf-8")
