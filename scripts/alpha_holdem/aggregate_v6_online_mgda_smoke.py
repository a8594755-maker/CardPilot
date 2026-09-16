"""Audit a matched ordinary-control versus online opponent-seat MGDA smoke."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--first-iteration", type=int, required=True)
    parser.add_argument("--iterations", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    audit_path = args.experiment_dir / "training_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    expected_iterations = list(
        range(args.first_iteration, args.first_iteration + args.iterations)
    )

    arms = {}
    for arm in ("control", "treatment"):
        run_dir = args.experiment_dir / arm
        manifest_path = run_dir / "run_manifest.json"
        metrics_path = run_dir / "h1_training_metrics.jsonl"
        checkpoint_path = run_dir / "latest.pt"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        rows = [
            row for row in load_jsonl(metrics_path)
            if int(row["iteration"]) in expected_iterations
        ]
        diagnostics = [
            diagnostic
            for row in rows
            for diagnostic in row.get("opponent_seat_gradient_diagnostics", [])
        ]
        updates = [
            update
            for row in rows
            for update in row.get("opponent_seat_mgda_updates", [])
        ]
        arms[arm] = {
            "iterations": [int(row["iteration"]) for row in rows],
            "environment_hands": int(
                rows[-1]["environment_hand_accounting"]["completed_hands"]
            ),
            "ordinary_probe_harmful_counts": [
                int(row["aggregate_harmful_objective_count"])
                for row in diagnostics
            ],
            "mgda_updates": len(updates),
            "mgda_worst_alignments": [
                float(update["worst_intervention_alignment"])
                for update in updates
            ],
            "mgda_norm_ratios": [
                float(update["intervention_actor_gradient_l2"])
                / float(update["ordinary_actor_gradient_l2"])
                for update in updates
            ],
            "mgda_kkt_slack": [
                float(update["kkt_min_product_minus_objective"])
                for update in updates
            ],
            "config_mgda": bool(
                manifest.get("config", {}).get("opponent_seat_mgda", False)
            ),
            "hashes": {
                "checkpoint": sha256_path(checkpoint_path),
                "manifest": sha256_path(manifest_path),
                "metrics": sha256_path(metrics_path),
            },
        }

    audited = {row["name"]: row for row in audit["runs"]}
    treatment_updates = arms["treatment"]["mgda_updates"]
    gates = {
        "training_audit_passed": bool(audit.get("passed")),
        "same_parent_checkpoint": (
            audited["control"]["continuation"]["parent_sha256"]
            == audited["treatment"]["continuation"]["parent_sha256"]
        ),
        "iterations_exact": all(
            row["iterations"] == expected_iterations for row in arms.values()
        ),
        "control_disabled": not arms["control"]["config_mgda"],
        "control_has_no_mgda_updates": arms["control"]["mgda_updates"] == 0,
        "treatment_enabled": arms["treatment"]["config_mgda"],
        "treatment_updates_present": treatment_updates > 0,
        "ordinary_conflict_observed_both_arms": all(
            counts and all(value > 0 for value in counts)
            for counts in (
                arms["control"]["ordinary_probe_harmful_counts"],
                arms["treatment"]["ordinary_probe_harmful_counts"],
            )
        ),
        "strict_common_descent_every_treatment_update": all(
            value > 0.0 for value in arms["treatment"]["mgda_worst_alignments"]
        ),
        "actor_gradient_norm_matched": all(
            math.isclose(value, 1.0, rel_tol=1e-5, abs_tol=1e-7)
            for value in arms["treatment"]["mgda_norm_ratios"]
        ),
        "simplex_kkt_valid": all(
            value >= -1e-7 for value in arms["treatment"]["mgda_kkt_slack"]
        ),
    }
    if not all(gates.values()):
        raise RuntimeError(f"online MGDA smoke gates failed: {gates}")
    result = {
        "schema": "cardpilot.integrated_online_mgda_smoke.v1",
        "arms": arms,
        "gates": gates,
        "passed": all(gates.values()),
        "decision": "ADMIT_ONLINE_MGDA_FRESH_BREADTH_PILOT",
        "training_audit_sha256": sha256_path(audit_path),
        "command": [sys.executable, *sys.argv],
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
