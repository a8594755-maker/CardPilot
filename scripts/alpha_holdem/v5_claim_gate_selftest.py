#!/usr/bin/env python3
"""Self-test V5 Slumbot claim gates with synthetic CI summaries.

This is a local, non-network guard. It makes sure small quick screens are not
misclassified as V4-baseline, L5, or L6 proof.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_baseline_gap import DEFAULT_BASELINE_BB100
from v5_baseline_gap import build_baseline_gap
from v5_scorecard import build_scorecard


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_run(root: Path, run_id: str) -> tuple[Path, Path]:
    run_dir = root / run_id
    output_dir = root / "models"
    run_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "run_manifest.json", {"run_id": run_id})
    write_json(run_dir / "health_status.json", {"overall": "PASS"})
    return run_dir, output_dir


def write_ci(output_dir: Path, run_id: str, tag: str, *, hands: int, bb100: float, lower: float, upper: float = 0.0) -> Path:
    path = output_dir / f"bench_v55_{run_id}_{tag}_ci_summary.json"
    write_json(
        path,
        {
            "hands": hands,
            "bb_per_100": bb100,
            "lower_bound_bb_per_100": lower,
            "upper_bound_bb_per_100": upper,
            "milestone_level": "SYNTHETIC",
            "l5_formal_win": hands >= 100_000 and bb100 > 0 and lower > 0,
            "l6_near_paper_target": hands >= 100_000 and bb100 >= 9.1 and lower > 0,
            "baseline_delta_bb_per_100": bb100 - DEFAULT_BASELINE_BB100,
        },
    )
    return path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="v5_claim_gate_") as tmp:
        root = Path(tmp)
        run_id = "v5_claim_gate_fake_run"

        run_dir, output_dir = make_run(root, run_id)
        write_ci(output_dir, run_id, "quick5k", hands=5_000, bb100=100.0, lower=80.0, upper=120.0)

        scorecard = build_scorecard(run_dir, output_dir)
        gap = build_baseline_gap(run_dir, output_dir)
        comparison = gap["baseline_comparison"]
        claims = gap["claim_rules"]

        require(scorecard["quality_status"] == "SLUMBOT_CANDIDATE_ONLY", "quick5k should only become candidate evidence")
        require(comparison["answer"] == "SAMPLE_TOO_SMALL_FOR_BASELINE_CLAIM", "quick5k must be too small for baseline claim")
        require(comparison["claim_allowed"] is False, "quick5k must not allow V4/BC baseline claim")
        require(claims["can_claim_stronger_than_v4"] is False, "quick5k must not prove stronger than V4/BC")
        require(claims["can_claim_l5"] is False, "quick5k must not prove L5")
        require(claims["can_claim_l6"] is False, "quick5k must not prove L6")

        run_dir, output_dir = make_run(root, run_id + "_formal")
        write_ci(output_dir, run_id + "_formal", "formal100k", hands=100_000, bb100=5.0, lower=1.0, upper=9.0)
        formal_gap = build_baseline_gap(run_dir, output_dir)
        formal_claims = formal_gap["claim_rules"]
        require(formal_claims["can_claim_l5"] is True, "100k positive lower CI should prove L5")
        require(formal_claims["can_claim_l6"] is False, "100k +5 bb/100 should not prove L6")

    print("v5 claim gate selftest PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
