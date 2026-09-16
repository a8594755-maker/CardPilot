"""Compare two CFR JSONL strategy checkpoints with deterministic key sampling.

All shallow flop nodes are retained; deeper information sets are selected by a
stable hash so very large checkpoints can be compared without loading either
entire file into memory.  This measures checkpoint drift, not exploitability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def selected(key: str, sample_rate: float) -> bool:
    street, _, _, history, _ = key.split("|", 4)
    if street == "F" and len(history) <= 1:
        return True
    value = int.from_bytes(hashlib.blake2b(key.encode(), digest_size=8).digest(), "big")
    return value / 2**64 < sample_rate


def normalize(values: Iterable[float]) -> list[float]:
    probs = [max(float(value), 0.0) for value in values]
    total = sum(probs)
    if total <= 0 or not math.isfinite(total):
        raise ValueError("invalid probability row")
    return [value / total for value in probs]


def js_divergence(left: list[float], right: list[float]) -> float:
    middle = [(a + b) / 2 for a, b in zip(left, right)]

    def kl(p: list[float], q: list[float]) -> float:
        return sum(a * math.log(a / b) for a, b in zip(p, q) if a > 0 and b > 0)

    return (kl(left, middle) + kl(right, middle)) / 2


def group_name(key: str) -> str:
    street, _, _, history, _ = key.split("|", 4)
    depth = len(history.replace("/", ""))
    return f"{street}:depth{min(depth, 8)}{'+' if depth > 8 else ''}"


def summarize(values: list[tuple[float, float, bool]]) -> dict[str, Any]:
    if not values:
        return {"rows": 0}
    tvs = sorted(value[0] for value in values)
    js = sorted(value[1] for value in values)

    def quantile(items: list[float], fraction: float) -> float:
        return items[min(len(items) - 1, int((len(items) - 1) * fraction))]

    return {
        "rows": len(values),
        "mean_total_variation": sum(tvs) / len(tvs),
        "median_total_variation": quantile(tvs, 0.5),
        "p90_total_variation": quantile(tvs, 0.9),
        "p99_total_variation": quantile(tvs, 0.99),
        "mean_js_divergence_nats": sum(js) / len(js),
        "p90_js_divergence_nats": quantile(js, 0.9),
        "argmax_agreement": sum(value[2] for value in values) / len(values),
        "fraction_tv_over_0_1": sum(value[0] > 0.1 for value in values) / len(values),
    }


def compare(old_path: Path, new_path: Path, sample_rate: float) -> dict[str, Any]:
    old: dict[str, list[float]] = {}
    old_rows = 0
    with old_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            old_rows += 1
            row = json.loads(line)
            key = str(row["key"])
            if selected(key, sample_rate):
                old[key] = normalize(row["probs"])

    compared: dict[str, list[tuple[float, float, bool]]] = defaultdict(list)
    found: set[str] = set()
    new_rows = 0
    new_selected = 0
    new_selected_not_old = 0
    for line in new_path.open("r", encoding="utf-8"):
        if not line.strip():
            continue
        new_rows += 1
        row = json.loads(line)
        key = str(row["key"])
        if not selected(key, sample_rate):
            continue
        new_selected += 1
        prior = old.get(key)
        if prior is None:
            new_selected_not_old += 1
            continue
        current = normalize(row["probs"])
        if len(prior) != len(current):
            raise ValueError(f"action-count mismatch for {key}")
        tv = sum(abs(a - b) for a, b in zip(prior, current)) / 2
        js = js_divergence(prior, current)
        argmax_same = prior.index(max(prior)) == current.index(max(current))
        compared[group_name(key)].append((tv, js, argmax_same))
        compared["ALL"].append((tv, js, argmax_same))
        found.add(key)

    old_missing_from_new = len(set(old) - found)
    return {
        "schema": "cardpilot.cfr_checkpoint_drift.v1",
        "claim_scope": "STRATEGY_DRIFT_NOT_EXPLOITABILITY",
        "old": {"path": str(old_path), "sha256": sha256_file(old_path), "rows": old_rows},
        "new": {"path": str(new_path), "sha256": sha256_file(new_path), "rows": new_rows},
        "sample_rate": sample_rate,
        "selection": "all flop histories of depth <=1 plus stable blake2b key sample",
        "old_selected_rows": len(old),
        "new_selected_rows": new_selected,
        "new_selected_not_old": new_selected_not_old,
        "old_selected_missing_from_new": old_missing_from_new,
        "groups": {
            key: summarize(values)
            for key, values in sorted(compared.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--sample-rate", type=float, default=0.01)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.sample_rate <= 1:
        raise ValueError("--sample-rate must be in (0, 1]")
    report = compare(args.old.resolve(), args.new.resolve(), args.sample_rate)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "old_rows": report["old"]["rows"],
        "new_rows": report["new"]["rows"],
        "old_selected": report["old_selected_rows"],
        "new_selected_not_old": report["new_selected_not_old"],
        "all": report["groups"].get("ALL", {}),
        "out": str(args.out),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
