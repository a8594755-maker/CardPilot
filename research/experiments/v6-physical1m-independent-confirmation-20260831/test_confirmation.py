import copy
import math
import pytest
import confirmation_contract as c


def passing():
    return [dict(anchor=a, bb_per_100=10., ci_adjusted=[1., 19.]) for a in range(5)], dict(bb_per_100=5., ci_adjusted=[1., 9.])


def test_fixed_budget():
    assert c.HANDS == 196608 and len(set(c.CELLS)) == 12
    assert c.SEED == 20261002 and c.PAIRS == 8192
    assert ('mid262', 0) not in c.CELLS


def test_expected_interval():
    r = c.estimate([1., 2., 3.])
    assert r['bb_per_100'] == 2.
    assert r['standard_error'] == pytest.approx(1/math.sqrt(3))
    assert r['ci95'][0] == pytest.approx(2-1.96/math.sqrt(3))
    assert r['ci_adjusted'][0] < r['ci95'][0]


@pytest.mark.parametrize('values', [[], [1.], [0., float('nan')], [float('inf'), 0.]])
def test_bad_samples(values):
    with pytest.raises(ValueError): c.estimate(values)


def test_gate_all_conditions():
    rows, growth = passing()
    assert c.gate(rows, growth)
    rows[4]['ci_adjusted'][0] = -1.
    assert c.gate(rows, growth)
    rows[1]['ci_adjusted'][0] = -1.
    assert c.gate(rows, growth)
    rows[2]['ci_adjusted'][0] = -1.
    assert not c.gate(rows, growth)


@pytest.mark.parametrize('which', ['source', 'heldout', 'growth', 'zero_point'])
def test_gate_cannot_rescue(which):
    rows, growth = passing()
    if which == 'source': rows[0]['ci_adjusted'][0] = 0.
    if which == 'heldout':
        for a in (3, 4): rows[a]['ci_adjusted'][0] = 0.
    if which == 'growth': growth['ci_adjusted'][0] = 0.
    if which == 'zero_point': rows[4].update(bb_per_100=0., ci_adjusted=[-10., 10.])
    assert not c.gate(rows, growth)


def test_gate_bad_family_and_nonfinite():
    rows, growth = passing()
    with pytest.raises(ValueError): c.gate(rows[::-1], growth)
    rows[0]['bb_per_100'] = float('nan')
    with pytest.raises(ValueError): c.gate(rows, growth)


def test_raw_count_ignores_partial_tail(tmp_path):
    path = tmp_path/'raw.jsonl'
    assert c.raw_count(path) == 0
    path.write_bytes(b'{}\n{}\n{"part')
    assert c.raw_count(path) == 2


def test_decks_disjoint_and_fail_closed():
    new, old = c.decks(count=8), c.decks(seed=20261001, count=8)
    c.disjoint_decks(new, old)
    assert new == c.decks(count=8)
    with pytest.raises(ValueError): c.disjoint_decks(new, new)
    with pytest.raises(ValueError): c.disjoint_decks(new+[new[0]], old)
    bad = copy.deepcopy(new)
    bad[0][0] = bad[0][1]
    with pytest.raises(ValueError): c.disjoint_decks(bad, old)


def test_missing_or_truncated_cell_fails_before_analysis():
    with pytest.raises(ValueError): c.analyze({})
    with pytest.raises(ValueError): c.analyze({key: [1.] for key in c.CELLS})


def test_common_pair_group_average_not_pseudoreplicated():
    values = {key: [0.]*c.PAIRS for key in c.CELLS}
    for a in range(5): values['final', a] = [10.+(i%2) for i in range(c.PAIRS)]
    values['mid262', 3] = [2.]*c.PAIRS
    values['mid262', 4] = [4.]*c.PAIRS
    report = c.analyze(values)
    expected = c.estimate([7.+(i%2) for i in range(c.PAIRS)])
    assert report['heldout_growth'] == expected and report['confirmation_gate_pass']
