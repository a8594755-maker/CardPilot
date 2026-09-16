import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("slumbot_ci_from_hands.py")
SPEC = importlib.util.spec_from_file_location("slumbot_ci_from_hands", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
slumbot_ci = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(slumbot_ci)


class SlumbotCiDefaultsTest(unittest.TestCase):
    def test_active_standard10_baseline_defaults(self):
        self.assertEqual(slumbot_ci.DEFAULT_BASELINE_BB100, -11.4275)
        self.assertEqual(slumbot_ci.DEFAULT_BASELINE_HANDS_MIN, 20_000)

    def test_baseline_fields_use_active_reference(self):
        summary = slumbot_ci.summarize(
            [-0.10] * 20_000,
            l6_target_bb100=11.1,
            l6_tolerance_bb100=2.0,
            baseline_bb100=slumbot_ci.DEFAULT_BASELINE_BB100,
            baseline_hands_min=slumbot_ci.DEFAULT_BASELINE_HANDS_MIN,
        )
        self.assertAlmostEqual(summary["bb_per_100"], -10.0)
        self.assertAlmostEqual(summary["baseline_delta_bb_per_100"], 1.4275)
        self.assertTrue(summary["baseline_point_estimate_improved"])

    def test_negative_milestone_text_is_baseline_agnostic(self):
        level = slumbot_ci.classify_level(
            hands=5_000,
            bb_per_100=-20.0,
            lower_bound_bb_per_100=-40.0,
            l6_target_bb100=11.1,
            l6_tolerance_bb100=2.0,
        )
        self.assertEqual(level["milestone_level"], "L2")
        self.assertNotIn("baseline", level["milestone_meaning"].lower())


if __name__ == "__main__":
    unittest.main()
