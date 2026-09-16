"""Independent terminal review of the matched soup pool-diversity pilot."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rows(path: Path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ci(values: np.ndarray) -> tuple[float, float, float]:
    mean = float(values.mean())
    half = float(1.96 * values.std(ddof=1) / math.sqrt(values.size))
    return mean, mean - half, mean + half


def main() -> None:
    control_audit = read(BASE / "control/session_audit.json")
    treatment_audit = read(BASE / "treatment/session_audit.json")
    checks = {
        "control_session_audit": control_audit["status"] == "PASS",
        "treatment_session_audit": treatment_audit["status"] == "PASS",
        "matched_iteration": control_audit["final_iteration"]
        == treatment_audit["final_iteration"]
        == 16,
        "physical_targets": control_audit["actual_environment_hands"] >= 65536
        and treatment_audit["actual_environment_hands"] >= 65536,
    }

    control_assignments = rows(BASE / "control/opponent_assignments.jsonl")
    treatment_assignments = rows(BASE / "treatment/opponent_assignments.jsonl")
    checks["matched_assignment_local_indices"] = (
        len(control_assignments) == len(treatment_assignments) == 16
        and all(
            c["group_metadata"] == t["group_metadata"]
            and [row["opponent"]["local_index"] for row in c["workers"]]
            == [row["opponent"]["local_index"] for row in t["workers"]]
            for c, t in zip(control_assignments, treatment_assignments)
        )
    )

    recorded = read(BASE / "eval/paired_delta.json")
    recomputed_anchors = []
    pooled = []
    for expected in recorded["anchors"]:
        name = expected["anchor"]
        control_path = BASE / "eval" / f"control_{name}" / "pairs.jsonl"
        treatment_path = BASE / "eval" / f"treatment_{name}" / "pairs.jsonl"
        control_rows = rows(control_path)
        treatment_rows = rows(treatment_path)
        checks[f"{name}_pair_count"] = (
            len(control_rows) == len(treatment_rows) == 2048
        )
        checks[f"{name}_deck_identity"] = all(
            c["deck"] == t["deck"] and c["pair_index"] == i and t["pair_index"] == i
            for i, (c, t) in enumerate(zip(control_rows, treatment_rows))
        )
        control = np.asarray(
            [float(np.mean(row["rewards_bb"]) * 100.0) for row in control_rows]
        )
        treatment = np.asarray(
            [float(np.mean(row["rewards_bb"]) * 100.0) for row in treatment_rows]
        )
        delta = treatment - control
        mean, lower, upper = ci(delta)
        checks[f"{name}_raw_recompute"] = (
            math.isclose(mean, expected["treatment_minus_control_bb100"], abs_tol=1e-12)
            and np.allclose([lower, upper], expected["paired_ci95"], atol=1e-12, rtol=0)
            and sha256(control_path) == expected["control_pairs_sha256"]
            and sha256(treatment_path) == expected["treatment_pairs_sha256"]
        )
        pooled.extend(delta.tolist())
        recomputed_anchors.append({"anchor": name, "delta_bb100": mean, "ci95": [lower, upper]})
    pooled_values = np.asarray(pooled)
    pooled_mean, pooled_lower, pooled_upper = ci(pooled_values)
    checks["pooled_raw_recompute"] = (
        math.isclose(pooled_mean, recorded["pooled"]["treatment_minus_control_bb100"], abs_tol=1e-12)
        and np.allclose(
            [pooled_lower, pooled_upper], recorded["pooled"]["paired_ci95"], atol=1e-12, rtol=0
        )
    )

    drift = read(BASE / "source_state_drift/summary.json")
    drift_rows = rows(BASE / "source_state_drift/state_metrics.jsonl")
    control_tv = np.asarray([row["control_total_variation"] for row in drift_rows])
    treatment_tv = np.asarray([row["treatment_total_variation"] for row in drift_rows])
    control_dis = np.asarray([row["control_greedy_disagreement"] for row in drift_rows])
    treatment_dis = np.asarray([row["treatment_greedy_disagreement"] for row in drift_rows])
    checks["source_state_count_hash"] = (
        len(drift_rows) == drift["states"] == 60671
        and sha256(BASE / "source_state_drift/state_metrics.jsonl") == drift["state_metrics_sha256"]
    )
    checks["source_state_raw_recompute"] = all(
        math.isclose(actual, expected, abs_tol=1e-12)
        for actual, expected in (
            (float(control_tv.mean()), drift["control_mean_total_variation"]),
            (float(treatment_tv.mean()), drift["treatment_mean_total_variation"]),
            (float(control_dis.mean()), drift["control_greedy_disagreement_rate"]),
            (float(treatment_dis.mean()), drift["treatment_greedy_disagreement_rate"]),
        )
    )
    checks["treatment_drift_worse"] = (
        float(treatment_tv.mean()) > float(control_tv.mean())
        and float(treatment_dis.mean()) > float(control_dis.mean())
        and not drift["gate"]["passed"]
    )
    checks["checkpoint_hashes"] = (
        sha256(BASE / "control/latest.pt")
        == control_audit["artifact_integrity"]["checkpoint"]["sha256"]
        and sha256(BASE / "treatment/latest.pt")
        == treatment_audit["artifact_integrity"]["checkpoint"]["sha256"]
    )

    output = {
        "schema": "cardpilot.soup_uniform_pool_diversity_terminal_review.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "training_hands": {
            "control_physical": control_audit["actual_environment_hands"],
            "treatment_physical": treatment_audit["actual_environment_hands"],
        },
        "learned_panel": {
            "anchors": recomputed_anchors,
            "pooled_delta_bb100": pooled_mean,
            "pooled_ci95": [pooled_lower, pooled_upper],
            "positive_anchors": recorded["pooled"]["positive_anchors"],
        },
        "source_state_drift": {
            "states": len(drift_rows),
            "control_tv": float(control_tv.mean()),
            "treatment_tv": float(treatment_tv.mean()),
            "control_greedy_disagreement": float(control_dis.mean()),
            "treatment_greedy_disagreement": float(treatment_dis.mean()),
        },
        "decision": "DO_NOT_ALLOCATE_SLUMBOT_NO_DIVERSITY_GAIN",
    }
    (BASE / "terminal_review.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, indent=2, sort_keys=True))
    if output["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
