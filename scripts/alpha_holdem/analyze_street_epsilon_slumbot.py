"""Off-policy screening for one-street epsilon exploration against Slumbot."""
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

from heuristic_policy_v3 import _eval_postflop


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
    # Do not filter on stat size: Windows can expose live flushed contents while
    # another process still reports stale zero-length metadata.
    return sorted(path.resolve() for path in paths if path.is_file())


def weighted_summary(weights: np.ndarray, rewards: np.ndarray) -> dict[str, Any]:
    matched = int((weights > 0).sum())
    total = float(weights.sum())
    if matched == 0 or total <= 0:
        return {"matched_hands": matched, "weight_sum": total, "ess": 0.0}
    mean = float(np.dot(weights, rewards) / total)
    ess = float(total * total / np.dot(weights, weights))
    influence = len(rewards) * weights * (rewards - mean) / total
    se = float(influence.std(ddof=1) / math.sqrt(len(rewards)))
    return {
        "matched_hands": matched,
        "match_rate": matched / len(rewards),
        "weight_sum": total,
        "max_weight": float(weights.max()),
        "ess": ess,
        "mean_bb_per_hand": mean,
        "bb_per_100": 100.0 * mean,
        "se_bb_per_100": 100.0 * se,
        "ci95_lower_bb_per_100": 100.0 * (mean - 1.96 * se),
        "ci95_upper_bb_per_100": 100.0 * (mean + 1.96 * se),
    }


def context(row: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(row["client_pos"]),
        int(float(row.get("to_call", 0)) > 0),
        int(_eval_postflop(row["hero_hole"], row["board"])),
    )


