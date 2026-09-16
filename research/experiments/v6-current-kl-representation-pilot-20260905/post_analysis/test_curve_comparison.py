import copy

import pytest

from curve_comparison import bucket_changes, independent_change


def row(point, se):
    return {'bb100': point, 'se_bb100': se, 'paired_decks': 8192}


def test_independent_variances_add_not_intervals_subtracted():
    result = independent_change(row(-20., 3.), row(-5., 4.))
    assert result['bb100'] == 15.
    assert result['se_bb100'] == 5.
    assert result['ci95'] == pytest.approx([5.2, 24.8])
    assert result['earlier_paired_decks'] == result['later_paired_decks'] == 8192


def test_no_change_does_not_remove_uncertainty():
    result = independent_change(row(2., 1.), row(2., 1.))
    assert result['bb100'] == 0
    assert result['se_bb100'] == pytest.approx(2**.5)


@pytest.mark.parametrize('key,value', [('bb100', float('nan')), ('se_bb100', float('inf')),
                                     ('se_bb100', -1.), ('paired_decks', 1)])
def test_invalid_statistics_rejected(key, value):
    bad = row(0., 1.)
    bad[key] = value
    with pytest.raises(ValueError, match='invalid stage'):
        independent_change(bad, row(1., 1.))


def test_bucket_identity_and_inputs_preserved():
    early = {'pooled': row(0., 1.), 'by_anchor': {'a': row(-2., 3.)}, 'by_seat': {'0': row(1., 1.)}}
    late = copy.deepcopy(early)
    late['by_anchor']['a']['bb100'] = 4.
    saved = copy.deepcopy((early, late))
    assert bucket_changes(early, late)['by_anchor']['a']['bb100'] == 6.
    assert (early, late) == saved
    late['by_anchor']['b'] = late['by_anchor'].pop('a')
    with pytest.raises(ValueError, match='bucket mismatch'):
        bucket_changes(early, late)
