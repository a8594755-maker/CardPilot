from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import torch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v5_h4_pool_measurement_design as design_tool
import v5_h4_pool_measurement_design_audit as audit_tool


def snapshot(identifier: int, loss: float) -> dict:
    return {
        "id": identifier,
        "iteration": identifier * 200,
        "hands": identifier * 1000,
        "selection_loss": loss,
        "state_dict": {"w": torch.tensor([float(identifier), loss])},
    }


class H4PoolMeasurementDesignTest(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path]:
        active = [snapshot(i, 1.0 + i / 100) for i in range(101, 106)]
        historical = [snapshot(11, 3.0), snapshot(12, 2.0), snapshot(13, 2.0), snapshot(14, 4.0)]
        history = [{k: row[k] for k in ("id", "iteration", "hands", "selection_loss")} for row in historical]
        source = {"iteration": 31400, "total_hands": 515_989_661, "env_version": "v55", "obs_version": "v55", "pool_snapshots": active, "pool_candidate_history": history}
        old = {"env_version": "v55", "obs_version": "v55", "pool_snapshots": historical}
        source_path, old_path = root / "source.pt", root / "old.pt"
        torch.save(source, source_path)
        torch.save(old, old_path)
        return source_path, old_path

    def test_payoff_blind_selection_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, old = self.fixture(Path(tmp))
            design = design_tool.build_design(source, old, excluded_count=3)
            self.assertEqual(design["selection_rule"]["selected_excluded_ids"], [12, 13, 11])
            design_path = Path(tmp) / "design.json"
            design_path.write_text(json.dumps(design), encoding="utf-8")
            result = audit_tool.audit(design_path)
            self.assertEqual(result["overall"], "PASS_IMMUTABLE_H4_POOL_MEASUREMENT_DESIGN")

    def test_tampered_panel_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, old = self.fixture(Path(tmp))
            design = design_tool.build_design(source, old, excluded_count=3)
            design["panel"][0]["state_sha256"] = "0" * 64
            design["design_payload_sha256"] = design_tool.payload_sha256(design)
            design_path = Path(tmp) / "design.json"
            design_path.write_text(json.dumps(design), encoding="utf-8")
            self.assertEqual(audit_tool.audit(design_path)["overall"], "FAIL_CLOSED")

    def test_tampered_payload_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, old = self.fixture(Path(tmp))
            design = design_tool.build_design(source, old, excluded_count=2)
            design["measurement"]["seed"] += 1
            design_path = Path(tmp) / "design.json"
            design_path.write_text(json.dumps(design), encoding="utf-8")
            self.assertEqual(audit_tool.audit(design_path)["overall"], "FAIL_CLOSED")


if __name__ == "__main__":
    unittest.main()
