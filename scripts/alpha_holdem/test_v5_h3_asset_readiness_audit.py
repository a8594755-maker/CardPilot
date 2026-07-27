import unittest

from v5_h3_asset_readiness_audit import action_count_bounds


class TestExpectedActions(unittest.TestCase):
    def test_opening_node(self):
        self.assertEqual(action_count_bounds("xx/"), (2, 5))

    def test_facing_first_bet_can_raise(self):
        self.assertEqual(action_count_bounds("xx/1"), (2, 6))

    def test_facing_raise_is_capped(self):
        self.assertEqual(action_count_bounds("xx/11"), (2, 2))

    def test_allin_is_facing_without_more_actions(self):
        self.assertEqual(action_count_bounds("xx/A"), (2, 2))


if __name__ == "__main__":
    unittest.main()
