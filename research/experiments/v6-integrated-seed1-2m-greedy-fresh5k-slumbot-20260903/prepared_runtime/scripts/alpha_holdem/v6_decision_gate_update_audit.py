"""Exact zero-hand update-magnitude audit for decision expert gates."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.v6_decision_expert_gate_smoke import ExpertGate
from alpha_holdem.v6_dual_contract_residual_training_smoke import sha256_path


def audit_checkpoint(path: Path) -> dict:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    if payload.get("schema") != "cardpilot.decision_expert_gate.v1":
        raise ValueError(f"unexpected gate schema: {path}")
    seed = int(payload["seed"])
    feature_dim = int(payload["feature_dim"])
    hidden = int(payload["hidden"])
    torch.manual_seed(seed)
    initial = ExpertGate(feature_dim, hidden=hidden)
    initial_state = initial.state_dict()
    final_state = payload["state_dict"]
    if set(initial_state) != set(final_state):
        raise ValueError("gate parameter key mismatch")
    deltas = {}
    flat = []
    for key in initial_state:
        delta = final_state[key].cpu() - initial_state[key]
        flat.append(delta.reshape(-1).double())
        deltas[key] = {
            "l2": float(torch.linalg.vector_norm(delta.double())),
            "max_abs": float(delta.abs().max()),
            "elements": delta.numel(),
        }
    final = ExpertGate(feature_dim, hidden=hidden)
    final.load_state_dict(final_state)
    probes = torch.cat((
        torch.zeros((1, feature_dim)),
        torch.eye(feature_dim),
        -torch.eye(feature_dim),
    ))
    with torch.inference_mode():
        initial_outputs = initial(probes)
        final_outputs = final(probes)
    output_delta = (final_outputs - initial_outputs).abs()
    return {
        "path": str(path), "sha256": sha256_path(path), "seed": seed,
        "feature_dim": feature_dim, "hidden": hidden,
        "parameter_delta_l2": float(torch.linalg.vector_norm(torch.cat(flat))),
        "parameter_delta_max_abs": max(row["max_abs"] for row in deltas.values()),
        "tensor_deltas": deltas,
        "probe_count": len(probes),
        "initial_output_min": float(initial_outputs.min()),
        "initial_output_max": float(initial_outputs.max()),
        "final_output_min": float(final_outputs.min()),
        "final_output_max": float(final_outputs.max()),
        "probe_mean_abs_output_delta": float(output_delta.mean()),
        "probe_max_abs_output_delta": float(output_delta.max()),
        "zero_probe_output_delta": float((final_outputs[0] - initial_outputs[0]).abs()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    started = time.time()
    reports = [audit_checkpoint(args.run_dir / f"seed{index}_gate.pt") for index in range(3)]
    gates = {
        "all_updates_nonzero": all(row["parameter_delta_l2"] > 0 for row in reports),
        "all_probe_max_changes_below_1pct": all(row["probe_max_abs_output_delta"] < 0.01 for row in reports),
        "all_initial_outputs_exact_5pct": all(
            np.isclose(row["initial_output_min"], 0.05, atol=1e-7)
            and np.isclose(row["initial_output_max"], 0.05, atol=1e-7)
            for row in reports
        ),
    }
    underdosed = all(gates.values())
    output = {
        "schema": "cardpilot.decision_gate_update_audit.v1", "status": "COMPLETED",
        "claim_scope": "SYNTHETIC_PARAMETER_AND_BASIS_SENSITIVITY_NOT_POLICY_STRENGTH",
        "reports": reports, "gates": gates,
        "decision": "ADMIT_ONE_HIGHER_DOSE_CALIBRATION" if underdosed else "CLOSE_CURRENT_EXPERT_PAIR_AFTER_MATERIAL_NEGATIVE_SMOKE",
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
