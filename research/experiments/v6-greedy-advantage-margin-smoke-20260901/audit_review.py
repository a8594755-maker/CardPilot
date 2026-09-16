"""Independent evidence review for the matched greedy-margin smoke."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = ROOT / "models/baseline/standard10/latest.pt"
SOURCE_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
EXPECTED = {
    "control": {
        "sha256": "d806394bc8f8068f8b72e19153d6f96c14f09e8c41c1418091e8441a977c8e29",
        "physical_hands": 10748,
        "transition_hands": 8220,
        "coef": 0.0,
    },
    "treatment": {
        "sha256": "412ec6b79463421e30ea51d93d1aa994a336c772102ed534739d6d8e8fb534f0",
        "physical_hands": 10746,
        "transition_hands": 8286,
        "coef": 0.05,
    },
}
ALLOWED_CHANGED_TENSORS = {
    "policy_head.weight", "policy_head.bias",
    "preflop_policy_head.weight", "preflop_policy_head.bias",
    "value_head.0.weight", "value_head.0.bias",
    "value_head.2.weight", "value_head.2.bias",
    "value_head.4.weight", "value_head.4.bias",
}


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def metric_rows(arm: str) -> list[dict]:
    path = BASE / arm / "h1_training_metrics.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def assignments(arm: str) -> list[dict]:
    path = BASE / arm / "opponent_assignments.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def raw_pair_values(path: Path) -> tuple[list[list[int]], np.ndarray]:
    decks, values = [], []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        row = json.loads(line)
        assert row["pair_index"] == index and len(row["rewards_bb"]) == 2
        decks.append(row["deck"])
        values.append(float(np.mean(row["rewards_bb"]) * 100.0))
    return decks, np.asarray(values, dtype=np.float64)


def mean_ci(values: np.ndarray) -> tuple[float, list[float]]:
    mean = float(values.mean())
    half = float(1.96 * values.std(ddof=1) / math.sqrt(values.size))
    return mean, [mean - half, mean + half]


def main() -> None:
    assert sha256(SOURCE) == SOURCE_SHA
    source = torch.load(SOURCE, map_location="cpu", weights_only=False)["model"]
    arm_report = {}
    for arm, expected in EXPECTED.items():
        checkpoint_path = BASE / arm / "latest.pt"
        assert sha256(checkpoint_path) == expected["sha256"]
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        changed = {name for name, tensor in checkpoint["model"].items() if not torch.equal(tensor, source[name])}
        assert changed == ALLOWED_CHANGED_TENSORS
        assert all(torch.isfinite(tensor).all() for tensor in checkpoint["model"].values())
        audit = read(BASE / arm / "session_audit.json")
        assert audit["status"] == "PASS"
        assert audit["actual_environment_hands"] == expected["physical_hands"]
        assert audit["legacy_training_marker_hands"] == expected["transition_hands"]
        assert audit["final_iteration"] == 2 and audit["kl_early_stop_count"] == 0
        rows = metric_rows(arm)
        assert len(rows) == 2
        assert rows[-1]["environment_hand_accounting"]["completed_hands"] == expected["physical_hands"]
        assert rows[-1]["hands"] == expected["transition_hands"]
        assert all(row["greedy_advantage_margin_coef"] == expected["coef"] for row in rows)
        if arm == "control":
            assert all(row["greedy_advantage_margin_loss"] == 0.0 for row in rows)
            assert all(row["greedy_advantage_margin_eligible_rows"] == 0 for row in rows)
        else:
            assert all(row["greedy_advantage_margin_loss"] > 0.0 for row in rows)
            assert all(row["greedy_advantage_margin_eligible_rows"] > 0 for row in rows)
        arm_report[arm] = {
            "checkpoint_sha256": expected["sha256"],
            "physical_hands": expected["physical_hands"],
            "transition_hands": expected["transition_hands"],
            "changed_tensors": sorted(changed),
            "final_reference_policy_kl": rows[-1]["reference_policy_kl"],
            "final_margin_loss": rows[-1]["greedy_advantage_margin_loss"],
            "final_margin_eligible_rows": rows[-1]["greedy_advantage_margin_eligible_rows"],
        }

    control_assignments, treatment_assignments = assignments("control"), assignments("treatment")
    assert len(control_assignments) == len(treatment_assignments) == 2
    for control, treatment in zip(control_assignments, treatment_assignments):
        assert control["applies_to_iteration"] == treatment["applies_to_iteration"]
        assert control["worker_seed_base"] == treatment["worker_seed_base"] == 2026111400
        assert control["workers"] == treatment["workers"]
        assert control["pool_snapshot_refs"] == treatment["pool_snapshot_refs"]
    assert control_assignments[0]["pool_sampling_weights"] == treatment_assignments[0]["pool_sampling_weights"]

    recorded = read(BASE / "eval/paired_delta.json")
    assert recorded["seed"] == 20261115 and recorded["pairs_per_anchor"] == 1024
    assert recorded["policy_mode"] == "greedy" and recorded["evaluation_hands"] == 12288
    anchor_rows, pooled = [], []
    for expected_row in recorded["anchors"]:
        name = expected_row["anchor"]
        control_path = BASE / "eval" / f"control_{name}/pairs.jsonl"
        treatment_path = BASE / "eval" / f"treatment_{name}/pairs.jsonl"
        control_decks, control = raw_pair_values(control_path)
        treatment_decks, treatment = raw_pair_values(treatment_path)
        assert len(control) == len(treatment) == 1024 and control_decks == treatment_decks
        delta = treatment - control
        mean, interval = mean_ci(delta)
        assert math.isclose(float(control.mean()), expected_row["control_bb100"], abs_tol=1e-12)
        assert math.isclose(float(treatment.mean()), expected_row["treatment_bb100"], abs_tol=1e-12)
        assert math.isclose(mean, expected_row["treatment_minus_control_bb100"], abs_tol=1e-12)
        assert np.allclose(interval, expected_row["paired_ci95"], atol=1e-12, rtol=0.0)
        assert sha256(control_path) == expected_row["control_pairs_sha256"]
        assert sha256(treatment_path) == expected_row["treatment_pairs_sha256"]
        pooled.extend(delta.tolist())
        anchor_rows.append({"anchor": name, "delta_bb100": mean, "paired_ci95": interval})
    pooled_mean, pooled_ci = mean_ci(np.asarray(pooled, dtype=np.float64))
    assert math.isclose(pooled_mean, recorded["pooled"]["treatment_minus_control_bb100"], abs_tol=1e-12)
    assert np.allclose(pooled_ci, recorded["pooled"]["paired_ci95"], atol=1e-12, rtol=0.0)
    assert sum(row["delta_bb100"] > 0.0 for row in anchor_rows) == recorded["pooled"]["positive_anchors"] == 1

    tests = ET.parse(BASE / "tests.xml").getroot()
    suites = [tests] if tests.tag == "testsuite" else list(tests)
    test_count = sum(int(suite.attrib.get("tests", 0)) for suite in suites)
    failures = sum(int(suite.attrib.get("failures", 0)) + int(suite.attrib.get("errors", 0)) for suite in suites)
    assert test_count == 18 and failures == 0

    report = {
        "schema": "cardpilot.greedy_margin_smoke_review.v1",
        "status": "PASS",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "decision": "DO_NOT_SCALE_GREEDY_ADVANTAGE_MARGIN",
        "arms": arm_report,
        "assignment_alignment": {
            "iterations": 2,
            "worker_schedules_identical": True,
            "initial_sampling_weights_identical": True,
            "later_weights_arm_adaptive": True,
        },
        "anchors": anchor_rows,
        "pooled_delta_bb100": pooled_mean,
        "pooled_paired_ci95": pooled_ci,
        "positive_anchors": 1,
        "tests": {"passed": test_count, "failures": failures},
        "environment_training_hands": sum(row["physical_hands"] for row in arm_report.values()),
        "evaluation_hands": 12288,
        "slumbot_hands": 0,
        "goal_achieved": False,
    }
    write(BASE / "reviewed_analysis.json", report)
    write(BASE / "analysis.json", {
        **report,
        "status": "COMPLETED",
        "conclusion": (
            "The auxiliary is active, finite, and session-valid, but the matched greedy endpoint gate "
            "does not show a positive cross-anchor efficacy signal."
        ),
    })
    (BASE / "result_summary.md").write_text(
        "# Greedy advantage-margin smoke\n\n"
        "Decision: `DO_NOT_SCALE_GREEDY_ADVANTAGE_MARGIN`. The auxiliary was active and stable, "
        f"but the pooled common-deck treatment-minus-control result was {pooled_mean:+.6f} bb/100 "
        f"with paired 95% CI [{pooled_ci[0]:+.6f}, {pooled_ci[1]:+.6f}] and only 1/3 anchor "
        "point estimates positive. Standard10 and Slumbot-free directions were negative; corrected-CFR96 "
        "was positive but imprecise. No Slumbot hands were used and the Goal is not achieved.\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
