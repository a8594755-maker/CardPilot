import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alpha_holdem.train_mp3_hybrid_h1 import prepare_h2_critic_returns
from scripts.alpha_holdem.train_v5 import paired_seat_average_actor_reward_blocks


def transition(*, player, reward=0.0, done=False):
    return (
        np.zeros((6, 4, 13), dtype=np.float32),
        np.zeros((25, 4, 5), dtype=np.float32),
        np.zeros(8, dtype=np.float32),
        np.ones(9, dtype=np.float32),
        1,
        0.0,
        float(reward),
        0.0,
        float(done),
        1.0,
        1.0,
        float(done),
        float('nan'),
        float(player),
    )


def terminal_overrides(block):
    return {
        int(row[13]): float(row[14])
        for row in block
        if float(row[8]) > 0.5
    }


def test_external_pair_keeps_raw_critic_reward_and_averages_actor_seats():
    source = [
        transition(player=0),
        transition(player=0, reward=4.0, done=True),
    ]
    mirror = [
        transition(player=1),
        transition(player=1, reward=-2.0, done=True),
    ]

    paired_source, paired_mirror, terminal_rows = (
        paired_seat_average_actor_reward_blocks(source, mirror)
    )

    assert terminal_rows == 2
    assert paired_source[-1][6] == 4.0
    assert paired_mirror[-1][6] == -2.0
    assert terminal_overrides(paired_source) == {0: 1.0}
    assert terminal_overrides(paired_mirror) == {1: 1.0}
    assert math.isnan(paired_source[0][14])
    assert math.isnan(paired_mirror[0][14])


def test_selfplay_pair_matches_private_hand_to_opposite_seat():
    source = [
        transition(player=0, reward=6.0, done=True),
        transition(player=1, reward=-6.0, done=True),
    ]
    mirror = [
        transition(player=0, reward=2.0, done=True),
        transition(player=1, reward=-2.0, done=True),
    ]

    paired_source, paired_mirror, terminal_rows = (
        paired_seat_average_actor_reward_blocks(source, mirror)
    )

    assert terminal_rows == 4
    assert terminal_overrides(paired_source) == {0: 2.0, 1: -2.0}
    assert terminal_overrides(paired_mirror) == {0: -2.0, 1: 2.0}
    assert [row[6] for row in paired_source] == [6.0, -6.0]
    assert [row[6] for row in paired_mirror] == [2.0, -2.0]


def test_player_sets_must_be_an_opposite_seat_bijection():
    source = [transition(player=0, reward=1.0, done=True)]
    mirror = [transition(player=0, reward=-1.0, done=True)]
    with pytest.raises(ValueError, match='opposite-seat bijection'):
        paired_seat_average_actor_reward_blocks(source, mirror)


def test_explicit_hand_rewards_support_a_seat_with_no_policy_decision():
    source = []
    mirror = [transition(player=1, reward=-2.0, done=True)]
    paired_source, paired_mirror, terminal_rows = (
        paired_seat_average_actor_reward_blocks(
            source,
            mirror,
            source_rewards={0: 4.0, 1: -4.0},
            mirror_rewards={0: 2.0, 1: -2.0},
        )
    )
    assert paired_source == []
    assert terminal_rows == 1
    assert terminal_overrides(paired_mirror) == {1: 1.0}


def test_actor_reward_stream_does_not_replace_raw_critic_return():
    advantages, actor_returns, critic_returns, override_mask = (
        prepare_h2_critic_returns(
            np.array([4.0]),
            np.array([0.0]),
            np.array([1.0]),
            np.array([np.nan]),
            actor_rewards=np.array([1.0]),
        )
    )
    np.testing.assert_allclose(advantages, [1.0])
    np.testing.assert_allclose(actor_returns, [1.0])
    np.testing.assert_allclose(critic_returns, [4.0])
    assert not override_mask.any()
