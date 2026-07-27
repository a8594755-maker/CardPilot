#!/usr/bin/env python3
"""Validate a duplicate-deal cross-play matrix and test supported cycles.

This tool does not run matches.  It consumes preregistered pairwise results and
prevents marginal action-rate oscillation or noisy probes from being promoted
to a claim of self-play cycling.  A supported temporal cycle requires a
complete common-deal matrix, precise pairwise confidence intervals, and ordered
training snapshots.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "v5.crossplay.cycle_audit.v1"
INPUT_SCHEMA_VERSION = "v5.crossplay.payoff_matrix.v1"
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def validate(payload: dict[str, Any], *, minimum_pairs: int) -> tuple[list[str], list[str], dict[tuple[str, str], dict[str, Any]]]:
    errors: list[str] = []
    warnings: list[str] = []
    if payload.get("template_only") is True:
        errors.append("template_only must be removed or set false after binding real result artifacts")
    if payload.get("schema_version") != INPUT_SCHEMA_VERSION:
        errors.append(f"schema_version must be {INPUT_SCHEMA_VERSION}")
    if payload.get("stack_bb") != 200.0:
        errors.append("stack_bb must be exactly 200.0")
    if payload.get("policy_mode") != "greedy":
        errors.append("top-level policy_mode must be greedy")
    deal_stream_id = payload.get("deal_stream_id")
    if not isinstance(deal_stream_id, str) or not deal_stream_id or "REPLACE" in deal_stream_id:
        errors.append("a frozen non-template deal_stream_id is required")
    players_raw = payload.get("players")
    if not isinstance(players_raw, list) or len(players_raw) < 3:
        errors.append("players must contain at least three entries")
        return errors, warnings, {}
    players = [str(item.get("id")) if isinstance(item, dict) else str(item) for item in players_raw]
    if any(not player or player == "None" for player in players):
        errors.append("every player requires a non-empty id")
    if len(set(players)) != len(players):
        errors.append("player ids must be unique")
    for index, item in enumerate(players_raw):
        if not isinstance(item, dict):
            errors.append(f"player {index} must be an identity-bound object")
            continue
        if not isinstance(item.get("iteration"), int):
            errors.append(f"player {index} requires integer iteration")
        checkpoint_path = item.get("checkpoint_path")
        if not isinstance(checkpoint_path, str) or not checkpoint_path or "REPLACE" in checkpoint_path:
            errors.append(f"player {index} requires a bound checkpoint_path")
        if not isinstance(item.get("checkpoint_sha256"), str) or not SHA256_RE.fullmatch(item["checkpoint_sha256"]):
            errors.append(f"player {index} requires a 64-hex checkpoint_sha256")
    if payload.get("ordered_training_snapshots") is True:
        iterations = [item.get("iteration") for item in players_raw if isinstance(item, dict)]
        if len(iterations) == len(players_raw) and all(isinstance(value, int) for value in iterations):
            if iterations != sorted(iterations) or len(set(iterations)) != len(iterations):
                errors.append("ordered training snapshot iterations must be unique and strictly increasing")
    player_set = set(players)
    matches = payload.get("matches")
    if not isinstance(matches, list):
        errors.append("matches must be a list")
        return errors, warnings, {}

    normalized: dict[tuple[str, str], dict[str, Any]] = {}
    for index, row in enumerate(matches):
        if not isinstance(row, dict):
            errors.append(f"match {index} is not an object")
            continue
        source = str(row.get("row") or "")
        target = str(row.get("column") or "")
        if source not in player_set or target not in player_set or source == target:
            errors.append(f"match {index} has invalid row/column identity")
            continue
        key = tuple(sorted((source, target)))
        if key in normalized:
            errors.append(f"duplicate unordered match for {key[0]} versus {key[1]}")
            continue
        mean = row.get("mean_bb100")
        lower = row.get("ci_lower_bb100")
        upper = row.get("ci_upper_bb100")
        if not all(finite_number(value) for value in (mean, lower, upper)):
            errors.append(f"match {index} has non-finite mean/CI")
            continue
        if float(lower) > float(mean) or float(mean) > float(upper):
            errors.append(f"match {index} mean is outside its CI")
        pairs = row.get("pairs")
        if not isinstance(pairs, int) or isinstance(pairs, bool) or pairs <= 0:
            errors.append(f"match {index} pairs must be a positive integer")
            continue
        if pairs < minimum_pairs:
            warnings.append(f"{source} versus {target} has {pairs} pairs < {minimum_pairs}")
        if row.get("common_deal") is not True:
            errors.append(f"{source} versus {target} is not common-deal paired")
        if row.get("seats_swapped") is not True:
            errors.append(f"{source} versus {target} is missing complete seat swaps")
        if str(row.get("policy_mode") or "") != "greedy":
            errors.append(f"{source} versus {target} policy_mode must be greedy")
        result_path = row.get("result_path")
        if not isinstance(result_path, str) or not result_path or "REPLACE" in result_path:
            errors.append(f"{source} versus {target} requires a bound result_path")
        if not isinstance(row.get("result_sha256"), str) or not SHA256_RE.fullmatch(row["result_sha256"]):
            errors.append(f"{source} versus {target} requires a 64-hex result_sha256")
        normalized[key] = {
            **row,
            "row": source,
            "column": target,
            "mean_bb100": float(mean),
            "ci_lower_bb100": float(lower),
            "ci_upper_bb100": float(upper),
        }

    expected = set(itertools.combinations(sorted(players), 2))
    missing = sorted(expected - set(normalized))
    for key in missing:
        warnings.append(f"missing pair {key[0]} versus {key[1]}")
    return errors, warnings, normalized


def directed_view(row: dict[str, Any], source: str, target: str) -> tuple[float, float, float]:
    if row["row"] == source and row["column"] == target:
        return row["mean_bb100"], row["ci_lower_bb100"], row["ci_upper_bb100"]
    return -row["mean_bb100"], -row["ci_upper_bb100"], -row["ci_lower_bb100"]


def supported_edges(
    players: list[str],
    matches: dict[tuple[str, str], dict[str, Any]],
    *,
    margin_bb100: float,
    minimum_pairs: int,
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for source, target in itertools.permutations(players, 2):
        if source >= target:
            continue
        row = matches.get(tuple(sorted((source, target))))
        if not row or int(row.get("pairs") or 0) < minimum_pairs:
            continue
        mean, lower, upper = directed_view(row, source, target)
        if lower > margin_bb100:
            edges.append(
                {
                    "winner": source,
                    "loser": target,
                    "mean_bb100": mean,
                    "ci_lower_bb100": lower,
                    "ci_upper_bb100": upper,
                    "pairs": row["pairs"],
                }
            )
        elif upper < -margin_bb100:
            reverse_mean, reverse_lower, reverse_upper = directed_view(row, target, source)
            edges.append(
                {
                    "winner": target,
                    "loser": source,
                    "mean_bb100": reverse_mean,
                    "ci_lower_bb100": reverse_lower,
                    "ci_upper_bb100": reverse_upper,
                    "pairs": row["pairs"],
                }
            )
    return edges


def find_cycles(players: list[str], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adjacency = {(edge["winner"], edge["loser"]): edge for edge in edges}
    cycles: list[dict[str, Any]] = []
    for a, b, c in itertools.combinations(sorted(players), 3):
        orientations = ((a, b, c), (a, c, b))
        for first, second, third in orientations:
            required = ((first, second), (second, third), (third, first))
            if all(edge in adjacency for edge in required):
                cycles.append(
                    {
                        "nodes": [first, second, third],
                        "edges": [adjacency[edge] for edge in required],
                        "interpretation": f"{first} > {second} > {third} > {first}",
                    }
                )
    return cycles


def build_audit(payload: dict[str, Any], *, minimum_pairs: int = 10_000, margin_bb100: float = 0.0) -> dict[str, Any]:
    errors, warnings, matches = validate(payload, minimum_pairs=minimum_pairs)
    players_raw = payload.get("players") if isinstance(payload.get("players"), list) else []
    players = [str(item.get("id")) if isinstance(item, dict) else str(item) for item in players_raw]
    expected_pairs = len(players) * (len(players) - 1) // 2
    complete = len(matches) == expected_pairs and not any(item.startswith("missing pair") for item in warnings)
    edges = supported_edges(players, matches, margin_bb100=margin_bb100, minimum_pairs=minimum_pairs) if not errors else []
    cycles = find_cycles(players, edges) if complete and not errors else []
    ordered_snapshots = payload.get("ordered_training_snapshots") is True
    iterations = [item.get("iteration") for item in players_raw if isinstance(item, dict)]
    temporal_identity_valid = ordered_snapshots and len(iterations) == len(players) and all(isinstance(value, int) for value in iterations)

    if errors:
        status = "INVALID_FAIL_CLOSED"
    elif not complete:
        status = "INCOMPLETE_MATRIX"
    elif cycles:
        status = "SUPPORTED_NONTRANSITIVE_CYCLE"
    elif len(edges) < expected_pairs:
        status = "NO_CYCLE_PROVEN_UNCERTAIN_EDGES"
    else:
        status = "NO_SUPPORTED_CYCLE_IN_TESTED_PANEL"

    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": utc_now(),
        "status": status,
        "input_design_id": payload.get("design_id"),
        "players": players_raw,
        "matrix": {
            "players": len(players),
            "expected_unordered_pairs": expected_pairs,
            "valid_unordered_pairs": len(matches),
            "complete": complete,
            "minimum_pairs_per_edge": minimum_pairs,
            "effect_margin_bb100": margin_bb100,
        },
        "supported_edges": edges,
        "cycles": cycles,
        "errors": errors,
        "warnings": warnings,
        "claims": {
            "nontransitivity_supported": bool(cycles) and not errors,
            "temporal_self_play_cycle_supported": bool(cycles) and temporal_identity_valid and not errors,
            "global_nonconvergence_proven": False,
            "strength_claim_authorized": False,
            "behavior_change_authorized": False,
        },
        "interpretation": {
            "supported_cycle_means": "a statistically supported non-transitive cycle exists in this frozen policy panel",
            "supported_cycle_does_not_mean": "all training is globally non-convergent or any policy is strong versus Slumbot",
            "no_cycle_does_not_mean": "the game or training process is transitive",
        },
    }


def fmt(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):+.2f}"


def write_markdown(result: dict[str, Any], path: Path) -> None:
    matrix = result["matrix"]
    lines = [
        "# V5 Cross-Play Cycle Audit",
        "",
        f"- Status: `{result['status']}`",
        f"- Matrix complete: `{matrix['complete']}` ({matrix['valid_unordered_pairs']}/{matrix['expected_unordered_pairs']})",
        f"- Non-transitivity supported: `{result['claims']['nontransitivity_supported']}`",
        f"- Temporal self-play cycle supported: `{result['claims']['temporal_self_play_cycle_supported']}`",
        f"- Global non-convergence proven: `{result['claims']['global_nonconvergence_proven']}`",
        "",
        "## Supported edges",
        "",
        "| winner | loser | mean bb/100 | 95% CI | pairs |",
        "|---|---|---:|---:|---:|",
    ]
    for edge in result["supported_edges"]:
        lines.append(
            f"| `{edge['winner']}` | `{edge['loser']}` | {fmt(edge['mean_bb100'])} | "
            f"[{fmt(edge['ci_lower_bb100'])}, {fmt(edge['ci_upper_bb100'])}] | {edge['pairs']:,} |"
        )
    if not result["supported_edges"]:
        lines.append("| none | none | n/a | n/a | 0 |")
    lines.extend(["", "## Supported cycles", ""])
    if result["cycles"]:
        lines.extend(f"- `{item['interpretation']}`" for item in result["cycles"])
    else:
        lines.append("- none proven")
    lines.extend(["", "This audit cannot authorize a Slumbot strength claim or a behavior change by itself.", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a frozen common-deal cross-play payoff matrix for supported cycles.")
    parser.add_argument("--matrix-json", required=True)
    parser.add_argument("--minimum-pairs", type=int, default=10_000)
    parser.add_argument("--margin-bb100", type=float, default=0.0)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()
    payload = json.loads(Path(args.matrix_json).read_text(encoding="utf-8"))
    result = build_audit(payload, minimum_pairs=args.minimum_pairs, margin_bb100=args.margin_bb100)
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.out_json:
        output = Path(args.out_json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(result, Path(args.out_md))
    return 2 if result["status"] == "INVALID_FAIL_CLOSED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
