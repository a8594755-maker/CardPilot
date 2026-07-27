import unittest

from v5_exp005c_primary_watch import locked_classification


def summary(lower_a=1, upper_a=3, half_a=1, lower_b=2, upper_b=4, half_b=1):
    return {'primary_effects': {
        'paired_native_axis_delta': {'ci95_lower_bb100': lower_a, 'ci95_upper_bb100': upper_a, 'ci95_halfwidth_bb100': half_a},
        'post_vs_pre_direct': {'ci95_lower_bb100': lower_b, 'ci95_upper_bb100': upper_b, 'ci95_halfwidth_bb100': half_b},
    }}


class PrimaryWatchTests(unittest.TestCase):
    def test_pass_requires_both_positive_lowers(self):
        self.assertEqual('PASS', locked_classification(summary(), {'status': 'PASS'})[0])
        self.assertEqual('INCONCLUSIVE', locked_classification(summary(lower_a=-1), {'status': 'PASS'})[0])

    def test_fail_nonpositive_upper_and_bundle(self):
        self.assertEqual('FAIL', locked_classification(summary(lower_a=-2, upper_a=0), {'status': 'PASS'})[0])
        self.assertEqual('FAIL', locked_classification(summary(), {'status': 'FAIL'})[0])

    def test_precision_is_inconclusive(self):
        self.assertEqual('INCONCLUSIVE', locked_classification(summary(half_b=20.01), {'status': 'PASS'})[0])


if __name__ == '__main__':
    unittest.main()
