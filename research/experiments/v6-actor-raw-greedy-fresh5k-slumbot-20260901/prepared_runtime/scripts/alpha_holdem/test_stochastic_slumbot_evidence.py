"""Synthetic evidence tests: no network calls and no actual poker hands."""
import copy
import hashlib
import json
from pathlib import Path
import random
import math
import statistics
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.alpha_holdem import audit_slumbot_hand_evidence as evidence
from scripts.alpha_holdem import audit_slumbot_session_independence as independence
from scripts.alpha_holdem import slumbot_ci_from_hands as ci

DECK = [rank+suit for rank in '23456789TJQKA' for suit in 'cdhs']


def dump_rows(n, seed, variant=0):
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        pos = i % 2
        row = dict(hand_idx=i, move_idx=0, client_pos=pos, hero_hole=rng.sample(DECK, 2),
            opp_hole=None, board=[], action_move='f' if not variant else 'c', action_amount=0,
            winnings_hero=(50 if pos == 0 else -50)+variant,
            who='opp' if pos == 0 else 'hero', hand_policy_execution_clean=True,
            hand_policy_execution_issues=[])
        if pos == 1:
            row.update(policy_mode='sample', policy_temperature=1., policy_action_slot=0,
                policy_legal_mask=[1]*9, policy_behavior_probs=[1/9]*9,
                policy_behavior_action_probability=1/9)
        rows.append(row)
    return rows


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    return path


def fixture(tmp_path, n=100):
    checkpoint = tmp_path / 'synthetic_not_a_poker_model.pt'
    checkpoint.write_bytes(b'synthetic audit input; not a real checkpoint')
    policy = dict(checkpoint=str(checkpoint), sha256=evidence.sha(checkpoint), strategy='model',
                  policy_mode='sample', temperature=1., starting_stack_bb=200, obs_version='v4')
    specs = []
    for index in range(2):
        rows = dump_rows(n, 2026090100+index)
        raw, cumulative = [], 0
        for i, row in enumerate(rows, 1):
            chips = row['winnings_hero']
            cumulative += chips
            raw.append(dict(attempted_hand=i, successful_hand=i, winnings_chips=chips,
                winnings_bb=chips/100, cumulative_chips=cumulative, cumulative_bb=cumulative/100,
                policy_seed=100+index, model_sha256=policy['sha256'], policy_mode='sample', policy_temperature=1.))
        prefix = tmp_path / f'part{index}'
        raw_path = write_rows(prefix.with_suffix('.hands.jsonl'), raw)
        dump_path = write_rows(prefix.with_suffix('.dump.jsonl'), rows)
        result = dict(requested_hands=n, successful_hands=n, model_sha256=policy['sha256'],
            strategy='model', obs_version='v4', policy_mode_raw='sample', policy_seed=100+index,
            temperature=1., starting_stack_bb=200, total_chips=cumulative, bb_per_100=cumulative/n)
        rewards = [row['winnings_bb'] for row in raw]
        std = statistics.stdev(rewards) if n > 1 else 0.
        mean, half_width = statistics.mean(rewards), 1.96*std/math.sqrt(n)
        result.update(avg_bb_per_hand=mean, std_bb_per_hand=std, ci95_bb_per_hand=half_width,
                      ci95_bb_per_100=half_width*100, lower_bound_bb_per_100=(mean-half_width)*100,
                      upper_bound_bb_per_100=(mean+half_width)*100)
        result_path = prefix.with_suffix('.result.json')
        result_path.write_text(json.dumps(result))
        specs.append(dict(id=f'part{index}', policy_seed=100+index, requested_hands=n,
                          raw_hands=str(raw_path), dump=str(dump_path), result=str(result_path)))
    manifest = dict(schema='cardpilot.slumbot_frozen_evidence_manifest.v1', policy=policy, sessions=specs)
    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path, manifest


