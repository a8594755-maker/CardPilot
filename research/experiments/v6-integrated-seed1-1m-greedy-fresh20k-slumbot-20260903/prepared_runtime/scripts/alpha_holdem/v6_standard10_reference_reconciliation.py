"""Reconcile historical and current exact-bridge Standard10 evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def estimate(record: dict) -> tuple[float, float, float]:
    metrics = record["metrics"]
    mean = float(metrics["bb_per_100"])
    low = float(metrics.get("ci95_lower", metrics.get("ci95_lower_bb_per_100")))
    high = float(metrics.get("ci95_upper", metrics.get("ci95_upper_bb_per_100")))
    return mean, low, high


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--parity", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    historical = json.loads(args.historical.read_text(encoding="utf-8"))
    current = json.loads(args.current.read_text(encoding="utf-8"))
    parity = json.loads(args.parity.read_text(encoding="utf-8"))
    old_mean, old_low, old_high = estimate(historical)
    new_mean, new_low, new_high = estimate(current)
    old_se = (old_high - old_low) / 3.92
    new_se = (new_high - new_low) / 3.92
    delta = old_mean - new_mean
    delta_se = math.sqrt(old_se * old_se + new_se * new_se)
    delta_low = delta - 1.96 * delta_se
    delta_high = delta + 1.96 * delta_se
    old_weight = 1.0 / (old_se * old_se)
    new_weight = 1.0 / (new_se * new_se)
    pooled = (old_weight * old_mean + new_weight * new_mean) / (old_weight + new_weight)
    pooled_se = math.sqrt(1.0 / (old_weight + new_weight))
    gates = {
        "same_policy_execution_exact_on_20000_states": (
            parity["metrics"]["exact_action_parity"] == 1.0
            and parity["metrics"]["exact_legacy_slot_parity"] == 1.0
            and parity["metrics"]["exact_v6_legality"] == 1.0
        ),
        "historical_point_inside_current_ci": new_low <= old_mean <= new_high,
        "current_point_inside_historical_ci": old_low <= new_mean <= old_high,
        "independent_difference_ci_contains_zero": delta_low <= 0 <= delta_high,
        "historical_raw_hands_not_available": not any(
            "hands.jsonl" in artifact or "sessions" in artifact
            for artifact in historical.get("artifacts", [])
        ),
    }
    output = {
        "schema": "cardpilot.standard10_reference_reconciliation.v1",
        "inputs": {
            "historical": str(args.historical.resolve()),
            "historical_sha256": sha256_path(args.historical),
            "current": str(args.current.resolve()),
            "current_sha256": sha256_path(args.current),
            "parity": str(args.parity.resolve()),
            "parity_sha256": sha256_path(args.parity),
        },
        "historical": {"hands": 20_000, "bb100": old_mean, "ci95": [old_low, old_high]},
        "current": {"hands": 20_000, "bb100": new_mean, "ci95": [new_low, new_high]},
        "historical_minus_current": {
            "bb100": delta,
            "ci95_low_bb100": delta_low,
            "ci95_high_bb100": delta_high,
        },
        "summary_only_inverse_variance_reference": {
            "hands": 40_000,
            "bb100": pooled,
            "ci95_low_bb100": pooled - 1.96 * pooled_se,
            "ci95_high_bb100": pooled + 1.96 * pooled_se,
            "formal_goal_evidence": False,
        },
        "gates": gates,
        "passed": all(gates.values()),
        "decision": (
            "RECONCILE_AS_SAME_POLICY_UNRESOLVED_SAMPLE_VARIATION"
            if all(gates.values()) else "REFERENCE_RECONCILIATION_FAILED"
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, sort_keys=True))
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