def load_hands(
    paths: list[Path], street: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    malformed = raw_rows = 0
    for path in paths:
        try:
            stream = path.open("r", encoding="utf-8")
        except OSError:
            continue
        with stream:
            for line in stream:
                if not line.strip():
                    continue
                raw_rows += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                groups[(str(path), int(row["hand_idx"]))].append(row)

    hands: list[dict[str, Any]] = []
    invalid = missing = 0
    for key, rows in groups.items():
        rows.sort(key=lambda row: int(row["move_idx"]))
        reward = float(rows[0]["winnings_hero"]) / 100.0
        traced_rows: list[dict[str, Any]] = []
        valid = True
        for row in rows:
            if row.get("who") != "hero":
                continue
            required = (
                row.get("policy_action_slot"),
                row.get("policy_greedy_action_slot"),
                row.get("policy_behavior_probs"),
            )
            if any(value is None for value in required):
                missing += 1
                valid = False
                break
            probabilities = np.asarray(
                row["policy_behavior_probs"], dtype=np.float64
            )
            selected = int(row["policy_action_slot"])
            if (
                selected < 0
                or selected >= len(probabilities)
                or probabilities[selected] <= 0
                or abs(float(probabilities.sum()) - 1.0) > 2e-5
            ):
                invalid += 1
                valid = False
                break
            row_street = int(row["street"])
            traced_rows.append({
                "selected": selected,
                "source": int(row["policy_greedy_action_slot"]),
                "probabilities": probabilities,
                "street": row_street,
                "context": context(row) if row_street == street else None,
            })
        if valid:
            hands.append({
                "key": key,
                "reward": reward,
                "decisions": traced_rows,
            })
    return hands, {
        "dump_files": len(paths),
        "raw_rows": raw_rows,
        "hand_groups": len(groups),
        "eligible_hands": len(hands),
        "hands_with_target_street_decision": sum(
            any(
                int(decision["street"]) == street
                for decision in hand["decisions"]
            )
            for hand in hands
        ),
        "target_street_decisions": sum(
            sum(
                int(decision["street"]) == street
                for decision in hand["decisions"]
            )
            for hand in hands
        ),
        "malformed_rows": malformed,
        "missing_trace_hands": missing,
        "invalid_probability_hands": invalid,
    }


def matches_rule(decision: dict[str, Any], rule: dict[str, Any]) -> bool:
    if int(decision["street"]) != int(rule["street"]):
        return False
    position, facing, strength = decision["context"]
    return (
        (rule["position"] == -1 or position == rule["position"])
        and facing == rule["facing"]
        and (rule["strength"] == -1 or strength == rule["strength"])
        and int(decision["source"]) == rule["replace"]
        and float(decision["probabilities"][rule["force"]]) > 0
    )


def trajectory_weights(
    hands: list[dict[str, Any]],
    rule: dict[str, Any] | None,
) -> np.ndarray:
    result = np.zeros(len(hands), dtype=np.float64)
    for hand_index, hand in enumerate(hands):
        weight = 1.0
        for decision in hand["decisions"]:
            target = int(decision["source"])
            if rule is not None and matches_rule(decision, rule):
                target = int(rule["force"])
            if int(decision["selected"]) != target:
                weight = 0.0
                break
            probability = float(decision["probabilities"][target])
            if probability <= 0:
                weight = 0.0
                break
            weight /= probability
        result[hand_index] = weight
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dumps", nargs="+", required=True)
    parser.add_argument("--street", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--min-affected", type=int, default=12)
    parser.add_argument("--min-observed-action", type=int, default=5)
    args = parser.parse_args()

    paths = discover(args.dumps)
    hands, diagnostics = load_hands(paths, args.street)
    if not hands:
        raise RuntimeError("no hands found")
    rewards = np.asarray([hand["reward"] for hand in hands], dtype=np.float64)
    source_weights = trajectory_weights(hands, None)
    source = weighted_summary(source_weights, rewards)
    source_mean = float(source["mean_bb_per_hand"])
    source_influence = (
        len(hands)
        * source_weights
        * (rewards - source_mean)
        / float(source_weights.sum())
    )

    contexts: dict[tuple[int, int, int, int], int] = defaultdict(int)
    support: dict[tuple[int, int, int, int], set[int]] = defaultdict(set)
    observed: dict[tuple[tuple[int, int, int, int], int], int] = defaultdict(int)
    for hand in hands:
        for decision in hand["decisions"]:
            if int(decision["street"]) != args.street:
                continue
            position, facing, strength = decision["context"]
            for key in {
                (position, facing, strength, int(decision["source"])),
                (-1, facing, strength, int(decision["source"])),
                (position, facing, -1, int(decision["source"])),
                (-1, facing, -1, int(decision["source"])),
            }:
                contexts[key] += 1
                observed[(key, int(decision["selected"]))] += 1
                support[key].update(
                    index
                    for index, probability in enumerate(
                        decision["probabilities"]
                    )
                    if float(probability) > 0
                )

    candidates: list[dict[str, Any]] = []
    for (position, facing, strength, replace), affected in contexts.items():
        if affected < args.min_affected:
            continue
        for force in sorted(support[(position, facing, strength, replace)]):
            if force == replace:
                continue
            observed_forced = observed[
                ((position, facing, strength, replace), force)
            ]
            if observed_forced < args.min_observed_action:
                continue
            rule = {
                "street": args.street,
                "position": position,
                "facing": facing,
                "strength": strength,
                "replace": replace,
                "force": force,
                "affected_decisions": affected,
                "observed_forced_decisions": observed_forced,
            }
            weights = trajectory_weights(hands, rule)
            summary = weighted_summary(weights, rewards)
            if "mean_bb_per_hand" not in summary:
                continue
            mean = float(summary["mean_bb_per_hand"])
            influence = (
                len(hands) * weights * (rewards - mean) / float(weights.sum())
            )
            difference = mean - source_mean
            difference_se = float(
                (influence - source_influence).std(ddof=1)
                / math.sqrt(len(hands))
            )
            candidates.append({
                **rule,
                **summary,
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
        ),
        reverse=True,
    )
    output = {
        "street": args.street,
        "diagnostics": diagnostics,
        "raw_behavior_bb_per_100": 100.0 * float(rewards.mean()),
        "source_policy_trajectory_snips": source,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    destination = Path(args.out_json).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(destination),
        "diagnostics": diagnostics,
        "raw_behavior_bb_per_100": output["raw_behavior_bb_per_100"],
        "source_bb_per_100": source.get("bb_per_100"),
        "source_ess": source.get("ess"),
        "best_candidate": candidates[0] if candidates else None,
    }, indent=2))


if __name__ == "__main__":
    main()
