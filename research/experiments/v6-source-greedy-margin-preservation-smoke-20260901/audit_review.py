"""Independent review and current-code snapshot for source-greedy preservation."""

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

import numpy as np
import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PRIOR = ROOT / "research/experiments/v6-greedy-advantage-margin-smoke-20260901"
SOURCE = ROOT / "models/baseline/standard10/latest.pt"
SOURCE_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
CONTROL_SHA = "d806394bc8f8068f8b72e19153d6f96c14f09e8c41c1418091e8441a977c8e29"
TREATMENT_SHA = "b3d2166eae7c7c3621b75c00688ae0c9ee8efe4b3c9323aa481a8038deb158c4"
sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance


def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def write(path, value): Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pairs(path):
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


def main():
    assert sha256(SOURCE) == SOURCE_SHA
    assert sha256(PRIOR / "control/latest.pt") == CONTROL_SHA
    assert sha256(BASE / "treatment/latest.pt") == TREATMENT_SHA
    prior_record = read(PRIOR / "experiment.json")
    assert prior_record["status"] == "COMPLETED"
    assert read(PRIOR / "control/session_audit.json")["status"] == "PASS"
    audit = read(BASE / "treatment/session_audit.json")
    assert audit["status"] == "PASS" and audit["actual_environment_hands"] == 10688
    assert audit["legacy_training_marker_hands"] == 8196
    assert audit["final_iteration"] == 2 and audit["kl_early_stop_count"] == 0

    rows = [json.loads(line) for line in (BASE / "treatment/h1_training_metrics.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert all(row["source_greedy_margin_coef"] == 0.1 for row in rows)
    assert all(row["source_greedy_margin_loss"] > 0.0 for row in rows)
    assert all(row["source_greedy_margin_eligible_rows"] > 0 for row in rows)
    assert all(row["source_greedy_margin_released_rows"] > 0 for row in rows)
    assert all(row["source_greedy_margin_violation_rows"] > 0 for row in rows)

    source = torch.load(SOURCE, map_location="cpu", weights_only=False)["model"]
    treatment = torch.load(BASE / "treatment/latest.pt", map_location="cpu", weights_only=False)["model"]
    changed = sorted(name for name in source if not torch.equal(source[name], treatment[name]))
    assert changed == [
        "policy_head.bias", "policy_head.weight", "preflop_policy_head.bias",
        "preflop_policy_head.weight", "value_head.0.bias", "value_head.0.weight",
        "value_head.2.bias", "value_head.2.weight", "value_head.4.bias", "value_head.4.weight",
    ]
    assert all(torch.isfinite(tensor).all() for tensor in treatment.values())

    control_assignments = [json.loads(line) for line in (PRIOR / "control/opponent_assignments.jsonl").read_text(encoding="utf-8").splitlines()]
    treatment_assignments = [json.loads(line) for line in (BASE / "treatment/opponent_assignments.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(control_assignments) == len(treatment_assignments) == 2
    for index, (control, treated) in enumerate(zip(control_assignments, treatment_assignments)):
        assert control["worker_seed_base"] == treated["worker_seed_base"] == 2026111400
        assert control["pool_snapshot_refs"] == treated["pool_snapshot_refs"]
        if index == 0:
            assert control["workers"] == treated["workers"]
            assert control["pool_sampling_weights"] == treated["pool_sampling_weights"]
        else:
            # The preregistered adaptive league responds to arm-specific first-
            # iteration rewards. Its second schedule is therefore conditional,
            # not a fixed matched assignment; self-play worker identities remain
            # aligned while fixed-anchor draws may differ.
            control_selfplay = [
                row["worker_id"] for row in control["workers"]
                if row["opponent"]["kind"] == "self_play"
            ]
            treatment_selfplay = [
                row["worker_id"] for row in treated["workers"]
                if row["opponent"]["kind"] == "self_play"
            ]
            assert control_selfplay == treatment_selfplay

    recorded = read(BASE / "eval/paired_delta.json")
    assert recorded["seed"] == 20261115 and recorded["pairs_per_anchor"] == 1024
    recomputed, pooled = [], []
    for expected in recorded["anchors"]:
        name = expected["anchor"]
        control_path = PRIOR / "eval" / f"control_{name}/pairs.jsonl"
        treatment_path = BASE / "eval" / f"treatment_{name}/pairs.jsonl"
        control_decks, control = load_pairs(control_path)
        treatment_decks, treated = load_pairs(treatment_path)
        assert len(control) == len(treated) == 1024 and control_decks == treatment_decks
        delta = treated - control
        mean, interval = stats(delta)
        assert math.isclose(mean, expected["treatment_minus_control_bb100"], abs_tol=1e-12)
        assert np.allclose(interval, expected["paired_ci95"], atol=1e-12, rtol=0.0)
        assert sha256(control_path) == expected["prior_control_pairs_sha256"]
        assert sha256(treatment_path) == expected["treatment_pairs_sha256"]
        pooled.extend(delta.tolist())
        recomputed.append({"anchor": name, "delta_bb100": mean, "paired_ci95": interval})
    pooled_mean, pooled_ci = stats(np.asarray(pooled, dtype=np.float64))
    assert math.isclose(pooled_mean, recorded["pooled"]["treatment_minus_control_bb100"], abs_tol=1e-12)
    assert np.allclose(pooled_ci, recorded["pooled"]["paired_ci95"], atol=1e-12, rtol=0.0)
    assert sum(row["delta_bb100"] > 0 for row in recomputed) == 1

    xml = ET.parse(BASE / "tests.xml").getroot()
    suites = [xml] if xml.tag == "testsuite" else list(xml)
    tests = sum(int(s.attrib.get("tests", 0)) for s in suites)
    failures = sum(int(s.attrib.get("failures", 0)) + int(s.attrib.get("errors", 0)) for s in suites)
    assert tests == 23 and failures == 0

    code_dir = BASE / "execution_code"
    paths = [
        "scripts/alpha_holdem/train_mp3_hybrid_h1.py",
        "scripts/alpha_holdem/train_v5.py",
        "scripts/alpha_holdem/test_source_greedy_margin_preservation.py",
        "scripts/alpha_holdem/v6_mirror_eval.py",
        "research/experiment_log.py",
        f"research/experiments/{BASE.name}/run_eval.py",
        f"research/experiments/{BASE.name}/audit_review.py",
    ]
    capture_code_provenance(ROOT, code_dir, paths)
    for relative in paths:
        target = code_dir / "source_files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)

    report = {
        "schema": "cardpilot.source_greedy_preservation_review.v1",
        "status": "PASS", "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "decision": "DO_NOT_SCALE_SOURCE_GREEDY_MARGIN_PRESERVATION",
        "control_sha256": CONTROL_SHA, "treatment_sha256": TREATMENT_SHA,
        "treatment_physical_hands": 10688, "treatment_transition_hands": 8196,
        "final_margin_loss": rows[-1]["source_greedy_margin_loss"],
        "final_eligible_rows": rows[-1]["source_greedy_margin_eligible_rows"],
        "final_released_rows": rows[-1]["source_greedy_margin_released_rows"],
        "final_violation_rows": rows[-1]["source_greedy_margin_violation_rows"],
        "final_reference_policy_kl": rows[-1]["reference_policy_kl"],
        "anchors": recomputed, "pooled_delta_bb100": pooled_mean,
        "pooled_paired_ci95": pooled_ci, "positive_anchors": 1,
        "new_environment_training_hands": 10688, "new_evaluation_hands": 6144,
        "reused_control_evaluation_hands": 6144, "slumbot_hands": 0,
        "tests_passed": tests, "goal_achieved": False,
    }
    write(BASE / "reviewed_analysis.json", report)
    write(BASE / "analysis.json", {**report, "status": "COMPLETED"})
    (BASE / "result_summary.md").write_text(
        "# Source-greedy margin preservation smoke\n\n"
        f"Decision: `DO_NOT_SCALE_SOURCE_GREEDY_MARGIN_PRESERVATION`. Pooled common-deck "
        f"treatment-minus-control was {pooled_mean:+.6f} bb/100 with paired 95% CI "
        f"[{pooled_ci[0]:+.6f}, {pooled_ci[1]:+.6f}] and 1/3 positive anchors. The source "
        "margin mechanism was active and stable, but did not establish efficacy. No Slumbot hands; Goal not achieved.\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__": main()
