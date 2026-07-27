#!/usr/bin/env python3

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import v5_h3_dataset_selection_finalize as target


class H3DatasetSelectionFinalizeTests(unittest.TestCase):
    def test_exact_target_and_bounds(self) -> None:
        populations = {f"{street}|{player}|{actions}": 10_000 + actions for street in "FTR" for player in (0, 1) for actions in range(2, 7)}
        quotas = target.capped_hamilton_quotas(populations)
        self.assertEqual(sum(quotas.values()), 30_000)
        self.assertTrue(all(128 <= quotas[key] <= populations[key] for key in quotas))

    def test_deterministic_independent_of_input_order(self) -> None:
        values = {"R|1|6": 9000, "F|0|2": 1000, "T|1|4": 4000, "F|1|3": 2000}
        reverse = dict(reversed(list(values.items())))
        self.assertEqual(target.capped_hamilton_quotas(values, 12_000), target.capped_hamilton_quotas(reverse, 12_000))

    def test_lexical_tie_break(self) -> None:
        quotas = target.capped_hamilton_quotas({"T|0|2": 1000, "F|0|2": 1000}, target=257, base=128)
        self.assertEqual(quotas, {"F|0|2": 129, "T|0|2": 128})

    def test_capacity_redistribution(self) -> None:
        quotas = target.capped_hamilton_quotas({"F|0|2": 129, "F|1|2": 1000, "R|0|2": 1000}, target=1000, base=128)
        self.assertEqual(quotas["F|0|2"], 129)
        self.assertEqual(sum(quotas.values()), 1000)

    def test_reject_population_below_target(self) -> None:
        with self.assertRaisesRegex(ValueError, "below_target"):
            target.capped_hamilton_quotas({"F|0|2": 10}, target=11, base=1)

    def test_reject_invalid_stratum(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_street"):
            target.capped_hamilton_quotas({"P|0|2": 100}, target=50, base=1)

    def test_refuse_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                target.atomic_no_overwrite_json(path, {"x": 1})

    def test_missing_smoke_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "smoke.json"
            path.write_text(json.dumps({"overall": "PENDING"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not_pass"):
                target.load_profile(path, Path(temporary))

    def test_registration_source_never_self_authorizes_materialization(self) -> None:
        source = Path(target.__file__).read_text(encoding="utf-8")
        self.assertIn('"dataset_materialization_authorized"] = False', source)
        self.assertIn('"independent_audit_required_before_materialization"] = True', source)
        self.assertNotIn('"dataset_materialization_authorized"] = True', source)


if __name__ == "__main__":
    unittest.main()
