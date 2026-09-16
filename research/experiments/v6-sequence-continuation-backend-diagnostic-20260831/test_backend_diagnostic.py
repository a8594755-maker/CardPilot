import numpy as np

import run_diagnostic as run


def test_sampled_actions_uses_one_fixed_uniform_per_row():
    probabilities = np.array([[0.2, 0.3, 0.5], [0.0, 0.6, 0.4]])
    uniforms = np.array([0.2, 0.9])
    assert run.sampled_actions(probabilities, uniforms).tolist() == [0, 2]


def test_backend_metrics_exact_action_disagreements():
    cpu = np.array([[0.6, 0.4], [0.5, 0.5]])
    gpu = np.array([[0.4, 0.6], [0.5, 0.5]])
    result = run.backend_metrics(cpu, gpu, np.array([0.5, 0.2]))
    assert np.isclose(result["max_probability_delta"], 0.2)
    assert np.isclose(result["mean_backend_tv"], 0.1)
    assert result["greedy_disagreement"] == 0.5
    assert result["sampled_disagreement"] == 0.5


def test_original_gate_requires_every_condition():
    parent = np.full(128, 0.16)
    current = np.full(128, 0.149)
    assert run.original_gate(current, parent)["passed"]
    assert not run.original_gate(np.full(128, 0.151), parent)["passed"]


def test_threshold_names_are_exactly_preregistered_metrics():
    assert set(run.THRESHOLDS) == {
        "max_probability_delta",
        "mean_backend_tv",
        "greedy_disagreement",
        "sampled_disagreement",
        "absolute_hero_tv_mean_difference",
    }
