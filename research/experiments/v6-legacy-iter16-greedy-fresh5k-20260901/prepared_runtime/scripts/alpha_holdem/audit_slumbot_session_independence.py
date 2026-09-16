"""Audit that parallel Slumbot parts do not replay one shared deal stream."""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


def resolve_inputs(specs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for spec in specs:
        matches = [Path(value).resolve() for value in glob.glob(spec)]
        if not matches and Path(spec).is_file():
            matches = [Path(spec).resolve()]
        paths.extend(matches)
    unique = sorted(set(paths))
    if len(unique) != len(paths):
        raise ValueError("duplicate or overlapping dump inputs")
    if len(unique) < 2:
        raise ValueError("independence audit requires at least two dump files")
    return unique


def load_hands(path: Path) -> tuple[dict[int, list[dict]], int]:
    hands: dict[int, list[dict]] = defaultdict(list)
    malformed = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                # A live writer can expose one incomplete trailing line.
                malformed += 1
                continue
            hands[int(row["hand_idx"])].append(row)
    return dict(hands), malformed


def fingerprint(rows: list[dict]) -> str:
    ordered = sorted(rows, key=lambda row: int(row["move_idx"]))
    first = ordered[0]
    board = max((tuple(row.get("board") or []) for row in ordered), key=len)
    opponent = next(
        (
            tuple(sorted(row["opp_hole"]))
            for row in ordered
            if row.get("opp_hole")
        ),
        (),
    )
    payload = {
        "client_pos": int(first["client_pos"]),
        "hero_hole": sorted(first.get("hero_hole") or []),
        "opp_hole": list(opponent),
        "board": list(board),
        "actions": [
            [str(row["action_move"]), int(row.get("action_amount", 0))]
            for row in ordered
        ],
        "winnings": int(ordered[-1].get("winnings_hero", 0)),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def longest_run(indices: list[int]) -> int:
    best = current = 0
    previous = None
    for index in sorted(indices):
        if previous is not None and index == previous + 1:
            current += 1
        else:
            current = 1
        best = max(best, current)
        previous = index
    return best


def initial_deal_fingerprint(rows: list[dict]) -> str:
    """Action-independent observable deal identity; hidden deck is not inferred."""
    identities = []
    for row in rows:
        cards = row.get('hero_hole')
        position = row.get('client_pos')
        if (type(position) is not int or position not in (0, 1)
                or not isinstance(cards, list) or len(cards) != 2
                or any(not isinstance(card, str) or not re.fullmatch(r'[2-9TJQKA][cdhs]', card) for card in cards)
                or len(set(cards)) != 2):
            raise ValueError('Missing or invalid initial hero cards/seat')
        identities.append((position, tuple(sorted(cards))))
    if not identities or any(value != identities[0] for value in identities):
        raise ValueError('Initial hero cards/seat change within one hand')
    return hashlib.sha256(json.dumps(identities[0]).encode()).hexdigest()


def consecutive_windows(mapping: dict[int, str], width: int = 5) -> set[tuple[str, ...]]:
    return {tuple(mapping[index+j] for j in range(width)) for index in mapping
            if all(index+j in mapping for j in range(width))}


def audit_paths(paths: list[Path]) -> dict:
    paths = resolve_inputs([str(path) for path in paths])
    sessions: dict[str, dict] = {}
    fingerprints: dict[str, dict[int, str]] = {}
    initial_fingerprints: dict[str, dict[int, str]] = {}
    for path in paths:
        label = path.stem.removesuffix("_dump")
        if label in sessions:
            raise ValueError(f"duplicate session label: {label}")
        hands, malformed = load_hands(path)
        if not hands:
            raise ValueError(f"dump has no complete rows: {path}")
        per_hand = {index: fingerprint(rows) for index, rows in hands.items()}
        positions = Counter(
            int(sorted(rows, key=lambda row: int(row["move_idx"]))[0]["client_pos"])
            for rows in hands.values()
        )
        fingerprints[label] = per_hand
        initial_fingerprints[label] = {index: initial_deal_fingerprint(rows) for index, rows in hands.items()}
        sessions[label] = {
            "path": str(path),
            "hands_observed": len(hands),
            "bb_hands": positions[0],
            "sb_hands": positions[1],
            "unique_fingerprints": len(set(per_hand.values())),
            "malformed_lines_while_live": malformed,
        }

    pairwise = []
    labels = sorted(sessions)
    for left_index, left in enumerate(labels):
        left_map = fingerprints[left]
        for right in labels[left_index + 1 :]:
            right_map = fingerprints[right]
            common_indices = sorted(set(left_map) & set(right_map))
            matches = [
                index
                for index in common_indices
                if left_map[index] == right_map[index]
            ]
            overlap = len(set(left_map.values()) & set(right_map.values()))
            initial_left, initial_right = initial_fingerprints[left], initial_fingerprints[right]
            initial_matches = [index for index in common_indices if initial_left[index] == initial_right[index]]
            shifted_windows = len(consecutive_windows(initial_left) & consecutive_windows(initial_right))
            pairwise.append(
                {
                    "left": left,
                    "right": right,
                    "common_hand_indices": len(common_indices),
                    "same_index_exact_fingerprint_matches": len(matches),
                    "same_index_match_fraction": (
                        len(matches) / len(common_indices) if common_indices else 0.0
                    ),
                    "longest_consecutive_same_index_match_run": longest_run(matches),
                    "fingerprint_overlap_at_any_index": overlap,
                    "same_index_initial_deal_matches": len(initial_matches),
                    "same_index_initial_deal_match_fraction": len(initial_matches)/len(common_indices) if common_indices else 0.,
                    "longest_consecutive_initial_deal_match_run": longest_run(initial_matches),
                    "shared_five_hand_initial_deal_windows_at_any_offset": shifted_windows,
                }
            )

    checks = {
        "no_malformed_final_jsonl": all(row['malformed_lines_while_live'] == 0 for row in sessions.values()),
        "at_least_two_sessions": len(sessions) >= 2,
        "aggregate_contains_both_seats": (
            sum(row["bb_hands"] for row in sessions.values()) > 0
            and sum(row["sb_hands"] for row in sessions.values()) > 0
        ),
        "seat_coverage_plausible_in_every_part": all(
            (row["hands_observed"] == 1)
            or (row["bb_hands"] > 0 and row["sb_hands"] > 0)
            for row in sessions.values()
        ),
        "no_pair_has_three_consecutive_identical_deals": all(
            row["longest_consecutive_same_index_match_run"] < 3
            for row in pairwise
        ),
        "no_pair_has_over_one_percent_same_index_matches": all(
            row["same_index_match_fraction"] <= 0.01 for row in pairwise
        ),
        "no_three_consecutive_same_index_initial_deals": all(
            row['longest_consecutive_initial_deal_match_run'] < 3 for row in pairwise),
        "no_excess_initial_matches_on_at_least100_common_indices": all(
            row['common_hand_indices'] < 100 or row['same_index_initial_deal_match_fraction'] <= .01
            for row in pairwise),
        "no_five_hand_initial_stream_replay_at_any_offset": all(
            row['shared_five_hand_initial_deal_windows_at_any_offset'] == 0 for row in pairwise),
    }
    output = {
        "schema": "cardpilot.slumbot_session_independence_audit.v3",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "claim_scope": (
            "DEAL_STREAM_AND_SEAT_INDEPENDENCE_DIAGNOSTIC_ONLY_"
            "NOT_STRENGTH_NOT_HAND_COUNT_AUDIT"
        ),
        "sessions": sessions,
        "pairwise": pairwise,
        "checks": checks,
        "interpretation": (
            "Each base or supplement process obtains its own opaque Slumbot token "
            "from new_hand. A one-hand supplement can legitimately contain only "
            "one seat; longer parts must contain both seats. "
            "This audit stores no token and retains full deal/action fingerprints plus "
            "action-independent initial hero-card/seat fingerprints. It detects aligned "
            "or shifted observable replay, not hidden-deck identity or full statistical independence. "
            "Three aligned matches or five consecutive matches at any offset fail; "
            "initial-match fractions are screened only with at least100 common indices."
        ),
    }
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", nargs="+", required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    output = audit_paths(resolve_inputs(args.dump))
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if output['status'] == 'PASS' else 1


if __name__ == "__main__":
    raise SystemExit(main())