def test_valid_strict_manifest_and_cli(tmp_path):
    path, _ = fixture(tmp_path)
    result = evidence.audit_manifest(path)
    assert result['status'] == 'PASS' and result['summary']['hands'] == 200
    assert result['summary']['bb_per_100'] == 0
    output = tmp_path / 'audit.json'
    process = subprocess.run([sys.executable, str(Path(evidence.__file__)), '--manifest', str(path),
                              '--out-json', str(output)], capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert json.loads(output.read_text())['summary'] == result['summary']


def test_stochastic_same_deals_different_actions_is_rejected(tmp_path):
    first, changed = dump_rows(100, 42), dump_rows(100, 42, variant=1)
    assert independence.fingerprint([first[0]]) != independence.fingerprint([changed[0]])
    assert independence.initial_deal_fingerprint([first[0]]) == independence.initial_deal_fingerprint([changed[0]])
    paths = [write_rows(tmp_path/'a_dump.jsonl', first), write_rows(tmp_path/'b_dump.jsonl', changed)]
    result = independence.audit_paths(paths)
    assert result['status'] == 'FAIL'
    assert result['pairwise'][0]['same_index_exact_fingerprint_matches'] == 0
    assert result['pairwise'][0]['same_index_initial_deal_matches'] == 100


def test_shifted_five_deal_replay_rejected(tmp_path):
    first = dump_rows(100, 55)
    shifted = copy.deepcopy(first[10:])
    for i, row in enumerate(shifted):
        row['hand_idx'] = i
        row['winnings_hero'] += 1
        row['action_move'] = 'c'
    result = independence.audit_paths([write_rows(tmp_path/'a_dump.jsonl', first),
                                       write_rows(tmp_path/'b_dump.jsonl', shifted)])
    assert result['status'] == 'FAIL'
    assert result['pairwise'][0]['shared_five_hand_initial_deal_windows_at_any_offset'] > 0


def test_fixed_seed_100k_independent_deal_streams(tmp_path):
    paths = [write_rows(tmp_path/f'part{i}_dump.jsonl', dump_rows(12500, 2026090200+i)) for i in range(8)]
    result = independence.audit_paths(paths)
    assert result['status'] == 'PASS', result['checks']
    assert sum(row['hands_observed'] for row in result['sessions'].values()) == 100000


def test_malformed_final_dump_and_duplicate_paths_rejected(tmp_path):
    a = write_rows(tmp_path/'a_dump.jsonl', dump_rows(100, 1))
    b = write_rows(tmp_path/'b_dump.jsonl', dump_rows(100, 2))
    with a.open('a') as stream:
        stream.write('{"partial":')
    assert independence.audit_paths([a, b])['status'] == 'FAIL'
    with pytest.raises(ValueError):
        independence.audit_paths([a, a])


@pytest.mark.parametrize('cards', [[], ['Ah'], ['Ah', 'Ah'], ['xx', 'Kh']])
def test_invalid_initial_cards_rejected(cards):
    row = dump_rows(1, 5)[0]
    row['hero_hole'] = cards
    with pytest.raises(ValueError):
        independence.initial_deal_fingerprint([row])


def test_initial_identity_ignores_visible_outcome_but_not_hero_cards():
    row = dump_rows(1, 5)[0]
    changed = copy.deepcopy(row)
    changed.update(board=['As', 'Ks', 'Qs'], opp_hole=['2s', '3s'], winnings_hero=999, action_move='b')
    assert independence.initial_deal_fingerprint([row]) == independence.initial_deal_fingerprint([changed])
    changed['hero_hole'] = ['Ah', 'Kh']
    with pytest.raises(ValueError):
        independence.initial_deal_fingerprint([row, changed])


@pytest.mark.parametrize('kind', ['duplicate_raw', 'missing_raw', 'failed_attempt', 'nan', 'bounds',
    'chips_bb', 'cumulative', 'duplicate_dump', 'missing_dump', 'dump_reward', 'fallback',
    'missing_telemetry', 'mode', 'temperature', 'illegal_slot', 'nonfinite_probs', 'prob_sum',
    'selected_probability', 'result_count', 'result_hash', 'result_seed', 'overlapping_paths',
    'changed_checkpoint', 'truncated_raw', 'raw_seed', 'raw_model', 'result_ci'])
def test_invalid_strict_evidence_rejected(tmp_path, kind):
    path, manifest = fixture(tmp_path)
    spec = manifest['sessions'][0]
    raw_path, dump_path, result_path = [Path(spec[k]) for k in ['raw_hands', 'dump', 'result']]
    raw, dump, result = evidence.jsonl(raw_path), evidence.jsonl(dump_path), json.loads(result_path.read_text())
    if kind == 'duplicate_raw': raw[1] = copy.deepcopy(raw[0])
    elif kind == 'missing_raw': raw.pop()
    elif kind == 'failed_attempt': raw[1]['attempted_hand'] += 1
    elif kind == 'nan': raw[0]['winnings_bb'] = float('nan')
    elif kind == 'bounds': raw[0]['winnings_chips'] = 20001
    elif kind == 'chips_bb': raw[0]['winnings_bb'] += 1
    elif kind == 'cumulative': raw[-1]['cumulative_chips'] += 1
    elif kind == 'duplicate_dump': dump.insert(1, copy.deepcopy(dump[0]))
    elif kind == 'missing_dump': dump.pop()
    elif kind == 'dump_reward': dump[0]['winnings_hero'] += 1
    elif kind == 'fallback': dump[0]['hand_policy_execution_clean'] = False
    elif kind == 'missing_telemetry': del dump[0]['hand_policy_execution_clean']
    elif kind == 'mode': dump[1]['policy_mode'] = 'guarded'
    elif kind == 'temperature': dump[1]['policy_temperature'] = .9
    elif kind == 'illegal_slot': dump[1]['policy_legal_mask'][0] = 0
    elif kind == 'nonfinite_probs': dump[1]['policy_behavior_probs'][0] = float('inf')
    elif kind == 'prob_sum': dump[1]['policy_behavior_probs'] = [.01]*9
    elif kind == 'selected_probability': dump[1]['policy_behavior_action_probability'] = .8
    elif kind == 'result_count': result['successful_hands'] -= 1
    elif kind == 'result_hash': result['model_sha256'] = 'other'
    elif kind == 'result_seed': result['policy_seed'] += 1
    elif kind == 'overlapping_paths': manifest['sessions'][1]['raw_hands'] = spec['raw_hands']
    elif kind == 'changed_checkpoint': Path(manifest['policy']['checkpoint']).write_bytes(b'changed')
    elif kind == 'raw_seed': raw[0]['policy_seed'] += 1
    elif kind == 'raw_model': raw[0]['model_sha256'] = 'other'
    elif kind == 'result_ci': result['ci95_bb_per_100'] += 1
    write_rows(raw_path, raw)
    if kind == 'truncated_raw': raw_path.write_text(raw_path.read_text().rstrip('\n'))
    write_rows(dump_path, dump)
    result_path.write_text(json.dumps(result))
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        evidence.audit_manifest(path)


def test_ci_rejects_overlapping_paths_and_invalid_values(tmp_path):
    path = write_rows(tmp_path/'hands.jsonl', [dict(winnings_bb=.5, winnings_chips=50)])
    assert ci.load_rewards([path]) == [.5]
    with pytest.raises(ValueError): ci.expand_inputs([str(path), str(tmp_path/'*.jsonl')])
    with pytest.raises(ValueError): ci.load_rewards([path, path])
    for value in [float('nan'), float('inf'), 200.01]:
        write_rows(path, [dict(winnings_bb=value)])
        with pytest.raises(ValueError): ci.load_rewards([path])
        with pytest.raises(ValueError): ci.summarize([value], 11.1, 2., -11.4275, 20000)
    write_rows(path, [dict(winnings_bb=1, winnings_chips=50)])
    with pytest.raises(ValueError): ci.load_rewards([path])
