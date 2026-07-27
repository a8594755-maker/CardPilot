from __future__ import annotations

import unittest

from v5_value_audit import classify, regression_metrics


class ValueAuditTest(unittest.TestCase):
    def test_perfect_calibration_metrics(self):
        metrics = regression_metrics([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0])
        self.assertAlmostEqual(metrics['explained_variance'], 1.0)
        self.assertAlmostEqual(metrics['rmse_bb'], 0.0)
        self.assertAlmostEqual(metrics['calibration_slope'], 1.0)

    def test_multi_signal_rule_does_not_use_low_positive_ev_alone(self):
        global_metrics = {
            'explained_variance': 0.01,
            'rmse_over_target_std': 0.995,
            'calibration_slope': 1.0,
            'prediction_std_over_target_std': 0.2,
            'bias_bb': 0.0,
            'target_std_bb': 10.0,
        }
        decision = classify(global_metrics, {})
        self.assertEqual(decision['decision'], 'DOES_NOT_SUPPORT_CRITIC_OR_REWARD_SCALE_PROBLEM')
        self.assertFalse(decision['route_pivot_exp_w1_eligible'])
        self.assertFalse(decision['exp_w1_registration_authorized_now'])


if __name__ == '__main__':
    unittest.main()
