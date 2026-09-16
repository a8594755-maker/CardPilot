"""Exact replay and opponent-seat gradient-conflict audit for decision gates."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.v6_decision_expert_gate_smoke import ExpertGate, train_gate
from alpha_holdem.v6_dual_contract_gradient_conflict_audit import flatten_gradients, normalized_alignments
from alpha_holdem.v6_dual_contract_mgda_matched_smoke import aggregate_policy_gradients
from alpha_holdem.v6_dual_contract_residual_training_smoke import sha256_path


def load_transition_arrays(path: Path) -> dict[str, np.ndarray]:
    with np.load(path) as payload:
        arrays = {key: payload[key].copy() for key in payload.files}
    required = {"features", "p0", "p1", "slots", "old_log_probs", "returns_bb", "groups"}
    if set(arrays) != required:
        raise ValueError(f"transition schema mismatch: {path}")
    return arrays


def arrays_to_rows(arrays: dict[str, np.ndarray]) -> list[dict]:
    return [
        {
            "features": arrays["features"][i], "p0": arrays["p0"][i],
            "p1": arrays["p1"][i], "slot": int(arrays["slots"][i]),
            "old_log_prob": float(arrays["old_log_probs"][i]),
            "return_bb": float(arrays["returns_bb"][i]),
            "group": int(arrays["groups"][i]),
        }
        for i in range(len(arrays["slots"]))
    ]


def policy_gradient_matrix(gate: ExpertGate, arrays: dict[str, np.ndarray], *, groups: int,
                           device: str) -> tuple[np.ndarray, dict]:
    features = torch.as_tensor(arrays["features"], dtype=torch.float32, device=device)
    p0 = torch.as_tensor(arrays["p0"], dtype=torch.float32, device=device)
    p1 = torch.as_tensor(arrays["p1"], dtype=torch.float32, device=device)
    slots = torch.as_tensor(arrays["slots"], dtype=torch.long, device=device)
    old = torch.as_tensor(arrays["old_log_probs"], dtype=torch.float32, device=device)
    returns = torch.as_tensor(arrays["returns_bb"], dtype=torch.float32, device=device)
    group_ids = torch.as_tensor(arrays["groups"], dtype=torch.long, device=device)
    parameters = list(gate.parameters())
    gradients = []
    supports = []
    for group in range(groups):
        selected = group_ids == group
        support = int(selected.sum())
        if support < 2:
            raise RuntimeError(f"insufficient group support: {group}={support}")
        values = returns[selected]
        advantage = ((values - values.mean()) / values.std().clamp_min(1e-6)).clamp(-5.0, 5.0)
        weight = gate(features[selected])
        mixture = (1.0 - weight[:, None]) * p0[selected] + weight[:, None] * p1[selected]
        log_probs = torch.log(mixture.gather(1, slots[selected, None]).squeeze(1).clamp_min(1e-12))
        ratio = torch.exp(log_probs - old[selected])
        surrogate = torch.minimum(ratio * advantage, ratio.clamp(0.8, 1.2) * advantage)
        gradients.append(flatten_gradients(-surrogate.mean(), parameters).cpu().double().numpy())
        supports.append(support)
    matrix = np.stack(gradients)
    norms = np.linalg.norm(matrix, axis=1)
    if np.any(norms <= 1e-15) or not np.isfinite(matrix).all():
        raise RuntimeError("nonfinite or zero group gradient")
    unit = matrix / norms[:, None]
    gram = unit @ unit.T
    ordinary = matrix.mean(axis=0)
    _, mgda = aggregate_policy_gradients(matrix, np.full(groups, 1.0 / groups), True)
    ordinary_alignment = normalized_alignments(unit, ordinary)
    upper = [float(gram[i, j]) for i in range(groups) for j in range(i + 1, groups)]
    return matrix, {
        "group_support": supports,
        "pairwise_cosine_minimum": min(upper),
        "negative_pairwise_cosines": sum(value < 0 for value in upper),
        "ordinary_worst_alignment": float(ordinary_alignment.min()),
        "ordinary_negative_group_alignments": int(np.sum(ordinary_alignment < 0)),
        "mgda_worst_alignment": mgda["applied_worst_alignment"],
        "mgda_weights": mgda["robust_weights"],
        "mgda_minimum_norm_objective": mgda["minimum_norm_objective"],
    }


def replay_seed(run_dir: Path, seed_index: int, device: str) -> dict:
    checkpoint_path = run_dir / f"seed{seed_index}_gate.pt"
    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    seed = int(payload["seed"])
    feature_dim = int(payload["feature_dim"])
    torch.manual_seed(seed)
    gate = ExpertGate(feature_dim, hidden=int(payload["hidden"])).to(device)
    optimizer = torch.optim.Adam(gate.parameters(), lr=0.01)
    chunks = []
    for offset in (0, 1024, 2048, 3072):
        path = run_dir / f"seed{seed_index}_chunk{offset:05d}_transitions.npz"
        arrays = load_transition_arrays(path)
        _, geometry = policy_gradient_matrix(gate, arrays, groups=12, device=device)
        rows = arrays_to_rows(arrays)
        replay_metrics = train_gate(
            gate, optimizer, rows, epochs=8, groups=12, device=device, reference_kl_coef=0.1,
        )
        chunks.append({
            "offset": offset, "path": str(path), "sha256": sha256_path(path),
            "transitions": len(rows), "geometry": geometry,
            "replay_final_metric": replay_metrics[-1],
        })
    replay_state = gate.state_dict()
    target_state = payload["state_dict"]
    errors = {
        key: float((replay_state[key].detach().cpu() - target_state[key].cpu()).abs().max())
        for key in target_state
    }
    return {
        "seed_index": seed_index, "seed": seed, "checkpoint_sha256": sha256_path(checkpoint_path),
        "endpoint_replay_max_abs_error": max(errors.values()),
        "endpoint_tensor_max_abs_errors": errors, "chunks": chunks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    reports = [replay_seed(args.run_dir, index, args.device) for index in range(3)]
    chunks = [chunk for report in reports for chunk in report["chunks"]]
    ordinary_conflicts = sum(chunk["geometry"]["ordinary_worst_alignment"] < 0 for chunk in chunks)
    gates = {
        "all_endpoint_replays_within_1e_6": all(report["endpoint_replay_max_abs_error"] <= 1e-6 for report in reports),
        "negative_pairwise_conflict_present": all(chunk["geometry"]["negative_pairwise_cosines"] > 0 for chunk in chunks),
        "ordinary_worst_alignment_negative_in_at_least_half": ordinary_conflicts >= len(chunks) / 2,
        "mgda_worst_alignment_nonnegative_every_chunk": all(chunk["geometry"]["mgda_worst_alignment"] >= -1e-8 for chunk in chunks),
        "mgda_strictly_improves_worst_alignment_every_chunk": all(
            chunk["geometry"]["mgda_worst_alignment"] > chunk["geometry"]["ordinary_worst_alignment"] + 1e-8
            for chunk in chunks
        ),
    }
    admitted = all(gates.values())
    output = {
        "schema": "cardpilot.decision_gate_gradient_conflict_audit.v1", "status": "COMPLETED",
        "claim_scope": "EXACT_SAVED_TRANSITION_GRADIENT_GEOMETRY_NOT_POLICY_STRENGTH",
        "reports": reports, "chunks": len(chunks), "ordinary_conflict_chunks": ordinary_conflicts,
        "gates": gates,
        "decision": "ADMIT_MATCHED_MGDA_GATE_SMOKE" if admitted else "CLOSE_DECISION_GATE_ROUTE",
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"decision": output["decision"], "gates": gates, "ordinary_conflict_chunks": ordinary_conflicts}, sort_keys=True))


if __name__ == "__main__":
    main()
