"""Frozen logit-level audit of whether contextual residuals use opponent context."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.contextual_residual_v6 import ContextualResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_broad_league_domain_feasibility import collect_balanced_states
from alpha_holdem.v6_dual_contract_residual_training_smoke import sha256_path, state_inputs


def final_group_contexts(path: Path, expected_groups: int = 12) -> np.ndarray:
    latest: dict[int, tuple[int, np.ndarray]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("kind") != "learning":
                continue
            group = int(row["group_index"])
            round_index = int(row["round_index"])
            context = np.asarray(row["context"], dtype=np.float32)
            if group not in latest or round_index > latest[group][0]:
                latest[group] = (round_index, context)
    if sorted(latest) != list(range(expected_groups)):
        raise ValueError("training evidence does not contain every context group")
    contexts = np.stack([latest[index][1] for index in range(expected_groups)])
    if contexts.shape != (expected_groups, 20) or not np.isfinite(contexts).all():
        raise ValueError("invalid final context matrix")
    return contexts


def summarize_state(base_logits: np.ndarray, candidate_logits: np.ndarray, legal: np.ndarray) -> dict:
    base = base_logits[legal]
    candidates = candidate_logits[:, legal]
    deltas = candidates - base[None, :]
    mean_delta = deltas.mean(axis=0)
    centered = deltas - mean_delta[None, :]
    predictions = candidates.argmax(axis=1)
    base_top = int(base.argmax())
    alternatives = [index for index in range(len(legal)) if index != base_top]
    if alternatives:
        base_margins = base[base_top] - base[alternatives]
        contextual_advantage = deltas[:, alternatives] - deltas[:, [base_top]]
        crossing_slack = float(np.max(contextual_advantage - base_margins[None, :]))
    else:
        crossing_slack = float("-inf")
    return {
        "generic_delta_rms": float(np.sqrt(np.mean(mean_delta**2))),
        "contextual_delta_rms": float(np.sqrt(np.mean(centered**2))),
        "maximum_context_logit_spread": float(np.max(deltas.max(axis=0) - deltas.min(axis=0))),
        "context_action_disagreement": bool(np.any(predictions != predictions[0])),
        "base_action_changed": bool(np.any(predictions != base_top)),
        "crossing_slack": crossing_slack,
    }


@torch.inference_mode()
def audit_checkpoint(model, base_policy, states, contexts: np.ndarray, device: str) -> dict:
    rows = []
    for state in states:
        values, obs, _ = state_inputs(base_policy, state, device)
        count = len(contexts)
        repeated = [tensor.repeat((count,) + (1,) * (tensor.ndim - 1)) for tensor in values]
        context_tensor = torch.as_tensor(contexts, dtype=torch.float32, device=device)
        candidate_logits = model(*repeated, context_tensor)[0].detach().cpu().numpy().astype(np.float64)
        base_logits = model.base(values[0], values[1], values[2], values[6])[0][0].detach().cpu().numpy().astype(np.float64)
        legal = np.flatnonzero(np.asarray(obs["legal_mask"]) > 0)
        rows.append({"street": state.street, "seat": state.actor, **summarize_state(base_logits, candidate_logits, legal)})
    generic = np.asarray([row["generic_delta_rms"] for row in rows])
    contextual = np.asarray([row["contextual_delta_rms"] for row in rows])
    partitions = []
    for street in range(4):
        for seat in (0, 1):
            selected = [row for row in rows if row["street"] == street and row["seat"] == seat]
            partitions.append({
                "street": street, "seat": seat, "states": len(selected),
                "context_action_disagreement_rate": float(np.mean([row["context_action_disagreement"] for row in selected])),
                "mean_contextual_delta_rms": float(np.mean([row["contextual_delta_rms"] for row in selected])),
            })
    return {
        "states": len(rows),
        "mean_generic_delta_rms": float(generic.mean()),
        "mean_contextual_delta_rms": float(contextual.mean()),
        "contextual_to_generic_rms_ratio": float(contextual.mean() / max(generic.mean(), 1e-15)),
        "median_maximum_context_logit_spread": float(np.median([row["maximum_context_logit_spread"] for row in rows])),
        "maximum_context_logit_spread": float(max(row["maximum_context_logit_spread"] for row in rows)),
        "context_action_disagreement_rate": float(np.mean([row["context_action_disagreement"] for row in rows])),
        "base_action_changed_under_any_context_rate": float(np.mean([row["base_action_changed"] for row in rows])),
        "positive_margin_crossing_slack_rate": float(np.mean([row["crossing_slack"] >= 0 for row in rows])),
        "maximum_crossing_slack": float(max(row["crossing_slack"] for row in rows)),
        "partitions": partitions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, action="append", required=True)
    parser.add_argument("--training-evidence", type=Path, action="append", required=True)
    parser.add_argument("--expected-checkpoint-sha256", action="append", required=True)
    parser.add_argument("--expected-evidence-sha256", action="append", required=True)
    parser.add_argument("--states", type=int, default=2048)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    count = len(args.checkpoint)
    if not (count == len(args.training_evidence) == len(args.expected_checkpoint_sha256) == len(args.expected_evidence_sha256)):
        parser.error("checkpoint/evidence/hash lists must have identical lengths")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    base_policy = load_policy(args.base_checkpoint, args.device)
    states = collect_balanced_states(args.states, args.seed)
    results = []
    for index in range(count):
        checkpoint_path = args.checkpoint[index]
        evidence_path = args.training_evidence[index]
        checkpoint_sha = sha256_path(checkpoint_path)
        evidence_sha = sha256_path(evidence_path)
        if checkpoint_sha != args.expected_checkpoint_sha256[index] or evidence_sha != args.expected_evidence_sha256[index]:
            raise ValueError(f"seed {index} artifact SHA mismatch")
        payload = torch.load(checkpoint_path, map_location=args.device, weights_only=False)
        model = ContextualResidualPolicy(base_policy.model, hidden=128, policy_delta_cap=0.25).to(args.device).eval()
        missing, unexpected = model.load_state_dict(payload["residual_state_dict"], strict=False)
        if unexpected or any(not name.startswith("base.") for name in missing):
            raise ValueError(f"invalid contextual checkpoint keys: missing={missing}, unexpected={unexpected}")
        contexts = final_group_contexts(evidence_path)
        pairwise = np.linalg.norm(contexts[:, None, :] - contexts[None, :, :], axis=2)
        result = {
            "seed_index": index, "checkpoint_sha256": checkpoint_sha, "evidence_sha256": evidence_sha,
            "context_pairwise_distance_median": float(np.median(pairwise[np.triu_indices(len(contexts), 1)])),
            "context_pairwise_distance_minimum": float(np.min(pairwise[np.triu_indices(len(contexts), 1)])),
            **audit_checkpoint(model, base_policy, states, contexts, args.device),
        }
        results.append(result)
    gates = {
        "all_context_matrices_distinct": all(row["context_pairwise_distance_minimum"] > 0 for row in results),
        "all_contextual_logit_rms_nontrivial": all(row["mean_contextual_delta_rms"] >= 1e-4 for row in results),
        "all_contextual_to_generic_ratio_at_least_10pct": all(row["contextual_to_generic_rms_ratio"] >= 0.10 for row in results),
        "any_seed_context_action_disagreement_at_least_0p5pct": any(row["context_action_disagreement_rate"] >= 0.005 for row in results),
        "any_seed_positive_margin_crossing_at_least_0p5pct": any(row["positive_margin_crossing_slack_rate"] >= 0.005 for row in results),
    }
    actionable_subargmax_signal = gates["all_contextual_logit_rms_nontrivial"] and gates["all_contextual_to_generic_ratio_at_least_10pct"]
    summary = {
        "schema": "cardpilot.contextual_residual_sensitivity_audit.v1", "status": "COMPLETED",
        "claim_scope": "FROZEN_CONTEXT_SENSITIVITY_NOT_POLICY_STRENGTH", "new_environment_hands": 0,
        "offline_state_context_queries": args.states * 12 * count, "results": results, "gates": gates,
        "actionable_subargmax_signal": actionable_subargmax_signal,
        "decision": "ADMIT_CONTEXTUAL_DOSE_CONTROL" if actionable_subargmax_signal else "REVISE_CONTEXTUAL_OBJECTIVE_OR_ARCHITECTURE",
        "wall_time_seconds": time.time() - started, "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
