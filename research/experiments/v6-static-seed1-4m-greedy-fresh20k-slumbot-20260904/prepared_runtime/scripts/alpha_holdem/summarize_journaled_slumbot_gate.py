"""Seat/session decomposition for journaled Slumbot raw-hand evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.slumbot_ci_from_hands import summarize


def stats(values: list[float]) -> dict:
    return summarize(values, 11.1, 2.0, -11.4275, 20_000)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", action="append", required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    sessions = {}
    seats = {0: [], 1: []}
    all_rewards = []
    for value in args.session_dir:
        directory = Path(value)
        rows = [
            json.loads(line)
            for line in (directory / "hands.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        rewards = [float(row["winnings_bb"]) for row in rows]
        sessions[directory.name] = stats(rewards)
        all_rewards.extend(rewards)
        for row, reward in zip(rows, rewards):
            seats[int(row["terminal_response"]["client_pos"])].append(reward)
    overall = stats(all_rewards)
    seat_stats = {str(seat): stats(values) for seat, values in seats.items()}
    admission = (
        overall["bb_per_100"] > -11.4275
        and all(row["bb_per_100"] > -50 for row in seat_stats.values())
    )
    clear_rejection = (
        overall["upper_bound_bb_per_100"] < -11.4275
        and all(row["bb_per_100"] < -25 for row in seat_stats.values())
    )
    result = {
        "schema": "cardpilot.journaled_slumbot_gate_summary.v1",
        "overall": overall,
        "seats": seat_stats,
        "sessions": sessions,
        "preregistered": {
            "admit_fresh20k": admission,
            "clear_external_alignment_rejection": clear_rejection,
            "decision": (
                "ADMIT_FRESH20K" if admission else
                "REJECT_EXTERNAL_ALIGNMENT" if clear_rejection else
                "HOLD_FOR_DIAGNOSTIC"
            ),
        },
    }
    args.out_json.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
