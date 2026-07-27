import unittest

from v5_hybrid_h2_treatment_launch_watch import readiness


class TestReadiness(unittest.TestCase):
    def test_waits(self):
        self.assertEqual(readiness({"overall": "PENDING"}, {"overall": "PENDING"})[0], "WAITING")

    def test_blocks_failure(self):
        self.assertEqual(readiness({"overall": "FAIL"}, {"overall": "PENDING"})[0], "TERMINAL_BLOCKED")

    def test_requires_exact_pass(self):
        endpoint = {"overall": "PASS", "state": "ARM_ENDPOINT_FROZEN"}
        protocol = {"overall": "PASS", "first60": {"status": "PASS_CONTROL_BASELINE_FROZEN"}}
        self.assertEqual(readiness(endpoint, protocol)[0], "READY")


if __name__ == "__main__":
    unittest.main()
