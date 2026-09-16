"""Independent evidence review for the matched 65k source-KL-temperature pilot."""

from datetime import datetime, timezone
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PRIOR = ROOT / "research/experiments/v6-low-temperature-65k-pilot-20260901"
CONTROL = BASE / "frozen/control_iter15.pt"
TREATMENT = BASE / "frozen/treatment_iter15.pt"
CONTROL_SHA = "0bcd70539d6117425ea88b6c1aeb22ee177d945cb17042ae97707e8c1ca7d9e7"
TREATMENT_SHA = "9e1566812f6550415be4d7d90b21180080a8c3f6f9b0096457a04a98a54b0847"

sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pairs(path):
    decks, values = [], []
    for index, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
        row = json.loads(line)
        assert row["pair_index"] == index
        decks.append(row["deck"])
        values.append(float(np.mean(row["rewards_bb"]) * 100.0))
    return decks, np.asarray(values, dtype=np.float64)


def stats(values):
    mean = float(values.mean())
    half = float(1.96 * values.std(ddof=1) / math.sqrt(values.size))
    return mean, [mean - half, mean + half]


def optimizer_steps(checkpoint):
    result = []
    for state in checkpoint["optimizer"]["state"].values():
        step = state["step"]
        result.append(int(step.item() if hasattr(step, "item") else step))
    return sorted(set(result))


