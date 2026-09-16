from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alpha_holdem.train_v5 import (
    exp003_allin_ev_reward,
    exp003_exact_showdown_counts,
    exp003_sampled_showdown_counts,
)


def terminal_state(
    *,
    folded_player: int = -1,
    is_done: bool = True,
    stacks: tuple[float, float] = (0.0, 0.0),
    hole_cards=((0, 1), (2, 3)),
):
    return SimpleNamespace(
        folded_player=folded_player,
        is_done=is_done,
        board=[4, 5, 6, 7, 8],
        hole_cards=list(hole_cards),
        stacks=list(stacks),
        config=SimpleNamespace(effective_stack=200.0),
    )


def test_sampled_showdown_counts_are_bounded_and_deterministic():
    args = ((0, 1), (2, 3), (4, 5, 6), 17)
    first = exp003_sampled_showdown_counts(*args)
    second = exp003_sampled_showdown_counts(*args)

    assert first == second
    assert sum(first[:3]) == first[3] == 17


def test_exact_allin_reward_matches_exhaustive_equity():
    state = terminal_state(stacks=(0.0, 50.0))
    pre_board = (4, 5, 6, 7)
    wins, losses, _ties, total = exp003_exact_showdown_counts(
        (0, 1), (2, 3), pre_board
    )

    reward, runouts, skipped = exp003_allin_ev_reward(
        state, acting_player=0, pre_board=pre_board, max_runouts=200
    )
    expected = (wins * 150.0 - losses * 200.0) / total

    assert runouts == total
    assert skipped is False
    assert reward == pytest.approx(expected)


def test_allin_ev_is_zero_sum_between_player_perspectives():
    state = terminal_state(stacks=(0.0, 0.0))
    kwargs = {'state': state, 'pre_board': (4, 5, 6), 'max_runouts': 31}

    reward0, runouts0, _ = exp003_allin_ev_reward(acting_player=0, **kwargs)
    reward1, runouts1, _ = exp003_allin_ev_reward(acting_player=1, **kwargs)

    assert runouts0 == runouts1 == 31
    assert reward0 == pytest.approx(-reward1)


def test_allin_ev_respects_bounded_runout_cap():
    result = exp003_allin_ev_reward(
        terminal_state(),
        acting_player=0,
        pre_board=(4, 5, 6),
        max_runouts=7,
    )

    assert result is not None
    _reward, runouts, skipped = result
    assert runouts == 7
    assert skipped is False


@pytest.mark.parametrize(
    ('state', 'pre_board'),
    [
        (terminal_state(folded_player=1), (4, 5, 6)),
        (terminal_state(is_done=False), (4, 5, 6)),
        (terminal_state(stacks=(25.0, 30.0)), (4, 5, 6)),
        (terminal_state(hole_cards=(None, (2, 3))), (4, 5, 6)),
        (terminal_state(), (4, 5, 6, 7, 8)),
    ],
)
def test_allin_ev_skips_nonqualifying_terminals(state, pre_board):
    assert exp003_allin_ev_reward(state, 0, pre_board, 200) is None
