#!/usr/bin/env python3
"""Run a stable, seat-resolved internal learning curve over frozen checkpoints.

Each candidate is evaluated by ``v5_mirror_eval.py`` against the same frozen
network opponents, shuffled-deck seed, and mirrored seats.  The aggregate is an
internal structural diagnostic, not a Slumbot result or a formal strength claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


THIS_DIR = Path(__file__).resolve().parent
MIRROR_EVALUATOR = THIS_DIR / "v5_mirror_eval.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_labeled_path(text: str) -> tuple[str, Path]:
    if "=" not in text:
        path = Path(text).resolve()
        return path.stem, path
    label, raw_path = text.split("=", 1)
    label = label.strip()
    if not label:
        raise ValueError(f"empty label in {text!r}")
    return label, Path(raw_path).resolve()


def safe_name(label: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("._")
    if not value:
        raise ValueError(f"label has no filename-safe characters: {label!r}")
    return value


def reusable_result(
    path: Path,
    *,
    candidate_sha256: str,
    anchor_sha256: dict[str, str],
    pairs: int,
    seed: int,
) -> bool:
    if not path.exists():
        return False
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    observed_anchors = {
        str(row.get("anchor")): str(row.get("anchor_sha256"))
        for row in result.get("anchors", [])
    }
    return bool(
        result.get("candidate", {}).get("sha256") == candidate_sha256
        and observed_anchors == anchor_sha256
        and int(result.get("pairs", -1)) == pairs
        and int(result.get("seed", -1)) == seed
        and all("paired_outcomes" in row for row in result.get("anchors", []))
    )


def structural_label(
    overall_delta: float,
    bb_delta: float,
    sb_delta: float,
) -> str:
    tolerance = 1e-9
    bb_up = bb_delta > tolerance
    sb_up = sb_delta > tolerance
    bb_down = bb_delta < -tolerance
    sb_down = sb_delta < -tolerance
    if bb_up and sb_up:
        return "BOTH_SEATS_IMPROVED"
    if bb_down and sb_down:
        return "BOTH_SEATS_REGRESSED"
    if (bb_up and sb_down) or (bb_down and sb_up):
        return "POSITION_TRADEOFF"
    if overall_delta > tolerance:
        return "NET_GAIN_WITH_ONE_SEAT_FLAT"
    if overall_delta < -tolerance:
        return "NET_LOSS_WITH_ONE_SEAT_FLAT"
    return "FLAT"


def paired_delta(
    previous: list[float],
    current: list[float],
) -> tuple[float, float]:
    if len(previous) != len(current) or not previous:
        raise ValueError("paired checkpoint outcomes have incompatible lengths")
    deltas = [
        float(current_value) - float(previous_value)
        for previous_value, current_value in zip(previous, current, strict=True)
    ]
    mean = statistics.fmean(deltas)
    std = statistics.stdev(deltas) if len(deltas) > 1 else 0.0
    ci95 = 1.96 * std / math.sqrt(len(deltas))
    return mean * 100.0, ci95 * 100.0


def build_summary(
    *,
    candidates: list[tuple[str, Path]],
    anchors: list[tuple[str, Path]],
    results: list[dict[str, Any]],
    pairs: int,
    seed: int,
    device: str,
    evaluator_sha256: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    outcome_lookup: dict[tuple[str, str], dict[str, list[float]]] = {}
    for candidate_index, ((label, path), result) in enumerate(
        zip(candidates, results, strict=True)
    ):
        checkpoint = result["candidate"]["checkpoint"]
        for anchor_result in result["anchors"]:
            outcome_lookup[(label, anchor_result["anchor"])] = anchor_result[
                "paired_outcomes"
            ]
            rows.append(
                {
                    "candidate_index": candidate_index,
                    "candidate": label,
                    "candidate_path": str(path),
                    "candidate_sha256": result["candidate"]["sha256"],
                    "checkpoint_iteration": checkpoint.get("iteration"),
                    "checkpoint_total_hands": checkpoint.get("total_hands"),
                    "checkpoint_run_id": checkpoint.get("run_id"),
                    "checkpoint_architecture": checkpoint.get("architecture"),
                    "position_adapter_hidden": checkpoint.get(
                        "position_adapter_hidden", 0
                    ),
                    "anchor": anchor_result["anchor"],
                    "anchor_sha256": anchor_result["anchor_sha256"],
                    "hands": anchor_result["hands"],
                    "overall_bb100": anchor_result["candidate_bb100"],
                    "overall_ci95_bb100": anchor_result[
                        "candidate_ci95_bb100"
                    ],
                    "bb_bb100": anchor_result["candidate_by_seat"]["bb"][
                        "candidate_bb100"
                    ],
                    "bb_ci95_bb100": anchor_result["candidate_by_seat"]["bb"][
                        "candidate_ci95_bb100"
                    ],
                    "sb_bb100": anchor_result["candidate_by_seat"]["sb"][
                        "candidate_bb100"
                    ],
                    "sb_ci95_bb100": anchor_result["candidate_by_seat"]["sb"][
                        "candidate_ci95_bb100"
                    ],
                    "seat_gap_sb_minus_bb": (
                        anchor_result["candidate_by_seat"]["sb"][
                            "candidate_bb100"
                        ]
                        - anchor_result["candidate_by_seat"]["bb"][
                            "candidate_bb100"
                        ]
                    ),
                    "mirror_signal_valid": anchor_result[
                        "mirror_signal_valid"
                    ],
                }
            )

    transitions: list[dict[str, Any]] = []
    for anchor_label, _ in anchors:
        anchor_rows = [row for row in rows if row["anchor"] == anchor_label]
        for previous, current in zip(anchor_rows, anchor_rows[1:]):
            previous_outcomes = outcome_lookup[
                (previous["candidate"], anchor_label)
            ]
            current_outcomes = outcome_lookup[
                (current["candidate"], anchor_label)
            ]
            overall_delta, overall_delta_ci95 = paired_delta(
                previous_outcomes["overall_bb_per_hand"],
                current_outcomes["overall_bb_per_hand"],
            )
            bb_delta, bb_delta_ci95 = paired_delta(
                previous_outcomes["bb_bb_per_hand"],
                current_outcomes["bb_bb_per_hand"],
            )
            sb_delta, sb_delta_ci95 = paired_delta(
                previous_outcomes["sb_bb_per_hand"],
                current_outcomes["sb_bb_per_hand"],
            )
            transitions.append(
                {
                    "anchor": anchor_label,
                    "from_candidate": previous["candidate"],
                    "to_candidate": current["candidate"],
                    "from_total_hands": previous["checkpoint_total_hands"],
                    "to_total_hands": current["checkpoint_total_hands"],
                    "overall_delta_bb100": overall_delta,
                    "overall_delta_ci95_bb100": overall_delta_ci95,
                    "bb_delta_bb100": bb_delta,
                    "bb_delta_ci95_bb100": bb_delta_ci95,
                    "sb_delta_bb100": sb_delta,
                    "sb_delta_ci95_bb100": sb_delta_ci95,
                    "structural_label": structural_label(
                        overall_delta, bb_delta, sb_delta
                    ),
                }
            )

    return {
        "kind": "stable_seat_resolved_internal_training_curve",
        "checked_at": utc_now(),
        "claim_scope": "INTERNAL_ONLY_NOT_SLUMBOT_NOT_FORMAL_STRENGTH",
        "interpretation_contract": {
            "valid_use": (
                "Compare frozen checkpoints from the same method/lineage using "
                "the fixed opponents, mirrored deals, and seed recorded here."
            ),
            "invalid_use": (
                "Do not combine hand counts across different methods or infer "
                "formal strength from this internal curve."
            ),
            "checkpoint_delta_ci": (
                "Adjacent checkpoint deltas and CI95 use per-deck paired outcomes "
                "under the same anchor and shuffled-deck stream."
            ),
        },
        "evaluator": {
            "path": str(MIRROR_EVALUATOR),
            "sha256": evaluator_sha256,
        },
        "pairs_per_candidate_anchor": pairs,
        "hands_per_candidate_anchor": pairs * 2,
        "seed": seed,
        "device": device,
        "candidate_order": [
            {"label": label, "path": str(path)} for label, path in candidates
        ],
        "anchors": [
            {"label": label, "path": str(path), "sha256": sha256_file(path)}
            for label, path in anchors
        ],
        "rows": rows,
        "transitions": transitions,
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# Stable Seat-Resolved Internal Training Curve",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Mirrored pairs per candidate/anchor: `{summary['pairs_per_candidate_anchor']}`",
        f"- Fixed seed: `{summary['seed']}`",
        f"- Evaluator SHA256: `{summary['evaluator']['sha256']}`",
        "",
        "Internal diagnostic only. Compare checkpoints from the same method; do not treat this as a Slumbot or formal-strength result.",
        "",
        "## Curve",
        "",
        "| candidate | total hands | anchor | overall bb/100 | CI95 | BB | SB | SB-BB gap |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary["rows"]:
        lines.append(
            "| {candidate} | {hands} | {anchor} | {overall:+.2f} | +/-{ci:.2f} | {bb:+.2f} | {sb:+.2f} | {gap:+.2f} |".format(
                candidate=row["candidate"],
                hands=(
                    f"{int(row['checkpoint_total_hands']):,}"
                    if row["checkpoint_total_hands"] is not None
                    else "unknown"
                ),
                anchor=row["anchor"],
                overall=float(row["overall_bb100"]),
                ci=float(row["overall_ci95_bb100"]),
                bb=float(row["bb_bb100"]),
                sb=float(row["sb_bb100"]),
                gap=float(row["seat_gap_sb_minus_bb"]),
            )
        )
    lines.extend(
        [
            "",
            "## Structural transitions",
            "",
            "| anchor | from | to | overall delta (CI95) | BB delta (CI95) | SB delta (CI95) | diagnosis |",
            "|---|---|---|---:|---:|---:|---|",
        ]
    )
    for row in summary["transitions"]:
        lines.append(
            "| {anchor} | {source} | {target} | {overall:+.2f} (+/-{overall_ci:.2f}) | {bb:+.2f} (+/-{bb_ci:.2f}) | {sb:+.2f} (+/-{sb_ci:.2f}) | {label} |".format(
                anchor=row["anchor"],
                source=row["from_candidate"],
                target=row["to_candidate"],
                overall=float(row["overall_delta_bb100"]),
                overall_ci=float(row["overall_delta_ci95_bb100"]),
                bb=float(row["bb_delta_bb100"]),
                bb_ci=float(row["bb_delta_ci95_bb100"]),
                sb=float(row["sb_delta_bb100"]),
                sb_ci=float(row["sb_delta_ci95_bb100"]),
                label=row["structural_label"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stable mirrored-deal learning curve over frozen checkpoints."
    )
    parser.add_argument(
        "--candidate",
        action="append",
        required=True,
        help="Ordered checkpoint as label=path; repeat for each volume milestone.",
    )
    parser.add_argument(
        "--anchor",
        action="append",
        required=True,
        help="Frozen network opponent as label=path; repeat for a fixed suite.",
    )
    parser.add_argument("--pairs", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=20260727)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--priority", choices=("below-normal", "normal"), default="below-normal")
    parser.add_argument("--torch-threads", type=int, default=1)
    parser.add_argument("--torch-interop-threads", type=int, default=1)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse a candidate result only when all hashes and settings match.",
    )
    args = parser.parse_args()

    candidates = [parse_labeled_path(item) for item in args.candidate]
    anchors = [parse_labeled_path(item) for item in args.anchor]
    labels = [label for label, _ in candidates]
    anchor_labels = [label for label, _ in anchors]
    if len(set(labels)) != len(labels):
        raise ValueError("candidate labels must be unique")
    if len(set(anchor_labels)) != len(anchor_labels):
        raise ValueError("anchor labels must be unique")
    if args.pairs <= 0:
        raise ValueError("--pairs must be positive")
    for _, path in [*candidates, *anchors]:
        if not path.is_file():
            raise FileNotFoundError(path)

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    evaluator_sha256 = sha256_file(MIRROR_EVALUATOR)
    anchor_hashes = {label: sha256_file(path) for label, path in anchors}
    results: list[dict[str, Any]] = []

    for label, candidate_path in candidates:
        stem = safe_name(label)
        result_path = out_dir / f"{stem}.mirror.json"
        markdown_path = out_dir / f"{stem}.mirror.md"
        execution_path = out_dir / f"{stem}.execution.json"
        candidate_sha256 = sha256_file(candidate_path)
        if not (
            args.resume
            and reusable_result(
                result_path,
                candidate_sha256=candidate_sha256,
                anchor_sha256=anchor_hashes,
                pairs=args.pairs,
                seed=args.seed,
            )
        ):
            command = [
                sys.executable,
                "-X",
                "utf8",
                str(MIRROR_EVALUATOR),
                "--candidate",
                str(candidate_path),
                "--candidate-label",
                label,
                "--pairs",
                str(args.pairs),
                "--include-pair-outcomes",
                "--seed",
                str(args.seed),
                "--device",
                args.device,
                "--priority",
                args.priority,
                "--torch-threads",
                str(args.torch_threads),
                "--torch-interop-threads",
                str(args.torch_interop_threads),
                "--out-json",
                str(result_path),
                "--out-md",
                str(markdown_path),
                "--execution-json",
                str(execution_path),
            ]
            for anchor_label, anchor_path in anchors:
                command.extend(["--anchor", f"{anchor_label}={anchor_path}"])
            subprocess.run(command, check=True)
        if sha256_file(candidate_path) != candidate_sha256:
            raise RuntimeError(
                f"candidate changed during evaluation and is not frozen: {candidate_path}"
            )
        if {
            anchor_label: sha256_file(anchor_path)
            for anchor_label, anchor_path in anchors
        } != anchor_hashes:
            raise RuntimeError("an anchor changed during evaluation")
        results.append(json.loads(result_path.read_text(encoding="utf-8")))

    summary = build_summary(
        candidates=candidates,
        anchors=anchors,
        results=results,
        pairs=args.pairs,
        seed=args.seed,
        device=args.device,
        evaluator_sha256=evaluator_sha256,
    )
    json_path = out_dir / "training_curve.json"
    markdown_path = out_dir / "training_curve.md"
    json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_markdown(summary, markdown_path)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
