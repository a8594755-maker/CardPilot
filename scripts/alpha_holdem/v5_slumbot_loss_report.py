#!/usr/bin/env python3
"""Loss-focused report for V5 Slumbot per-hand dumps.

The benchmark runner already writes one hand JSONL and one decision dump JSONL
per session. This report groups those decision dumps back into hands and
surfaces where bb/100 is being won or lost.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

BIG_BLIND = 100
STREET_NAMES = ["preflop", "flop", "turn", "river"]
RANK_ORDER = "AKQJT98765432"
RANK_VALUE = {rank: len(RANK_ORDER) - idx for idx, rank in enumerate(RANK_ORDER)}


def load_rows(patterns: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    paths: list[str] = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        paths.extend(matches if matches else [pattern])
    for path_text in paths:
        path = Path(path_text)
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    row["_file"] = str(path)
                    rows.append(row)
    return rows


def hand_key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row.get("_file") or ""), int(row.get("hand_idx") or 0)


def action_token(row: dict[str, Any]) -> str:
    move = str(row.get("action_move") or "?")
    if move == "b":
        return f"b{int(row.get('action_amount') or 0)}"
    return move


def preflop_line(moves: list[dict[str, Any]]) -> str:
    tokens: list[str] = []
    for row in moves:
        if int(row.get("street") or 0) != 0:
            continue
        who = "H" if row.get("who") == "hero" else "O"
        tokens.append(f"{who}:{action_token(row)}")
    return " ".join(tokens) if tokens else "none"


def terminal_type(moves: list[dict[str, Any]]) -> tuple[str, int]:
    if not moves:
        return "unknown", -1
    last = moves[-1]
    last_move = str(last.get("action_move") or "")
    last_who = str(last.get("who") or "")
    max_street = max(int(row.get("street") or 0) for row in moves)
    if last_move == "f":
        return ("hero_fold" if last_who == "hero" else "opp_fold"), max_street
    if max_street == 3:
        return "showdown", max_street
    if last_move == "c":
        return "allin_runout", max_street
    return "other", max_street


def parse_first_bet(action_str: str) -> int | None:
    match = re.search(r"b(\d+)", action_str or "")
    return int(match.group(1)) if match else None


def amount_bucket(amount: int | None) -> str:
    if amount is None:
        return "none"
    bb = amount / BIG_BLIND
    if bb < 2.5:
        return "lt2.5bb"
    if bb < 4.0:
        return "2.5-4bb"
    if bb < 8.0:
        return "4-8bb"
    if bb < 20.0:
        return "8-20bb"
    if bb < 100.0:
        return "20-100bb"
    return "100bb_plus"


def first_preflop_decision(hand: dict[str, Any]) -> str:
    client_pos = int(hand.get("client_pos") or 0)
    hero_moves = [
        row for row in hand["moves"]
        if row.get("who") == "hero" and int(row.get("street") or 0) == 0
    ]
    if not hero_moves:
        return "no_hero_preflop"
    first = hero_moves[0]
    move = str(first.get("action_move") or "?")
    action_before = str(first.get("action_str_before") or "")
    if client_pos == 1 and action_before == "":
        if move == "b":
            return f"sb_open_raise_{amount_bucket(int(first.get('action_amount') or 0))}"
        return f"sb_open_{move}"
    if client_pos == 0 and action_before.startswith("b"):
        open_amount = parse_first_bet(action_before)
        if move == "b":
            return f"bb_vs_open_{amount_bucket(open_amount)}_raise_{amount_bucket(int(first.get('action_amount') or 0))}"
        return f"bb_vs_open_{amount_bucket(open_amount)}_{move}"
    if client_pos == 0 and action_before == "":
        return f"bb_vs_limp_{move}"
    return f"preflop_other_{move}"


def normalize_hole(cards: Any) -> str:
    if not isinstance(cards, list) or len(cards) != 2:
        return "unknown"
    ranks = [str(card)[0] for card in cards]
    suits = [str(card)[1] if len(str(card)) > 1 else "" for card in cards]
    if ranks[0] == ranks[1]:
        return f"{ranks[0]}{ranks[1]}"
    ranks_sorted = sorted(ranks, key=lambda rank: RANK_VALUE.get(rank, -1), reverse=True)
    suited = "s" if suits[0] == suits[1] else "o"
    return f"{ranks_sorted[0]}{ranks_sorted[1]}{suited}"


def hole_family(combo: str) -> str:
    if combo == "unknown":
        return "unknown"
    if len(combo) == 2:
        return "pair"
    ranks = combo[:2]
    suited = combo[-1] == "s"
    values = [RANK_VALUE.get(rank, 0) for rank in ranks]
    high, low = max(values), min(values)
    if high >= RANK_VALUE["T"] and low >= RANK_VALUE["T"]:
        return "broadway_suited" if suited else "broadway_offsuit"
    if high >= RANK_VALUE["A"] and low <= RANK_VALUE["5"]:
        return "wheel_ace_suited" if suited else "wheel_ace_offsuit"
    if high >= RANK_VALUE["A"]:
        return "ace_suited" if suited else "ace_offsuit"
    if high - low <= 2 and suited:
        return "suited_connector"
    if suited:
        return "other_suited"
    return "other_offsuit"


def build_hands(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        key = hand_key(row)
        hand = grouped.setdefault(
            key,
            {
                "source": key[0],
                "hand_idx": key[1],
                "client_pos": row.get("client_pos"),
                "winnings": int(row.get("winnings_hero") or 0),
                "hero_hole": row.get("hero_hole"),
                "moves": [],
            },
        )
        hand["moves"].append(row)
        hand["winnings"] = int(row.get("winnings_hero") or hand["winnings"] or 0)
    hands = list(grouped.values())
    for hand in hands:
        hand["moves"].sort(key=lambda row: int(row.get("move_idx") or 0))
        terminal, street = terminal_type(hand["moves"])
        hand["terminal_type"] = terminal
        hand["terminal_street"] = street
        hand["terminal_street_name"] = STREET_NAMES[street] if 0 <= street < len(STREET_NAMES) else "unknown"
        hand["preflop_line"] = preflop_line(hand["moves"])
        hand["first_preflop_decision"] = first_preflop_decision(hand)
        hand["hole_combo"] = normalize_hole(hand.get("hero_hole"))
        hand["hole_family"] = hole_family(hand["hole_combo"])
    return sorted(hands, key=lambda hand: (hand["source"], hand["hand_idx"]))


def aggregate(hands: list[dict[str, Any]], key_fn) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for hand in hands:
        key = str(key_fn(hand))
        bucket = buckets.setdefault(key, {"key": key, "hands": 0, "chips": 0})
        bucket["hands"] += 1
        bucket["chips"] += int(hand.get("winnings") or 0)
    rows = []
    for bucket in buckets.values():
        hands_n = int(bucket["hands"])
        chips = int(bucket["chips"])
        rows.append(
            {
                "key": bucket["key"],
                "hands": hands_n,
                "chips": chips,
                "bb_per_100": chips / max(hands_n, 1),
                "bb_per_hand": chips / max(hands_n, 1) / BIG_BLIND,
            }
        )
    return rows


def sorted_loss(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (float(row["chips"]), -int(row["hands"])))[:limit]


def sorted_profit(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (float(row["chips"]), int(row["hands"])), reverse=True)[:limit]


def rate_for(hands: list[dict[str, Any]], predicate) -> float | None:
    denom = len(hands)
    if denom == 0:
        return None
    return sum(1 for hand in hands if predicate(hand)) / denom


def build_summary(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    hands = build_hands(rows)
    total_chips = sum(int(hand.get("winnings") or 0) for hand in hands)
    n = len(hands)

    by_position = aggregate(hands, lambda hand: "SB" if int(hand.get("client_pos") or 0) == 1 else "BB")
    by_terminal = aggregate(hands, lambda hand: hand["terminal_type"])
    by_terminal_street = aggregate(hands, lambda hand: f"{hand['terminal_type']}@{hand['terminal_street_name']}")
    by_first_preflop = aggregate(hands, lambda hand: hand["first_preflop_decision"])
    by_preflop_line = aggregate(hands, lambda hand: hand["preflop_line"])
    by_hole_family = aggregate(hands, lambda hand: hand["hole_family"])
    by_hole_combo = aggregate(hands, lambda hand: hand["hole_combo"])

    sb_open_hands = [hand for hand in hands if hand["first_preflop_decision"].startswith("sb_open_")]
    sb_open_fold_rate = rate_for(sb_open_hands, lambda hand: hand["first_preflop_decision"] == "sb_open_f")
    sb_open_call_rate = rate_for(sb_open_hands, lambda hand: hand["first_preflop_decision"] == "sb_open_c")
    sb_open_allin_rate = rate_for(
        sb_open_hands,
        lambda hand: hand["first_preflop_decision"] in {"sb_open_a", "sb_open_raise_100bb_plus"},
    )
    sb_open_raise_rate = rate_for(
        sb_open_hands,
        lambda hand: hand["first_preflop_decision"].startswith("sb_open_raise_")
        and hand["first_preflop_decision"] != "sb_open_raise_100bb_plus",
    )
    bb_vs_open_hands = [hand for hand in hands if hand["first_preflop_decision"].startswith("bb_vs_open_")]
    bb_vs_open_call_rate = rate_for(bb_vs_open_hands, lambda hand: hand["first_preflop_decision"].endswith("_c"))
    bb_vs_open_raise_rate = rate_for(bb_vs_open_hands, lambda hand: "_raise_" in hand["first_preflop_decision"])

    warnings: list[str] = []
    if sb_open_fold_rate is not None and sb_open_fold_rate > 0.30:
        warnings.append(f"SB open fold rate is high ({sb_open_fold_rate:.1%}); this leaks small blind EV.")
    if sb_open_call_rate is not None and sb_open_call_rate > 0.45:
        warnings.append(f"SB open limp/call rate is high ({sb_open_call_rate:.1%}); check for limp-heavy first action.")
    if sb_open_raise_rate is not None and sb_open_raise_rate < 0.20:
        warnings.append(f"SB open raise rate is low ({sb_open_raise_rate:.1%}); check for under-raising first action.")
    if bb_vs_open_call_rate is not None and bb_vs_open_call_rate < 0.05:
        warnings.append(f"BB vs open call rate is extremely low ({bb_vs_open_call_rate:.1%}); defence is fold/3bet-heavy.")
    if bb_vs_open_raise_rate is not None and bb_vs_open_raise_rate > 0.45:
        warnings.append(f"BB vs open raise rate is very high ({bb_vs_open_raise_rate:.1%}); check for 3bet overuse.")
    showdown = next((row for row in by_terminal if row["key"] == "showdown"), None)
    if showdown and float(showdown["chips"]) < 0:
        warnings.append(
            f"Showdown hands are losing {showdown['chips']:+,} chips "
            f"({showdown['bb_per_100']:+.1f} bb/100 within bucket)."
        )

    return {
        "label": label,
        "move_records": len(rows),
        "hands": n,
        "total_chips": total_chips,
        "bb_per_100": total_chips / max(n, 1),
        "position": sorted(by_position, key=lambda row: row["key"]),
        "terminal": sorted(by_terminal, key=lambda row: row["chips"]),
        "terminal_street": sorted_loss(by_terminal_street, 20),
        "first_preflop_decision": sorted_loss(by_first_preflop, 30),
        "top_losing_preflop_lines": sorted_loss(by_preflop_line, 20),
        "top_winning_preflop_lines": sorted_profit(by_preflop_line, 12),
        "hole_family": sorted_loss(by_hole_family, 20),
        "worst_hole_combos": sorted_loss([row for row in by_hole_combo if row["hands"] >= 8], 20),
        "rates": {
            "sb_open_fold_rate": sb_open_fold_rate,
            "sb_open_call_rate": sb_open_call_rate,
            "sb_open_raise_rate": sb_open_raise_rate,
            "sb_open_allin_rate": sb_open_allin_rate,
            "bb_vs_open_call_rate": bb_vs_open_call_rate,
            "bb_vs_open_raise_rate": bb_vs_open_raise_rate,
        },
        "warnings": warnings,
    }


def fmt_float(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def table(rows: list[dict[str, Any]], title: str, limit: int | None = None) -> list[str]:
    out = [
        title,
        "",
        "| key | hands | chips | bb/100 | BB/hand |",
        "|---|---:|---:|---:|---:|",
    ]
    selected = rows if limit is None else rows[:limit]
    for row in selected:
        out.append(
            f"| `{row['key']}` | {int(row['hands']):,} | {int(row['chips']):+,} | "
            f"{float(row['bb_per_100']):+.1f} | {float(row['bb_per_hand']):+.3f} |"
        )
    out.append("")
    return out


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    rates = summary["rates"]
    lines = [
        "# V5 Slumbot Loss Report",
        "",
        f"- Label: `{summary['label']}`",
        f"- Hands: `{summary['hands']:,}`",
        f"- Move records: `{summary['move_records']:,}`",
        f"- Total chips: `{summary['total_chips']:+,}`",
        f"- bb/100: `{float(summary['bb_per_100']):+.3f}`",
        f"- SB open fold / call / raise / all-in rate: `{fmt_float(rates.get('sb_open_fold_rate'))}` / `{fmt_float(rates.get('sb_open_call_rate'))}` / `{fmt_float(rates.get('sb_open_raise_rate'))}` / `{fmt_float(rates.get('sb_open_allin_rate'))}`",
        f"- BB vs open call / raise rate: `{fmt_float(rates.get('bb_vs_open_call_rate'))}` / `{fmt_float(rates.get('bb_vs_open_raise_rate'))}`",
        "",
        "Warnings:",
        "",
    ]
    if summary["warnings"]:
        lines.extend(f"- {item}" for item in summary["warnings"])
    else:
        lines.append("- none")
    lines.append("")
    lines.extend(table(summary["position"], "## Position"))
    lines.extend(table(summary["terminal"], "## Terminal"))
    lines.extend(table(summary["terminal_street"], "## Terminal By Street"))
    lines.extend(table(summary["first_preflop_decision"], "## First Preflop Decision"))
    lines.extend(table(summary["top_losing_preflop_lines"], "## Top Losing Preflop Lines"))
    lines.extend(table(summary["top_winning_preflop_lines"], "## Top Winning Preflop Lines"))
    lines.extend(table(summary["hole_family"], "## Hole Families"))
    lines.extend(table(summary["worst_hole_combos"], "## Worst Hole Combos", limit=20))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a loss-focused report from Slumbot dump JSONL files.")
    parser.add_argument("--dumps", nargs="+", required=True)
    parser.add_argument("--label", default="slumbot")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    rows = load_rows(args.dumps)
    summary = build_summary(args.label, rows)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(summary, Path(args.out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
