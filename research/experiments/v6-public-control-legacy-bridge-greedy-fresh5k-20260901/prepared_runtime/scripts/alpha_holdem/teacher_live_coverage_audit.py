"""Measure compact-CFR support coverage of live AlphaHoldem decision states.

This is a data/representation diagnostic, not a policy selector.  Compact CFR
rows are compared with hero decisions from ``play_slumbot.py --dump-slumbot``
using progressively stricter public-state signatures.  The report highlights
which live topologies need additional learned-policy training data.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator


STREET_NAMES = ("PREFLOP", "FLOP", "TURN", "RIVER")
TEACHER_PREFLOP_SHAPE = "BC"
ACTION_RE = re.compile(r"([fkcx]|b\d+)")
POT_BUCKETS = (2.0, 5.0, 10.0, 20.0, 40.0, 80.0, 160.0)
SPR_BUCKETS = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_inputs(values: Iterable[str], *, teacher: bool = False) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        path = Path(value)
        if teacher and path.is_dir():
            paths.extend(sorted(path.glob("flop_*.jsonl")))
            continue
        matches = [Path(item) for item in glob.glob(value)]
        paths.extend(matches or [path])
    unique = sorted({path.resolve() for path in paths})
    missing = [str(path) for path in unique if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing input files: {missing}")
    if not unique:
        raise ValueError("no input files resolved")
    return unique


def jsonl_rows(paths: Iterable[Path]) -> Iterator[dict[str, Any]]:
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"{path}:{line_no}: {error}") from error


def bucket(value: float, boundaries: tuple[float, ...]) -> str:
    if not math.isfinite(value):
        return "inf"
    lower = 0.0
    for upper in boundaries:
        if value < upper:
            return f"[{lower:g},{upper:g})"
        lower = upper
    return f"[{lower:g},inf)"


def mask_signature(mask: Iterable[float | int]) -> str:
    values = list(mask)
    if len(values) != 9:
        raise ValueError(f"expected 9-slot legal mask, got {len(values)}")
    return "".join("1" if float(value) > 0 else "0" for value in values)


def action_shape(action_str: str) -> tuple[str, ...]:
    """Normalize a Slumbot action string to public action-type shapes."""
    shapes: list[str] = []
    for street in action_str.split("/"):
        tokens = ACTION_RE.findall(street)
        shapes.append(
            "".join(
                "B"
                if token.startswith("b")
                else "K"
                if token == "x"
                else token.upper()
                for token in tokens
            )
        )
    return tuple(shapes)


def preflop_topology(preflop_shape: str) -> str:
    bets = preflop_shape.count("B")
    if bets == 0:
        return "limped_or_checked"
    if bets == 1:
        return "single_raised"
    if bets == 2:
        return "three_bet"
    return "four_bet_plus"


def teacher_history_shape(row: dict[str, Any]) -> tuple[str, ...]:
    current_street = STREET_NAMES.index(str(row["street"]))
    preflop = row.get("preflop") or {}
    preflop_shape = str(preflop.get("historyShape", TEACHER_PREFLOP_SHAPE))
    streets = [preflop_shape] + ["" for _ in range(current_street)]
    for event in row.get("events", []):
        event_street = STREET_NAMES.index(str(event["street"]))
        action_type = str(event["actionType"])
        symbol = (
            "B"
            if action_type in {"BET", "RAISE", "ALLIN"}
            else "C"
            if action_type == "CALL"
            else "K"
            if action_type == "CHECK"
            else "F"
        )
        streets[event_street] += symbol
    return tuple(streets)


def position_name_from_teacher(player: int) -> str:
    # HUNLGameState player 0 posts BB; player 1 posts SB/button.
    return "BB" if player == 0 else "SB"


def position_name_from_dump(client_pos: int) -> str:
    # Slumbot protocol client_pos 0 is BB/OOP; client_pos 1 is SB/button.
    return "BB" if client_pos == 0 else "SB"


def teacher_signature(row: dict[str, Any]) -> dict[str, Any]:
    history = teacher_history_shape(row)
    street_index = STREET_NAMES.index(str(row["street"]))
    state = row["state"]
    stacks = [float(value) for value in state["stacks"]]
    pot = float(state["pot"])
    spr = min(stacks) / max(pot, 1e-9)
    return {
        "street": STREET_NAMES[street_index],
        "position": position_name_from_teacher(int(row["player"])),
        "topology": preflop_topology(history[0]),
        "facing_bet": float(state.get("toCall", 0.0)) > 1e-9,
        "raise_count": int(state.get("raiseCount", 0)),
        "legal_mask": mask_signature(row["legalMask"]),
        "history": "/".join(history),
        "current_depth": len(history[-1]),
        "pot_bucket": bucket(pot, POT_BUCKETS),
        "spr_bucket": bucket(spr, SPR_BUCKETS),
    }


def dump_signature(row: dict[str, Any]) -> dict[str, Any]:
    street_index = int(row["street"])
    history = action_shape(str(row.get("action_str_before", "")))
    if len(history) <= street_index:
        history = history + tuple("" for _ in range(street_index + 1 - len(history)))
    pot = float(row["pot_before"]) / 100.0
    hero_stack = float(row["stack_remaining"]) / 100.0
    opponent_stack = max(0.0, 400.0 - pot - hero_stack)
    spr = min(hero_stack, opponent_stack) / max(pot, 1e-9)
    current_shape = history[street_index]
    return {
        "street": STREET_NAMES[street_index],
        "position": position_name_from_dump(int(row["client_pos"])),
        "topology": preflop_topology(history[0]),
        "facing_bet": float(row.get("to_call", 0.0)) > 0.0,
        "raise_count": current_shape.count("B"),
        "legal_mask": mask_signature(row["policy_legal_mask"]),
        "history": "/".join(history[: street_index + 1]),
        "current_depth": len(current_shape),
        "pot_bucket": bucket(pot, POT_BUCKETS),
        "spr_bucket": bucket(spr, SPR_BUCKETS),
    }


KEY_LEVELS: dict[str, tuple[str, ...]] = {
    "street": ("street",),
    "street_position": ("street", "position"),
    "topology": ("street", "position", "topology"),
    "public_shape_no_mask": (
        "street",
        "position",
        "topology",
        "facing_bet",
        "raise_count",
        "current_depth",
    ),
    "public_shape_with_mask": (
        "street",
        "position",
        "topology",
        "facing_bet",
        "raise_count",
        "current_depth",
        "legal_mask",
    ),
    "history_shape_no_mask": (
        "street",
        "position",
        "topology",
        "history",
    ),
    "history_shape_with_mask": (
        "street",
        "position",
        "topology",
        "history",
        "legal_mask",
    ),
    "history_pot_spr_no_mask": (
        "street",
        "position",
        "topology",
        "history",
        "pot_bucket",
        "spr_bucket",
    ),
    "history_pot_spr_with_mask": (
        "street",
        "position",
        "topology",
        "history",
        "legal_mask",
        "pot_bucket",
        "spr_bucket",
    ),
}


def key_for(signature: dict[str, Any], fields: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(signature[field] for field in fields)


def counter_rows(counter: Counter[str], total: int) -> list[dict[str, Any]]:
    return [
        {"key": key, "decisions": count, "fraction": count / max(total, 1)}
        for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def audit(
    teacher_paths: list[Path],
    dump_paths: list[Path],
) -> dict[str, Any]:
    support: dict[str, set[tuple[Any, ...]]] = {
        level: set() for level in KEY_LEVELS
    }
    teacher_counts = Counter()
    teacher_masks = Counter()
    teacher_rows = 0
    teacher_boards: set[int] = set()
    for row in jsonl_rows(teacher_paths):
        if row.get("schema") != "cfr.v55.compact.v1":
            raise ValueError(f"unexpected teacher schema: {row.get('schema')!r}")
        signature = teacher_signature(row)
        teacher_rows += 1
        teacher_boards.add(int(row["boardId"]))
        teacher_counts[
            f"{signature['street']}|{signature['position']}|{signature['topology']}"
        ] += 1
        teacher_masks[signature["legal_mask"]] += 1
        for level, fields in KEY_LEVELS.items():
            support[level].add(key_for(signature, fields))

    live_counts = Counter()
    live_masks = Counter()
    live_total = 0
    live_postflop_total = 0
    covered = Counter()
    unsupported = {level: Counter() for level in KEY_LEVELS}
    unique_hands: set[tuple[str, int]] = set()
    for path in dump_paths:
        session = path.stem.replace("_dump", "")
        for row in jsonl_rows([path]):
            if row.get("who") != "hero" or "policy_legal_mask" not in row:
                continue
            signature = dump_signature(row)
            live_total += 1
            if signature["street"] != "PREFLOP":
                live_postflop_total += 1
            unique_hands.add((session, int(row["hand_idx"])))
            category = (
                f"{signature['street']}|{signature['position']}|"
                f"{signature['topology']}"
            )
            live_counts[category] += 1
            live_masks[signature["legal_mask"]] += 1
            for level, fields in KEY_LEVELS.items():
                key = key_for(signature, fields)
                if key in support[level]:
                    covered[level] += 1
                else:
                    unsupported[level][category] += 1

    coverage = {}
    for level in KEY_LEVELS:
        coverage[level] = {
            "covered_decisions": int(covered[level]),
            "total_live_decisions": live_total,
            "total_live_postflop_decisions": live_postflop_total,
            "fraction": covered[level] / max(live_total, 1),
            "fraction_all_live": covered[level] / max(live_total, 1),
            "fraction_postflop": covered[level]
            / max(live_postflop_total, 1),
            "teacher_unique_keys": len(support[level]),
            "largest_unsupported_categories": counter_rows(
                unsupported[level], live_total
            )[:20],
        }

    topology_total = Counter()
    for key, count in live_counts.items():
        topology_total[key.rsplit("|", 1)[-1]] += count

    return {
        "schema": "cardpilot.teacher_live_coverage.v1",
        "claim_scope": "DATA_SUPPORT_DIAGNOSTIC_NOT_POLICY_STRENGTH",
        "teacher": {
            "files": len(teacher_paths),
            "rows": teacher_rows,
            "boards": len(teacher_boards),
            "distribution": counter_rows(teacher_counts, teacher_rows),
            "legal_mask_distribution": counter_rows(
                teacher_masks, teacher_rows
            ),
        },
        "live": {
            "files": len(dump_paths),
            "hands": len(unique_hands),
            "hero_decisions": live_total,
            "hero_postflop_decisions": live_postflop_total,
            "distribution": counter_rows(live_counts, live_total),
            "topology_distribution": counter_rows(topology_total, live_total),
            "legal_mask_distribution": counter_rows(live_masks, live_total),
        },
        "coverage": coverage,
        "interpretation": {
            "street_and_position_only": "Sanity ceiling; not sufficient support.",
            "topology": "Requires the same preflop pot family as teacher data.",
            "public_shape_no_mask": "Adds facing-bet, raise-count, and current-depth support.",
            "public_shape_with_mask": "Also requires the same legal action-slot abstraction.",
            "history_shape_no_mask": "Adds the complete normalized public action-type history.",
            "history_shape_with_mask": "Also requires the same legal action-slot abstraction.",
            "history_pot_spr_no_mask": "Adds coarse pot and effective-stack-to-pot regime support.",
            "history_pot_spr_with_mask": "Also requires the same legal action-slot abstraction.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher", nargs="+", required=True)
    parser.add_argument("--dumps", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    teacher_paths = resolve_inputs(args.teacher, teacher=True)
    dump_paths = resolve_inputs(args.dumps)
    report = audit(teacher_paths, dump_paths)
    report["inputs"] = {
        "teacher": [
            {"path": str(path), "sha256": sha256_file(path)}
            for path in teacher_paths
        ],
        "dumps": [
            {"path": str(path), "sha256": sha256_file(path)}
            for path in dump_paths
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "teacher_rows": report["teacher"]["rows"],
        "live_decisions": report["live"]["hero_decisions"],
        "coverage": {
            level: {
                "all_live": round(value["fraction_all_live"], 6),
                "postflop": round(value["fraction_postflop"], 6),
            }
            for level, value in report["coverage"].items()
        },
        "out": str(args.out),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
