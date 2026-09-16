"""Compare realized parameter/output steps for online MGDA and its control."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import torch


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def actor_delta(left: dict, right: dict) -> torch.Tensor:
    prefixes = ("policy_head.", "preflop_policy_head.")
    keys = [key for key in left if key.startswith(prefixes)]
    if not keys or any(key not in right for key in keys):
        raise ValueError("policy-head tensor contract mismatch")
    return torch.cat([
        (right[key].float() - left[key].float()).reshape(-1) for key in keys
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--treatment", type=Path, required=True)
    parser.add_argument("--control-drift", type=Path, required=True)
    parser.add_argument("--treatment-drift", type=Path, required=True)
    parser.add_argument("--direct-drift", type=Path, required=True)
    parser.add_argument("--breadth-audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    checkpoints = {
        name: torch.load(path, map_location="cpu", weights_only=False)
        for name, path in (
            ("parent", args.parent),
            ("control", args.control),
            ("treatment", args.treatment),
        )
    }
    parent = checkpoints["parent"]["model"]
    control_delta = actor_delta(parent, checkpoints["control"]["model"])
    treatment_delta = actor_delta(parent, checkpoints["treatment"]["model"])
    direct_delta = actor_delta(
        checkpoints["control"]["model"], checkpoints["treatment"]["model"]
    )
    control_norm = float(torch.linalg.vector_norm(control_delta).item())
    treatment_norm = float(torch.linalg.vector_norm(treatment_delta).item())
    cosine = float(
        torch.dot(control_delta, treatment_delta).item()
        / (control_norm * treatment_norm)
    )
    drifts = {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in (
            ("control", args.control_drift),
            ("treatment", args.treatment_drift),
            ("treatment_vs_control", args.direct_drift),
        )
    }
    breadth = json.loads(args.breadth_audit.read_text(encoding="utf-8"))
    gates = {
        "same_parent_resume": (
            Path(checkpoints["control"]["resume"]).resolve()
            == args.parent.resolve()
            == Path(checkpoints["treatment"]["resume"]).resolve()
        ),
        "all_drift_audits_pass": all(
            drift["status"] == "PASS" for drift in drifts.values()
        ),
        "direct_drift_hash_chain": (
            drifts["treatment_vs_control"]["parent"]["sha256"]
            == sha256_path(args.control)
            and drifts["treatment_vs_control"]["treatment"]["sha256"]
            == sha256_path(args.treatment)
        ),
        "breadth_raw_audit_pass": bool(breadth["passed"]),
        "nonzero_actor_steps": control_norm > 0.0 and treatment_norm > 0.0,
    }
    if not all(gates.values()):
        raise RuntimeError(f"step analysis gates failed: {gates}")
    result = {
        "schema": "cardpilot.online_mgda_realized_step.v1",
        "gates": gates,
        "passed": all(gates.values()),
        "actor_parameter_step": {
            "control_l2": control_norm,
            "treatment_l2": treatment_norm,
            "treatment_to_control_norm_ratio": treatment_norm / control_norm,
            "treatment_control_cosine": cosine,
            "treatment_minus_control_l2": float(
                torch.linalg.vector_norm(direct_delta).item()
            ),
        },
        "output_step": {
            "control_vs_standard10": drifts["control"]["overall"],
            "treatment_vs_standard10": drifts["treatment"]["overall"],
            "treatment_vs_control": drifts["treatment_vs_control"]["overall"],
        },
        "breadth": {
            "pooled_delta_bb100": breadth["pooled_delta_bb100"],
            "pooled_ci95_upper_bb100": breadth["pooled_ci95_upper_bb100"],
        },
        "inference": (
            "gradient_norm_matching_did_not_match_realized_adam_parameter_step"
            if treatment_norm / control_norm > 1.10
            else "realized_parameter_step_was_approximately_matched"
        ),
        "hashes": {
            "parent": sha256_path(args.parent),
            "control": sha256_path(args.control),
            "treatment": sha256_path(args.treatment),
            "breadth_audit": sha256_path(args.breadth_audit),
        },
        "command": [sys.executable, *sys.argv],
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
