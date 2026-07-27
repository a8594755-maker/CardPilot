"""Analyze Slumbot hands with randomized preflop and greedy postflop play.

The script has two deliberately small jobs:

1. Estimate first-decision action values inside position/strength/source-action
   cells with inverse-propensity weighting.
2. Evaluate deterministic one-rule preflop overrides with trajectory
   self-normalized importance sampling.  Every later hero preflop decision must
   match the frozen source argmax; postflop is already greedy in the corpus.

The estimates are screening evidence.  A candidate still has to play Slumbot.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from heuristic_policy_v3 import _hand_notation
from heuristic_policy_v4 import PREFLOP_PERCENTILE


def discover(values: Iterable[str]) -> list[Path]:
    paths: set[Path] = set()
    for value in values:
        path = Path(value)
        if path.is_dir():
            paths.update(path.rglob("*_dump.jsonl"))
        elif path.is_file():
            paths.add(path)
        else:
            paths.update(Path(item) for item in glob.glob(value, recursive=True))
    return sorted(path.resolve() for path in paths if path.is_file() and path.stat().st_size)


def first_context(row: dict[str, Any]) -> str | None:
    prefix = str(row.get("action_str_before", ""))
    position = int(row.get("client_pos", -1))
    if position == 1 and prefix == "":
        return "sb_open"
    if position == 0 and prefix.startswith("b") and "/" not in prefix:
        # The first action is the opponent's open and no other action follows it.
        tail = prefix[1:]
        if tail.isdigit():
            return "bb_vs_open"
    if position == 0 and prefix == "c":
        return "bb_vs_limp"
    return "other_preflop"


def summarize_weighted(weights: np.ndarray, rewards: np.ndarray) -> dict[str, Any]:
    positive = weights > 0.0
    count = int(positive.sum())
    total = float(weights.sum())
    if count == 0 or total <= 0.0:
        return {"matched_hands": count, "weight_sum": total, "ess": 0.0}
    mean = float(np.dot(weights, rewards) / total)
    ess = float(total * total / np.dot(weights, weights))
    # Influence-function standard error for a self-normalized mean.
    influence = len(rewards) * weights * (rewards - mean) / total
    se = (
        float(influence.std(ddof=1) / math.sqrt(len(rewards)))
        if len(rewards) > 1
        else 0.0
    )
    return {
        "matched_hands": count,
        "match_rate": float(count / len(rewards)),
        "weight_sum": total,
        "max_weight": float(weights.max()),
        "ess": ess,
        "mean_bb_per_hand": mean,
        "bb_per_100": 100.0 * mean,
        "se_bb_per_100": 100.0 * se,
        "ci95_lower_bb_per_100": 100.0 * (mean - 1.96 * se),
        "ci95_upper_bb_per_100": 100.0 * (mean + 1.96 * se),
    }


def load_hands(paths: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    raw_rows = 0
    malformed = 0
    for path in paths:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                raw_rows += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                grouped[(str(path), int(row["hand_idx"]))].append(row)

    hands: list[dict[str, Any]] = []
    missing_trace = 0
    invalid_probability = 0
    postflop_nongreedy = 0
    for key, rows in grouped.items():
        rows.sort(key=lambda row: int(row["move_idx"]))
        hero_rows = [row for row in rows if row.get("who") == "hero"]
        reward_row = hero_rows[0] if hero_rows else rows[0]
        preflop = [row for row in hero_rows if int(row["street"]) == 0]
        if not preflop:
            hands.append({
                "key": key,
                "reward": float(reward_row["winnings_hero"]) / 100.0,
                "context": None,
                "notation": None,
                "percentile": None,
                "decile": None,
                "first": None,
                "preflop": [],
            })
            continue
        first = preflop[0]
        context = first_context(first)
        traced: list[dict[str, Any]] = []
        valid = True
        for row in preflop:
            required = (
                row.get("policy_action_slot"),
                row.get("policy_greedy_action_slot"),
                row.get("policy_behavior_action_probability"),
                row.get("policy_behavior_probs"),
            )
            if any(value is None for value in required):
                missing_trace += 1
                valid = False
                break
            probability = float(row["policy_behavior_action_probability"])
            probabilities = [float(value) for value in row["policy_behavior_probs"]]
            if (
                not 0.0 < probability <= 1.0
                or abs(sum(probabilities) - 1.0) > 2e-5
                or int(row["policy_action_slot"]) >= len(probabilities)
            ):
                invalid_probability += 1
                valid = False
                break
            traced.append({
                "selected": int(row["policy_action_slot"]),
                "source": int(row["policy_greedy_action_slot"]),
                "probability": probability,
                "probabilities": probabilities,
            })
        if not valid:
            continue
        for row in hero_rows:
            if int(row["street"]) > 0 and (
                int(row.get("policy_action_slot", -1))
                != int(row.get("policy_greedy_action_slot", -2))
            ):
                postflop_nongreedy += 1
        notation = _hand_notation(first["hero_hole"])
        percentile = float(PREFLOP_PERCENTILE[notation])
        hands.append({
            "key": key,
            "reward": float(first["winnings_hero"]) / 100.0,
            "context": context,
            "notation": notation,
            "percentile": percentile,
            "decile": min(9, int(percentile * 10.0)),
            "first": traced[0],
            "preflop": traced,
        })
    diagnostics = {
        "dump_files": len(paths),
        "raw_rows": raw_rows,
        "hero_hand_groups": len(grouped),
        "eligible_hands": len(hands),
        "malformed_json_rows": malformed,
        "hands_missing_trace": missing_trace,
        "hands_with_invalid_probability": invalid_probability,
        "postflop_nongreedy_rows": postflop_nongreedy,
    }
    return hands, diagnostics


def trajectory_weights(
    hands: list[dict[str, Any]],
    rule: dict[str, Any] | None,
) -> np.ndarray:
    weights = np.zeros(len(hands), dtype=np.float64)
    for index, hand in enumerate(hands):
        if not hand["preflop"]:
            weights[index] = 1.0
            continue
        first_target = int(hand["first"]["source"])
        if rule is not None and (
            hand["context"] == rule["context"]
            and rule["minimum"] <= hand["percentile"] < rule["maximum"]
            and first_target == rule["replace"]
            and float(hand["first"]["probabilities"][rule["force"]]) > 0.0
        ):
            first_target = int(rule["force"])
        target_actions = [first_target] + [
            int(row["source"]) for row in hand["preflop"][1:]
        ]
        weight = 1.0
        for target, row in zip(target_actions, hand["preflop"]):
            if int(row["selected"]) != target:
                weight = 0.0
                break
            probability = float(row["probabilities"][target])
            if probability <= 0.0:
                weight = 0.0
                break
            weight /= probability
        weights[index] = weight
    return weights


def action_cells(hands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    for index, hand in enumerate(hands):
        if hand["first"] is None:
            continue
        grouped[
            (hand["context"], int(hand["decile"]), int(hand["first"]["source"]))
        ].append(index)
    rewards = np.asarray([hand["reward"] for hand in hands], dtype=np.float64)
    result: list[dict[str, Any]] = []
    for (context, decile, source), indices in sorted(grouped.items()):
        selection = np.asarray(indices, dtype=np.int64)
        for action in range(9):
            weights = np.zeros(len(selection), dtype=np.float64)
            raw_rewards: list[float] = []
            for local, global_index in enumerate(selection):
                row = hands[int(global_index)]["first"]
                probability = float(row["probabilities"][action])
                if int(row["selected"]) == action and probability > 0.0:
                    weights[local] = 1.0 / probability
                    raw_rewards.append(float(hands[int(global_index)]["reward"]))
            if not raw_rewards:
                continue
            summary = summarize_weighted(weights, rewards[selection])
            result.append({
                "context": context,
                "strength_decile": decile,
                "source_action": source,
                "forced_action": action,
                "eligible_states": len(indices),
                "observed_action_hands": len(raw_rewards),
                "raw_mean_bb": float(np.mean(raw_rewards)),
                **summary,
            })
    return result


def candidate_rules(hands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    ranges: set[tuple[float, float]] = set()
    for lower in np.arange(0.0, 1.0, 0.1):
        ranges.add((round(float(lower), 2), round(float(lower + 0.1), 2)))
    for upper in np.arange(0.05, 0.55, 0.05):
        ranges.add((0.0, round(float(upper), 2)))
    for context in ("sb_open", "bb_vs_open", "bb_vs_limp"):
        context_hands = [hand for hand in hands if hand["context"] == context]
        for minimum, maximum in sorted(ranges):
            band = [
                hand for hand in context_hands
                if minimum <= hand["percentile"] < maximum
            ]
            if not band:
                continue
            replacements = sorted({int(hand["first"]["source"]) for hand in band})
            forces = sorted({
                action
                for hand in band
                for action, probability in enumerate(hand["first"]["probabilities"])
                if float(probability) > 0.0
            })
            for replace in replacements:
                affected = [
                    hand for hand in band
                    if int(hand["first"]["source"]) == replace
                ]
                if len(affected) < 15:
                    continue
                for force in forces:
                    if force == replace:
                        continue
                    supported = sum(
                        float(hand["first"]["probabilities"][force]) > 0.0
                        for hand in affected
                    )
                    if supported != len(affected):
                        continue
                    rules.append({
                        "context": context,
                        "minimum": minimum,
                        "maximum": maximum,
                        "replace": replace,
                        "force": force,
                        "affected_logged_states": len(affected),
                        "supported_logged_states": supported,
                    })
    return rules


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dumps", nargs="+", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--top", type=int, default=40)
    args = parser.parse_args()

    paths = discover(args.dumps)
    if not paths:
        raise FileNotFoundError("no non-empty dump files found")
    hands, diagnostics = load_hands(paths)
    if not hands:
        raise RuntimeError("no eligible preflop-mixed hands")
    rewards = np.asarray([hand["reward"] for hand in hands], dtype=np.float64)

    source_weights = trajectory_weights(hands, None)
    source = summarize_weighted(source_weights, rewards)
    candidates: list[dict[str, Any]] = []
    for rule in candidate_rules(hands):
        weights = trajectory_weights(hands, rule)
        candidate = summarize_weighted(weights, rewards)
        if "mean_bb_per_hand" not in candidate:
            continue
        candidate_influence = (
            len(hands)
            * weights
            * (rewards - float(candidate["mean_bb_per_hand"]))
            / float(weights.sum())
        )
        source_influence = (
            len(hands)
            * source_weights
            * (rewards - float(source["mean_bb_per_hand"]))
            / float(source_weights.sum())
        )
        difference = (
            float(candidate["mean_bb_per_hand"])
            - float(source["mean_bb_per_hand"])
        )
        difference_influence = candidate_influence - source_influence
        difference_se = float(
            difference_influence.std(ddof=1) / math.sqrt(len(hands))
        )
        candidates.append({
            **rule,
            **candidate,
            "delta_bb_per_100": 100.0 * difference,
            "delta_se_bb_per_100": 100.0 * difference_se,
            "delta_ci95_lower_bb_per_100": 100.0 * (
                difference - 1.96 * difference_se
            ),
            "delta_ci95_upper_bb_per_100": 100.0 * (
                difference + 1.96 * difference_se
            ),
        })
    candidates.sort(
        key=lambda row: (
            float(row["delta_ci95_lower_bb_per_100"]),
            float(row["delta_bb_per_100"]),
            float(row["ess"]),
        ),
        reverse=True,
    )
    output = {
        "diagnostics": diagnostics,
        "raw_behavior": {
            "hands": len(hands),
            "bb_per_100": 100.0 * float(rewards.mean()),
            "mean_bb_per_hand": float(rewards.mean()),
        },
        "source_policy_trajectory_snips": source,
        "action_cells": action_cells(hands),
        "candidate_count": len(candidates),
        "top_candidate_rules": candidates[: max(1, int(args.top))],
    }
    destination = Path(args.out_json).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(destination),
        "eligible_hands": len(hands),
        "raw_bb_per_100": output["raw_behavior"]["bb_per_100"],
        "source_bb_per_100": source.get("bb_per_100"),
        "source_ess": source.get("ess"),
        "candidate_count": len(candidates),
        "best_candidate": candidates[0] if candidates else None,
    }, indent=2))


if __name__ == "__main__":
    main()
