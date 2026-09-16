import json
from pathlib import Path

import numpy as np
import pytest
import torch

from scripts.alpha_holdem.paired_mirror_treatment_delta import paired_delta
from scripts.alpha_holdem.v5_mirror_eval import (
    ACTION_RNG_SCHEMA,
    POLICY_MODE,
    SAMPLED_POLICY_MODE,
    Policy,
    action_uniform,
    sample_legal_slot,
    summarize_anchor,
)


class UniformLegalModel(torch.nn.Module):
    def forward(self, cards, actions, extras, mask):
        return torch.zeros_like(mask).masked_fill(mask == 0, -1e9), torch.zeros((1, 1))


def policy():
    return Policy(
        label="uniform", path=Path("unused.pt"), sha256="test", checkpoint={},
        model=UniformLegalModel(), env_version="v55preflopv2v4obs", obs_version="v4",
        emulate_raise_cap1_legality=False, device="cpu",
    )


def test_counter_uniform_is_reproducible_and_coordinate_separated():
    values = [action_uniform(42, pair, seat, decision)
              for pair in range(8) for seat in range(2) for decision in range(8)]
    assert all(0 <= value < 1 for value in values)
    assert len(set(values)) == len(values)
    assert action_uniform(42, 3, 1, 4) == action_uniform(42, 3, 1, 4)
    assert action_uniform(43, 3, 1, 4) != action_uniform(42, 3, 1, 4)


def test_inverse_cdf_preserves_legal_categorical_probabilities():
    logits = np.array([1000.0, np.log(0.2), np.log(0.3), np.log(0.5)])
    slots = [sample_legal_slot(logits, [1, 2, 3], (i + 0.5) / 1000) for i in range(1000)]
    assert slots.count(0) == 0
    assert [slots.count(i) for i in (1, 2, 3)] == [200, 300, 500]


def test_sampler_fails_closed_on_invalid_input():
    with pytest.raises(ValueError):
        sample_legal_slot(np.zeros(2), [], 0.5)
    with pytest.raises(ValueError):
        sample_legal_slot(np.zeros(2), [0, 1], 1.0)
    with pytest.raises(ValueError):
        sample_legal_slot(np.array([np.nan, 0.0]), [0, 1], 0.5)


def test_sampled_identical_policy_mirror_cancels_exactly_and_repeats():
    p = policy()
    kwargs = dict(candidate=p, anchor=p, pairs=32, seed=8123, starting_stack=200,
                  include_pair_outcomes=True, policy_mode=SAMPLED_POLICY_MODE)
    first = summarize_anchor(**kwargs)
    second = summarize_anchor(**kwargs)
    assert first["candidate_bb100"] == 0.0
    assert first["candidate_ci95_bb100"] == 0.0
    assert first["paired_outcomes"] == second["paired_outcomes"]
    assert first["action_rng"] == {"schema": ACTION_RNG_SCHEMA, "seed": 8123}
    assert any(value != 0 for value in first["paired_outcomes"]["bb_bb_per_hand"])


def test_greedy_default_is_identical_to_explicit_greedy_mode():
    p = policy()
    kwargs = dict(candidate=p, anchor=p, pairs=8, seed=999, starting_stack=200,
                  include_pair_outcomes=True)
    default = summarize_anchor(**kwargs)
    explicit = summarize_anchor(**kwargs, policy_mode=POLICY_MODE)
    assert default["paired_outcomes"] == explicit["paired_outcomes"]
    assert default["policy_mode"] == POLICY_MODE
    assert default["action_rng"] is None


def test_paired_delta_rejects_misaligned_action_randomness(tmp_path):
    document = {
        "seed": 42, "pairs": 2, "starting_stack": 200,
        "policy_mode": SAMPLED_POLICY_MODE, "action_rng_schema": ACTION_RNG_SCHEMA,
        "anchors": [{"anchor": "a", "anchor_sha256": "same",
                     "action_rng": {"schema": ACTION_RNG_SCHEMA, "seed": 42},
                     "paired_outcomes": {"overall_bb_per_hand": [0.0, 1.0]},
                     "candidate_bb100": 50.0}],
    }
    control = tmp_path / "control.json"
    treatment = tmp_path / "treatment.json"
    control.write_text(json.dumps(document))
    document["anchors"][0]["action_rng"]["seed"] = 43
    treatment.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="action random-stream mismatch"):
        paired_delta(control, treatment)
