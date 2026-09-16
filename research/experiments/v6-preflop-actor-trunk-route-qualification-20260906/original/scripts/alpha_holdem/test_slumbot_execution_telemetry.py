"""No-network real client tests for seed and fallback evidence semantics."""
import io
import json
from pathlib import Path
import random
import sys

import numpy as np
import pytest
import requests
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from alpha_holdem import play_slumbot as play


def decision(*args, **kwargs):
    assert kwargs['policy_mode'] == 'sample'
    return 0, dict(policy_mode='sample', temperature=1., preflop_epsilon=.3,
        legal_mask=[1]*9, behavior_probs=[1.]+[0.]*8, behavior_action_probability=1.,
        greedy_action_slot=0)


@pytest.mark.parametrize('http_fallback', [False, True])
def test_real_play_hand_records_clean_or_http_fallback(monkeypatch, http_fallback):
    initial = dict(token='synthetic-token-never-logged', action='b200', client_pos=0,
                   hole_cards=['Ac', 'Ad'], board=[])
    terminal = dict(initial, action='b200f', winnings=-100)
    monkeypatch.setattr(play, 'new_hand', lambda token: initial)
    monkeypatch.setattr(play, 'decide_action', decision)
    calls = []
    def act(token, incr):
        calls.append(incr)
        if http_fallback and len(calls) == 1:
            raise requests.HTTPError('synthetic failure')
        return terminal
    monkeypatch.setattr(play, 'act', act)
    output = io.StringIO()
    _, winnings = play.play_hand(None, None, 'cpu', policy_mode='sample', dump_fp=output)
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert winnings == -100 and calls == (['f', 'f'] if http_fallback else ['f'])
    assert rows and all(row['hand_policy_execution_clean'] is (not http_fallback) for row in rows)
    assert rows[-1]['policy_mode'] == 'sample' and rows[-1]['policy_action_slot'] == 0
    assert rows[-1]['hand_policy_execution_issues'] == (['http_action_fallback'] if http_fallback else [])
    assert 'synthetic-token' not in output.getvalue()


def test_real_out_of_turn_fallback_is_marked(monkeypatch):
    initial = dict(token='synthetic', action='', client_pos=0, hole_cards=['Ac', 'Ad'], board=[])
    monkeypatch.setattr(play, 'new_hand', lambda token: initial)
    monkeypatch.setattr(play, 'act', lambda token, incr: dict(initial, action='f', winnings=50))
    monkeypatch.setattr(play, 'decide_action', lambda *a, **k: pytest.fail('No legal client decision expected'))
    output = io.StringIO()
    play.play_hand(None, None, 'cpu', policy_mode='sample', dump_fp=output)
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert rows and rows[0]['hand_policy_execution_clean'] is False
    assert rows[0]['hand_policy_execution_issues'] == ['out_of_turn_fallback']


def test_same_explicit_seed_reproduces_all_action_rngs():
    def draw():
        return random.random(), float(np.random.random()), float(torch.rand(()))
    play.configure_policy_rng(2026090301)
    first = draw()
    play.configure_policy_rng(2026090301)
    assert draw() == first
    play.configure_policy_rng(2026090302)
    assert draw() != first


def test_no_seed_leaves_default_rng_state_unchanged():
    before = random.getstate(), np.random.get_state(), torch.get_rng_state().clone()
    play.configure_policy_rng(None)
    assert random.getstate() == before[0]
    after = np.random.get_state()
    assert after[0] == before[1][0] and np.array_equal(after[1], before[1][1]) and after[2:] == before[1][2:]
    assert torch.equal(torch.get_rng_state(), before[2])


@pytest.mark.parametrize('seed', [-1, 2**63, True])
def test_invalid_seed_rejected(seed):
    with pytest.raises(ValueError):
        play.configure_policy_rng(seed)
