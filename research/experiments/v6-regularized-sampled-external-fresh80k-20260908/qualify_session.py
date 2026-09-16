"""Offline full journal integration with actual exports and a local rules server."""
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import protocol as p
sys.path.insert(0, str(p.ROOT / 'scripts'))
import audit_sampled as audit
from alpha_holdem.legacy_observation_bridge_v6 import load_policy, external_decision, card_string
from alpha_holdem.play_slumbot_v6_journaled import run_session
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.policy_contract_v6 import apply_incr
import torch


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


class LocalServer:
    def __init__(self, arm):
        self.arm, self.count, self.total = arm, 0, 0
        self.token = 'offline_fixture_' + arm
        self.deck_keys = []
        self.streets = set()

    def step(self, action):
        old = self.state.street
        self.state = apply_incr(self.state, action)
        self.history += action
        if not self.state.terminal and self.state.street != old:
            self.history += '/'

    def respond(self):
        while not self.state.terminal and self.state.actor != self.seat:
            self.step('c' if self.state.to_call else 'k')
        s = self.state
        row = dict(token=self.token, action=self.history, client_pos=self.seat,
                   hole_cards=[card_string(c) for c in s.holes[self.seat]],
                   board=[card_string(c) for c in s.board])
        if s.terminal:
            win = s.payoffs()[self.seat]
            self.total += win
            row.update(winnings=win, session_num_hands=self.count, session_total=self.total,
                       bot_hole_cards=[card_string(c) for c in s.holes[1-self.seat]])
        else:
            self.streets.add(s.street)
        return row

    def new_hand(self, token):
        assert token == (None if self.count == 0 else self.token)
        self.count += 1
        deck = list(range(52))
        random.Random(f'{BASE.name}/offline-v2/{self.arm}/{self.count}').shuffle(deck)
        self.deck_keys.append(hashlib.sha256(bytes(deck)).hexdigest())
        self.state, self.seat, self.history = ChipState.new(deck), self.count % 2, ''
        return self.respond()

    def act(self, token, increment):
        assert token == self.token
        self.step(increment)
        return self.respond()


def main():
    started = time.monotonic()
    out = BASE / 'offline_sessions_v2'
    out.mkdir(exist_ok=False)
    torch.set_num_threads(1)
    reports = []
    for i, arm in enumerate(p.ARMS):
        model_path = p.EXPORTS / (arm + '.pt')
        assert sha(model_path) == p.MODEL_HASHES[arm]
        model = load_policy(model_path, 'cpu')
        server = LocalServer(arm)
        directory = out / arm
        run_session(model, model_path, model.sha256, hands=16, seed=901230+i,
            session_id='offline_regularized_sampled_' + arm, out_dir=directory,
            new_hand_fn=server.new_hand, act_fn=server.act, policy_mode='sample',
            command=[sys.executable, '-B', str(Path(__file__).resolve())],
            decision_fn=external_decision, execution_metadata=dict(observation_bridge_contract=p.BRIDGE, model_obs_version='v4'))
        result = audit.original.audit_session(directory, model=model, expected_model_sha256=model.sha256,
            decision_fn=external_decision, expected_observation_bridge=p.BRIDGE)
        assert result['status'] == 'PASS' and result['successful_hands'] == 16
        for line in (directory / 'hands.jsonl').read_text().splitlines():
            for d in json.loads(line)['decisions']:
                p.validate_decision(d)
        reports.append(dict(arm=arm, audit=result, deck_keys=server.deck_keys,
                            observed_streets=sorted(server.streets),
                            files={str(f):sha(f) for f in directory.glob('*') if f.is_file()}))
    report = dict(passed=True, reports=reports, network_requests=0, training_hands=0,
        fixture_hands=64, external_hands=0, wall_seconds=time.monotonic()-started,
        exact_command=subprocess.list2cmdline([sys.executable, '-B', str(Path(__file__).resolve())]),
        source_hashes={str(f):sha(f) for f in BASE.glob('*.py')})
    with (BASE / 'session_qualification.json').open('x') as f:
        json.dump(report, f, indent=2)
    print(json.dumps(dict(passed=True, fixture_hands=64, network_requests=0,
                         decision_replays=sum(r['audit']['decision_replays'] for r in reports))))


if __name__ == '__main__':
    main()
