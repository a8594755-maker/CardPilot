from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
MECHANISM_REVIEW = (
    ROOT
    / "research/experiments/v6-preflop-head-only-context-prior-smoke-20260901/audit_review.py"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pairs(path: Path):
    decks, values = [], []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        row = json.loads(line)
        if row["pair_index"] != index:
            raise ValueError("non-contiguous pair evidence")
        decks.append(row["deck"])
        values.append(float(np.mean(row["rewards_bb"]) * 100.0))
    return decks, np.asarray(values, dtype=np.float64)


def ci(values):
    mean = float(values.mean())
    half = float(1.96 * values.std(ddof=1) / math.sqrt(values.size))
    return mean, mean - half, mean + half


def main() -> None:
    spec = importlib.util.spec_from_file_location("mechanism_review", MECHANISM_REVIEW)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.BASE = BASE
    module.PARENT = (
        ROOT
        / "research/experiments/v6-procedural-iter32-soup-preservation-20260901/frozen/treatment.pt"
    )
    module.main()

    result_path = BASE / "terminal_review.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    panel = json.loads((BASE / "eval/paired_delta.json").read_text(encoding="utf-8"))
    panel_ok = (
        sha256(BASE / "control/latest.pt") == panel["control_sha256"]
        and sha256(BASE / "treatment/latest.pt") == panel["treatment_sha256"]
    )
    pooled = []
    for expected in panel["anchors"]:
        anchor = expected["anchor"]
        control_path = BASE / "eval" / f"control_{anchor}/pairs.jsonl"
        treatment_path = BASE / "eval" / f"treatment_{anchor}/pairs.jsonl"
        control_decks, control = load_pairs(control_path)
        treatment_decks, treatment = load_pairs(treatment_path)
        delta = treatment - control
        mean, lower, upper = ci(delta)
        pooled.extend(delta.tolist())
        panel_ok &= control_decks == treatment_decks
        panel_ok &= len(delta) == panel["pairs_per_anchor"]
        panel_ok &= sha256(control_path) == expected["control_pairs_sha256"]
        panel_ok &= sha256(treatment_path) == expected["treatment_pairs_sha256"]
        panel_ok &= np.allclose(
            [mean, lower, upper],
            [expected["treatment_minus_control_bb100"], *expected["paired_ci95"]],
            rtol=0.0,
            atol=1e-12,
        )
    mean, lower, upper = ci(np.asarray(pooled, dtype=np.float64))
    panel_ok &= np.allclose(
        [mean, lower, upper],
        [panel["pooled"]["treatment_minus_control_bb100"], *panel["pooled"]["paired_ci95"]],
        rtol=0.0,
        atol=1e-12,
    )
    result["checks"]["learned_panel_raw_recompute"] = bool(panel_ok)
    mechanism = json.loads((BASE / "mechanism/summary.json").read_text(encoding="utf-8"))
    all_drift = mechanism["contexts"]["all"]["treatment_vs_parent"]
    eligibility = {
        "contextual_target_distance_improved": all(
            abs(mechanism["contexts"][context]["treatment"]["mean_class_mass_fold_call_raise_allin"][2] - target)
            < abs(mechanism["contexts"][context]["control"]["mean_class_mass_fold_call_raise_allin"][2] - target)
            for context, target in (("sb_open", 0.63), ("bb_vs_open", 0.18))
        ),
        "overall_parent_tv_at_most_0_05": all_drift["mean_total_variation"] <= 0.05,
        "overall_parent_disagreement_at_most_0_05": all_drift["greedy_disagreement"] <= 0.05,
        "pooled_learned_delta_positive": panel["pooled"]["treatment_minus_control_bb100"] > 0.0,
        "at_least_two_positive_anchors": panel["pooled"]["positive_anchors"] >= 2,
    }
    eligibility["slumbot_allocation_passed"] = all(eligibility.values())
    result["slumbot_allocation_gate"] = eligibility
    result["learned_panel"] = panel["pooled"]
    result["status"] = "PASS" if all(result["checks"].values()) else "FAIL"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
