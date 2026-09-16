import gzip
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('scope_post_review', Path(__file__).with_name('review.py'))
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def test_pair_statistics_are_in_big_blinds_per_hundred():
    result = review.stats([-1., 0., 1.])
    assert result['bb100'] == 0
    assert result['se_bb100'] == pytest.approx(100 / 3**.5)
    assert result['ci95'][1] == pytest.approx(1.96 * 100 / 3**.5)


@pytest.mark.parametrize('values', [[], [1.], [1., float('nan')], [1., float('inf')]])
def test_insufficient_nonfinite_samples_rejected(values):
    with pytest.raises(ValueError):
        review.stats(values)


def row():
    return {'anchor': 'standard10', 'anchor_seed': 1, 'pair_index': 0, 'deck': list(range(52)),
            'control_rewards_bb': [1., -1.], 'treatment_rewards_bb': [2., 3.],
            'control_pair_mean_bb': 0., 'treatment_pair_mean_bb': 2.5,
            'treatment_minus_control_rewards_bb': [1., 4.], 'treatment_minus_control_pair_mean_bb': 2.5}


@pytest.mark.parametrize('problem', ['duplicate', 'bad_deck', 'bad_reward', 'bad_mean', 'bad_seat'])
def test_raw_corruption_is_rejected_before_summary(tmp_path, problem):
    sample = row()
    if problem == 'bad_deck':
        sample['deck'][0] = 1
    elif problem == 'bad_reward':
        sample['treatment_rewards_bb'][1] = 201
    elif problem == 'bad_mean':
        sample['treatment_pair_mean_bb'] = 1
    elif problem == 'bad_seat':
        sample['treatment_minus_control_rewards_bb'] = [1., 3.]
    path = tmp_path / 'fixture.jsonl.gz'
    with gzip.open(path, 'wt') as handle:
        handle.write(json.dumps(sample) + '\n')
        if problem == 'duplicate':
            handle.write(json.dumps(sample) + '\n')
    with pytest.raises(ValueError):
        review.raw_map(path)


def test_common_deck_seats_are_averaged_before_interval():
    rows = [(anchor, pair) for anchor in ('a', 'b', 'c', 'd') for pair in ([1., -1.], [2., -2.])]
    result = review.buckets(rows)
    assert result['pooled']['ci95'] == [0., 0.]
    assert result['pooled']['paired_decks'] == 8
    assert result['by_seat']['0']['bb100'] == 150
    assert result['by_seat']['1']['bb100'] == -150


def test_reported_summary_disagreement_rejected():
    computed = review.buckets([(anchor, pair) for anchor in ('a', 'b', 'c', 'd') for pair in ([1., -1.], [2., -2.])])
    def convert(value):
        return {'bb100': value['bb100'], 'ci95_low_bb100': value['ci95'][0], 'ci95_high_bb100': value['ci95'][1]}
    reported = {'pooled': convert(computed['pooled']),
                'by_anchor': {k: convert(v) for k, v in computed['by_anchor'].items()},
                'by_seat': {k: convert(v) for k, v in computed['by_seat'].items()}}
    review.check_reported(computed, reported)
    reported['by_seat']['1']['bb100'] += 1
    with pytest.raises(ValueError):
        review.check_reported(computed, reported)


def test_realized_PPO_dose_is_not_inferred_from_physical_hands():
    rows = [{'iteration': i, 'entropy': .5, 'approx_kl': .01, 'reference_policy_kl': .02} for i in (5, 6)]
    result = review.training_health(rows, '[ 5] ep=1/2 klstop=1\n[ 6] ep=2/2 klstop=0\n', 4, 6)
    assert result['kl_early_stop_iterations'] == 1
    assert result['reported_epoch_counts'] == {'1': 1, '2': 1}
    assert result['epoch_counts_are_not_optimizer_step_counts']
    with pytest.raises(ValueError):
        review.training_health(rows, '[ 5] ep=1/2 klstop=1\n', 4, 6)
    with pytest.raises(ValueError):
        review.training_health(rows, '[ 5] ep=1/3 klstop=1\n[ 6] ep=2/3 klstop=0\n', 4, 6)
