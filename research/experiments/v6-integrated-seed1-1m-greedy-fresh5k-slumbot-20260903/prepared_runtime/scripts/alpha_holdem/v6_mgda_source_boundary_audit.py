"""Outcome-blind Standard10 boundary audit for frozen MGDA curve checkpoints."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
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


def stable_score(row: dict) -> str:
    payload = json.dumps(
        {
            "seed_index": row["seed_index"],
            "dose_index": row["dose_index"],
            "arm": row["arm"],
            "opponent_index": row["opponent_index"],
            "hero_seat": row["hero_seat"],
            "deck": row["deck"],
            "action_prefix": row["action_prefix"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def distribution_metrics(
    base_logits: torch.Tensor,
    candidate_logits: torch.Tensor,
    legal_mask: torch.Tensor,
):
    masked_base = base_logits + (1.0 - legal_mask) * -1e9
    masked_candidate = candidate_logits + (1.0 - legal_mask) * -1e9
    base_log_prob = torch.log_softmax(masked_base, dim=1)
    candidate_log_prob = torch.log_softmax(masked_candidate, dim=1)
    base_prob = base_log_prob.exp()
    kl = (base_prob * (base_log_prob - candidate_log_prob)).sum(dim=1)
    agreement = masked_base.argmax(dim=1) == masked_candidate.argmax(dim=1)
    delta = (candidate_logits - base_logits).abs() * legal_mask
    mean_abs_delta = delta.sum(dim=1) / legal_mask.sum(dim=1).clamp_min(1.0)
    max_abs_delta = delta.max(dim=1).values
    return agreement, kl, mean_abs_delta, max_abs_delta


def describe(indices, agreement, kl, mean_delta, max_delta):
    selected = torch.as_tensor(indices, dtype=torch.long, device=agreement.device)
    selected_agreement = agreement[selected].float()
    selected_kl = kl[selected]
    selected_mean_delta = mean_delta[selected]
    selected_max_delta = max_delta[selected]
    return {
        "states": int(len(indices)),
        "greedy_agreement": float(selected_agreement.mean()),
        "greedy_disagreement": float(1.0 - selected_agreement.mean()),
        "mean_kl_base_to_candidate": float(selected_kl.mean()),
        "p95_kl_base_to_candidate": float(torch.quantile(selected_kl, 0.95)),
        "maximum_kl_base_to_candidate": float(selected_kl.max()),
        "mean_abs_legal_logit_delta": float(selected_mean_delta.mean()),
        "maximum_abs_legal_logit_delta": float(selected_max_delta.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--states-per-stratum", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.states_per_stratum < 64:
        parser.error("states-per-stratum below audit minimum")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()

    run_dir = args.run_dir.resolve()
    source_summary_path = run_dir / "summary.json"
    training_path = run_dir / "training_hands.jsonl.gz"
    source_summary = json.loads(source_summary_path.read_text(encoding="utf-8"))
    base_path = args.base_checkpoint.resolve()
    base_sha = sha256_path(base_path)
    if base_sha != source_summary["base_sha256"]:
        raise RuntimeError("base checkpoint hash mismatch")
    if sha256_path(training_path) != source_summary["training_evidence_sha256"]:
        raise RuntimeError("training evidence hash mismatch")

    strata = defaultdict(list)
    source_hand_count = 0
    with gzip.open(training_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            hand = json.loads(line)
            source_hand_count += 1
            stratum = (
                int(hand["seed_index"]),
                int(hand["dose_index"]),
                str(hand["arm"]),
                int(hand["opponent_index"]),
                int(hand["hero_seat"]),
            )
            for decision_index, decision in enumerate(hand["hero_decisions"]):
                # Deliberately do not read reward_bb or any terminal outcome field.
                row = {
                    "seed_index": stratum[0],
                    "dose_index": stratum[1],
                    "arm": stratum[2],
                    "opponent_index": stratum[3],
                    "hero_seat": stratum[4],
                    "hand_index": int(hand["hand_index"]),
                    "decision_index": decision_index,
                    "deck": hand["deck"],
                    "action_prefix": decision["action_prefix"],
                }
                strata[stratum].append(row)
    if len(strata) != 48:
        raise RuntimeError(f"expected 48 strata, got {len(strata)}")
    minimum_support = min(len(rows) for rows in strata.values())
    if minimum_support < args.states_per_stratum:
        raise RuntimeError(
            f"minimum stratum support {minimum_support} below requested panel size"
        )
    panel = []
    for stratum in sorted(strata):
        selected = sorted(strata[stratum], key=stable_score)[: args.states_per_stratum]
        panel.extend(selected)
    panel_path = args.out_dir / "state_panel.jsonl.gz"
    with gzip.open(panel_path, "xt", encoding="utf-8", newline="\n") as handle:
        for row in panel:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    base_policy = load_policy(base_path, args.device)
    inputs = []
    for row in panel:
        state = reconstruct(row["deck"], row["action_prefix"])
        tensors, _, _ = state_inputs(base_policy, state, args.device)
        inputs.append(
            tuple(tensor.squeeze(0).detach().cpu().numpy() for tensor in tensors)
        )
    stacked = [
        torch.as_tensor(
            np.stack([row[index] for row in inputs]),
            dtype=torch.float32,
            device=args.device,
        )
        for index in range(8)
    ]
    with torch.no_grad():
        base_logits = base_policy.model(
            stacked[0], stacked[1], stacked[2], stacked[6]
        )[0]

    expected_checkpoints = {
        Path(row["path"]).name: row["sha256"]
        for row in source_summary["checkpoints"]
    }
    checkpoint_hashes_valid = True
    checkpoint_metrics = []
    metric_lookup = {}
    for seed_index in range(2):
        for arm in ("control", "treatment"):
            for dose_hands in (4096, 8192):
                checkpoint_path = run_dir / f"seed{seed_index}_{arm}_{dose_hands}.pt"
                actual_sha = sha256_path(checkpoint_path)
                checkpoint_hashes_valid &= (
                    expected_checkpoints.get(checkpoint_path.name) == actual_sha
                )
                checkpoint = torch.load(
                    checkpoint_path, map_location=args.device, weights_only=False
                )
                if checkpoint["base_sha256"] != base_sha:
                    raise RuntimeError("checkpoint base hash mismatch")
                model = DualContractResidualPolicy(
                    base_policy.model, hidden=128, policy_delta_cap=0.25
                ).to(args.device).eval()
                model.load_state_dict(checkpoint["residual_state_dict"], strict=False)
                with torch.no_grad():
                    candidate_logits = model(*stacked)[0]
                    agreement, kl, mean_delta, max_delta = distribution_metrics(
                        base_logits, candidate_logits, stacked[6]
                    )
                overall = describe(
                    np.arange(len(panel)), agreement, kl, mean_delta, max_delta
                )
                partitions = []
                for opponent_index in range(3):
                    for seat in (0, 1):
                        indices = [
                            index
                            for index, row in enumerate(panel)
                            if row["opponent_index"] == opponent_index
                            and row["hero_seat"] == seat
                        ]
                        partitions.append(
                            {
                                "opponent_index": opponent_index,
                                "seat": seat,
                                **describe(
                                    indices, agreement, kl, mean_delta, max_delta
                                ),
                            }
                        )
                row = {
                    "seed_index": seed_index,
                    "arm": arm,
                    "dose_hands": dose_hands,
                    "checkpoint_sha256": actual_sha,
                    "overall": overall,
                    "opponent_seat_partitions": partitions,
                }
                checkpoint_metrics.append(row)
                metric_lookup[(seed_index, arm, dose_hands)] = row

    comparisons = []
    per_seed_gates = []
    for seed_index in range(2):
        c4 = metric_lookup[(seed_index, "control", 4096)]["overall"]
        t4 = metric_lookup[(seed_index, "treatment", 4096)]["overall"]
        c8 = metric_lookup[(seed_index, "control", 8192)]["overall"]
        t8 = metric_lookup[(seed_index, "treatment", 8192)]["overall"]
        control_growth = c8["greedy_disagreement"] - c4["greedy_disagreement"]
        treatment_growth = t8["greedy_disagreement"] - t4["greedy_disagreement"]
        gates = {
            "treatment_8k_agreement_at_least_95pct": t8["greedy_agreement"] >= 0.95,
            "treatment_8k_within_1pp_control_agreement": t8[
                "greedy_agreement"
            ]
            >= c8["greedy_agreement"] - 0.01,
            "treatment_growth_within_control_plus_1pp": treatment_growth
            <= control_growth + 0.01,
            "treatment_8k_kl_within_1_25x_control": t8[
                "mean_kl_base_to_candidate"
            ]
            <= 1.25 * c8["mean_kl_base_to_candidate"] + 1e-12,
        }
        comparisons.append(
            {
                "seed_index": seed_index,
                "control_disagreement_growth_4k_to_8k": control_growth,
                "treatment_disagreement_growth_4k_to_8k": treatment_growth,
                "treatment_minus_control_8k_agreement": t8["greedy_agreement"]
                - c8["greedy_agreement"],
                "treatment_over_control_8k_mean_kl_ratio": t8[
                    "mean_kl_base_to_candidate"
                ]
                / max(c8["mean_kl_base_to_candidate"], 1e-12),
                "gates": gates,
            }
        )
        per_seed_gates.append(gates)

    treatment_8k_rows = [
        metric_lookup[(seed_index, "treatment", 8192)] for seed_index in range(2)
    ]
    worst_partition_disagreement = max(
        partition["greedy_disagreement"]
        for row in treatment_8k_rows
        for partition in row["opponent_seat_partitions"]
    )
    global_gates = {
        "source_training_hash_valid": sha256_path(training_path)
        == source_summary["training_evidence_sha256"],
        "all_checkpoint_hashes_valid": checkpoint_hashes_valid,
        "balanced_48_strata": len(strata) == 48,
        "exact_panel_size": len(panel) == 48 * args.states_per_stratum,
        "reward_fields_accessed": False,
        "all_per_seed_preservation_gates": all(
            all(gates.values()) for gates in per_seed_gates
        ),
        "worst_treatment_8k_partition_disagreement_at_most_10pct": worst_partition_disagreement
        <= 0.10,
        "all_treatment_residual_caps_respected": all(
            row["overall"]["maximum_abs_legal_logit_delta"] <= 0.250001
            for row in treatment_8k_rows
        ),
    }
    # reward_fields_accessed is an asserted negative property, not a pass flag.
    pass_values = [
        value
        for key, value in global_gates.items()
        if key != "reward_fields_accessed"
    ]
    admit = all(pass_values) and global_gates["reward_fields_accessed"] is False
    summary = {
        "schema": "cardpilot.mgda_source_boundary_audit.v1",
        "status": "COMPLETED",
        "base_sha256": base_sha,
        "source_training_sha256": sha256_path(training_path),
        "source_summary_sha256": sha256_path(source_summary_path),
        "source_hands": source_hand_count,
        "strata": len(strata),
        "minimum_stratum_support": minimum_support,
        "states_per_stratum": args.states_per_stratum,
        "panel_states": len(panel),
        "panel_sha256": sha256_path(panel_path),
        "checkpoint_metrics": checkpoint_metrics,
        "comparisons": comparisons,
        "worst_treatment_8k_partition_disagreement": worst_partition_disagreement,
        "gates": global_gates,
        "admit_resume_geometric_scale": admit,
        "decision": (
            "PRESERVATION_AUDIT_ADMITS_GEOMETRIC_RESUME"
            if admit
            else "PRESERVATION_AUDIT_HOLDS_SCALE"
        ),
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
