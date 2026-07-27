#!/usr/bin/env python3
"""Estimate first-on-street action effects from randomized Slumbot traces.

Only the hero's first decision on the selected street is compared. Because the
street-epsilon behavior has not randomized an earlier hero action on that
street, the reached-state distribution is source-policy compatible. Later hero
decisions on the same street are importance-weighted back to the greedy source
continuation. Within each coarse context, logged action propensities therefore
provide a randomized comparison between the source action and each alternative.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
from collections import defaultdict
from pathlib import Path

from heuristic_policy_v3 import _eval_postflop

BIG_BLIND = 100.0


def expand_inputs(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matches = glob.glob(pattern)
        paths.extend(Path(match) for match in (matches or [pattern]))
    return sorted({path.resolve() for path in paths if path.is_file()})


def hajek(rows: list[dict], action: int) -> tuple[float, float, int] | None:
    selected: list[tuple[float, float]] = []
    for row in rows:
        if int(row["action"]) != action:
            continue
        probability = float(row["probs"][action])
        continuation_weight = float(row["continuation_weight"])
        if probability <= 0.0 or continuation_weight <= 0.0:
            continue
        selected.append(
            (continuation_weight / probability, float(row["return_bb"]))
        )
    if not selected:
        return None
    weight_sum = sum(weight for weight, _ in selected)
    mean = sum(weight * value for weight, value in selected) / weight_sum
    # First-order Hájek influence standard error. Each row is from a distinct
    # hand because only the first hero decision on the street is retained.
    variance = sum((weight * (value - mean)) ** 2 for weight, value in selected)
    se = math.sqrt(variance) / weight_sum if len(selected) > 1 else math.inf
    return mean, se, len(selected)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dumps", nargs="+", required=True)
    parser.add_argument("--street", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--min-context", type=int, default=20)
    parser.add_argument("--min-action", type=int, default=5)
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args()

    paths = expand_inputs(args.dumps)
    street_rows: dict[tuple[str, int], list[dict]] = defaultdict(list)
    all_hands: set[tuple[str, int]] = set()
    malformed = 0
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    raw = json.loads(line)
                    hand_key = (str(path), int(raw["hand_idx"]))
                    all_hands.add(hand_key)
                    if (
                        raw.get("who") != "hero"
                        or int(raw.get("street", -1)) != args.street
                        or "policy_behavior_probs" not in raw
                        or "policy_greedy_action_slot" not in raw
                    ):
                        continue
                    mask = [float(value) for value in raw["policy_legal_mask"]]
                    probs = [float(value) for value in raw["policy_behavior_probs"]]
                    if len(mask) != len(probs) or not any(probs):
                        continue
                    street_rows[hand_key].append({
                        "move_idx": int(raw["move_idx"]),
                        "position": int(raw["client_pos"]),
                        "facing": int(float(raw.get("to_call", 0)) > 0),
                        "strength": int(
                            _eval_postflop(raw["hero_hole"], raw["board"])
                        ),
                        "source": int(raw["policy_greedy_action_slot"]),
                        "action": int(raw["policy_action_slot"]),
                        "mask": mask,
                        "probs": probs,
                        "return_bb": float(raw["winnings_hero"]) / BIG_BLIND,
                    })
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    malformed += 1

    contexts: dict[tuple[int, int, int, int], list[dict]] = defaultdict(list)
    first_rows: dict[tuple[str, int], dict] = {}
    for hand_key, rows in street_rows.items():
        rows.sort(key=lambda row: int(row["move_idx"]))
        first = rows[0]
        continuation_weight = 1.0
        for later in rows[1:]:
            later_source = int(later["source"])
            probability = float(later["probs"][later_source])
            if int(later["action"]) != later_source or probability <= 0.0:
                continuation_weight = 0.0
                break
            continuation_weight *= 1.0 / probability
        first["continuation_weight"] = continuation_weight
        first_rows[hand_key] = first
    for row in first_rows.values():
        key = (
            row["position"],
            row["facing"],
            row["strength"],
            row["source"],
        )
        contexts[key].append(row)

    results: list[dict] = []
    total_hands = len(all_hands)
    for (position, facing, strength, source), context_rows in contexts.items():
        if len(context_rows) < args.min_context:
            continue
        for force in range(len(context_rows[0]["mask"])):
            if force == source:
                continue
            eligible = [row for row in context_rows if row["mask"][force] > 0.0]
            if len(eligible) < args.min_context:
                continue
            source_estimate = hajek(eligible, source)
            force_estimate = hajek(eligible, force)
            if source_estimate is None or force_estimate is None:
                continue
            source_mean, source_se, source_count = source_estimate
            force_mean, force_se, force_count = force_estimate
            if min(source_count, force_count) < args.min_action:
                continue
            delta = force_mean - source_mean
            delta_se = math.sqrt(source_se**2 + force_se**2)
            reach_rate = len(eligible) / total_hands if total_hands else 0.0
            scale = 100.0 * reach_rate
            results.append(
                {
                    "street": args.street,
                    "position": position,
                    "facing": facing,
                    "strength": strength,
                    "replace": source,
                    "force": force,
                    "context_hands": len(context_rows),
                    "eligible_hands": len(eligible),
                    "source_observed": source_count,
                    "force_observed": force_count,
                    "source_mean_return_bb": source_mean,
                    "force_mean_return_bb": force_mean,
                    "delta_bb_per_reached_hand": delta,
                    "delta_se_bb_per_reached_hand": delta_se,
                    "reach_rate_per_hand": reach_rate,
                    "policy_delta_bb_per_100": scale * delta,
                    "policy_delta_ci95_lower_bb_per_100": scale
                    * (delta - 1.96 * delta_se),
                    "policy_delta_ci95_upper_bb_per_100": scale
                    * (delta + 1.96 * delta_se),
                }
            )

    results.sort(
        key=lambda row: (
            float(row["policy_delta_ci95_lower_bb_per_100"]),
            float(row["policy_delta_bb_per_100"]),
        ),
        reverse=True,
    )
    output = {
        "schema": "slumbot_first_street_action_rct.v2",
        "street": args.street,
        "dump_files": [str(path) for path in paths],
        "total_hands": total_hands,
        "first_street_decisions": len(first_rows),
        "malformed_rows": malformed,
        "min_context": args.min_context,
        "min_action": args.min_action,
        "candidates": results,
    }
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(out_path.resolve()),
                "total_hands": total_hands,
                "first_street_decisions": len(first_rows),
                "candidates": len(results),
                "best_candidate": results[0] if results else None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
