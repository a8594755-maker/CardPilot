from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import torch


BASE = Path(__file__).resolve().parent
PARENT = BASE.parent / "v6-procedural-iter32-soup-preservation-20260901/frozen/treatment.pt"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assignment_schedule(path: Path):
    result = []
    for row in rows(path):
        result.append(
            {
                "iteration": int(row["applies_to_iteration"]),
                "workers": [
                    (
                        int(worker["worker_id"]),
                        worker["opponent"]["kind"],
                        int(worker["opponent"]["local_index"]),
                    )
                    for worker in row["workers"]
                ],
            }
        )
    return result


def model_state(checkpoint):
    for key in ("model_state_dict", "model"):
        if isinstance(checkpoint.get(key), dict):
            return checkpoint[key]
    raise ValueError("checkpoint has no model state")


def main() -> None:
    summary = read(BASE / "mechanism/summary.json")
    raw_path = BASE / "mechanism/state_metrics.jsonl"
    raw = rows(raw_path)
    checks = {}
    checks["session_audits_pass"] = all(
        read(BASE / arm / "session_audit.json")["status"] == "PASS"
        for arm in ("control", "treatment")
    )
    checks["matched_assignment_schedule"] = (
        assignment_schedule(BASE / "control/opponent_assignments.jsonl")
        == assignment_schedule(BASE / "treatment/opponent_assignments.jsonl")
    )
    checks["checkpoint_hashes"] = all(
        sha256(BASE / arm / "latest.pt") == summary["checkpoint_sha256"][arm]
        for arm in ("control", "treatment")
    ) and sha256(PARENT) == summary["checkpoint_sha256"]["parent"]
    checks["raw_count_hash"] = (
        len(raw) == summary["states"]
        and sha256(raw_path) == summary["state_metrics_sha256"]
    )

    context_masks = {
        "all": np.ones(len(raw), dtype=bool),
        "postflop": np.asarray([row["context"] == "postflop" for row in raw]),
        "sb_open": np.asarray([row["context"] == "sb_open" for row in raw]),
        "bb_vs_open": np.asarray([row["context"] == "bb_vs_open" for row in raw]),
    }
    raw_recompute = True
    for context, mask in context_masks.items():
        expected = summary["contexts"][context]
        raw_recompute &= int(mask.sum()) == expected["states"]
        for arm in ("parent", "control", "treatment"):
            mass = np.asarray([row[f"{arm}_class_mass"] for row in raw])[mask]
            greedy = np.asarray([row[f"{arm}_greedy_class"] for row in raw])[mask]
            observed_mass = mass.mean(axis=0)
            observed_greedy = np.asarray([np.mean(greedy == index) for index in range(4)])
            raw_recompute &= np.allclose(
                observed_mass,
                expected[arm]["mean_class_mass_fold_call_raise_allin"],
                rtol=0.0,
                atol=1e-12,
            )
            raw_recompute &= np.allclose(
                observed_greedy,
                expected[arm]["greedy_class_frequency_fold_call_raise_allin"],
                rtol=0.0,
                atol=1e-12,
            )
        for label, key in (
            ("control_vs_parent", "control_parent_tv"),
            ("treatment_vs_parent", "treatment_parent_tv"),
            ("treatment_vs_control", "treatment_control_tv"),
        ):
            observed = float(np.asarray([row[key] for row in raw])[mask].mean())
            raw_recompute &= np.isclose(
                observed,
                expected[label]["mean_total_variation"],
                rtol=0.0,
                atol=1e-12,
            )
    checks["raw_summary_recompute"] = bool(raw_recompute)

    checkpoints = {
        "parent": torch.load(PARENT, map_location="cpu", weights_only=False),
        "control": torch.load(BASE / "control/latest.pt", map_location="cpu", weights_only=False),
        "treatment": torch.load(BASE / "treatment/latest.pt", map_location="cpu", weights_only=False),
    }
    parent_state = model_state(checkpoints["parent"])
    changed = {}
    allowed = ("policy_head.", "preflop_policy_head.", "value_head.")
    tensor_scope = True
    for arm in ("control", "treatment"):
        endpoint = model_state(checkpoints[arm])
        names = [name for name in parent_state if not torch.equal(parent_state[name], endpoint[name])]
        changed[arm] = names
        tensor_scope &= bool(names) and all(name.startswith(allowed) for name in names)
    checks["allowed_tensor_scope"] = bool(tensor_scope)

    gate = summary["gate"]
    sb = summary["contexts"]["sb_open"]
    bb = summary["contexts"]["bb_vs_open"]
    post = summary["contexts"]["postflop"]["treatment_vs_control"]
    overall = summary["contexts"]["all"]["treatment_vs_parent"]
    recomputed_gate = {
        "sb_raise_mass_reduced": sb["treatment"]["mean_class_mass_fold_call_raise_allin"][2] < sb["control"]["mean_class_mass_fold_call_raise_allin"][2],
        "sb_greedy_raise_frequency_not_increased": sb["treatment"]["greedy_class_frequency_fold_call_raise_allin"][2] <= sb["control"]["greedy_class_frequency_fold_call_raise_allin"][2],
        "bb_vs_open_raise_mass_reduced": bb["treatment"]["mean_class_mass_fold_call_raise_allin"][2] < bb["control"]["mean_class_mass_fold_call_raise_allin"][2],
        "bb_vs_open_greedy_raise_frequency_not_increased": bb["treatment"]["greedy_class_frequency_fold_call_raise_allin"][2] <= bb["control"]["greedy_class_frequency_fold_call_raise_allin"][2],
        "postflop_treatment_control_tv_at_most_0_005": post["mean_total_variation"] <= 0.005,
        "overall_treatment_parent_tv_at_most_0_02": overall["mean_total_variation"] <= 0.02,
        "overall_treatment_parent_disagreement_at_most_0_02": overall["greedy_disagreement"] <= 0.02,
    }
    recomputed_gate["passed"] = all(recomputed_gate.values())
    checks["gate_recompute"] = recomputed_gate == gate
    result = {
        "schema": "cardpilot.contextual_preflop_prior_terminal_review.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "changed_tensors": changed,
        "mechanism_gate": gate,
        "summary_sha256": sha256(BASE / "mechanism/summary.json"),
        "raw_sha256": sha256(raw_path),
    }
    (BASE / "terminal_review.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
