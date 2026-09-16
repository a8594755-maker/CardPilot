import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('physical_budget_eval', Path(__file__).with_name('run_evaluation.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def archive(iteration, physical, reward=0):
    return dict(iteration=iteration, physical_hands=physical, prefix_complete=True, reward=reward)


def test_selection_uses_physical_budget_not_reward_or_marker_iteration():
    rows = [archive(32, 150000, 1000), archive(64, 310000, -1000),
            archive(96, 470000, 5000), archive(128, 620000, -5000)]
    chosen = runner.choose_archives(rows[::-1], archive(216, 1050000))
    assert chosen['early']['iteration'] == 64
    assert chosen['mid']['iteration'] == 128
    assert chosen['final']['iteration'] == 216


@pytest.mark.parametrize('rows,final', [
    ([archive(32, 150000)], archive(128, 1000000)),
    ([archive(32, 700000), archive(64, 600000)], archive(216, 1050000)),
    ([archive(32, 500000), archive(32, 600000)], archive(216, 1050000)),
    ([dict(archive(32, 600000), prefix_complete=False)], archive(216, 1050000)),
    ([archive(32, 200000)], archive(216, 1050000)),
])
def test_invalid_budget_evidence_is_rejected(rows, final):
    with pytest.raises(ValueError):
        runner.choose_archives(rows, final)


def cell(mode='sampled_both_sides', pairs=4):
    sampled = mode == 'sampled_both_sides'
    rows = []
    for index, (label, _, digest) in enumerate(runner.ANCHORS):
        rows.append(dict(anchor=label, anchor_sha256=digest, pairs=pairs, hands=2*pairs,
            action_rng={'schema': runner.ACTION_RNG_SCHEMA, 'seed': runner.SEED + index*1000003} if sampled else None,
            candidate_bb100=0,
            paired_outcomes={key: [0.] * pairs for key in
                             ['overall_bb_per_hand', 'bb_bb_per_hand', 'sb_bb_per_hand']}))
    return dict(seed=runner.SEED, pairs=pairs, starting_stack=200., policy_mode=mode,
                action_rng_schema=runner.ACTION_RNG_SCHEMA if sampled else None,
                candidate={'sha256': 'candidate'}, execution={'status': 'COMPLETED'}, anchors=rows)


@pytest.mark.parametrize('mode', ['sampled_both_sides', 'greedy_argmax_both_sides'])
def test_complete_cell_accounting(mode):
    assert runner.validate_cell(cell(mode), {'status': 'COMPLETED'}, 'candidate', mode, 4) == 24


@pytest.mark.parametrize('mutation', ['seed', 'candidate', 'anchor', 'raw_length', 'rng', 'nonfinite', 'score', 'seat'])
def test_cell_rejects_misaligned_or_incomplete_evidence(mutation):
    doc = copy.deepcopy(cell())
    row = doc['anchors'][0]
    if mutation == 'seed':
        doc['seed'] += 1
    elif mutation == 'candidate':
        doc['candidate']['sha256'] = 'changed'
    elif mutation == 'anchor':
        row['anchor_sha256'] = 'changed'
    elif mutation == 'raw_length':
        row['paired_outcomes']['overall_bb_per_hand'].pop()
    elif mutation == 'rng':
        row['action_rng']['seed'] += 1
    elif mutation == 'nonfinite':
        row['paired_outcomes']['overall_bb_per_hand'][0] = float('nan')
    elif mutation == 'score':
        row['candidate_bb100'] = 1
    elif mutation == 'seat':
        row['paired_outcomes']['bb_bb_per_hand'][0] = 1
    with pytest.raises(ValueError):
        runner.validate_cell(doc, {'status': 'COMPLETED'}, 'candidate', 'sampled_both_sides', 4)
