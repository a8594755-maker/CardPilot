import math
import unittest

from v5_relative_v4_ci import welch


class RelativeV4Tests(unittest.TestCase):
    def test_welch_direction_and_gate_inputs(self):
        result = welch([10.0, 12.0, 14.0, 16.0], [0.0, 2.0, 4.0, 6.0])
        self.assertAlmostEqual(10.0, result['delta_candidate_minus_v4_bb100'])
        self.assertGreater(result['ci95_halfwidth_bb100'], 0.0)
        self.assertAlmostEqual(result['candidate_sd_chips'], result['baseline_sd_chips'])

    def test_independent_se_formula(self):
        candidate = [1.0, 3.0, 5.0, 7.0]
        baseline = [-1.0, 1.0, 3.0, 5.0]
        result = welch(candidate, baseline)
        expected = math.sqrt(result['candidate_sd_chips'] ** 2 / 4 + result['baseline_sd_chips'] ** 2 / 4)
        self.assertAlmostEqual(expected, result['welch_standard_error_bb100'])


if __name__ == '__main__':
    unittest.main()
