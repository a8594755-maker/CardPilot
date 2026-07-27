import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v5_method_selection_diagnostic as diagnostic


def train_line(iteration: int, *, kl: float, clip: float) -> str:
    return (
        f"[{iteration}] hands={iteration * 16_384:,} rew=+0.000 rew100=+0.000 "
        f"ploss=0.0000 vloss=1000.0000 ent=1.2000 kl={kl:.4f} clipfrac={clip:.4f} "
        "d1bite=0.000 aprior=2.0000 eps=0.000 pool=5 mirror=0/0 aiev=1:100 "
        "aiev_skip=0:0 trans=100 terms=50 mix=F0.25/C0.25/R0.45/A0.05 "
        "pmix=F0.25/C0.25/R0.45/A0.05 xmix=F0.25/C0.25/R0.45/A0.05 "
        "h/s=4000 tdec/s=8000 inf_bs=160 collect=4.0s ppo=5.0s"
    )


def write_fixture(root: Path, *, high_kl: bool, warning_counts: list[int], mismatch_last_gate: bool = False):
    (root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "fixture-run",
                "config": {"opponent_assignment": "per-iteration", "run_id": "fixture-run"},
            }
        ),
        encoding="utf-8",
    )
    rows = [
        train_line(
            iteration,
            kl=(0.08 if high_kl else 0.01),
            clip=(0.30 if high_kl else 0.10),
        )
        for iteration in range(1, 301)
    ]
    (root / "latest_train.log").write_text("\n".join(rows) + "\n", encoding="utf-8")
    for index, warnings in enumerate(warning_counts, start=1):
        target = index * 100
        gate_checkpoint = target + 100 if mismatch_last_gate and index == len(warning_counts) else target
        (root / f"gate_{target}_status.json").write_text(
            json.dumps(
                {
                    "overall": "PASS",
                    "target_iteration": target,
                    "checkpoint_iteration": gate_checkpoint,
                    "checkpoint_hands": target * 16_384,
                }
            ),
            encoding="utf-8",
        )
        (root / f"v5_post_gate_review_{target}.json").write_text(
            json.dumps(
                {
                    "target_iteration": target,
                    "gate_overall": "PASS",
                    "gate_checkpoint_iteration": gate_checkpoint,
                    "preflop_probe": {
                        "overall": "PASS" if warnings == 0 else "WARN",
                        "warning_count": warnings,
                    },
                    "internal_probe": {
                        "latest_l6_verdict": "MIXED_INTERNAL",
                        "latest_l6_delta_mean_bb100": 100.0,
                        "latest_l6_delta_lower_bb100": -100.0,
                    },
                }
            ),
            encoding="utf-8",
        )
    (root / "v5_trend_ledger.json").write_text(
        json.dumps(
            {
                "latest_official": {
                    "hands": 20_400,
                    "bb_per_100": -140.151,
                    "lower_bound_bb_per_100": -178.386,
                    "upper_bound_bb_per_100": -101.916,
                    "milestone_level": "L0",
                },
                "direction": {"answer": "SLUMBOT_POINT_ESTIMATE_DOWN", "claim_allowed": False},
            }
        ),
        encoding="utf-8",
    )


class ParserTest(unittest.TestCase):
    def test_parse_train_line(self):
        row = diagnostic.parse_train_line(train_line(12, kl=0.1234, clip=0.3456))
        self.assertEqual(row["iteration"], 12)
        self.assertEqual(row["hands"], 12 * 16_384)
        self.assertAlmostEqual(row["kl"], 0.1234)
        self.assertAlmostEqual(row["clipfrac"], 0.3456)


class SelectionDiagnosticTest(unittest.TestCase):
    def test_high_kl_and_oscillation_rank_isolated_exp006a_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, high_kl=True, warning_counts=[0, 7, 0, 6, 0, 7, 0, 6, 0, 7])
            result = diagnostic.build_diagnostic(root, tail=200, gate_tail=10)
        self.assertTrue(result["ppo_stability"]["exp006a_isolated_kl_support"])
        self.assertTrue(result["opponent_distribution_instability"]["exp005_group_assignment_support"])
        self.assertEqual(
            result["current_priority"],
            "EXP006A_DIRECT_SIGNAL_PRIORITY_EXP005_STRUCTURAL_SECONDARY",
        )
        self.assertEqual(result["selection_status"], "WAIT_FOR_500M_OFFICIAL_PROMOTION_RESULT")
        self.assertTrue(result["decision_rule"]["no_cutover_before_500m"])
        self.assertEqual(result["latest_official_slumbot"]["hands"], 20_400)
        self.assertEqual(result["latest_official_slumbot"]["bb100"], -140.151)

    def test_low_kl_and_stable_gates_prove_no_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, high_kl=False, warning_counts=[0] * 10)
            result = diagnostic.build_diagnostic(root, tail=200, gate_tail=10)
        self.assertFalse(result["ppo_stability"]["exp006a_isolated_kl_support"])
        self.assertFalse(result["opponent_distribution_instability"]["exp005_group_assignment_support"])
        self.assertEqual(result["current_priority"], "NO_METHOD_PRIORITY_PROVEN")

    def test_mismatched_gate_is_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(
                root,
                high_kl=True,
                warning_counts=[0, 7, 0, 6, 0, 7],
                mismatch_last_gate=True,
            )
            gates = diagnostic.load_gate_rows(root, gate_tail=10)
        self.assertEqual(len(gates), 5)
        self.assertNotIn(600, [row["target_iteration"] for row in gates])

    def test_thresholds_are_frozen_in_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, high_kl=True, warning_counts=[0, 7, 0, 6, 0, 7])
            result = diagnostic.build_diagnostic(root, tail=200, gate_tail=6)
        thresholds = result["thresholds_frozen_before_500m_result"]
        self.assertEqual(thresholds["kl_target_max"], 0.03)
        self.assertEqual(thresholds["preflop_warning_range_min"], 4)
        self.assertEqual(result["claim_scope"], "pre500m_method_selection_diagnostic_only_not_behavior_authorization_not_strength")


if __name__ == "__main__":
    unittest.main()
