from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ENGINE = (
    ROOT
    / "research/experiments/v6-contextual-preflop-prior-mechanism-smoke-20260901/evaluate_mechanism.py"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(actual, expected):
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(close(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(close(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, float):
        return bool(np.isclose(actual, expected, rtol=0.0, atol=1e-12))
    return actual == expected


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
    spec = importlib.util.spec_from_file_location("mechanism_engine", ENGINE)
    engine = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(engine)
    summary = json.loads((BASE / "dose_curve.json").read_text(encoding="utf-8"))
    raw_path = BASE / "state_probabilities.npz"
    arrays = np.load(raw_path)
    masks = {
        "all": np.ones(summary["states"], dtype=bool),
        "postflop": arrays["postflop_mask"].astype(bool),
        "sb_open": arrays["sb_open_mask"].astype(bool),
        "bb_vs_open": arrays["bb_vs_open_mask"].astype(bool),
    }
    parent = arrays["parent"]
    curve_ok = sha256(raw_path) == summary["state_probabilities_sha256"]
    eligible_iterations = []
    for row in summary["curve"]:
        iteration = int(row["iteration"])
        control = arrays[f"control_iter{iteration:02d}"]
        treatment = arrays[f"treatment_iter{iteration:02d}"]
        contexts = {
            name: engine.context_summary(mask, parent, control, treatment)
            for name, mask in masks.items()
        }
        postflop_exact = (
            np.array_equal(control[masks["postflop"]], parent[masks["postflop"]])
            and np.array_equal(treatment[masks["postflop"]], parent[masks["postflop"]])
        )
        target_improved = all(
            abs(contexts[context]["treatment"]["mean_class_mass_fold_call_raise_allin"][2] - target)
            < abs(contexts[context]["control"]["mean_class_mass_fold_call_raise_allin"][2] - target)
            for context, target in (("sb_open", 0.63), ("bb_vs_open", 0.18))
        )
        drift = contexts["all"]["treatment_vs_parent"]
        eligible = postflop_exact and target_improved and drift["mean_total_variation"] <= 0.05 and drift["greedy_disagreement"] <= 0.05
        if eligible:
            eligible_iterations.append(iteration)
        curve_ok &= close(contexts, row["contexts"])
        curve_ok &= postflop_exact == row["postflop_exact"]
        curve_ok &= target_improved == row["contextual_target_distance_improved"]
        curve_ok &= eligible == row["eligible"]
        for arm in ("control", "treatment"):
            path = ROOT / row["checkpoint_paths"][arm]
            curve_ok &= sha256(path) == row["checkpoint_sha256"][arm]
    selected = max(eligible_iterations) if eligible_iterations else None
    curve_ok &= selected == summary["selected_iteration"]
    curve_ok &= all(
        sha256(ROOT / item["path"]) == item["sha256"]
        for item in summary["input_hands"]
    )

    panel = json.loads((BASE / "eval/paired_delta.json").read_text(encoding="utf-8"))
    panel_ok = panel["control_sha256"] == summary["selected_checkpoint_sha256"]["control"]
    panel_ok &= panel["treatment_sha256"] == summary["selected_checkpoint_sha256"]["treatment"]
    pooled = []
    for expected in panel["anchors"]:
        anchor = expected["anchor"]
        control_path = BASE / "eval" / f"control_{anchor}/pairs.jsonl"
        treatment_path = BASE / "eval" / f"treatment_{anchor}/pairs.jsonl"
        control_decks, control = load_pairs(control_path)
        treatment_decks, treatment = load_pairs(treatment_path)
        delta = treatment - control
        pooled.extend(delta.tolist())
        mean, lower, upper = ci(delta)
        panel_ok &= control_decks == treatment_decks
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
    allocation = {
        "selected_dose_exists": selected is not None,
        "pooled_delta_positive": panel["pooled"]["treatment_minus_control_bb100"] > 0.0,
        "at_least_two_positive_anchors": panel["pooled"]["positive_anchors"] >= 2,
    }
    allocation["slumbot_allocation_passed"] = all(allocation.values())
    checks = {
        "dose_curve_raw_recompute": bool(curve_ok),
        "selected_panel_raw_recompute": bool(panel_ok),
    }
    result = {
        "schema": "cardpilot.preflop_context_dose_curve_terminal_review.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "selected_iteration": selected,
        "learned_panel": panel["pooled"],
        "slumbot_allocation_gate": allocation,
        "dose_curve_sha256": sha256(BASE / "dose_curve.json"),
        "state_probabilities_sha256": sha256(raw_path),
        "paired_delta_sha256": sha256(BASE / "eval/paired_delta.json"),
    }
    (BASE / "terminal_review.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
