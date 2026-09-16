"""Aggregate a frozen-evidence seven-objective parent-KL dose curve."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.audit_v6_integrated_gradient_conflict import (
    parse_named_path,
    sha256_path,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dose-run", action="append", type=parse_named_path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    started = time.time()
    rows = []
    audit_hashes = set()
    parent_hashes = None
    for label, path in args.dose_run:
        summary = json.loads(path.read_text(encoding="utf-8"))
        dose = float(summary["target_parent_kl"])
        audit_hashes.add(tuple(sorted(summary["audit"].items())))
        current_parents = tuple(
            (name, row["parent"]["sha256"])
            for name, row in sorted(summary["candidates"].items())
        )
        if parent_hashes is None:
            parent_hashes = current_parents
        elif current_parents != parent_hashes:
            raise ValueError("dose runs do not share parent checkpoints")
        candidate_rows = {}
        for candidate, candidate_row in summary["candidates"].items():
            treatment = candidate_row["arms"]["treatment"]
            control = candidate_row["arms"]["control"]
            candidate_rows[candidate] = {
                "treatment_all_seven_improve": treatment[
                    "all_seven_objectives_improve_on_training_cohort"
                ],
                "treatment_source_kl_delta": treatment["source_forward_kl_delta"],
                "treatment_worst_reward_loss_delta": max(
                    treatment["group_policy_loss_deltas"].values()
                ),
                "treatment_checkpoint": treatment["checkpoint"],
                "control_all_seven_improve": control[
                    "all_seven_objectives_improve_on_training_cohort"
                ],
                "control_source_kl_delta": control["source_forward_kl_delta"],
                "control_worst_reward_loss_delta": max(
                    control["group_policy_loss_deltas"].values()
                ),
                "control_checkpoint": control["checkpoint"],
                "treatment_parent_kl": treatment["achieved_parent_kl"],
                "control_parent_kl": control["achieved_parent_kl"],
            }
        admit = bool(summary["admit_untouched_evaluation"])
        rows.append(
            {
                "label": label,
                "target_parent_kl": dose,
                "summary_path": str(path.resolve()),
                "summary_sha256": sha256_path(path),
                "admit_untouched_evaluation": admit,
                "candidates": candidate_rows,
            }
        )
    rows.sort(key=lambda row: row["target_parent_kl"])
    admitted = [row for row in rows if row["admit_untouched_evaluation"]]
    selected = admitted[-1] if admitted else None
    gates = {
        "shared_audit_evidence": len(audit_hashes) == 1,
        "shared_parent_checkpoints": parent_hashes is not None,
        "strictly_increasing_doses": all(
            left["target_parent_kl"] < right["target_parent_kl"]
            for left, right in zip(rows, rows[1:])
        ),
        "at_least_one_common_descent_dose": selected is not None,
    }
    result = {
        "schema": "cardpilot.integrated_seven_objective_dose_curve.v1",
        "status": "COMPLETED",
        "dose_rows": rows,
        "gates": gates,
        "selected": selected,
        "decision": (
            "EVALUATE_LARGEST_COMMON_DESCENT_DOSE"
            if all(gates.values())
            else "REJECT_DIRECT_SEVEN_OBJECTIVE_UPDATE_AT_TESTED_DOSES"
        ),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
