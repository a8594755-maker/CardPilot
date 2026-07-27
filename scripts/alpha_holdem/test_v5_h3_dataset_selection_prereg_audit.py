#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path

import v5_h3_dataset_selection_prereg_audit as target


class H3DatasetSelectionPreregAuditTests(unittest.TestCase):
    def test_reference_total_and_bounds(self) -> None:
        population = {f"{street}|{player}|{actions}": 50_000 + actions for street in "FTR" for player in (0, 1) for actions in range(2, 7)}
        quotas = target.independent_quota_reference(population, 30_000, 128)
        self.assertEqual(sum(quotas.values()), 30_000)
        self.assertTrue(all(0 < quotas[key] <= population[key] for key in quotas))

    def test_lexical_tie_break(self) -> None:
        self.assertEqual(
            target.independent_quota_reference({"T|0|2": 1000, "F|0|2": 1000}, 257, 128),
            {"F|0|2": 129, "T|0|2": 128},
        )

    def test_capacity_redistribution(self) -> None:
        quotas = target.independent_quota_reference({"F|0|2": 129, "F|1|2": 1000, "R|0|2": 1000}, 1000, 128)
        self.assertEqual(quotas["F|0|2"], 129)
        self.assertEqual(sum(quotas.values()), 1000)

    def test_reject_invalid_action_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_stratum"):
            target.independent_quota_reference({"F|0|7": 100}, 50, 1)

    def test_source_keeps_behavior_and_official_authority_false(self) -> None:
        source = Path(target.__file__).read_text(encoding="utf-8")
        self.assertIn('"behavior_launch_authorized": False', source)
        self.assertIn('"official_hands_authorized": 0', source)


if __name__ == "__main__":
    unittest.main()
