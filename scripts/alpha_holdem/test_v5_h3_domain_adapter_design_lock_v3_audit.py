#!/usr/bin/env python3

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import v5_h3_domain_adapter_design_lock_v3_audit as target


class H3DomainAdapterV3LockAuditTests(unittest.TestCase):
    def test_authoritative_lock_passes(self) -> None:
        result = target.audit()
        self.assertEqual(result["overall"], "PASS_IMMUTABLE_SNAPSHOT_ADAPTER_LOCK")
        self.assertEqual(result["assertions_passed"], result["assertions_total"])
        self.assertFalse(result["behavior_launch_authorized"])

    def test_tampered_mass_cap_fails(self) -> None:
        lock = json.loads(target.LOCK.read_text(encoding="utf-8"))
        lock["full_selected_corpus_domain_risk_gate"]["maximum_projection_mass_fraction"] = 1.0
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lock.json"
            path.write_text(json.dumps(lock), encoding="utf-8")
            result = target.audit(path)
        self.assertEqual(result["overall"], "FAIL_CLOSED")
        self.assertFalse(result["checks"]["full_projection_mass_cap"])

    def test_source_never_grants_behavior_or_official_authority(self) -> None:
        source = Path(target.__file__).read_text(encoding="utf-8")
        self.assertIn('"behavior_launch_authorized": False', source)
        self.assertIn('"official_hands_authorized": 0', source)


if __name__ == "__main__":
    unittest.main()
