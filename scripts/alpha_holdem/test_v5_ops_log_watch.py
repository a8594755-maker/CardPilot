#!/usr/bin/env python3
"""Focused tests for append-only V5 Ops evidence rows."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_ops_log_watch import append_event_row, ledger_has_gate_row, reconcile_status_fields, scan_once


def completed_review(target: int, hands: int) -> dict:
    return {
        "overall": "REVIEW_REQUIRED_NO_AUTO_RESTART",
        "target_iteration": target,
        "gate": {
            "overall": "PASS",
            "checkpoint_iteration": target,
            "checkpoint_hands": hands,
            "live_iteration": target + 3,
            "live_hands": hands + 49_000,
        },
        "health": {"overall": "PASS", "entropy": 1.35, "value_loss": 1800.0},
        "internal_probe": {
            "state": "COMPLETED",
            "latest_l6_verdict": "MIXED_INTERNAL",
            "latest_l6_delta_mean_bb100": 10.0,
            "latest_l6_delta_lower_bb100": -20.0,
        },
        "preflop_probe": {"overall": "WARN", "warning_count": 2},
        "checkpoint_delta": {"overall": "LOCAL_GUARDRAILS_MIXED"},
        "slumbot_trend": {
            "latest_official_hands": 20_400,
            "latest_official_bb100": -140.151,
            "latest_official_ci_lower": -178.386,
        },
    }


class OpsLogWatchTest(unittest.TestCase):
    def test_status_reconciliation_preserves_unrelated_invalid_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "ledger.md"
            ledger.write_bytes(b"before\xff\n- status: OLD\nafter\n")
            spec = root / "spec.json"
            spec.write_text(
                json.dumps({"replacements": [{"old": "- status: OLD", "new": "- status: NEW"}]}),
                encoding="utf-8",
            )

            result = reconcile_status_fields(ledger, spec, dry_run=False)
            raw = ledger.read_bytes()

        self.assertEqual(result["overall"], "PASS")
        self.assertEqual(raw, b"before\xff\n- status: NEW\nafter\n")

    def test_generic_event_append_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.md"
            first = append_event_row(
                ledger,
                event_id="CONTROL-001",
                title="control update",
                detail="reporting only",
                dry_run=False,
            )
            second = append_event_row(
                ledger,
                event_id="CONTROL-001",
                title="control update",
                detail="reporting only",
                dry_run=False,
            )

        self.assertTrue(first["appended"])
        self.assertFalse(second["appended"])
        self.assertEqual(second["reason"], "already_logged")

    def test_pending_row_does_not_suppress_evidence_update(self):
        text = "| 2026-07-09 | EXP-003 run gate_24000 PASS / evidence refresh pending | pending |"

        self.assertFalse(ledger_has_gate_row(text, 24_000))
        self.assertTrue(
            ledger_has_gate_row(
                text + "\n| 2026-07-09 | EXP-003 run gate_24000 evidence update | done |",
                24_000,
            )
        )

    def test_scan_survives_historical_invalid_utf8_and_appends_current_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "v5_exp003_run"
            run_dir.mkdir()
            review_path = run_dir / "v5_post_gate_review_24000.json"
            review_path.write_text(json.dumps(completed_review(24_000, 394_254_129)), encoding="utf-8")
            ledger = root / "ledger.md"
            ledger.write_bytes(b"# ledger\n\xffhistorical\n")

            status = scan_once(run_dir, ledger, None, dry_run=False)
            raw = ledger.read_bytes()

        self.assertEqual(status["appended_count"], 1)
        appended = status["appended"][0]["row"]
        self.assertIn("EXP-003 run gate_24000 evidence update", appended)
        self.assertIn("causal mirror bundle", appended)
        self.assertNotIn("EXP-002 cutover remains blocked", appended)
        self.assertTrue(raw.endswith((appended + "\n").encode("utf-8")))

    def test_terminal_exp003_judgment_suppresses_stale_eligibility_instruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "v5_exp003_run"
            run_dir.mkdir()
            target = 29_500
            review_path = run_dir / f"v5_post_gate_review_{target}.json"
            review_path.write_text(
                json.dumps(completed_review(target, 484_734_368)), encoding="utf-8"
            )
            judgment_path = run_dir / "v5_exp003_judgment_gate24900.json"
            judgment_path.write_text(
                json.dumps(
                    {
                        "decision": "INCONCLUSIVE",
                        "decision_valid": True,
                        "candidate_checkpoint_iteration": 24_900,
                        "candidate_checkpoint_hands": 409_058_520,
                    }
                ),
                encoding="utf-8",
            )
            ledger = root / "ledger.md"

            status = scan_once(run_dir, ledger, None, dry_run=False)

        appended = status["appended"][0]["row"]
        self.assertIn("terminally `INCONCLUSIVE`", appended)
        self.assertIn("do not rerun, add pairs, change seeds", appended)
        self.assertNotIn("bundle is eligible", appended)
        self.assertNotIn("follow the registered three-role protocol", appended)

    def test_continuation_inherits_terminal_exp003_judgment_from_lineage_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "v5_exp003_parent"
            parent.mkdir()
            judgment_path = parent / "v5_exp003_judgment_gate24900.json"
            judgment_path.write_text(
                json.dumps(
                    {
                        "decision": "INCONCLUSIVE",
                        "decision_valid": True,
                        "candidate_checkpoint_iteration": 24_900,
                        "candidate_checkpoint_hands": 409_058_520,
                    }
                ),
                encoding="utf-8",
            )
            run_dir = root / "v5_exp003_exp005_continuation"
            run_dir.mkdir()
            (run_dir / "run_manifest.json").write_text(
                json.dumps({"lineage_parent_checkpoint": str(parent / "frozen.pt")}),
                encoding="utf-8",
            )
            target = 31_500
            (run_dir / f"v5_post_gate_review_{target}.json").write_text(
                json.dumps(completed_review(target, 517_633_535)), encoding="utf-8"
            )
            ledger = root / "ledger.md"

            status = scan_once(run_dir, ledger, None, dry_run=False)

        appended = status["appended"][0]["row"]
        self.assertIn("terminally `INCONCLUSIVE`", appended)
        self.assertNotIn("bundle is eligible", appended)
        self.assertNotIn("follow the registered three-role protocol", appended)


if __name__ == "__main__":
    unittest.main()
