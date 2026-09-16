import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent


def test_independent_review_passes():
    spec = importlib.util.spec_from_file_location("review_tail", BASE / "review_tail.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.review()
    assert result["status"] == "PASS"
    assert result["tail_parent"]["ci95"][0] > 0
    assert result["training_matrix_is_generalization_evidence"] is False

