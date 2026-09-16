import copy
import math
import unittest
from review import stats, validate_row


class ReviewTests(unittest.TestCase):
    def test_stats_scale(self):
        result = stats([1., 3.])
        self.assertEqual(result['bb100'], 200.)
        self.assertAlmostEqual(result['se_bb100'], 100.)
        self.assertAlmostEqual(result['ci95'][0], 4.)

    def test_invalid_samples(self):
        for values in ([1], [], [0, math.nan], [0, math.inf]):
            with self.assertRaises(ValueError):
                stats(values)

    def test_zero_matched_difference(self):
        self.assertEqual(stats([0.] * 1024)['ci95'], [0., 0.])

    def test_row_and_rejections(self):
        deck = list(range(52))
        row = dict(seed=1, anchor='standard10', pair_index=0, deck=deck,
                   rewards_bb={'root': [-200, 200], 'final': [0, 1], 'aggregate': [2, 3]})
        validate_row(row, 1, 'standard10', 0, deck)
        for key, value in [('seed', 3), ('pair_index', 1), ('anchor', 'wrong'), ('deck', list(reversed(deck)))]:
            bad = copy.deepcopy(row); bad[key] = value
            with self.assertRaises(ValueError):
                validate_row(bad, 1, 'standard10', 0, deck)
        for value in (201, math.nan, math.inf, True):
            bad = copy.deepcopy(row); bad['rewards_bb']['root'][0] = value
            with self.assertRaises(ValueError):
                validate_row(bad, 1, 'standard10', 0, deck)


if __name__ == '__main__':
    unittest.main()
