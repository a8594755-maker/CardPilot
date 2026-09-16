import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent


def test_review_passes_and_rejects_transfer():
    spec = importlib.util.spec_from_file_location("tail_live_review", BASE / "review_finish.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reviewed = module.review()
    assert reviewed["status"] == "PASS"
    assert reviewed["decision"] == "FRESH5K_TRANSFER_GATE_NOT_PASSED"
    assert reviewed["statistics"]["raw_hand_ci95"][1] < 0

