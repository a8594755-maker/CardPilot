from __future__ import annotations

import unittest

from v5_exp005_speed_diagnosis import diagnose


def row(iteration: int, hands: int, collect: float, ppo: float, inf_bs: float = 100.0) -> dict:
    return {
        "iteration": iteration,
        "hands": hands,
        "iteration_hands": 100,
        "collect_seconds": collect,
        "ppo_seconds": ppo,
        "hands_per_second": 100 / collect,
        "inference_batch_size": inf_bs,
    }


class Exp005SpeedDiagnosisTest(unittest.TestCase):
    def test_passes_at_success_floor(self):
        baseline = [row(i, i * 100, 0.5, 0.5) for i in range(3)]
        candidate = [row(i, i * 100, 0.6, 0.5, 40.0) for i in range(3)]
        result = diagnose(baseline, candidate, success_ratio=0.9, abort_ratio=0.85, min_candidate_rows=3)
        self.assertEqual(result["decision"], "CONTINUE_SPEED_GATE_CURRENTLY_PASS")
        self.assertGreaterEqual(result["ratios"]["effective_hps_weighted"], 0.9)

    def test_aborts_below_abort_floor(self):
        baseline = [row(i, i * 100, 0.5, 0.5) for i in range(3)]
        candidate = [row(i, i * 100, 0.8, 0.5) for i in range(3)]
        result = diagnose(baseline, candidate, success_ratio=0.9, abort_ratio=0.85, min_candidate_rows=3)
        self.assertEqual(result["decision"], "ABORT_THRESHOLD_CONFIRMED_ROLLBACK_AT_EXACT_GATE")


if __name__ == "__main__":
    unittest.main()
