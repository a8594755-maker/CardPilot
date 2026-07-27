from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v5_loss_inference_audit as audit
from v5_slumbot_loss_report import load_rows


def write_session(path: Path, *, winnings: int, client_pos: int, hands: int = 30) -> None:
    rows = []
    for hand_idx in range(hands):
        rows.append(
            {
                "hand_idx": hand_idx,
                "move_idx": 0,
                "who": "hero",
                "client_pos": client_pos,
                "action_str_before": "" if client_pos == 1 else "b200",
                "street": 0,
                "hero_hole": ["As", "Kd"],
                "action_move": "b",
                "action_amount": 200 if client_pos == 1 else 400,
                "winnings_hero": winnings,
            }
        )
        rows.append(
            {
                "hand_idx": hand_idx,
                "move_idx": 1,
                "who": "opp",
                "client_pos": client_pos,
                "action_str_before": "b200",
                "street": 0,
                "hero_hole": ["As", "Kd"],
                "action_move": "f",
                "action_amount": 0,
                "winnings_hero": winnings,
            }
        )
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


class LossInferenceAuditTest(unittest.TestCase):
    def test_realized_loss_is_never_promoted_to_regret(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_paths = []
            for index in range(4):
                path = root / f"candidate_{index}.jsonl"
                write_session(path, winnings=-100, client_pos=index % 2)
                candidate_paths.append(str(path))
            result = audit.build_audit(
                candidate_rows=load_rows(candidate_paths),
                label="fixture",
                bootstrap_samples=200,
                minimum_hands=10,
            )
        guardrails = result["research_guardrails"]
        self.assertEqual(result["overall_decision"], "LOCALIZE_ONLY_COUNTERFACTUAL_OR_CONTROL_REQUIRED_FOR_INTERVENTION")
        self.assertFalse(guardrails["realized_winnings_identify_action_value"])
        self.assertFalse(guardrails["counterfactual_action_regret_available"])
        self.assertFalse(guardrails["behavior_change_authorized"])
        position = next(item for item in result["dimensions"] if item["dimension"] == "position")
        self.assertTrue(position["rows"])
        self.assertIn("candidate_ci95_lower_bb100", position["rows"][0])

    def test_baseline_difference_is_labeled_association_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_paths = []
            baseline_paths = []
            for index in range(6):
                candidate = root / f"candidate_{index}.jsonl"
                baseline = root / f"baseline_{index}.jsonl"
                write_session(candidate, winnings=200, client_pos=1)
                write_session(baseline, winnings=-200, client_pos=1)
                candidate_paths.append(str(candidate))
                baseline_paths.append(str(baseline))
            result = audit.build_audit(
                candidate_rows=load_rows(candidate_paths),
                baseline_rows=load_rows(baseline_paths),
                label="paired-fixture",
                bootstrap_samples=300,
                minimum_hands=10,
            )
        position = next(item for item in result["dimensions"] if item["dimension"] == "position")
        row = next(item for item in position["rows"] if item["key"] == "SB")
        self.assertGreater(row["difference_bb100"], 0)
        self.assertGreater(row["difference_ci95_lower_bb100"], 0)
        self.assertEqual(row["inference"], "association_not_counterfactual_action_value")
        self.assertTrue(result["multiplicity_controlled_associations"])


if __name__ == "__main__":
    unittest.main()
