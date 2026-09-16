"""Production entry-point wiring; no optimization and no external network."""
import inspect
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import numpy as np
import pytest
import torch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'scripts/alpha_holdem'))  # match train_v5.py CLI sibling imports
from alpha_holdem import train_v5 as trainer
from alpha_holdem import environment_v6 as environment
from alpha_holdem import execution_v6 as execution
from alpha_holdem.policy_contract_v6 import METADATA, training_metadata, validate_resume, apply_incr, observation
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_mirror_eval import play_pair
from alpha_holdem.play_slumbot_v6 import play_one
from deep_cfr.hand_eval import card_to_str


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs): raise AssertionError('No network allowed')
    monkeypatch.setattr('socket.socket.connect', denied)
    monkeypatch.setattr('socket.create_connection', denied)


def args(**overrides):
    return SimpleNamespace(**(dict(env_version='v6', starting_stack=200, resume=None,
        allow_resume=False, reset_optimizer=False, reset_hand_counter=False,
        hero_preflop_strategy='model', v6_rebind_legacy_weights=False) | overrides))


def test_metadata_roundtrip_and_explicit_rebinding():
    checkpoint = training_metadata(args())
    validate_resume(args(resume='v6.pt'), checkpoint)
    with pytest.raises(ValueError): validate_resume(args(resume='old.pt'), {'env_version':'v55'})
    with pytest.raises(ValueError): validate_resume(args(env_version='v55'), checkpoint)
    rebind = args(resume='old.pt', allow_resume=True, reset_optimizer=True,
                  reset_hand_counter=True, v6_rebind_legacy_weights=True)
    validate_resume(rebind, {'env_version':'v55'})
    assert training_metadata(rebind)['legacy_weights_rebound_to_new_contract']
    for key in ['resume', 'allow_resume', 'reset_optimizer', 'reset_hand_counter']:
        invalid = SimpleNamespace(**(vars(rebind) | {key: False}))
        with pytest.raises(ValueError): training_metadata(invalid)
    with pytest.raises(ValueError): training_metadata(args(starting_stack=100))
    with pytest.raises(ValueError): training_metadata(args(hero_preflop_strategy='heuristic'))
    with pytest.raises(ValueError): training_metadata(args(pool_strategy='elo-kbest'))
    with pytest.raises(ValueError): training_metadata(args(action_q_counterfactual_dataset='legacy.npz'))
    with pytest.raises(ValueError): training_metadata(SimpleNamespace(**(vars(rebind) | {'ppo_replay_buffer_iterations': 4})))


@pytest.mark.parametrize('worker', [trainer.worker_process_v5, trainer.worker_process_v5_multi])
def test_real_worker_selects_v6(monkeypatch, worker):
    class Chosen(Exception): pass
    class Memory:
        def __init__(self, **kw): self.buf = bytearray(max(trainer.OBS_SIZE, trainer.RESULT_SIZE)*4*4)
    def constructor(**kw):
        assert kw == {'starting_stack': 200}
        raise Chosen()
    monkeypatch.setattr('multiprocessing.shared_memory.SharedMemory', Memory)
    monkeypatch.setattr(environment, 'HUNLEnvironment', constructor)
    arguments = {key: None for key, parameter in inspect.signature(worker).parameters.items()
                 if parameter.default is inspect.Parameter.empty}
    arguments.update(worker_id=0, starting_stack=200, env_version='v6')
    if 'envs_per_worker' in arguments: arguments['envs_per_worker'] = 2
    with pytest.raises(Chosen): worker(**arguments)


def test_real_trainer_fixed_deal_and_mirror_reset():
    env = environment.HUNLEnvironmentV6()
    obs = trainer.exp003_reset_env_with_deck(env, list(range(52)))
    assert env.state.core.holes == ((0,1),(2,3))
    mirror = trainer.exp003_mirrored_deck_from_env(env)
    mirrored_obs = trainer.exp003_reset_env_with_deck(env, mirror)
    assert env.state.core.holes == ((2,3),(0,1))
    np.testing.assert_array_equal(obs['legal_mask'], mirrored_obs['legal_mask'])
    env.step(1)
    assert env.state.current_player == 0 and env.state.street == 0


class FixedModel(torch.nn.Module):
    def forward(self, cards, actions, extra, mask):
        logits = torch.arange(9, dtype=torch.float32).expand(len(cards), 9)*.1
        return logits.masked_fill(mask == 0, -1e9), torch.zeros((len(cards),1))


def test_mirror_selfmatch_exact_cancel():
    model = FixedModel()
    result = play_pair(model, model, list(range(52)), 20260915, 0)
    assert sum(result['rewards_bb']) == 0


@pytest.mark.parametrize('seat', [0, 1])
def test_real_deployment_loop_against_offline_rules_server(seat):
    model = FixedModel()
    server = SimpleNamespace(state=ChipState.new(range(52)), text='')
    def move(incr):
        old = server.state.street
        server.state = apply_incr(server.state, incr)
        server.text += incr
        if server.state.street > old and not server.state.terminal: server.text += '/'
    def response():
        while not server.state.terminal and server.state.actor != seat:
            move('c' if server.state.to_call else 'k')
        s = server.state
        result = dict(token='offline-session-fixture', action=server.text, client_pos=seat,
                      hole_cards=[card_to_str(c) for c in s.holes[seat]],
                      board=[card_to_str(c) for c in s.board])
        if s.terminal: result['winnings'] = s.payoffs()[seat]
        return result
    def new_hand(token):
        assert token is None
        return response()
    def act(token, incr):
        assert token == 'offline-session-fixture'
        move(incr)
        return response()
    _, record = play_one(model, None, random.Random(20260915+seat), new_hand_fn=new_hand, act_fn=act)
    assert record['winnings_chips'] == server.state.payoffs()[seat]
    assert record['strict_policy_execution'] and record['decisions']
    assert 'token' not in record['terminal_response']
    for row in record['decisions']:
        incr, replay = execution.external_decision(model, row, uniform=row['uniform'])
        assert incr == row['direct_increment'] and replay['behavior_probs'] == row['behavior_probs']


def test_real_frozen_loader_and_forward_contract(monkeypatch):
    path = ROOT/'models/baseline/standard10/latest.pt'
    source = torch.load(path, map_location='cpu', weights_only=False)
    before = execution.sha256_file(path)
    # Test-only explicit rebinding IN MEMORY, not a new deployed artifact or
    # same-policy claim. Real source checkpoint remains byte-identical.
    rebound = dict(source, **METADATA)
    monkeypatch.setattr(torch, 'load', lambda *a, **kw: rebound)
    model, checkpoint, digest = execution.load_policy(path)
    assert digest == before
    s = ChipState.new(range(52))
    response = dict(action='', hole_cards=[card_to_str(c) for c in s.holes[1]], board=[], client_pos=1)
    incr, native = execution.decide(model, s, uniform=.345)
    external_incr, external = execution.external_decision(model, response, uniform=.345)
    assert incr == external_incr and native == external
    assert execution.sha256_file(path) == before
    monkeypatch.setattr(torch, 'load', lambda *a, **kw: source)
    with pytest.raises(ValueError): execution.load_policy(path)


def test_bad_logits_fail_closed():
    class Bad(FixedModel):
        def forward(self, *values): return torch.full((1,9), float('nan')), None
    with pytest.raises(ValueError): execution.decide(Bad(), ChipState.new(range(52)), uniform=.1)
