from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.alpha_holdem import v5_path1_progress_audit as audit


class Path1ProgressAuditTests(unittest.TestCase):
    def test_board_ids_accepts_only_complete_asset_names(self) -> None:
        paths = [
            Path("flop_002.jsonl.gz"),
            Path("flop_013.meta.json"),
            Path("board_014.jsonl.gz"),
            Path("flop_bad.meta.json"),
        ]
        self.assertEqual(audit.board_ids(paths), {2, 13})

    def test_latest_qa_uses_last_record_and_preserves_failure_history(self) -> None:
        content = """\
[2026-07-13T00:00:00Z] C:\\asset\\flop_211.jsonl.gz
illegal post-all-in extra-action rows: 8
QA: FAIL (illegal post-all-in)

[2026-07-13T01:00:00Z] C:\\asset\\flop_005.jsonl.gz
illegal post-all-in extra-action rows: 0
QA: PASS (converged + legal post-all-in)

[2026-07-13T02:00:00Z] C:\\asset\\flop_211.jsonl.gz
illegal post-all-in extra-action rows: 0
QA: PASS (converged + legal post-all-in)
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qa.log"
            path.write_text(content, encoding="utf-8")
            latest, failure_history, records = audit.latest_qa(path)
        self.assertEqual(records, 3)
        self.assertEqual(failure_history, [211])
        self.assertEqual(latest[5], {"status": "PASS", "illegal_postallin_rows": 0})
        self.assertEqual(latest[211], {"status": "PASS", "illegal_postallin_rows": 0})

    def test_latest_qa_keeps_missing_illegal_count_fail_closed(self) -> None:
        content = """\
[2026-07-13T00:00:00Z] C:\\asset\\flop_010.jsonl.gz
QA: PASS (malformed record)
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qa.log"
            path.write_text(content, encoding="utf-8")
            latest, _, _ = audit.latest_qa(path)
        self.assertIsNone(latest[10]["illegal_postallin_rows"])

    def test_active_boards_reports_latest_board_per_worker(self) -> None:
        content = """\
W0 starting board=123
W1 starting board=127
W0 starting board=131
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "parallel.log"
            path.write_text(content, encoding="utf-8")
            result = audit.active_boards(path)
        self.assertEqual(result, [{"worker": 0, "board": 131}, {"worker": 1, "board": 127}])


if __name__ == "__main__":
    unittest.main()
