import unittest

from v5_pilot_stop_rearm_supervisor import TRANSIENT_ERRORS


class SupervisorTests(unittest.TestCase):
    def test_only_expected_transient_errors_are_allowed(self):
        self.assertIn('manifest process_id mismatch', TRANSIENT_ERRORS)
        self.assertIn('checkpoint hands below pilot endpoint', TRANSIENT_ERRORS)
        self.assertNotIn('trainer process command identity mismatch', TRANSIENT_ERRORS)
        self.assertNotIn('gate run_id mismatch', TRANSIENT_ERRORS)


if __name__ == '__main__':
    unittest.main()
