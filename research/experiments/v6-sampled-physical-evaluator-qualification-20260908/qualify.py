"""Deterministic categorical tests and two retained real-model fixtures."""
import hashlib
import json
from pathlib import Path
import random
import time

import numpy as np
import torch
import sampled_eval as ev
from alpha_holdem.v5_mirror_eval import init_model, read_checkpoint
from alpha_holdem.v6_elo_eval import _play_hand

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def main():
    assert not (BASE/'qualification.json').exists(), 'preserve existing qualification'
    started = time.perf_counter()
    torch.set_num_threads(1)
    values = np.zeros(9)
    mask = np.array([1,0,1,0,0,0,0,0,0])
    assert ev.legal_slot(values, mask, 0.0) == 0
    assert ev.legal_slot(values, mask, 0.499999) == 0
    assert ev.legal_slot(values, mask, 0.5) == 2
    assert ev.legal_slot(values, mask, np.nextafter(1.0,0.0)) == 2
    values[1] = np.nan
    assert ev.legal_slot(values, mask, 0.7) == 2
    for uniform in (-0.1, 1.0, float('nan')):
        try: ev.legal_slot(values, mask, uniform)
        except ValueError: pass
        else: raise AssertionError('invalid uniform accepted')
    for invalid in (np.zeros(9), np.full(9,np.nan), np.full(9,0.5)):
        try: ev.legal_slot(np.zeros(9), invalid, 0.5)
        except ValueError: pass
        else: raise AssertionError('invalid mask accepted')
    try: ev.legal_slot(np.full(9,np.inf), mask, 0.5)
    except ValueError: pass
    else: raise AssertionError('nonfinite legal logits accepted')
    keys = [ev.action_uniform(seed, pair, player, step)
            for seed in (1,2) for pair in range(10) for player in (0,1) for step in range(10)]
    assert len(set(keys)) == len(keys) and all(0 <= x < 1 for x in keys)
    assert ev.action_uniform(1,2,0,3) == ev.action_uniform(1,2,0,3)
    chosen = [ev.legal_slot(np.zeros(9), mask, ev.action_uniform(42,i,0,0)) for i in range(10000)]
    assert 0.47 < chosen.count(0)/10000 < 0.53
    manifest = json.loads((ROOT/'research/experiments/v6-independent-critic-two-seed-geometric-20260908/input_contract.json').read_text())
    rows = []
    hands = 0
    for seed in ('1','3'):
        path = Path(manifest['parents'][seed]['path'])
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        assert before == manifest['parents'][seed]['sha256']
        model = init_model(read_checkpoint(path), 'cpu').eval()
        for index in range(2):
            deck = list(range(52))
            random.Random(202609086000 + int(seed)*10 + index).shuffle(deck)
            # Four completed hands for old/new greedy parity.
            for seat in (0,1):
                old = _play_hand(model,model,deck,candidate_seat=seat,
                    candidate_observation_style='legacy_v4',anchor_observation_style='legacy_v4',device='cpu')
                new = ev.play_hand(model,model,deck,candidate_seat=seat,
                    action_seed=777,pair_index=index,mode='greedy')
                hands += 2
                assert old == new
            first = ev.pair_outcome(model,model,deck,action_seed=777,pair_index=index)
            second = ev.pair_outcome(model,model,deck,action_seed=777,pair_index=index)
            hands += 4
            assert first == second and first['candidate_pair_mean_bb'] == 0
            rows.append(dict(seed=seed, checkpoint_sha256=before, outcome=first))
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert hands == 32
    result = dict(passed=True,fixture_evaluation_hands=hands,unique_fixture_decks=4,
        wall_seconds=time.perf_counter()-started,rows=rows,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (BASE/'sampled_eval.py',BASE/'qualify.py',ROOT/'scripts/alpha_holdem/v6_elo_eval.py')},
        scope='Categorical/key guards and real-parent greedy parity, sampled reproducibility and self-match cancellation; not policy strength.')
    with (BASE/'qualification.json').open('x',encoding='utf-8') as handle: json.dump(result,handle,indent=2)
    print(json.dumps(dict(passed=True,fixture_evaluation_hands=hands)))


if __name__ == '__main__': main()
