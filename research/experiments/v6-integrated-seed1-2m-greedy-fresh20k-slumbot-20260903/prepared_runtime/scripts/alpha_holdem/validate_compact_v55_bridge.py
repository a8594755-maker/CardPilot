"""Validate compact CFR rows against the deployed AlphaHoldem v55 engine.

The converter and the Python environment are independent implementations.  This
tool replays every compact row through ``HUNLGameState`` and compares actor,
street, pot, stacks, raise count, to-call amount, legal mask, and target support.
It is a representation gate, not a poker-strength metric.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from alpha_holdem.environment_v55 import build_action_table
from deep_cfr.game_state import (
    Action,
    ActionType,
    BetSizeConfig,
    GameConfig,
    HUNLGameState,
    Street,
)


ACTION_TYPES = {
    "FOLD": ActionType.FOLD,
    "CHECK": ActionType.CHECK,
    "CALL": ActionType.CALL,
    "BET": ActionType.BET,
    "RAISE": ActionType.RAISE,
    "ALLIN": ActionType.ALLIN,
}
STREETS = {"FLOP": Street.FLOP, "TURN": Street.TURN, "RIVER": Street.RIVER}
V55_FRACTIONS = [0.33, 0.50, 0.67, 0.75, 1.00, 1.50]


def resolve_inputs(values: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        path = Path(value)
        if path.is_dir():
            paths.extend(sorted(path.glob("flop_*.jsonl")))
        else:
            matches = [Path(item) for item in glob.glob(value)]
            paths.extend(matches or [path])
    resolved = sorted({path.resolve() for path in paths})
    missing = [str(path) for path in resolved if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing inputs: {missing}")
    if not resolved:
        raise ValueError("no compact JSONL inputs resolved")
    return resolved


def rows(paths: Iterable[Path]) -> Iterator[tuple[Path, int, dict[str, Any]]]:
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if line.strip():
                    yield path, line_no, json.loads(line)


def initial_state(row: dict[str, Any]) -> HUNLGameState:
    preflop = row.get("preflop") or {}
    topology = str(preflop.get("topology", "single_raised"))
    if topology == "three_bet":
        pot, stack = 17.5, 191.25
    elif topology == "single_raised":
        pot, stack = 5.0, 197.5
    else:
        raise ValueError(f"unsupported compact topology: {topology}")
    config = GameConfig(
        starting_pot=pot,
        effective_stack=stack,
        bet_sizes=BetSizeConfig(
            flop=V55_FRACTIONS,
            turn=V55_FRACTIONS,
            river=V55_FRACTIONS,
        ),
        # HUNLEnvironmentV55 overrides the postflop cap to effectively
        # unlimited.  The solver's cap=1 is an abstraction choice and should
        # therefore show up as a legal-mask support gap here.
        raise_cap_per_street=999,
        include_preflop=False,
    )
    return HUNLGameState(config)


def replay(row: dict[str, Any]) -> HUNLGameState:
    state = initial_state(row)
    for event in row.get("events", []):
        expected_street = STREETS[str(event["street"])]
        if state.street != expected_street:
            raise ValueError(
                f"event street mismatch: engine={state.street.name} row={expected_street.name}"
            )
        if int(event["player"]) != state.current_player:
            raise ValueError(
                f"event actor mismatch: engine={state.current_player} row={event['player']}"
            )
        action_type = ACTION_TYPES[str(event["actionType"])]
        amount = 0.0
        if action_type in {ActionType.BET, ActionType.RAISE, ActionType.ALLIN}:
            committed = float(state.street_committed[state.current_player])
            if action_type == ActionType.ALLIN:
                # Reconstruct the semantic all-in from the live engine's exact
                # residual stack.  Serialized TypeScript amounts can differ by
                # ~1e-14 and otherwise leave a phantom stack, suppress the
                # engine's aggressive-action count, and expose bogus raises.
                amount = committed + float(state.stacks[state.current_player])
            else:
                additional = float(event.get("additionalAmount") or 0.0)
                amount = committed + additional
        state = state.apply(Action(action_type, amount))
    return state


def mask_text(mask: Iterable[float | int]) -> str:
    return "".join("1" if float(value) > 0 else "0" for value in mask)


def validate(paths: list[Path], raise_action_mapping: str) -> dict[str, Any]:
    total = 0
    target_failures = 0
    replay_failures = Counter()
    state_mismatches = Counter()
    mismatch_examples: dict[str, list[dict[str, Any]]] = {}
    mask_pairs = Counter()
    topology_rows = Counter()
    max_abs_delta = Counter()

    for path, line_no, row in rows(paths):
        total += 1
        if row.get("schema") != "cfr.v55.compact.v1":
            raise ValueError(f"{path}:{line_no}: unexpected schema {row.get('schema')!r}")
        target = np.asarray(row["target"], dtype=np.float64)
        source_mask = np.asarray(row["legalMask"], dtype=np.float64)
        if (
            target.shape != (9,)
            or source_mask.shape != (9,)
            or not np.all(np.isfinite(target))
            or abs(float(target.sum()) - 1.0) > 1e-5
            or np.any(target < -1e-9)
            or np.any(target[source_mask <= 0] > 1e-7)
        ):
            target_failures += 1

        topology_rows[str((row.get("preflop") or {}).get("topology", "single_raised"))] += 1
        try:
            state = replay(row)
        except ValueError as error:
            replay_failures[str(error)] += 1
            continue

        expected = row["state"]
        scalar_pairs = {
            "pot": (float(state.pot), float(expected["pot"])),
            "stack0": (float(state.stacks[0]), float(expected["stacks"][0])),
            "stack1": (float(state.stacks[1]), float(expected["stacks"][1])),
            "to_call": (
                max(
                    float(state.street_committed[1 - state.current_player])
                    - float(state.street_committed[state.current_player]),
                    0.0,
                ),
                float(expected.get("toCall", 0.0)),
            ),
        }
        for name, (actual, wanted) in scalar_pairs.items():
            delta = abs(actual - wanted)
            max_abs_delta[name] = max(float(max_abs_delta[name]), delta)
            if delta > 1e-6:
                state_mismatches[name] += 1
        if state.current_player != int(expected["currentPlayer"]):
            state_mismatches["current_player"] += 1
        if state.street != STREETS[str(expected["street"])]:
            state_mismatches["street"] += 1
        expected_raise_count = int(expected.get("raiseCount", 0))
        if state.raise_count != expected_raise_count:
            state_mismatches["raise_count"] += 1
            mismatch_examples.setdefault("raise_count", [])
            if len(mismatch_examples["raise_count"]) < 10:
                mismatch_examples["raise_count"].append(
                    {
                        "path": str(path),
                        "line": line_no,
                        "historyKey": row.get("historyKey"),
                        "engine": int(state.raise_count),
                        "row": expected_raise_count,
                        "events": row.get("events", []),
                    }
                )
        aggressive_event_count = sum(
            1
            for event in row.get("events", [])
            if str(event["street"]) == str(row["street"])
            and str(event["actionType"]) in {"BET", "RAISE", "ALLIN"}
        )
        if state.raise_count != aggressive_event_count:
            state_mismatches["raise_count_event_replay"] += 1
            mismatch_examples.setdefault("raise_count_event_replay", [])
            if len(mismatch_examples["raise_count_event_replay"]) < 10:
                mismatch_examples["raise_count_event_replay"].append(
                    {
                        "path": str(path),
                        "line": line_no,
                        "historyKey": row.get("historyKey"),
                        "engine": int(state.raise_count),
                        "events_count": aggressive_event_count,
                        "events": row.get("events", []),
                    }
                )

        engine_mask, _ = build_action_table(state, raise_action_mapping)
        source_text = mask_text(source_mask)
        engine_text = mask_text(engine_mask)
        mask_pairs[f"{source_text}->{engine_text}"] += 1

    exact_masks = sum(
        count for pair, count in mask_pairs.items() if pair.split("->", 1)[0] == pair.split("->", 1)[1]
    )
    # Per-field counters intentionally do not permit deriving a union.  The
    # mask equality and field-wise rates are both reported explicitly.
    return {
        "schema": "cardpilot.compact_v55_bridge_validation.v1",
        "claim_scope": "REPRESENTATION_PARITY_NOT_POLICY_STRENGTH",
        "inputs": [str(path) for path in paths],
        "raise_action_mapping": raise_action_mapping,
        "rows": total,
        "topology_rows": dict(topology_rows),
        "target_failures": target_failures,
        "replay_failures": dict(replay_failures),
        "state_field_mismatches": dict(state_mismatches),
        "state_field_mismatch_examples": mismatch_examples,
        "max_abs_state_delta": {key: float(value) for key, value in max_abs_delta.items()},
        "mask_exact_rows": exact_masks,
        "mask_exact_fraction": exact_masks / max(total, 1),
        "mask_pairs": [
            {"pair": pair, "rows": count, "fraction": count / max(total, 1)}
            for pair, count in mask_pairs.most_common()
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--raise-action-mapping",
        choices=("legacy_total_over_pot", "preflop_pot_fraction_v2", "pot_fraction_v2"),
        default="preflop_pot_fraction_v2",
    )
    args = parser.parse_args()
    report = validate(resolve_inputs(args.input), args.raise_action_mapping)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "rows": report["rows"],
        "target_failures": report["target_failures"],
        "replay_failures": sum(report["replay_failures"].values()),
        "state_field_mismatches": report["state_field_mismatches"],
        "mask_exact_fraction": report["mask_exact_fraction"],
        "out": str(args.out),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
