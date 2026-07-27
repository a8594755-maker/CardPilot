import gzip
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "qa-200bb-board-strict.mjs"


class StrictBoardQaTests(unittest.TestCase):
    def run_fixture(self, lines, info_sets):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            gz = root / "flop_000.jsonl.gz"
            meta = root / "flop_000.meta.json"
            out = root / "audit.json"
            with gzip.open(gz, "wt", encoding="utf-8", newline="\n") as handle:
                for line in lines:
                    handle.write(line + "\n")
            meta.write_text(json.dumps({
                "game": "HU_NLHE_SRP", "stack": "200bb", "config": "pipeline_srp_v3_200bb",
                "boardId": 0, "flopCards": [0, 1, 2], "iterations": 200000,
                "bucketCount": 50, "infoSets": info_sets,
            }), encoding="utf-8")
            proc = subprocess.run(
                ["node", str(SCRIPT), str(gz), str(meta), str(out)],
                text=True, capture_output=True, check=False,
            )
            return proc.returncode, json.loads(out.read_text(encoding="utf-8"))

    def test_valid_structure_but_small_fixture_fails_proxy_only(self):
        code, report = self.run_fixture([
            json.dumps({"key": "F|0|0|a", "probs": [0.8, 0.2]}),
            json.dumps({"key": "T|0|0|b", "probs": [0.5, 0.5]}),
            json.dumps({"key": "R|0|0|c", "probs": [0.7, 0.3]}),
        ], 3)
        self.assertEqual(code, 2)
        self.assertTrue(report["structural_pass"])
        self.assertFalse(report["convergence_proxy"]["pass"])

    def test_unknown_street_prefix_fails_structure(self):
        code, report = self.run_fixture([
            json.dumps({"key": "X|0|0|a", "probs": [0.8, 0.2]}),
        ], 1)
        self.assertEqual(code, 2)
        self.assertEqual(report["counts"]["schema_errors"], 1)
        self.assertFalse(report["structural_pass"])

    def test_parse_error_is_not_skipped(self):
        code, report = self.run_fixture([
            json.dumps({"key": "R|0|0|a", "probs": [0.8, 0.2]}), "{broken",
        ], 2)
        self.assertEqual(code, 2)
        self.assertEqual(report["counts"]["parse_errors"], 1)
        self.assertFalse(report["structural_pass"])

    def test_probability_sum_error_fails(self):
        code, report = self.run_fixture([
            json.dumps({"key": "R|0|0|a", "probs": [0.8, 0.8]}),
        ], 1)
        self.assertEqual(code, 2)
        self.assertEqual(report["counts"]["probability_errors"], 1)
        self.assertFalse(report["structural_pass"])


if __name__ == "__main__":
    unittest.main()
