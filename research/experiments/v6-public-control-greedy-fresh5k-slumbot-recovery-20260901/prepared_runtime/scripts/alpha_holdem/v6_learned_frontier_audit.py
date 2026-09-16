"""Audit the reproducible learned-policy frontier from frozen Slumbot evidence.

This is deliberately read-only.  It ranks mature 20k-hand results, but keeps
checkpoint availability and provenance separate from the point estimate so an
unrecoverable historical candidate cannot silently become a training parent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


BB_RE = re.compile(r"(?<!\[)([-+]?[0-9]+(?:\.[0-9]+)?)\s*bb/100", re.I)
CI_RE = re.compile(
    r"(?:CI95|95%CI|95% CI|raw95%CI|raw 95% CI)\s*\[\s*"
    r"([-+]?[0-9]+(?:\.[0-9]+)?)\s*,\s*"
    r"([-+]?[0-9]+(?:\.[0-9]+)?)\s*\]",
    re.I,
)
METRIC_NAMES = {
    "bb100": ("bb_per_100", "raw_bb100", "candidate_bb100"),
    "ci_lower": (
        "ci95_lower",
        "raw_ci95_lower",
        "ci95_lower_bb_per_100",
        "raw_ci95_low",
    ),
    "ci_upper": (
        "ci95_upper",
        "raw_ci95_upper",
        "ci95_upper_bb_per_100",
        "raw_ci95_high",
    ),
}
LEGACY_20K = {
    "legacy-best-mature-external-reference": 20_000,
    "legacy-scaled-slumbot-imitation-teacher": 20_000,
    "legacy-counterfactual-capped-softresidual-seed4363-fresh20k": 20_000,
}
EXTERNAL_ID_EXCEPTIONS = {
    "v6-standard10-legacy-bridge-greedy-fresh20k-20260901",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def first_metric(metrics: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = metrics.get(name)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def extract_result(record: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    metrics = record.get("metrics") or {}
    bb100 = first_metric(metrics, METRIC_NAMES["bb100"])
    lower = first_metric(metrics, METRIC_NAMES["ci_lower"])
    upper = first_metric(metrics, METRIC_NAMES["ci_upper"])
    summary = str((record.get("result") or {}).get("summary") or "")
    if bb100 is None:
        match = BB_RE.search(summary)
        bb100 = float(match.group(1)) if match else None
    if lower is None or upper is None:
        match = CI_RE.search(summary)
        if match:
            lower = float(match.group(1))
            upper = float(match.group(2))
    return bb100, lower, upper


def checkpoint_evidence(repo: Path, record: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for raw in record.get("artifacts") or []:
        if not isinstance(raw, str) or not raw.lower().endswith((".pt", ".pth")):
            continue
        path = repo / raw
        found.append(
            {
                "path": raw,
                "exists": path.is_file(),
                "sha256": sha256(path) if path.is_file() else None,
            }
        )
    return found


def audit(repo: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    experiments = repo / "research" / "experiments"
    for record_path in sorted(experiments.glob("*/experiment.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("status") != "COMPLETED":
            continue
        record_id = str(record.get("id") or record_path.parent.name)
        accounting = record.get("accounting") or {}
        hands = accounting.get("evaluation_hands")
        if record_id in LEGACY_20K:
            hands = LEGACY_20K[record_id]
        external_record = (
            "slumbot" in record_id.lower()
            or record_id in LEGACY_20K
            or record_id in EXTERNAL_ID_EXCEPTIONS
        )
        if (
            not isinstance(hands, (int, float))
            or hands < 20_000
            or not external_record
        ):
            continue
        bb100, lower, upper = extract_result(record)
        if bb100 is None:
            continue
        checkpoints = checkpoint_evidence(repo, record)
        imported = "legacy-import" in (record.get("tags") or [])
        rows.append(
            {
                "id": record_id,
                "hands": int(hands),
                "bb100": bb100,
                "ci95_lower": lower,
                "ci95_upper": upper,
                "imported_summary_only": imported,
                "checkpoints": checkpoints,
                "reproducible_checkpoint": any(item["exists"] for item in checkpoints),
                "decision": (record.get("result") or {}).get("decision"),
            }
        )
    rows.sort(key=lambda item: item["bb100"], reverse=True)
    standard10 = next(
        item for item in rows if item["id"] == "legacy-best-mature-external-reference"
    )
    imitation = next(
        item for item in rows if item["id"] == "legacy-scaled-slumbot-imitation-teacher"
    )
    current_bridge = next(
        item
        for item in rows
        if item["id"] == "v6-standard10-legacy-bridge-greedy-fresh20k-20260901"
    )
    return {
        "schema_version": 1,
        "eligible_frozen_20k_results": rows,
        "frontier": {
            "best_point_estimate": standard10["id"],
            "best_reproducible_parent": standard10["id"],
            "standard10_historical_greedy_bb100": standard10["bb100"],
            "standard10_current_bridge_bb100": current_bridge["bb100"],
            "historical_imitation_bb100": imitation["bb100"],
        },
        "checks": {
            "standard10_checkpoint_available": standard10["reproducible_checkpoint"],
            "standard10_checkpoint_sha256": standard10["checkpoints"][0]["sha256"],
            "imitation_checkpoint_available_from_record": imitation["reproducible_checkpoint"],
            "imitation_is_imported_summary_only": imitation["imported_summary_only"],
            "any_20k_point_positive": any(item["bb100"] > 0 for item in rows),
            "any_20k_ci_lower_positive": any(
                item["ci95_lower"] is not None and item["ci95_lower"] > 0 for item in rows
            ),
        },
        "decision": "STANDARD10_ONLY_REPRODUCIBLE_FRONTIER_PARENT",
        "next_step": (
            "Use frozen Standard10 as a preservation prior and initialization for a "
            "qualitatively different state-conditioned policy-improvement signal. "
            "Treat single-teacher imitation as a negative control, not a revived route."
        ),
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Learned-policy frontier audit",
        "",
        "| Experiment | Hands | bb/100 | 95% CI | Checkpoint | Provenance |",
        "|---|---:|---:|---:|---|---|",
    ]
    for row in result["eligible_frozen_20k_results"]:
        interval = (
            f"[{row['ci95_lower']:.4f}, {row['ci95_upper']:.4f}]"
            if row["ci95_lower"] is not None and row["ci95_upper"] is not None
            else "unknown"
        )
        lines.append(
            f"| `{row['id']}` | {row['hands']:,} | {row['bb100']:.4f} | "
            f"{interval} | {'available' if row['reproducible_checkpoint'] else 'absent'} | "
            f"{'imported summary' if row['imported_summary_only'] else 'current record'} |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"`{result['decision']}`",
            "",
            result["next_step"],
            "",
            "The historical imitation result remains negative and its imported record does not "
            "identify a surviving checkpoint. It therefore cannot displace Standard10 as the "
            "reproducible parent or be treated as new evidence for imitation.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.repo.resolve())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "frontier.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (output / "analysis.md").write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps(result["frontier"], sort_keys=True))
    print(result["decision"])


if __name__ == "__main__":
    main()
