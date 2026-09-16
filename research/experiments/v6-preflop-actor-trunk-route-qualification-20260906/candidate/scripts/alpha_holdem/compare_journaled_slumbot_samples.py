"""Independent-sample comparison of two journaled Slumbot policy evaluations."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np


def load(root: Path) -> list[dict]:
    files = sorted(root.glob("s*/hands.jsonl"))
    if len(files) < 2:
        raise ValueError(f"Need multiple session files under {root}")
    return [json.loads(line) for path in files for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def describe(values: list[float]) -> dict:
    array = np.asarray(values, dtype=np.float64)
    if len(array) < 2:
        raise ValueError("At least two hands required")
    mean = float(array.mean())
    variance = float(array.var(ddof=1))
    half = 1.96 * math.sqrt(variance / len(array))
    return {
        "hands": len(array), "bb_per_100": mean * 100,
        "variance_bb2_per_hand": variance,
        "ci95_low_bb_per_100": (mean - half) * 100,
        "ci95_high_bb_per_100": (mean + half) * 100,
    }


def difference(later: list[float], earlier: list[float]) -> dict:
    later_array = np.asarray(later, dtype=np.float64)
    earlier_array = np.asarray(earlier, dtype=np.float64)
    mean = float(later_array.mean() - earlier_array.mean())
    standard_error = math.sqrt(
        float(later_array.var(ddof=1)) / len(later_array)
        + float(earlier_array.var(ddof=1)) / len(earlier_array)
    )
    half = 1.96 * standard_error
    return {
        "later_hands": len(later_array), "earlier_hands": len(earlier_array),
        "delta_bb_per_100": mean * 100,
        "ci95_low_bb_per_100": (mean - half) * 100,
        "ci95_high_bb_per_100": (mean + half) * 100,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--earlier-root", type=Path, required=True)
    parser.add_argument("--later-root", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--comparison-label", default="dose_12k_minus_8k")
    parser.add_argument("--omit-internal-reference", action="store_true")
    args = parser.parse_args()
    earlier_rows = load(args.earlier_root)
    later_rows = load(args.later_root)
    all_rows = earlier_rows + later_rows
    identities = [(row["session_id"], row["session_token_sha256"]) for row in all_rows]
    if len({value[0] for value in identities}) != 16 or len({value[1] for value in identities}) != 16:
        raise ValueError("The two evaluations do not contain 16 independent session identities")
    earlier = [float(row["winnings_bb"]) for row in earlier_rows]
    later = [float(row["winnings_bb"]) for row in later_rows]
    seat_differences = {}
    for seat in (0, 1):
        early = [float(row["winnings_bb"]) for row in earlier_rows if row["terminal_response"]["client_pos"] == seat]
        late = [float(row["winnings_bb"]) for row in later_rows if row["terminal_response"]["client_pos"] == seat]
        seat_differences[str(seat)] = difference(late, early)
    earlier_summary, later_summary = describe(earlier), describe(later)
    delta = difference(later, earlier)
    result = {
        "schema": "cardpilot.independent_slumbot_sample_comparison.v1",
        "comparison_label": args.comparison_label,
        "earlier": earlier_summary,
        "later": later_summary,
        "pooled_policy_average": describe(earlier + later),
        "later_minus_earlier": delta,
        "seat_later_minus_earlier": seat_differences,
        "session_identities_disjoint": True,
        "internal_later_minus_earlier_bb_per_100": None if args.omit_internal_reference else 21.7583,
        "internal_external_slope_sign_agreement": None if args.omit_internal_reference else delta["delta_bb_per_100"] > 0,
        "clear_external_dose_reversal": delta["ci95_high_bb_per_100"] < 0,
        "both_doses_upper_ci_below_standard10_point": (
            earlier_summary["ci95_high_bb_per_100"] < -11.4275
            and later_summary["ci95_high_bb_per_100"] < -11.4275
        ),
    }
    args.out_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
