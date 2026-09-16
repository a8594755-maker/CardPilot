import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('training_review_test',Path(__file__).with_name('review_training.py'))
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def test_update_count_includes_replay_minibatch_boundary():
    assert review.expected_steps([{'policy_rows':23525,'ppo_epochs_completed':2}],16384) == 4


def test_update_count_respects_early_epochs():
    assert review.expected_steps([{'policy_rows':16384,'ppo_epochs_completed':1},
                                  {'policy_rows':16385,'ppo_epochs_completed':2}],16384) == 5


def test_invalid_batch_fails():
    with pytest.raises(ValueError): review.expected_steps([],0)
