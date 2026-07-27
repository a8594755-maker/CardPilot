import unittest

from v5_l6_claim_audit import fmt_count


class FormatOptionalCountTests(unittest.TestCase):
    def test_formats_integer_with_grouping(self):
        self.assertEqual(fmt_count(2_700_000_000), "2,700,000,000")

    def test_missing_count_is_fail_closed_unknown(self):
        self.assertEqual(fmt_count(None), "unknown")

    def test_invalid_count_is_fail_closed_unknown(self):
        self.assertEqual(fmt_count("not-a-count"), "unknown")


if __name__ == "__main__":
    unittest.main()
