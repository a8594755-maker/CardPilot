"""Audit opponent-seat policy-gradient conflict on frozen residual evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.dual_contract_residual_v6 import DualContractResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_dual_contract_advantage_balance import reconstruct
from alpha_holdem.v6_dual_contract_residual_training_smoke import (
    sha256_path,
    state_inputs,
)


def residual_state_digest(model: torch.nn.Module) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        if name.startswith("base."):
            continue
        digest.update(name.encode())
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def flatten_gradients(
    loss: torch.Tensor, parameters: list[torch.nn.Parameter]
) -> torch.Tensor:
    gradients = torch.autograd.grad(loss, parameters, allow_unused=True)
    return torch.cat(
        [
            torch.zeros_like(parameter).reshape(-1)
            if gradient is None
            else gradient.detach().reshape(-1)
            for parameter, gradient in zip(parameters, gradients)
        ]
    )


def minimum_norm_simplex(gram: np.ndarray, tolerance: float = 1e-10):
    """Solve min w'G w over the simplex by enumerating active sets."""
    count = gram.shape[0]
    best = None
    for active_count in range(1, count + 1):
        for active in itertools.combinations(range(count), active_count):
            selected = gram[np.ix_(active, active)]
            ones = np.ones(active_count, dtype=np.float64)
            # The augmented KKT system also represents a zero-norm convex
            # combination, where the usual inverse/denominator formula is
            # singular (for example two exactly opposite gradients).
            kkt = np.block(
                [
                    [2.0 * selected, -ones[:, None]],
                    [ones[None, :], np.zeros((1, 1), dtype=np.float64)],
                ]
            )
            target = np.concatenate(
                [np.zeros(active_count, dtype=np.float64), np.ones(1)]
            )
            solution, _, _, _ = np.linalg.lstsq(kkt, target, rcond=1e-12)
            active_weights = solution[:active_count]
            if np.linalg.norm(kkt @ solution - target) > 1e-7:
                continue
            if float(active_weights.min()) < -tolerance:
                continue
            weights = np.zeros(count, dtype=np.float64)
            weights[list(active)] = np.maximum(active_weights, 0.0)
            weights /= weights.sum()
            objective = float(weights @ gram @ weights)
            products = gram @ weights
            if any(products[index] < objective - 1e-7 for index in set(range(count)) - set(active)):
                continue
            candidate = (objective, tuple(active), weights, products)
            if best is None or candidate[0] < best[0]:
                best = candidate
    if best is None:
        raise RuntimeError("failed to solve minimum-norm simplex problem")
    return best


