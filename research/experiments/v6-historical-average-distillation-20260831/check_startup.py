"""Read-only CPU check of an immutable64-hand prefix while collection continues."""
import hashlib
import itertools
import json
from pathlib import Path
import sys

import numpy as np
import torch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BASE/'execution_code/source_files/scripts'))
from research.experiment_log import atomic_json
from alpha_holdem.execution_v6 import load_policy, decide, sha256_file
from alpha_holdem.policy_contract_v6 import observation, apply_incr
from alpha_holdem.rules_v6 import ChipState
from temporal_average import hand_spec, uniform_for, observation_digest, canonical, select


def prefix():
    with (BASE/'training_hands.jsonl').open('rb') as handle:
        lines = list(itertools.islice(handle, 64))
    assert len(lines) == 64 and all(line.endswith(b'\n') for line in lines)
    return b''.join(lines)


def main():
    if sys.argv[1:] or (BASE/'startup_review.json').exists():
        raise ValueError('Do not repeat startup review')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    captured = BASE/'execution_code/source_files'/BASE.relative_to(ROOT)/'temporal_average.py'
    assert sha256_file(captured) == sha256_file(BASE/'temporal_average.py')
    inputs = json.loads((BASE/'input_manifest.json').read_text())
    models = [load_policy(row['path'], 'cpu')[0] for row in inputs['teachers']]
    data = prefix()
    previous, calls, maximum, mismatches = '0'*64, 0, 0., 0
    for index, line in enumerate(data.splitlines()):
        row = json.loads(line)
        digest = row.pop('sha256')
        assert hashlib.sha256(canonical(row).encode()).hexdigest() == digest
        assert row['previous_sha256'] == previous
        previous = digest
        deck, teachers = hand_spec(2026101001, index, 17)
        assert row['index'] == index and row['deck'] == deck and row['teachers'] == teachers
        state, counts = ChipState.new(deck), [0, 0]
        for event in row['events']:
            seat = state.actor
            obs, table = observation(state)
            assert event['teacher'] == teachers[seat] and event['seat'] == seat
            assert observation_digest(obs) == event['observation_sha256']
            uniform = uniform_for(2026101001, index, seat, counts[seat])
            assert event['uniform'] == uniform
            _, info = decide(models[teachers[seat]], state, uniform=uniform)
            error = float(np.abs(np.asarray(event['probabilities'])-info['behavior_probs']).max())
            assert error <= 2e-5
            maximum = max(maximum, error)
            mismatches += int(info['selected_action_slot'] != event['action'])
            action = select(event['probabilities'], uniform)
            assert action == event['action'] and table[action] == event['increment']
            state = apply_incr(state, event['increment'])
            counts[seat] += 1
            calls += 1
        assert state.terminal and list(state.payoffs()) == row['payoffs']
    assert prefix() == data
    for row in inputs['teachers']:
        assert sha256_file(row['path']) == row['sha256']
    report = dict(status='PASS', preserved_prefix_hands=64, new_unique_hands=0, model_queries=calls,
        cpu_scalar_max_probability_difference=maximum, cpu_scalar_selected_action_disagreements=mismatches,
        raw_prefix_sha256=hashlib.sha256(data).hexdigest(), terminal_and_teacher_identity_checks='PASS',
        collector_modified=False, frozen_models_modified=False)
    atomic_json(BASE/'startup_review.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
