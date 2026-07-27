import unittest
from pathlib import Path

from v5_exp005c_goal_audit import markdown


class GoalAuditTests(unittest.TestCase):
    def test_markdown_keeps_pending_visible(self):
        payload = {'overall': 'IN_PROGRESS', 'classification': None, 'pending_count': 1, 'failed_count': 0,
                   'requirements': [{'requirement': 'x', 'status': 'PENDING', 'evidence': 'waiting'}],
                   'next_action': 'continue'}
        text = markdown(payload)
        self.assertIn('`PENDING`', text)
        self.assertIn('does not shrink the goal', text)

    def test_markdown_distinguishes_protocol_fail_from_goal_completion(self):
        payload = {
            'overall': 'COMPLETE_EXP005C_FAIL_PROTOCOL_ABORT_ROUTE_PIVOT_W1_PREREGISTERED_NO_LAUNCH',
            'classification': 'EXP005C_FAIL_PROTOCOL_ABORT', 'pending_count': 0, 'failed_count': 0,
            'requirements': [{'requirement': 'stop rule', 'status': 'PROVEN', 'evidence': 'Tier-2 frozen'}],
            'next_action': 'objective complete',
        }
        text = markdown(payload)
        self.assertIn('EXP005C_FAIL_PROTOCOL_ABORT', text)
        self.assertIn('never becomes a method PASS', text)


if __name__ == '__main__':
    unittest.main()
