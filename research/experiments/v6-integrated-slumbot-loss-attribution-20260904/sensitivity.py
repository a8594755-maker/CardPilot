#!/usr/bin/env python3
"""Post-hoc robustness checks for the preregistered supported class."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path


BASE = Path(__file__).resolve().parent
RAW = BASE / "hand_attribution_raw.jsonl.gz"
ANALYSIS = BASE / "analysis.json"
OUT = BASE / "sensitivity.json"
KEY = "final_pot_bucket=ge30"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def effect(rows: list[dict]) -> dict:
    selected = [row["winnings_bb"] for row in rows if KEY in row["class_keys"]]
    other = [row["winnings_bb"] for row in rows if KEY not in row["class_keys"]]
    selected_mean = sum(selected) / len(selected)
    other_mean = sum(other) / len(other)
    return {
        "class_hands": len(selected),
        "complement_hands": len(other),
        "class_net_bb": sum(selected),
        "complement_net_bb": sum(other),
        "class_minus_complement_bb100": (selected_mean - other_mean) * 100.0,
    }


def proxy(rows: list[dict]) -> dict:
    selected = [row for row in rows if KEY in row["class_keys"] and row["teacher_admissible"]]
    other = [row for row in rows if KEY not in row["class_keys"] and row["teacher_admissible"]]
    a = sum(row["onpolicy_vs_teacher_consensus"] for row in selected)
    c = sum(row["onpolicy_vs_teacher_consensus"] for row in other)
    p1, p0 = a / len(selected), c / len(other)
    difference = p1 - p0
    se = math.sqrt(p1 * (1.0 - p1) / len(selected) + p0 * (1.0 - p0) / len(other))
    return {
        "class_rows": len(selected),
        "class_disagreements": a,
        "complement_rows": len(other),
        "complement_disagreements": c,
        "difference": difference,
        "wald_ci95_low": difference - 1.96 * se,
        "wald_ci95_high": difference + 1.96 * se,
    }


def main() -> None:
    if OUT.exists():
        raise FileExistsError(OUT)
    analysis = json.loads(ANALYSIS.read_text(encoding="utf-8"))
    if analysis["supported_classes"] != [KEY] or analysis["raw_sha256"] != sha256_file(RAW):
        raise RuntimeError("preregistered analysis or raw hash mismatch")
    rows = []
    with gzip.open(RAW, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["split"] == "confirmation":
                rows.append(row)
    by_corpus = defaultdict(list)
    for row in rows:
        by_corpus[row["corpus"]].append(row)
    corpora = {}
    for corpus, current in sorted(by_corpus.items()):
        leave_one_session_out = {
            str(session): effect([row for row in current if int(row["session"]) != session])
            for session in (5, 6, 7, 8)
        }
        subclasses = {}
        for field in ("seat", "terminal_kind", "final_street", "final_action_class"):
            for value in sorted({row[field] for row in current if KEY in row["class_keys"]}):
                subset = [row for row in current if row[field] == value]
                subclasses[f"{field}={value}"] = effect(subset)
        corpora[corpus] = {
            "full": effect(current),
            "proxy": proxy(current),
            "leave_one_session_out": leave_one_session_out,
            "all_leave_one_session_out_effects_negative": all(
                item["class_minus_complement_bb100"] < 0
                for item in leave_one_session_out.values()
            ),
            "subclasses_posthoc": subclasses,
        }
    result = {
        "schema": "cardpilot.integrated_slumbot_loss_attribution_sensitivity.v1",
        "status": "COMPLETED",
        "posthoc_not_used_for_preregistered_decision": True,
        "supported_class": KEY,
        "corpora": corpora,
        "raw_sha256": sha256_file(RAW),
        "analysis_sha256": sha256_file(ANALYSIS),
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
