import argparse
import json
import tempfile
import unittest
from pathlib import Path

import experiment_log


class ExperimentLogTest(unittest.TestCase):
    def test_lifecycle_and_indexes(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "research" / "experiments"
            repo = base / "repo"
            repo.mkdir()
            start = argparse.Namespace(
                id="test-run", title="Test run", status="RUNNING",
                hypothesis="A measurable hypothesis", change="One material change",
                baseline="baseline", source="source.pt", parent=None,
                command="python train.py", count=["new_training_hands=100"],
                metric=["loss=1.25"], artifact=["model.pt"], note=["started"],
                tag=["smoke"], started_at=None, code_path=[],
            )
            record = experiment_log.create_record(root, repo, start)
            self.assertEqual(record["accounting"]["new_training_hands"], 100)
            self.assertEqual(record["metrics"]["loss"], 1.25)

            finish = argparse.Namespace(
                id="test-run", status="COMPLETED", count=["evaluation_hands=5000"],
                metric=["bb_per_100=-2.5"], artifact=[], note=["finished"],
                summary="No improvement", conclusion="Hypothesis rejected",
                decision="REJECT", next_step="Change the target", ended_at=None,
            )
            experiment_log.mutate_record(root, repo, finish, finishing=True)
            records = experiment_log.rebuild_index(root)
            self.assertEqual(len(records), 1)
            saved = json.loads(
                (root / "test-run" / "experiment.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved["status"], "COMPLETED")
            self.assertEqual(saved["metrics"]["bb_per_100"], -2.5)
            self.assertIsNotNone(saved["accounting"]["wall_time_seconds"])
            self.assertTrue(saved["reproducibility"]["exact_command_available"])
            self.assertTrue(saved["reproducibility"]["all_recorded_commands_exact"])
            self.assertIn(
                "test-run", (root.parent / "EXPERIMENTS.md").read_text(encoding="utf-8")
            )
            self.assertIn(
                "historical experiments",
                (root.parent / "HISTORY.md").read_text(encoding="utf-8"),
            )

    def test_rejects_duplicate_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "experiments"
            args = argparse.Namespace(
                id="duplicate", title="Duplicate", status="RUNNING",
                hypothesis="Hypothesis", change="Change", baseline="", source="",
                parent=None, command="", count=[], metric=[], artifact=[], note=[], tag=[],
                started_at=None, code_path=[],
            )
            experiment_log.create_record(root, Path(temporary), args)
            with self.assertRaises(experiment_log.LogError):
                experiment_log.create_record(root, Path(temporary), args)

    def test_artifact_hash_and_command_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "experiments"
            artifact = base / "result.json"
            artifact.write_text('{"ok": true}\n', encoding="utf-8")
            args = argparse.Namespace(
                id="integrity-run", title="Integrity", status="RUNNING",
                hypothesis="Hash artifacts", change="Capture integrity",
                baseline="", source="", parent=None, command="python train.py --steps 10",
                count=[], metric=[], artifact=[str(artifact)], note=[], tag=[],
                started_at=None, code_path=[],
            )
            record = experiment_log.create_record(root, base, args)
            metadata = record["artifact_integrity"][str(artifact)]
            self.assertEqual(metadata["type"], "file")
            self.assertEqual(len(metadata["sha256"]), 64)
            self.assertTrue(record["reproducibility"]["exact_command_available"])
            self.assertFalse(experiment_log.command_audit("python train.py --data <dir>")["exact"])
            self.assertTrue(
                experiment_log.command_audit(
                    r"C:\Users\runner\Python312\python.exe train.py --steps 10"
                )["exact"]
            )
            self.assertFalse(
                experiment_log.command_audit(r"C:\Users\runner\notes.txt training")[
                    "exact"
                ]
            )

    def test_code_provenance_capture_in_git_repo(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            subprocess = __import__("subprocess")
            subprocess.run(["git", "init"], cwd=base, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=base, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=base, check=True)
            source = base / "train.py"
            source.write_text("print('v1')\n", encoding="utf-8")
            subprocess.run(["git", "add", "train.py"], cwd=base, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=base, check=True, capture_output=True)
            source.write_text("print('v2')\n", encoding="utf-8")
            root = base / "research" / "experiments"
            args = argparse.Namespace(
                id="provenance-run", title="Provenance", status="RUNNING",
                hypothesis="Capture code", change="Modify train.py", baseline="", source="",
                parent=None, command="python train.py", count=[], metric=[], artifact=[],
                note=[], tag=[], started_at=None, code_path=["train.py"],
            )
            record = experiment_log.create_record(root, base, args)
            self.assertTrue(record["code"]["provenance_complete"])
            self.assertEqual(len(record["code"]["patch_sha256"]), 64)
            self.assertEqual(len(record["code"]["source_manifest_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
