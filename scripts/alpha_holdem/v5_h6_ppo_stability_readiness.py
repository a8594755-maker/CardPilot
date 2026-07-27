#!/usr/bin/env python3
"""Reporting-only readiness evidence for a possible H6 PPO KL-stability window."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


ROW_RE = re.compile(
    r"^\[(?P<iteration>\d+)\].*?hands=(?P<hands>[\d,]+).*?"
    r"ent=(?P<entropy>[+-]?\d+(?:\.\d+)?)\s+kl=(?P<kl>[+-]?\d+(?:\.\d+)?)\s+"
    r"(?:ep=\d+/\d+\s+)?(?:klstop=[01]\s+)?"
    r"clipfrac=(?P<clip>[+-]?\d+(?:\.\d+)?).*?rmax=(?P<rmax>[+-]?\d+(?:\.\d+)?)"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_rows(text: str) -> list[dict[str, float | int]]:
    rows = []
    for line in text.splitlines():
        match = ROW_RE.search(line.strip())
        if not match:
            continue
        rows.append({
            "iteration": int(match.group("iteration")),
            "hands": int(match.group("hands").replace(",", "")),
            "entropy": float(match.group("entropy")),
            "approx_kl": float(match.group("kl")),
            "clip_frac": float(match.group("clip")),
            "ratio_max": float(match.group("rmax")),
        })
    return rows


def summarize(rows: list[dict[str, float | int]], threshold: float = 0.03) -> dict[str, Any]:
    if not rows:
        raise ValueError("no parseable training rows")
    kl = np.asarray([row["approx_kl"] for row in rows], dtype=np.float64)
    clip = np.asarray([row["clip_frac"] for row in rows], dtype=np.float64)
    rmax = np.asarray([row["ratio_max"] for row in rows], dtype=np.float64)
    return {
        "rows": len(rows),
        "iteration_first": int(rows[0]["iteration"]),
        "iteration_last": int(rows[-1]["iteration"]),
        "hands_first": int(rows[0]["hands"]),
        "hands_last": int(rows[-1]["hands"]),
        "registered_roadmap_kl_threshold": threshold,
        "approx_kl": {
            "mean": float(kl.mean()),
            "p50": float(np.quantile(kl, 0.50)),
            "p95": float(np.quantile(kl, 0.95)),
            "p99": float(np.quantile(kl, 0.99)),
            "max": float(kl.max()),
            "rows_above_threshold": int((kl > threshold).sum()),
            "fraction_above_threshold": float((kl > threshold).mean()),
        },
        "clip_frac": {"mean": float(clip.mean()), "p95": float(np.quantile(clip, 0.95)), "max": float(clip.max())},
        "ratio_max": {"p95": float(np.quantile(rmax, 0.95)), "p99": float(np.quantile(rmax, 0.99)), "max": float(rmax.max())},
    }


def build(log: Path, trainer: Path, ppo: Path, roadmap: Path) -> dict[str, Any]:
    rows = parse_rows(log.read_text(encoding="utf-8-sig", errors="replace"))
    summary = summarize(rows)
    trainer_text = trainer.read_text(encoding="utf-8-sig", errors="replace")
    ppo_text = ppo.read_text(encoding="utf-8-sig", errors="replace")
    early_stop_present = "target_kl" in trainer_text or "target_kl" in ppo_text or "early_stop_kl" in trainer_text or "early_stop_kl" in ppo_text
    excursions = summary["approx_kl"]["rows_above_threshold"]
    return {
        "schema_version": "v5.hybrid.h6.ppo_stability_readiness.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "ASSOCIATIONAL_MECHANISM_SUPPORT_NO_LAUNCH" if excursions else "NO_REGISTERED_THRESHOLD_EXCURSION",
        "question": "Does the exact H2 control window exhibit PPO KL excursions above the pre-existing roadmap threshold while the trainer lacks KL early-stop?",
        "evidence_level": "ASSOCIATIONAL_CODE_MECHANISM_ONLY",
        "summary": summary,
        "implementation": {"kl_early_stop_present": early_stop_present, "ppo_epochs_fixed": 4},
        "source_identity": [
            {"path": str(path.resolve()), "sha256": sha256(path)}
            for path in (log, trainer, ppo, roadmap)
        ],
        "inference": "This may nominate a separately preregistered same-start KL-early-stop-only window. It cannot prove poker strength, choose an action, or launch behavior by itself.",
        "behavior_launch_authorized": False,
        "official_hands_authorized": 0,
        "strength_claim": "FORBIDDEN",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--trainer", required=True, type=Path)
    parser.add_argument("--ppo", required=True, type=Path)
    parser.add_argument("--roadmap", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f"one-shot output exists: {args.out}")
    result = build(args.log, args.trainer, args.ppo, args.roadmap)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": result["overall"], **result["summary"]["approx_kl"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
