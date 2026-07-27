#!/usr/bin/env python3
"""Measure exact fold counterfactuals for completed postflop calls."""
from __future__ import annotations

import argparse
import glob
import json
import math
from collections import defaultdict
from pathlib import Path

from heuristic_policy_v3 import _eval_postflop
from play_slumbot import BIG_BLIND, compute_commitments, parse_action


def expand_inputs(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matches = glob.glob(pattern)
        paths.extend(Path(match) for match in (matches or [pattern]))
    return sorted({path.resolve() for path in paths if path.is_file()})


def summary(values: list[float]) -> dict:
    if not values:
        return {"rows": 0}
    mean = sum(values) / len(values)
    variance = (
        sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        if len(values) > 1
        else 0.0
    )
    se = math.sqrt(variance / len(values))
    return {
        "rows": len(values),
        "mean_call_minus_fold_bb": mean,
        "total_call_minus_fold_bb": sum(values),
        "se_bb": se,
        "ci95_lower_bb": mean - 1.96 * se,
        "ci95_upper_bb": mean + 1.96 * se,
        "fold_better_rows": sum(value < 0.0 for value in values),
        "call_better_rows": sum(value > 0.0 for value in values),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dumps", nargs="+", required=True)
    parser.add_argument("--street", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args()

    paths = expand_inputs(args.dumps)
    all_hands: set[tuple[str, int]] = set()
    groups: dict[str, list[float]] = defaultdict(list)
    details: list[dict] = []
    malformed = 0
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    hand_key = (str(path), int(row["hand_idx"]))
                    all_hands.add(hand_key)
                    if (
                        row.get("who") != "hero"
                        or int(row.get("street", -1)) != args.street
                        or row.get("action_move") != "c"
                        or (
                            row.get("policy_action_slot") is not None
                            and int(row["policy_action_slot"]) != 1
                        )
                    ):
                        continue
                    state = parse_action(str(row["action_str_before"]))
                    commitments = compute_commitments(state)
                    to_call = float(commitments["to_call"])
                    pot = max(float(commitments["pot"]), 1.0)
                    if to_call <= 0.0:
                        continue
                    strength = int(
                        _eval_postflop(row["hero_hole"], row["board"])
                    )
                    actual_return = float(row["winnings_hero"]) / BIG_BLIND
                    fold_return = -float(commitments["hero_total"]) / BIG_BLIND
                    delta = actual_return - fold_return
                    fraction = to_call / pot
                    if fraction < 0.25:
                        fraction_bucket = "lt25pct"
                    elif fraction < 0.35:
                        fraction_bucket = "25to35pct"
                    elif fraction < 0.50:
                        fraction_bucket = "35to50pct"
                    else:
                        fraction_bucket = "ge50pct"
                    keys = (
                        "all",
                        f"strength_{strength}",
                        f"strength_{strength}_position_{int(row['client_pos'])}",
                        f"strength_{strength}_{fraction_bucket}",
                    )
                    for key in keys:
                        groups[key].append(delta)
                    details.append(
                        {
                            "path": str(path),
                            "hand_idx": int(row["hand_idx"]),
                            "position": int(row["client_pos"]),
                            "strength": strength,
                            "to_call_bb": to_call / BIG_BLIND,
                            "pot_before_bb": pot / BIG_BLIND,
                            "to_call_pot_fraction": fraction,
                            "actual_return_bb": actual_return,
                            "fold_return_bb": fold_return,
                            "call_minus_fold_bb": delta,
                        }
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    malformed += 1

    total_hands = len(all_hands)
    summaries = {}
    for key, values in groups.items():
        item = summary(values)
        improvement = -float(item.get("total_call_minus_fold_bb", 0.0))
        item["fold_policy_delta_bb_per_100"] = (
            100.0 * improvement / total_hands if total_hands else 0.0
        )
        summaries[key] = item
    output = {
        "schema": "slumbot_postflop_call_regret.v2",
        "street": args.street,
        "dump_files": [str(path) for path in paths],
        "total_hands": total_hands,
        "malformed_rows": malformed,
        "groups": summaries,
        "details": details,
    }
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(out_path.resolve()),
                "total_hands": total_hands,
                "postflop_calls": len(details),
                "air": summaries.get("strength_4"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
