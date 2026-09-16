"""Offline child crash boundary: terminate only this new fixture process."""
import os
from pathlib import Path
import sys
import socket

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from alpha_holdem.play_slumbot_v6_journaled import run_session
from alpha_holdem.execution_v6 import sha256_file
from offline_fixture import ToyPolicy


if __name__ == '__main__':
    model_path, out_dir = sys.argv[1:]
    def boundary(token): os._exit(17)
    def deny_network(*args, **kwargs): raise AssertionError('No network in crash fixture')
    socket.socket.connect = deny_network
    socket.create_connection = deny_network
    run_session(ToyPolicy().eval(), model_path, sha256_file(model_path), hands=2, seed=1001,
                session_id='crash_boundary', out_dir=out_dir, new_hand_fn=boundary,
                command=[sys.executable, *sys.argv])