def normalized_alignments(unit_gradients: np.ndarray, aggregate: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(aggregate))
    if norm <= 1e-15:
        return np.zeros(unit_gradients.shape[0], dtype=np.float64)
    return unit_gradients @ (aggregate / norm)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--opponent", action="append", type=Path, required=True)
    parser.add_argument("--training-evidence", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if len(args.opponent) != 3:
        parser.error("exactly three --opponent checkpoints are required")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(args.seed)
    started = time.time()

    evidence_path = args.training_evidence.resolve()
    base_path = args.base_checkpoint.resolve()
    base_sha = sha256_path(base_path)
    evidence_sha = sha256_path(evidence_path)
    base_policy = load_policy(base_path, args.device)
    # Match the parent collection script's RNG sequence exactly. Loading each
    # policy constructs a module before restoring weights and therefore consumes
    # Torch RNG even though these policies are not evaluated by this audit.
    opponent_shas = [
        load_policy(path.resolve(), args.device).sha256 for path in args.opponent
    ]
    model = DualContractResidualPolicy(
        base_policy.model, hidden=128, policy_delta_cap=0.25
    ).to(args.device).eval()
    initial_residual_sha = residual_state_digest(model)
    parameters = list(model.trainable_parameters())

    hands = [
        json.loads(line)
        for line in gzip.open(evidence_path, "rt", encoding="utf-8")
    ]
    input_rows: list[tuple[np.ndarray, ...]] = []
    actions: list[int] = []
    returns: list[float] = []
    groups: list[str] = []
    evidence_rows: list[dict] = []
    for hand in hands:
        group = f"opponent{hand['opponent_index']}_seat{hand['hero_seat']}"
        for decision_index, decision in enumerate(hand["hero_decisions"]):
            state = reconstruct(hand["deck"], decision["action_prefix"])
            tensors, _, _ = state_inputs(base_policy, state, args.device)
            input_rows.append(
                tuple(tensor.squeeze(0).detach().cpu().numpy() for tensor in tensors)
            )
            actions.append(int(decision["slot"]))
            returns.append(float(hand["reward_bb"]) / 200.0)
            groups.append(group)
            evidence_rows.append(
                {
                    "hand_index": int(hand["hand_index"]),
                    "decision_index": decision_index,
                    "action_prefix": decision["action_prefix"],
                    "slot": int(decision["slot"]),
                    "group": group,
                    "return_normalized": returns[-1],
                }
            )

    tensors = [
        torch.as_tensor(
            np.stack([row[index] for row in input_rows]),
            dtype=torch.float32,
            device=args.device,
        )
        for index in range(8)
    ]
    action_tensor = torch.tensor(actions, dtype=torch.long, device=args.device)
    return_tensor = torch.tensor(returns, dtype=torch.float32, device=args.device)
    with torch.no_grad():
        logits, values = model(*tensors)
        distribution = torch.distributions.Categorical(
            logits=logits + (1.0 - tensors[6]) * -1e9
        )
        old_log_probs = distribution.log_prob(action_tensor)
        raw_advantages = return_tensor - values.squeeze(1)

    group_names = sorted(set(groups))
    gradient_rows = []
    group_metrics = []
    for group in group_names:
        indices = torch.tensor(
            [index for index, value in enumerate(groups) if value == group],
            dtype=torch.long,
            device=args.device,
        )
        advantages = raw_advantages[indices]
        normalized = (advantages - advantages.mean()) / advantages.std().clamp_min(1e-6)
        normalized = normalized.clamp(-5.0, 5.0)
        batch = [tensor[indices] for tensor in tensors]
        group_logits, _ = model(*batch)
        group_distribution = torch.distributions.Categorical(
            logits=group_logits + (1.0 - batch[6]) * -1e9
        )
        log_probs = group_distribution.log_prob(action_tensor[indices])
        ratio = torch.exp(log_probs - old_log_probs[indices])
        policy_loss = -(ratio * normalized).mean()
        gradient = flatten_gradients(policy_loss, parameters)
        gradient_rows.append(gradient.cpu().double().numpy())
        for local_index, global_index in enumerate(indices.detach().cpu().tolist()):
            evidence_rows[global_index]["raw_advantage"] = float(advantages[local_index])
            evidence_rows[global_index]["group_normalized_advantage"] = float(
                normalized[local_index]
            )
        group_metrics.append(
            {
                "group": group,
                "decisions": int(len(indices)),
                "gradient_l2": float(gradient.norm()),
                "raw_advantage_mean": float(advantages.mean()),
                "raw_advantage_std": float(advantages.std()),
                "normalized_advantage_mean": float(normalized.mean()),
                "normalized_advantage_std": float(normalized.std()),
            }
        )

    gradients = np.stack(gradient_rows)
    norms = np.linalg.norm(gradients, axis=1)
    if np.any(norms <= 1e-15):
        raise RuntimeError("one or more group policy gradients are zero")
    unit_gradients = gradients / norms[:, None]
    gram = unit_gradients @ unit_gradients.T
    off_diagonal = [
        float(gram[left, right])
        for left in range(len(group_names))
        for right in range(left + 1, len(group_names))
    ]
    decision_weights = np.asarray(
        [row["decisions"] for row in group_metrics], dtype=np.float64
    )
    decision_weights /= decision_weights.sum()
    ordinary_aggregate = decision_weights @ gradients
    ordinary_alignments = normalized_alignments(unit_gradients, ordinary_aggregate)

    objective, active, robust_weights, products = minimum_norm_simplex(gram)
    robust_aggregate = robust_weights @ unit_gradients
    robust_alignments = normalized_alignments(unit_gradients, robust_aggregate)
    conflict_pairs = int(sum(value < -0.10 for value in off_diagonal))
    ordinary_harmful_groups = int(
        sum(value <= 0.0 for value in ordinary_alignments)
    )
    material_conflict = bool(
        conflict_pairs >= 2 or ordinary_harmful_groups >= 1
    )
    robust_common_descent = bool(np.all(robust_alignments > 1e-8))
    improves_worst_alignment = bool(
        robust_alignments.min() > ordinary_alignments.min() + 1e-6
    )
    gates = {
        "all_six_groups_present": len(group_names) == 6,
        "initial_residual_matches_parent": initial_residual_sha
        == "f0888035682556bfee647ed57a28ae2d3c66578e26192bb84a1e69b79329fbce",
        "material_gradient_conflict": material_conflict,
        "robust_common_descent_for_all_groups": robust_common_descent,
        "robust_improves_worst_normalized_alignment": improves_worst_alignment,
        "simplex_weights_valid": bool(
            np.all(robust_weights >= -1e-10)
            and abs(float(robust_weights.sum()) - 1.0) < 1e-9
        ),
        "minimum_norm_kkt_valid": bool(
            np.all(products >= objective - 1e-7)
        ),
    }
    admit = all(gates.values())

    raw_path = args.out_dir / "reconstructed_decisions.jsonl.gz"
    with gzip.open(raw_path, "xt", encoding="utf-8", newline="\n") as handle:
        for row in evidence_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    gradients_path = args.out_dir / "group_gradients.npz"
    np.savez_compressed(
        gradients_path,
        groups=np.asarray(group_names),
        gradients=gradients,
        unit_gradients=unit_gradients,
        cosine_matrix=gram,
        decision_weights=decision_weights,
        ordinary_alignments=ordinary_alignments,
        robust_weights=robust_weights,
        robust_alignments=robust_alignments,
    )
    summary = {
        "schema": "cardpilot.dual_contract_gradient_conflict_audit.v1",
        "status": "COMPLETED",
        "base_sha256": base_sha,
        "opponent_sha256": opponent_shas,
        "source_training_sha256": evidence_sha,
        "initial_residual_sha256": initial_residual_sha,
        "training_hands_reused": len(hands),
        "reconstructed_decisions": len(evidence_rows),
        "group_metrics": group_metrics,
        "pairwise_cosine_matrix": gram.tolist(),
        "off_diagonal_cosine_minimum": min(off_diagonal),
        "off_diagonal_cosine_maximum": max(off_diagonal),
        "pairwise_cosines_below_negative_0_10": conflict_pairs,
        "ordinary_decision_weights": decision_weights.tolist(),
        "ordinary_normalized_alignments": ordinary_alignments.tolist(),
        "ordinary_worst_normalized_alignment": float(ordinary_alignments.min()),
        "ordinary_harmful_group_count": ordinary_harmful_groups,
        "robust_method": "minimum_norm_convex_combination_of_unit_group_gradients",
        "robust_active_groups": [group_names[index] for index in active],
        "robust_weights": robust_weights.tolist(),
        "robust_normalized_alignments": robust_alignments.tolist(),
        "robust_worst_normalized_alignment": float(robust_alignments.min()),
        "minimum_norm_objective": objective,
        "gates": gates,
        "admit_matched_training_smoke": admit,
        "decision": (
            "ADMIT_CONFLICT_AWARE_MATCHED_TRAINING_SMOKE"
            if admit
            else "REJECT_CONFLICT_AWARE_AGGREGATION_ROUTE"
        ),
        "raw_sha256": sha256_path(raw_path),
        "gradient_artifact_sha256": sha256_path(gradients_path),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
