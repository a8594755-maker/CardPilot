import json

import run_recovery as run


def test_parent_and_endpoint_are_exactly_preserved():
    run.protect()
    assert run.sha(run.PARENT / "production/latest.pt") == run.ENDPOINT_SHA


def test_finite_tree_accepts_current_metric_schema():
    row = json.loads((run.PARENT / "production/h1_training_metrics.jsonl").read_text().splitlines()[0])
    run.assert_finite_tree(row)
    assert all(key in row for key in ("approx_kl", "entropy", "reference_policy_kl"))


def test_evaluation_was_not_previously_started():
    assert not (run.PARENT / "evaluation").exists()
    assert run.read(run.PARENT / "execution.json")["evaluation_hands"] == 0
