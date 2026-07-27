#!/usr/bin/env python3
"""Uncertainty-aware, non-causal audit of Slumbot loss slices.

The historical loss report is intentionally descriptive.  This companion
audit adds uncertainty, session-cluster resampling, opportunity counts and
multiplicity control, while explicitly refusing to reinterpret realized
terminal winnings as counterfactual action value or regret.

It is reporting-only: it reads decision dumps and writes JSON/Markdown.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from v5_slumbot_loss_report import BIG_BLIND, build_hands, load_rows


SCHEMA_VERSION = "v5.loss_inference.audit.v1"
EVIDENCE_CLASS = "DESCRIPTIVE_LOCALIZATION_WITH_CLUSTER_UNCERTAINTY"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = min(max(probability, 0.0), 1.0) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def deterministic_seed(*parts: str, base: int) -> int:
    payload = "\x1f".join(parts).encode("utf-8")
    suffix = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return (int(base) ^ suffix) & ((1 << 63) - 1)


def group_key(hand: dict[str, Any], dimension: str) -> str:
    if dimension == "position":
        return "SB" if int(hand.get("client_pos") or 0) == 1 else "BB"
    if dimension == "terminal":
        return str(hand.get("terminal_type") or "unknown")
    if dimension == "terminal_street":
        return f"{hand.get('terminal_type', 'unknown')}@{hand.get('terminal_street_name', 'unknown')}"
    if dimension == "first_preflop_decision":
        return str(hand.get("first_preflop_decision") or "unknown")
    if dimension == "hole_family":
        return str(hand.get("hole_family") or "unknown")
    if dimension == "hole_combo":
        return str(hand.get("hole_combo") or "unknown")
    if dimension == "preflop_line":
        return str(hand.get("preflop_line") or "none")
    raise ValueError(f"unsupported dimension: {dimension}")


def cluster_totals(
    hands: Iterable[dict[str, Any]],
    *,
    dimension: str,
) -> dict[str, dict[str, tuple[float, int]]]:
    result: dict[str, dict[str, list[float | int]]] = defaultdict(dict)
    for hand in hands:
        key = group_key(hand, dimension)
        cluster = str(hand.get("source") or "unknown")
        current = result[key].setdefault(cluster, [0.0, 0])
        current[0] = float(current[0]) + float(hand.get("winnings") or 0) / BIG_BLIND
        current[1] = int(current[1]) + 1
    return {
        key: {cluster: (float(values[0]), int(values[1])) for cluster, values in rows.items()}
        for key, rows in result.items()
    }


def pooled_mean_bb100(rows: dict[str, tuple[float, int]]) -> float | None:
    total = sum(value[0] for value in rows.values())
    count = sum(value[1] for value in rows.values())
    return total / count * 100.0 if count else None


def resampled_mean_bb100(
    rows: dict[str, tuple[float, int]],
    *,
    rng: random.Random,
) -> float | None:
    clusters = sorted(rows)
    if not clusters:
        return None
    selected = [rng.choice(clusters) for _ in clusters]
    total = sum(rows[name][0] for name in selected)
    count = sum(rows[name][1] for name in selected)
    return total / count * 100.0 if count else None


def bootstrap_summary(
    candidate: dict[str, tuple[float, int]],
    baseline: dict[str, tuple[float, int]] | None,
    *,
    samples: int,
    seed: int,
) -> dict[str, Any]:
    rng = random.Random(seed)
    candidate_draws: list[float] = []
    difference_draws: list[float] = []
    for _ in range(samples):
        candidate_value = resampled_mean_bb100(candidate, rng=rng)
        if candidate_value is None:
            continue
        candidate_draws.append(candidate_value)
        if baseline:
            baseline_value = resampled_mean_bb100(baseline, rng=rng)
            if baseline_value is not None:
                difference_draws.append(candidate_value - baseline_value)
    result: dict[str, Any] = {
        "candidate_ci95_lower_bb100": percentile(candidate_draws, 0.025),
        "candidate_ci95_upper_bb100": percentile(candidate_draws, 0.975),
        "bootstrap_samples": len(candidate_draws),
        "resampling_unit": "source_session_dump",
    }
    if baseline:
        result.update(
            {
                "difference_ci95_lower_bb100": percentile(difference_draws, 0.025),
                "difference_ci95_upper_bb100": percentile(difference_draws, 0.975),
                "difference_bootstrap_samples": len(difference_draws),
                "difference_p_two_sided": (
                    min(
                        1.0,
                        2.0
                        * min(
                            (1 + sum(value <= 0.0 for value in difference_draws))
                            / (len(difference_draws) + 1),
                            (1 + sum(value >= 0.0 for value in difference_draws))
                            / (len(difference_draws) + 1),
                        ),
                    )
                    if difference_draws
                    else None
                ),
            }
        )
    return result


def benjamini_hochberg(rows: list[dict[str, Any]]) -> None:
    indexed = [
        (index, float(row["difference_p_two_sided"]))
        for index, row in enumerate(rows)
        if row.get("difference_p_two_sided") is not None
    ]
    indexed.sort(key=lambda item: item[1])
    count = len(indexed)
    running = 1.0
    for reverse_rank, (index, p_value) in enumerate(reversed(indexed), start=1):
        rank = count - reverse_rank + 1
        running = min(running, p_value * count / max(rank, 1))
        rows[index]["difference_bh_q"] = min(1.0, running)


def dimension_policy(dimension: str) -> dict[str, Any]:
    high_cardinality = dimension in {"hole_combo", "preflop_line"}
    return {
        "selection": "predeclared_dimension_then_minimum_sample_and_opportunity_count_only",
        "selected_by_observed_loss": False,
        "high_cardinality_exploratory": high_cardinality,
        "causal_action_value_identified": False,
        "action_regret_identified": False,
        "may_authorize_tuning": False,
    }


def context_family(dimension: str, key: str) -> str:
    if dimension == "first_preflop_decision":
        if key.startswith("sb_open_"):
            return "sb_first_action"
        if key.startswith("bb_vs_open_"):
            return "bb_facing_open"
        if key.startswith("bb_vs_limp_"):
            return "bb_facing_limp"
        return "other_preflop_context"
    if dimension == "terminal_street":
        return key.split("@", 1)[0]
    return "all_hands"


def summarize_dimension(
    candidate_hands: list[dict[str, Any]],
    baseline_hands: list[dict[str, Any]],
    *,
    dimension: str,
    minimum_hands: int,
    maximum_rows: int,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    candidate = cluster_totals(candidate_hands, dimension=dimension)
    baseline = cluster_totals(baseline_hands, dimension=dimension) if baseline_hands else {}
    candidate_context_totals: dict[str, int] = defaultdict(int)
    baseline_context_totals: dict[str, int] = defaultdict(int)
    for grouped_key, grouped_clusters in candidate.items():
        candidate_context_totals[context_family(dimension, grouped_key)] += sum(value[1] for value in grouped_clusters.values())
    for grouped_key, grouped_clusters in baseline.items():
        baseline_context_totals[context_family(dimension, grouped_key)] += sum(value[1] for value in grouped_clusters.values())
    rows: list[dict[str, Any]] = []
    for key, candidate_clusters in candidate.items():
        candidate_n = sum(value[1] for value in candidate_clusters.values())
        if candidate_n < minimum_hands:
            continue
        baseline_clusters = baseline.get(key)
        baseline_n = sum(value[1] for value in baseline_clusters.values()) if baseline_clusters else 0
        context = context_family(dimension, key)
        candidate_context_n = candidate_context_totals[context]
        baseline_context_n = baseline_context_totals[context] if baseline_hands else 0
        row: dict[str, Any] = {
            "key": key,
            "context": context,
            "candidate_hands": candidate_n,
            "candidate_clusters": len(candidate_clusters),
            "candidate_opportunity_rate": candidate_n / max(len(candidate_hands), 1),
            "candidate_context_opportunities": candidate_context_n,
            "candidate_rate_within_context": candidate_n / max(candidate_context_n, 1),
            "candidate_bb100": pooled_mean_bb100(candidate_clusters),
            "baseline_hands": baseline_n if baseline_hands else None,
            "baseline_clusters": len(baseline_clusters) if baseline_clusters else None,
            "baseline_opportunity_rate": baseline_n / max(len(baseline_hands), 1) if baseline_hands else None,
            "baseline_context_opportunities": baseline_context_n if baseline_hands else None,
            "baseline_rate_within_context": baseline_n / max(baseline_context_n, 1) if baseline_hands else None,
            "baseline_bb100": pooled_mean_bb100(baseline_clusters) if baseline_clusters else None,
            "difference_bb100": (
                pooled_mean_bb100(candidate_clusters) - pooled_mean_bb100(baseline_clusters)
                if baseline_clusters and pooled_mean_bb100(candidate_clusters) is not None
                else None
            ),
            "inference": "association_not_counterfactual_action_value",
        }
        row.update(
            bootstrap_summary(
                candidate_clusters,
                baseline_clusters,
                samples=bootstrap_samples,
                seed=deterministic_seed(dimension, key, base=seed),
            )
        )
        rows.append(row)
    rows.sort(key=lambda row: (-int(row["candidate_hands"]), str(row["key"])))
    rows = rows[:maximum_rows]
    benjamini_hochberg(rows)
    return {
        "dimension": dimension,
        "minimum_hands": minimum_hands,
        "maximum_rows": maximum_rows,
        "policy": dimension_policy(dimension),
        "rows": rows,
    }


def source_manifest(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paths = sorted({Path(str(row.get("_file"))).resolve() for row in rows if row.get("_file")})
    return [
        {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in paths
    ]


def build_audit(
    *,
    candidate_rows: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]] | None = None,
    label: str,
    bootstrap_samples: int = 2000,
    seed: int = 20260710,
    minimum_hands: int = 30,
) -> dict[str, Any]:
    if not candidate_rows:
        raise ValueError("candidate decision dumps contain no valid rows")
    baseline_rows = baseline_rows or []
    candidate_hands = build_hands(candidate_rows)
    baseline_hands = build_hands(baseline_rows) if baseline_rows else []
    if not candidate_hands:
        raise ValueError("candidate decision dumps contain no reconstructed hands")

    dimensions = [
        ("position", minimum_hands, 8),
        ("terminal", minimum_hands, 12),
        ("terminal_street", minimum_hands, 24),
        ("first_preflop_decision", minimum_hands, 30),
        ("hole_family", minimum_hands, 20),
        ("hole_combo", max(minimum_hands, 100), 30),
        ("preflop_line", max(minimum_hands, 50), 30),
    ]
    summaries = [
        summarize_dimension(
            candidate_hands,
            baseline_hands,
            dimension=dimension,
            minimum_hands=minimum,
            maximum_rows=maximum,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        )
        for dimension, minimum, maximum in dimensions
    ]
    associations = [
        {
            "dimension": summary["dimension"],
            "key": row["key"],
            "difference_bb100": row.get("difference_bb100"),
            "ci95_lower": row.get("difference_ci95_lower_bb100"),
            "ci95_upper": row.get("difference_ci95_upper_bb100"),
            "bh_q": row.get("difference_bh_q"),
            "interpretation": "multiplicity_controlled_slice_association_not_action_regret",
        }
        for summary in summaries
        for row in summary["rows"]
        if row.get("difference_bh_q") is not None and float(row["difference_bh_q"]) <= 0.05
    ]
    candidate_total_bb100 = (
        sum(float(hand.get("winnings") or 0) for hand in candidate_hands)
        / BIG_BLIND
        / len(candidate_hands)
        * 100.0
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "checked_at": utc_now(),
        "label": label,
        "status": "PASS_DESCRIPTIVE_INFERENCE_AUDIT",
        "evidence_class": EVIDENCE_CLASS,
        "candidate": {
            "hands": len(candidate_hands),
            "decision_rows": len(candidate_rows),
            "source_sessions": len({hand["source"] for hand in candidate_hands}),
            "bb100": candidate_total_bb100,
            "sources": source_manifest(candidate_rows),
        },
        "baseline": (
            {
                "hands": len(baseline_hands),
                "decision_rows": len(baseline_rows),
                "source_sessions": len({hand["source"] for hand in baseline_hands}),
                "sources": source_manifest(baseline_rows),
            }
            if baseline_hands
            else None
        ),
        "method": {
            "bootstrap_samples": bootstrap_samples,
            "bootstrap_seed": seed,
            "cluster_unit": "Slumbot source session / dump file",
            "multiplicity": "Benjamini-Hochberg across retained rows within each predeclared dimension",
            "row_selection": "minimum sample then opportunity count; never observed loss rank",
        },
        "dimensions": summaries,
        "multiplicity_controlled_associations": associations,
        "research_guardrails": {
            "realized_winnings_identify_action_value": False,
            "terminal_bucket_loss_identifies_bad_terminal_action": False,
            "top_losing_line_identifies_bad_action": False,
            "hole_family_loss_identifies_policy_error": False,
            "counterfactual_action_regret_available": False,
            "behavior_change_authorized": False,
            "allowed_use": [
                "loss localization",
                "hypothesis generation",
                "candidate-versus-baseline association when baseline is supplied",
                "designing a separately registered counterfactual or same-start experiment",
            ],
            "forbidden_use": [
                "action-specific tuning from realized bucket loss",
                "claiming a fold, call, raise, or all-in was causally wrong",
                "V4/L5/L6 strength claims",
            ],
        },
        "overall_decision": "LOCALIZE_ONLY_COUNTERFACTUAL_OR_CONTROL_REQUIRED_FOR_INTERVENTION",
    }
    return result


def fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}"


def write_markdown(result: dict[str, Any], path: Path) -> None:
    candidate = result["candidate"]
    lines = [
        "# V5 Loss Inference Audit",
        "",
        f"- Status: `{result['status']}`",
        f"- Evidence class: `{result['evidence_class']}`",
        f"- Candidate hands / sessions: `{candidate['hands']:,}` / `{candidate['source_sessions']}`",
        f"- Candidate bb/100: `{candidate['bb100']:+.3f}`",
        f"- Decision: `{result['overall_decision']}`",
        "",
        "Realized losses localize where outcomes occurred. They do **not** identify the EV of an unchosen action or action regret. This artifact cannot authorize tuning by itself.",
        "",
    ]
    for summary in result["dimensions"]:
        lines.extend(
            [
                f"## {summary['dimension']}",
                "",
                "| slice | n | total share | context rate | bb/100 | cluster CI | baseline delta | BH q |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in summary["rows"][:15]:
            lines.append(
                f"| `{row['key']}` | {row['candidate_hands']:,} | {row['candidate_opportunity_rate']:.3f} | "
                f"{row['candidate_rate_within_context']:.3f} | {fmt(row['candidate_bb100'])} | "
                f"[{fmt(row.get('candidate_ci95_lower_bb100'))}, {fmt(row.get('candidate_ci95_upper_bb100'))}] | "
                f"{fmt(row.get('difference_bb100'))} | {fmt(row.get('difference_bh_q'), 3)} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Interpretation contract",
            "",
            "- Allowed: localization, uncertainty-aware association, and hypothesis design.",
            "- Forbidden: treating hero-fold loss, a losing line, or a hole-family loss as counterfactual action regret.",
            "- Required before action-specific tuning: a validated counterfactual estimator or a registered same-state/same-start controlled experiment.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Slumbot loss slices without claiming causal action value.")
    parser.add_argument("--candidate-dumps", nargs="+", required=True)
    parser.add_argument("--baseline-dumps", nargs="*", default=[])
    parser.add_argument("--label", default="v5_loss_inference")
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260710)
    parser.add_argument("--minimum-hands", type=int, default=30)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()
    if args.bootstrap_samples < 100:
        parser.error("--bootstrap-samples must be >= 100")
    candidate_rows = load_rows(args.candidate_dumps)
    baseline_rows = load_rows(args.baseline_dumps) if args.baseline_dumps else []
    result = build_audit(
        candidate_rows=candidate_rows,
        baseline_rows=baseline_rows,
        label=args.label,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
        minimum_hands=args.minimum_hands,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.out_json:
        output = Path(args.out_json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(result, Path(args.out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
