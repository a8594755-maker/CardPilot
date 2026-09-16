"""Compare two independent raw Slumbot hand samples with a normal CI."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np


def load(paths: list[Path]) -> np.ndarray:
    values = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            values.extend(float(json.loads(line)["winnings_chips"]) for line in handle if line.strip())
    return np.asarray(values, dtype=np.float64)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="append", type=Path, required=True)
    parser.add_argument("--control", action="append", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    if args.out_json.exists():
        raise FileExistsError(args.out_json)
    candidate, control = load(args.candidate), load(args.control)
    delta = float(candidate.mean() - control.mean())
    half = 1.96 * math.sqrt(
        float(candidate.var(ddof=1)) / len(candidate) + float(control.var(ddof=1)) / len(control)
    )
    result = {
        "schema": "cardpilot.independent_slumbot_sample_comparison.v1",
        "candidate_hands": len(candidate), "control_hands": len(control),
        "candidate_bb_per_100": float(candidate.mean()),
        "control_bb_per_100": float(control.mean()),
        "candidate_minus_control_bb_per_100": delta,
        "ci95_lower": delta - half, "ci95_upper": delta + half,
        "paired": False, "command": [sys.executable, *sys.argv],
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
