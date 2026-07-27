#!/usr/bin/env python3
"""Focused tests for official Slumbot loss trend extraction."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_trend_ledger import (
    clean_inherited_slumbot_rows,
    load_official_slumbot_loss_trend,
    load_parent_trend_ledger,
    load_slumbot_analysis_coverage,
    merge_slumbot_history,
)


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def write_slumbot_artifacts(
    root: Path,
    stem: str,
    *,
    bb100: float,
    sb_bb100: float,
    bb_bb100: float,
    hero_fold_bb100: float,
    showdown_bb100: float,
) -> Path:
    ci_path = root / f"{stem}_ci_summary.json"
    write_json(ci_path, {"bb_per_100": bb100, "hands": 5000})
    write_json(
        root / f"{stem}_loss_report.json",
        {
            "position": [
                {"key": "SB", "hands": 2500, "chips": int(sb_bb100 * 2500), "bb_per_100": sb_bb100},
                {"key": "BB", "hands": 2500, "chips": int(bb_bb100 * 2500), "bb_per_100": bb_bb100},
            ],
            "terminal": [
                {"key": "hero_fold", "hands": 1000, "chips": int(hero_fold_bb100 * 1000), "bb_per_100": hero_fold_bb100},
                {"key": "showdown", "hands": 1000, "chips": int(showdown_bb100 * 1000), "bb_per_100": showdown_bb100},
            ],
            "rates": {
                "sb_open_fold_rate": 0.327,
                "sb_open_call_rate": 0.506,
                "sb_open_raise_rate": 0.167,
                "sb_open_allin_rate": 0.0,
                "bb_vs_open_call_rate": 0.34,
                "bb_vs_open_raise_rate": 0.088,
            },
            "first_preflop_decision": [
                {"key": "sb_open_c", "hands": 1264, "chips": -170873, "bb_per_100": -135.184},
                {"key": "bb_vs_open_lt2.5bb_f", "hands": 1289, "chips": -128900, "bb_per_100": -100.0},
            ],
            "hole_family": [
                {"key": "other_offsuit", "hands": 2703, "chips": -266377, "bb_per_100": -98.549},
            ],
            "warnings": ["SB open limp/call rate is high."],
        },
    )
    write_json(root / f"{stem}_artifact_audit.json", {"overall": "PASS"})
    write_json(root / f"{stem}_promotion_gate.json", {"overall": "FAIL"})
    write_json(
        root / f"{stem}_hand_review.json",
        {
            "overall": "PASS",
            "evidence_class": "quick_screen",
            "training_adjustment": "SMOKE_ONLY_USE_AS_ONE_SIGNAL",
            "loss_hypotheses": [{"area": "SB_EV"}, {"area": "BB_EV"}],
        },
    )
    return ci_path


class OfficialSlumbotLossTrendTest(unittest.TestCase):
    def test_continuation_inherits_parent_slumbot_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "parent_run"
            child = root / "child_run"
            parent.mkdir()
            child.mkdir()
            ci_path = root / "models" / "bench_v55_parent_150M_quick5k_ci_summary.json"
            write_json(
                ci_path,
                {
                    "hands": 5000,
                    "bb_per_100": -94.9,
                    "lower_bound_bb_per_100": -124.555,
                    "upper_bound_bb_per_100": -65.246,
                },
            )
            write_json(
                parent / "v5_trend_ledger.json",
                {
                    "slumbot_history": [
                        {
                            "hands": 5000,
                            "bb_per_100": -94.9,
                            "lower_bound_bb_per_100": -124.555,
                            "upper_bound_bb_per_100": -65.246,
                            "milestone_level": "L0",
                            "path": str(ci_path),
                        }
                    ]
                },
            )
            write_json(
                child / "run_manifest.json",
                {
                    "lineage_parent_checkpoint": str(parent / "latest.pt"),
                    "config": {"resume": str(parent / "latest.pt")},
                },
            )

            parent_trend, parent_path = load_parent_trend_ledger(child)
            inherited = clean_inherited_slumbot_rows(parent_trend)
            merged = merge_slumbot_history(inherited, [dict(inherited[0])])

        self.assertEqual(parent_path, parent / "v5_trend_ledger.json")
        self.assertEqual(len(inherited), 1)
        self.assertEqual(inherited[0]["bb_per_100"], -94.9)
        self.assertEqual(inherited[0]["source"], "lineage_parent_trend")
        self.assertEqual(len(merged), 1)

    def test_extracts_loss_buckets_and_delta(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_ci = write_slumbot_artifacts(
                root,
                "bench_v55_example_75M_quick5k",
                bb100=-71.462,
                sb_bb100=-36.366,
                bb_bb100=-106.558,
                hero_fold_bb100=-269.17,
                showdown_bb100=-795.126,
            )
            second_ci = write_slumbot_artifacts(
                root,
                "bench_v55_example_100M_quick5k",
                bb100=-85.037,
                sb_bb100=-115.046,
                bb_bb100=-55.028,
                hero_fold_bb100=-167.737,
                showdown_bb100=-10.629,
            )
            slumbot_rows = [
                {"path": str(first_ci), "hands": 5000, "bb_per_100": -71.462, "lower_bound_bb_per_100": -136.249},
                {"path": str(second_ci), "hands": 5000, "bb_per_100": -85.037, "lower_bound_bb_per_100": -129.224},
            ]

            rows = load_official_slumbot_loss_trend(slumbot_rows, root)

        self.assertEqual(len(rows), 2)
        latest = rows[-1]
        self.assertEqual(latest["artifact_audit_overall"], "PASS")
        self.assertTrue(latest["hand_review_exists"])
        self.assertTrue(latest["loss_report_exists"])
        self.assertEqual(latest["training_adjustment"], "SMOKE_ONLY_USE_AS_ONE_SIGNAL")
        self.assertEqual(latest["hypothesis_areas"], ["SB_EV", "BB_EV"])
        self.assertEqual(latest["delta_vs_previous"]["bb_per_100"], -13.575)
        self.assertEqual(latest["delta_vs_previous"]["sb_bb100"], -78.68)
        self.assertEqual(latest["delta_vs_previous"]["bb_bb100"], 51.53)
        self.assertEqual(latest["position"]["sb_bb100"], -115.046)
        self.assertEqual(latest["terminal"]["hero_fold_bb100"], -167.737)
        self.assertEqual(latest["worst_first_preflop_decisions"][0]["key"], "sb_open_c")
        self.assertEqual(latest["worst_hole_families"][0]["key"], "other_offsuit")

    def test_missing_sibling_artifacts_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ci_path = root / "bench_v55_missing_100M_quick5k_ci_summary.json"
            write_json(ci_path, {"bb_per_100": -85.037, "hands": 5000})

            rows = load_official_slumbot_loss_trend(
                [{"path": str(ci_path), "hands": 5000, "bb_per_100": -85.037}],
                root,
            )

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["loss_report_exists"])
        self.assertFalse(rows[0]["hand_review_exists"])
        self.assertIsNone(rows[0]["artifact_audit_overall"])
        self.assertEqual(rows[0]["worst_first_preflop_decisions"], [])


class SlumbotAnalysisCoverageTest(unittest.TestCase):
    def test_historical_incomplete_rows_warn_when_latest_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "bench_v55_example_50M_quick5k_ci_summary.json",
                {"bb_per_100": -76.221, "hands": 5000},
            )
            write_json(root / "bench_v55_example_50M_quick5k_promotion_gate.json", {"overall": "FAIL"})
            write_slumbot_artifacts(
                root,
                "bench_v55_example_100M_quick5k_cadence",
                bb100=-85.037,
                sb_bb100=-115.046,
                bb_bb100=-55.028,
                hero_fold_bb100=-167.737,
                showdown_bb100=-10.629,
            )

            coverage = load_slumbot_analysis_coverage(root)

        self.assertEqual(coverage["overall"], "WARN_HISTORICAL_INCOMPLETE")
        self.assertEqual(coverage["total_count"], 2)
        self.assertEqual(coverage["complete_count"], 1)
        self.assertEqual(coverage["incomplete_count"], 1)
        self.assertEqual(coverage["latest"]["milestone_m"], 100)
        self.assertTrue(coverage["latest"]["analysis_complete"])
        self.assertEqual(coverage["latest_complete"]["milestone_m"], 100)
        self.assertIn("loss_report", coverage["rows"][0]["missing_parts"])
        self.assertIn("artifact_audit", coverage["rows"][0]["missing_parts"])
        self.assertIn("hand_review", coverage["rows"][0]["missing_parts"])

    def test_latest_incomplete_requires_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_slumbot_artifacts(
                root,
                "bench_v55_example_75M_quick5k",
                bb100=-71.462,
                sb_bb100=-36.366,
                bb_bb100=-106.558,
                hero_fold_bb100=-269.17,
                showdown_bb100=-795.126,
            )
            write_json(
                root / "bench_v55_example_150M_quick5k_cadence_ci_summary.json",
                {"bb_per_100": -12.0, "hands": 5000},
            )
            write_json(root / "bench_v55_example_150M_quick5k_cadence_promotion_gate.json", {"overall": "FAIL"})

            coverage = load_slumbot_analysis_coverage(root)

        self.assertEqual(coverage["overall"], "REVIEW_REQUIRED")
        self.assertEqual(coverage["latest"]["milestone_m"], 150)
        self.assertFalse(coverage["latest"]["analysis_complete"])
        self.assertEqual(coverage["latest_complete"]["milestone_m"], 75)


if __name__ == "__main__":
    unittest.main()
