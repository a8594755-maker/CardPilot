import unittest
from pathlib import Path


class GoalAuditWatchTests(unittest.TestCase):
    def test_reporting_only_contract(self):
        source = Path(__file__).with_name('v5_exp005c_goal_audit_watch.py').read_text(encoding='utf-8')
        self.assertIn('REPORTING_ONLY_NO_EXPERIMENT_ADVANCE', source)
        self.assertNotIn('subprocess', source)
        self.assertNotIn('train_v5', source)
        self.assertNotIn('slumbot', source.lower())
        self.assertIn("payload['goal_complete'] is True", source)


if __name__ == '__main__':
    unittest.main()
