import random
import sys
from pathlib import Path
from dataclasses import replace
import numpy as np
import pytest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from oracle_validation import ChipState, make_oracle, assert_equal, advance
from alpha_holdem.policy_contract_v6 import action_table, observation, from_external, apply_incr, METADATA, validate_metadata
from alpha_holdem.environment_v6 import HUNLEnvironmentV6
from deep_cfr.hand_eval import card_to_str


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('No network allowed in contract validation')
    monkeypatch.setattr('socket.socket.connect', denied)
    monkeypatch.setattr('socket.create_connection', denied)


def prefix(actions, initial=(20000, 20000)):
    s = ChipState.new(range(52), initial)
    o = make_oracle(s)
    assert_equal(s, o)
    for action in actions:
        s = advance(s, o, action)
    return s, o


def test_bb_option_and_minimum():
    s, _ = prefix(['c'])
    assert (s.street, s.actor, s.board, s.min_to) == (0, 0, (), 200)
    s, _ = prefix(['c', 'k'])
    assert (s.street, s.actor, s.pot, s.min_to) == (1, 0, 200, 100)
    assert all(int(a[1:]) >= 100 for a in action_table(s)[1] if a and a.startswith('b'))


def test_raise_increment():
    s, o = prefix(['c', 'k', 'b300'])
    assert s.min_to == 600
    s = advance(s, o, 'b700')
    assert s.last_full_raise == 400 and s.min_to == 1100
    with pytest.raises(ValueError): s.act('b', 1099)


def test_no_raise_cap_and_history_overflow():
    actions = ['b200', 'b300', 'b400', 'b500', 'b600', 'b700', 'b800', 'c', 'k']
    s, _ = prefix(actions)
    assert s.street == 1 and s.actor == 1
    obs, _ = observation(s)
    assert obs['action_info'][6, 1, 1] == 1  # flop check survives preflop overflow
    assert sum(obs['action_info'][:6, 3, 0]) == 6


def test_opening_allin_is_bet():
    s, _ = prefix(['c', 'k', 'b19900'])
    obs, table = observation(s)
    assert obs['action_info'][6, 1, 3] == 1
    assert obs['action_info'][6, 1, 4] == 0
    assert table == ['f', 'c', None, None, None, None, None, None, None]


@pytest.mark.parametrize('actions,initial', [
    (['b20000', 'c'], (20000, 20000)),
    (['b20000', 'f'], (20000, 20000)),
    (['b1000', 'b1500', 'c'], (1500, 20000)),
    (['c', 'k', 'b150', 'c'], (250, 20000)),
    (['c', 'k', 'b50', 'c'], (150, 20000)),
    (['b20000', 'c'], (1500, 20000)),
    (['c', 'k', 'k', 'k', 'k', 'k', 'k', 'k'], (20000, 20000)),
    (['f'], (20000, 20000)),
])
def test_terminal_oracle(actions, initial):
    s, _ = prefix(actions, initial)
    assert s.terminal and sum(s.payoffs()) == 0


@pytest.mark.parametrize('action', ['k', 'b199', 'b20001', 'b-5', 'b1.5', 'x'])
def test_illegal_fails(action):
    s = ChipState.new(range(52))
    with pytest.raises(ValueError): apply_incr(s, action)
    assert len(s.history) == 0 and s.pot == 150


def test_integer_and_deck_validation():
    s = ChipState.new(range(52))
    with pytest.raises(ValueError): s.act('b', 200.0)
    with pytest.raises(ValueError): ChipState.new([0]*52)
    with pytest.raises(ValueError): ChipState.new(range(52), (20000.0, 20000))
    with pytest.raises(ValueError): s.act('c', 50)


def test_mask_has_no_duplicate_actions():
    s, _ = prefix([])
    _, table = action_table(s)
    assert table == ['f', 'c', 'b200', None, 'b234', 'b250', 'b300', 'b400', 'b20000']
    assert len(set(x for x in table if x)) == sum(x is not None for x in table)


@pytest.mark.parametrize('actions', [[], ['c'], ['c','k'], ['b300','c','k'],
    ['c','k','b19900'], ['b200','b300','b400','b500','b600','b700','b800','c','k'],
    ['c','k','k','k','b100','c','k']])
def test_external_and_environment_parity(actions):
    s, _ = prefix(actions)
    text = ''
    street = 0
    for e in s.history:
        if e.street != street:
            text += '/'
            street = e.street
        text += e.kind + (str(e.amount) if e.kind == 'b' else '')
    ext = from_external(text, [card_to_str(c) for c in s.holes[s.actor]],
                        [card_to_str(c) for c in s.board], s.actor)
    obs, table = observation(s)
    external_obs, external_table = observation(ext)
    assert table == external_table
    for key in obs:
        np.testing.assert_array_equal(obs[key], external_obs[key])
    env = HUNLEnvironmentV6()
    env.reset_with_deck(s.deck)
    env.state = type(env.state)(s)
    env_obs = env._get_obs()
    for key in obs:
        np.testing.assert_array_equal(obs[key], env_obs[key])


def test_environment_strict_and_immutable():
    env = HUNLEnvironmentV6()
    env.reset_with_deck(range(52))
    before = env.state.core
    with pytest.raises(ValueError): env.step(3)
    with pytest.raises(ValueError): env.step(-1)
    with pytest.raises(ValueError): env.step(9)
    assert env.state.core == before
    _, _, done = env.step(1)
    assert not done and env.state.street == 0 and env.state.current_player == 0
    assert before.history == ()


def test_metadata_fails_closed():
    validate_metadata(METADATA)
    for key in METADATA:
        invalid = dict(METADATA)
        del invalid[key]
        with pytest.raises(ValueError): validate_metadata(invalid)
    with pytest.raises(ValueError): validate_metadata({'env_version': 'v55'})


@pytest.mark.parametrize('action', ['/', 'x', 'c//', 'b199', 'kk', 'f'])
def test_external_prefix_rejected(action):
    with pytest.raises(ValueError): from_external(action, ['As','Ah'], [], 1)