def main():
    assert sha(CONTROL) == CONTROL_SHA and sha(TREATMENT) == TREATMENT_SHA
    assert sha(BASE / "treatment/latest.pt") == TREATMENT_SHA
    control_audit = read(PRIOR / "control/session_audit.json")
    treatment_audit = read(BASE / "treatment/session_audit.json")
    assert control_audit["status"] == treatment_audit["status"] == "PASS"
    assert control_audit["final_iteration"] == treatment_audit["final_iteration"] == 15
    assert control_audit["actual_environment_hands"] == 71353
    assert treatment_audit["actual_environment_hands"] == 70457
    assert control_audit["legacy_training_marker_hands"] == 61850
    assert treatment_audit["legacy_training_marker_hands"] == 61810
    assert treatment_audit["assignment_audit"]["pending_assignments"] is None
    assert treatment_audit["kl_early_stop_count"] == 0
    metrics = [
        json.loads(line)
        for line in (BASE / "treatment/h1_training_metrics.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(metrics) == 15
    assert [row["iteration"] for row in metrics] == list(range(1, 16))
    assert all(row["hero_policy_temperature"] == 1.0 for row in metrics)
    assert all(row["reference_policy_temperature"] == 0.5 for row in metrics)
    assert all(not row["kl_early_stop_triggered"] for row in metrics)
    control = torch.load(CONTROL, map_location="cpu", weights_only=False)
    treatment = torch.load(TREATMENT, map_location="cpu", weights_only=False)
    assert control["iteration"] == treatment["iteration"] == 15
    assert optimizer_steps(control) == [564]
    assert optimizer_steps(treatment) == [566]
    assert len(control["optimizer"]["state"]) == len(treatment["optimizer"]["state"]) == 10
    assert all(torch.isfinite(value).all() for value in treatment["model"].values())
    control_assignments = [
        json.loads(line)
        for line in (PRIOR / "control/opponent_assignments.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    treatment_assignments = [
        json.loads(line)
        for line in (BASE / "treatment/opponent_assignments.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(control_assignments) == len(treatment_assignments) == 15
    assert control_assignments[0]["workers"] == treatment_assignments[0]["workers"]
    for control_row, treatment_row in zip(control_assignments, treatment_assignments):
        assert control_row["worker_seed_base"] == treatment_row["worker_seed_base"] == 2026111600
        assert control_row["pool_snapshot_refs"] == treatment_row["pool_snapshot_refs"]

    recorded = read(BASE / "eval/paired_delta.json")
    assert recorded["evaluation_hands"] == 49152
    assert recorded["pairs_per_anchor"] == 4096 and recorded["seed"] == 20261118
    recomputed, pooled = [], []
    for expected in recorded["anchors"]:
        name = expected["anchor"]
        control_path = BASE / "eval" / f"control_{name}/pairs.jsonl"
        treatment_path = BASE / "eval" / f"treatment_{name}/pairs.jsonl"
        control_decks, control_values = pairs(control_path)
        treatment_decks, treatment_values = pairs(treatment_path)
        assert len(control_values) == len(treatment_values) == 4096
        assert control_decks == treatment_decks
        delta = treatment_values - control_values
        mean, interval = stats(delta)
        pooled.extend(delta.tolist())
        assert math.isclose(mean, expected["treatment_minus_control_bb100"], abs_tol=1e-12)
        assert np.allclose(interval, expected["paired_ci95"], atol=1e-12, rtol=0)
        assert sha(control_path) == expected["control_pairs_sha256"]
        assert sha(treatment_path) == expected["treatment_pairs_sha256"]
        recomputed.append({"anchor": name, "delta_bb100": mean, "paired_ci95": interval})
    pooled_mean, pooled_ci = stats(np.asarray(pooled, dtype=np.float64))
    assert math.isclose(pooled_mean, recorded["pooled"]["treatment_minus_control_bb100"], abs_tol=1e-12)
    assert np.allclose(pooled_ci, recorded["pooled"]["paired_ci95"], atol=1e-12, rtol=0)
    assert pooled_mean > 0 and sum(row["delta_bb100"] > 0 for row in recomputed) == 2
    assert recomputed[0]["delta_bb100"] > 0

    xml = ET.parse(BASE / "prerun_tests.xml").getroot()
    suites = [xml] if xml.tag == "testsuite" else list(xml)
    tests = sum(int(suite.attrib.get("tests", 0)) for suite in suites)
    failures = sum(
        int(suite.attrib.get("failures", 0)) + int(suite.attrib.get("errors", 0))
        for suite in suites
    )
    assert tests == 20 and failures == 0
    paths = [
        "scripts/alpha_holdem/train_mp3_hybrid_h1.py",
        "scripts/alpha_holdem/train_v5.py",
        "scripts/alpha_holdem/test_source_policy_kl_temperature.py",
        "scripts/alpha_holdem/v6_mirror_eval.py",
        "scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py",
        "research/experiment_log.py",
        f"research/experiments/{BASE.name}/run_eval.py",
        f"research/experiments/{BASE.name}/audit_review.py",
        "research/experiments/v6-greedy-advantage-margin-smoke-20260901/run_eval.py",
    ]
    code = BASE / "execution_code"
    capture_code_provenance(ROOT, code, paths)
    for relative in paths:
        target = code / "source_files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    report = {
        "schema": "cardpilot.source_kl_temperature_65k_review.v1",
        "status": "PASS",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "decision": "ADMIT_FRESH5K_SOURCE_KL_TEMPERATURE",
        "control_sha256": CONTROL_SHA,
        "treatment_sha256": TREATMENT_SHA,
        "control_physical_hands": 71353,
        "treatment_physical_hands": 70457,
        "control_transition_hands": 61850,
        "treatment_transition_hands": 61810,
        "treatment_optimizer_steps": optimizer_steps(treatment),
        "final_reference_policy_kl": metrics[-1]["reference_policy_kl"],
        "anchors": recomputed,
        "pooled_delta_bb100": pooled_mean,
        "pooled_paired_ci95": pooled_ci,
        "positive_anchors": 2,
        "new_environment_training_hands": 70457,
        "evaluation_hands": 49152,
        "slumbot_hands": 0,
        "tests_passed": tests,
        "goal_achieved": False,
    }
    write(BASE / "reviewed_analysis.json", report)
    write(BASE / "analysis.json", {**report, "status": "COMPLETED"})
    (BASE / "result_summary.md").write_text(
        "# Matched 65k top-action-weighted source-KL pilot\n\n"
        "Decision: `ADMIT_FRESH5K_SOURCE_KL_TEMPERATURE`. Source-KL T=0.5 "
        f"versus T=1 pooled {pooled_mean:+.6f} bb/100, paired 95% CI "
        f"[{pooled_ci[0]:+.6f}, {pooled_ci[1]:+.6f}], 2/3 positive anchors; "
        f"Standard10 delta {recomputed[0]['delta_bb100']:+.6f}. "
        "This passes only the internal point/anchor gate; no Slumbot evidence yet.\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
