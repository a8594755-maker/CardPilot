import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent


def load_runner():
    spec = importlib.util.spec_from_file_location("tail_fresh5k", BASE / "run_pilot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixed_fresh_allocation_and_identity():
    module = load_runner()
    assert module.SOURCE_SHA == "6f3bf54433d72fdc4ebb9de33c52947c6da4fd0af2259d8b9561f7956821db5b"
    assert [module.session_seed(i) for i in range(1, 9)] == list(range(2026110201, 2026110209))
    assert len({module.session_id(i) for i in range(1, 9)}) == 8
    text = (BASE / "preregistration.md").read_text(encoding="utf-8")
    assert "cannot be pooled" in text and "at least 4/8" in text


def test_commands_are_generic_greedy():
    module = load_runner()
    module.BASE = BASE
    command = ["client", "--model", str(BASE / "frozen/final.pt"), "--hands", "625",
               "--seed", str(module.session_seed(1)), "--session-id", module.session_id(1),
               "--out-dir", str(BASE / "sessions/s01"), "--device", "cpu", "--policy-mode", "greedy"]
    assert command[command.index("--hands") + 1] == "625"
    assert command[command.index("--policy-mode") + 1] == "greedy"

