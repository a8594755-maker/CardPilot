"""Independent review for the top-action-weighted source-KL smoke."""

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
PRIOR = ROOT / "research/experiments/v6-greedy-advantage-margin-smoke-20260901"
SOURCE = ROOT / "models/baseline/standard10/latest.pt"
SOURCE_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
CONTROL_SHA = "d806394bc8f8068f8b72e19153d6f96c14f09e8c41c1418091e8441a977c8e29"
TREATMENT_SHA = "d413f3fd2b980a9eeab47d11331b9db0c899ebbf350610306daa50493882ecfe"

sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


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


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    assert sha(SOURCE) == SOURCE_SHA
    assert sha(PRIOR / "control/latest.pt") == CONTROL_SHA
    assert sha(BASE / "treatment/latest.pt") == TREATMENT_SHA
    assert read(PRIOR / "control/session_audit.json")["status"] == "PASS"
    audit = read(BASE / "treatment/session_audit.json")
    assert audit["status"] == "PASS" and audit["actual_environment_hands"] == 10407
    assert audit["legacy_training_marker_hands"] == 8235
    assert audit["kl_early_stop_count"] == 0 and audit["assignment_rows"] == 2
    metrics = [
        json.loads(line)
        for line in (BASE / "treatment/h1_training_metrics.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(metrics) == 2
    assert all(row["hero_policy_temperature"] == 1.0 for row in metrics)
    assert all(row["reference_policy_temperature"] == 0.5 for row in metrics)
    assert all(not row["kl_early_stop_triggered"] for row in metrics)
    source = torch.load(SOURCE, map_location="cpu", weights_only=False)["model"]
    model = torch.load(BASE / "treatment/latest.pt", map_location="cpu", weights_only=False)["model"]
    assert all(torch.isfinite(value).all() for value in model.values())
    changed = sorted(key for key in source if not torch.equal(source[key], model[key]))
    assert len(changed) == 10
    control_assignments = [
        json.loads(line)
        for line in (PRIOR / "control/opponent_assignments.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    treatment_assignments = [
        json.loads(line)
        for line in (BASE / "treatment/opponent_assignments.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(control_assignments) == len(treatment_assignments) == 2
    assert control_assignments[0]["workers"] == treatment_assignments[0]["workers"]
    assert control_assignments[0]["pool_sampling_weights"] == treatment_assignments[0]["pool_sampling_weights"]
    for control_row, treatment_row in zip(control_assignments, treatment_assignments):
        assert control_row["worker_seed_base"] == treatment_row["worker_seed_base"] == 2026111400
        assert control_row["pool_snapshot_refs"] == treatment_row["pool_snapshot_refs"]

    recorded = read(BASE / "eval/paired_delta.json")
    recomputed, pooled = [], []
    for expected in recorded["anchors"]:
        name = expected["anchor"]
        control_path = PRIOR / "eval" / f"control_{name}/pairs.jsonl"
        treatment_path = BASE / "eval" / f"treatment_{name}/pairs.jsonl"
        control_decks, control = pairs(control_path)
        treatment_decks, treatment = pairs(treatment_path)
        assert len(control) == len(treatment) == 1024 and control_decks == treatment_decks
        delta = treatment - control
        mean, interval = stats(delta)
        pooled.extend(delta.tolist())
        assert math.isclose(mean, expected["treatment_minus_control_bb100"], abs_tol=1e-12)
        assert np.allclose(interval, expected["paired_ci95"], atol=1e-12, rtol=0)
        assert sha(control_path) == expected["prior_control_pairs_sha256"]
        assert sha(treatment_path) == expected["treatment_pairs_sha256"]
        recomputed.append({"anchor": name, "delta_bb100": mean, "paired_ci95": interval})
    pooled_mean, pooled_ci = stats(np.asarray(pooled, dtype=np.float64))
    assert math.isclose(pooled_mean, recorded["pooled"]["treatment_minus_control_bb100"], abs_tol=1e-12)
    assert np.allclose(pooled_ci, recorded["pooled"]["paired_ci95"], atol=1e-12, rtol=0)
    assert sum(row["delta_bb100"] > 0 for row in recomputed) == 2
    assert recomputed[0]["delta_bb100"] > 0 and pooled_mean > 0

    xml = ET.parse(BASE / "tests.xml").getroot()
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
        "scripts/alpha_holdem/test_hero_policy_temperature.py",
        "scripts/alpha_holdem/v6_mirror_eval.py",
        "research/experiment_log.py",
        f"research/experiments/{BASE.name}/run_eval.py",
        f"research/experiments/{BASE.name}/audit_review.py",
    ]
    code = BASE / "execution_code"
    capture_code_provenance(ROOT, code, paths)
    for relative in paths:
        target = code / "source_files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    report = {
        "schema": "cardpilot.source_kl_temperature_smoke_review.v1",
        "status": "PASS",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "decision": "ADMIT_MATCHED_65K_SOURCE_KL_TEMPERATURE",
        "control_sha256": CONTROL_SHA,
        "treatment_sha256": TREATMENT_SHA,
        "hero_policy_temperature": 1.0,
        "source_policy_kl_temperature": 0.5,
        "treatment_physical_hands": 10407,
        "treatment_transition_hands": 8235,
        "final_reference_policy_kl": metrics[-1]["reference_policy_kl"],
        "anchors": recomputed,
        "pooled_delta_bb100": pooled_mean,
        "pooled_paired_ci95": pooled_ci,
        "positive_anchors": 2,
        "new_environment_training_hands": 10407,
        "new_evaluation_hands": 6144,
        "reused_control_evaluation_hands": 6144,
        "slumbot_hands": 0,
        "tests_passed": tests,
        "goal_achieved": False,
    }
    write(BASE / "reviewed_analysis.json", report)
    write(BASE / "analysis.json", {**report, "status": "COMPLETED"})
    (BASE / "result_summary.md").write_text(
        "# Top-action-weighted source-KL smoke\n\n"
        "Decision: `ADMIT_MATCHED_65K_SOURCE_KL_TEMPERATURE`. Source-KL T=0.5 "
        f"versus T=1 pooled {pooled_mean:+.6f} bb/100, paired 95% CI "
        f"[{pooled_ci[0]:+.6f}, {pooled_ci[1]:+.6f}], 2/3 positive anchors; "
        f"Standard10 delta {recomputed[0]['delta_bb100']:+.6f}. No Slumbot; Goal not achieved.\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
