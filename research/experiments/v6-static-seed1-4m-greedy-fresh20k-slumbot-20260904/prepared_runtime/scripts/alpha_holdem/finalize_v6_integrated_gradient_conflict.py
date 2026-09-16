"""Verify integrated conflict evidence and analyze the deployed objective geometry."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.legacy_observation_bridge_v6 import legacy_observation, load_policy
from alpha_holdem.v6_dual_contract_advantage_balance import reconstruct
from alpha_holdem.v6_dual_contract_gradient_conflict_audit import (
    minimum_norm_simplex,
    normalized_alignments,
)
from alpha_holdem.audit_v6_integrated_gradient_conflict import sha256_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--input", action="append", type=Path, default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    started = time.time()
    summary_path = args.run_dir / "summary.json"
    raw_path = args.run_dir / "frozen_training_hands.jsonl.gz"
    gradient_path = args.run_dir / "gradient_geometry.npz"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    arrays = np.load(gradient_path)

    gates = {
        "summary_completed": summary["status"] == "COMPLETED",
        "raw_hash_exact": sha256_path(raw_path) == summary["raw_hands_sha256"],
        "gradient_hash_exact": sha256_path(gradient_path)
        == summary["gradient_artifact_sha256"],
    }
    policies = {
        name: load_policy(Path(row["checkpoint"]), "cpu")
        for name, row in summary["candidates"].items()
    }
    gates["candidate_hashes_exact"] = all(
        policy.sha256 == summary["candidates"][name]["checkpoint_sha256"]
        for name, policy in policies.items()
    )
    source_path = Path(summary["source_checkpoint"])
    gates["source_hash_exact"] = sha256_path(source_path) == summary["source_sha256"]
    gates["opponent_hashes_exact"] = all(
        sha256_path(Path(row["path"])) == row["sha256"]
        for row in summary["opponents"]
    )

    expected_hands = (
        len(policies) * 6 * int(summary["hands_per_group"])
    )
    counts = Counter()
    decision_counts = Counter()
    decks = defaultdict(dict)
    legal_decisions = 0
    rows = 0
    with gzip.open(raw_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            hand = json.loads(line)
            rows += 1
            candidate = str(hand["candidate"])
            group = str(hand["group"])
            local_index = int(hand["local_hand_index"])
            counts[(candidate, group)] += 1
            decision_counts[(candidate, group)] += len(hand["hero_decisions"])
            decks[(group, local_index)][candidate] = tuple(hand["deck"])
            policy = policies[candidate]
            for decision in hand["hero_decisions"]:
                state = reconstruct(hand["deck"], decision["action_prefix"])
                obs, _ = legacy_observation(policy, state)
                slot = int(decision["legacy_slot"])
                if not 0 <= slot < len(obs["legal_mask"]):
                    raise ValueError("legacy slot outside action space")
                if float(obs["legal_mask"][slot]) <= 0.0:
                    raise ValueError("recorded legacy slot is not legal")
                probability = float(decision["behavior_probability"])
                if not 0.0 < probability <= 1.0:
                    raise ValueError("invalid sampled behavior probability")
                legal_decisions += 1
    gates["raw_hand_count_exact"] = rows == expected_hands
    gates["all_candidate_groups_exact"] = all(
        counts[(candidate, group["group"])] == int(summary["hands_per_group"])
        and decision_counts[(candidate, group["group"])] == int(group["decisions"])
        for candidate, candidate_row in summary["candidates"].items()
        for group in candidate_row["collection"]["groups"]
    )
    gates["all_decisions_reconstruct_and_legal"] = legal_decisions == sum(
        decision_counts.values()
    )
    gates["matched_decks_across_candidates"] = all(
        len(candidate_decks) == len(policies)
        and len(set(candidate_decks.values())) == 1
        for candidate_decks in decks.values()
    )

    objective_rows = {}
    for candidate in sorted(policies):
        prefix = candidate.replace("-", "_") + "__"
        gradients = arrays[prefix + "group_gradients"].astype(np.float64)
        units = arrays[prefix + "group_unit_gradients"].astype(np.float64)
        ordinary = arrays[prefix + "ordinary_gradient"].astype(np.float64)
        source_kl = arrays[prefix + "source_kl_all"].astype(np.float64)
        robust_weights = arrays[prefix + "robust_weights"].astype(np.float64)
        source_unit = source_kl / np.linalg.norm(source_kl)
        coefficient_one = ordinary + source_kl
        coefficient_one_alignments = normalized_alignments(units, coefficient_one)
        group_robust = robust_weights @ units
        seven_units = np.vstack([units, source_unit])
        gram = seven_units @ seven_units.T
        objective, active, seven_weights, products = minimum_norm_simplex(gram)
        seven_aggregate = seven_weights @ seven_units
        seven_alignments = normalized_alignments(seven_units, seven_aggregate)
        names = arrays[prefix + "group_names"].tolist() + ["standard10_source_kl"]
        objective_rows[candidate] = {
            "ordinary_gradient_l2": float(np.linalg.norm(ordinary)),
            "source_kl_gradient_l2": float(np.linalg.norm(source_kl)),
            "source_kl_to_ordinary_norm_ratio": float(
                np.linalg.norm(source_kl) / np.linalg.norm(ordinary)
            ),
            "coefficient_one_group_alignments": coefficient_one_alignments.tolist(),
            "coefficient_one_harmful_group_count": int(
                sum(coefficient_one_alignments <= 0.0)
            ),
            "coefficient_one_source_kl_alignment": float(
                np.dot(source_unit, coefficient_one / np.linalg.norm(coefficient_one))
            ),
            "group_only_robust_vs_source_kl_cosine": float(
                np.dot(group_robust / np.linalg.norm(group_robust), source_unit)
            ),
            "seven_objective_names": names,
            "seven_objective_active": [names[index] for index in active],
            "seven_objective_weights": seven_weights.tolist(),
            "seven_objective_alignments": seven_alignments.tolist(),
            "seven_objective_worst_alignment": float(seven_alignments.min()),
            "seven_objective_minimum_norm": float(np.sqrt(max(objective, 0.0))),
            "seven_objective_kkt_valid": bool(
                np.all(products >= objective - 1e-7)
            ),
        }
    gates.update(
        {
            "material_conflict_reproduced": bool(
                summary["gates"]["material_gradient_conflict_replicates"]
            ),
            "source_kl_conflict_reproduced": bool(
                summary["gates"][
                    "ordinary_gradient_conflicts_with_source_kl_replicates"
                ]
            ),
            "coefficient_one_harms_group_in_both_candidates": all(
                row["coefficient_one_harmful_group_count"] >= 1
                for row in objective_rows.values()
            ),
            "group_only_robust_conflicts_with_source_in_both_candidates": all(
                row["group_only_robust_vs_source_kl_cosine"] < 0.0
                for row in objective_rows.values()
            ),
            "seven_objective_common_descent_in_both_candidates": all(
                row["seven_objective_worst_alignment"] > 0.0
                and row["seven_objective_kkt_valid"]
                for row in objective_rows.values()
            ),
            "standard10_not_underexposed": not bool(
                summary["gates"][
                    "standard10_underexposed_below_15pct_pool_hands"
                ]
            ),
        }
    )
    input_hashes = {
        str(path.resolve()): sha256_path(path.resolve()) for path in args.input
    }
    passed = all(gates.values())
    result = {
        "schema": "cardpilot.integrated_gradient_conflict_finalization.v1",
        "status": "COMPLETED",
        "passed": passed,
        "gates": gates,
        "raw_hands": rows,
        "legal_decisions": legal_decisions,
        "candidate_group_counts": {
            f"{candidate}/{group}": count
            for (candidate, group), count in sorted(counts.items())
        },
        "objective_geometry": objective_rows,
        "input_hashes": input_hashes,
        "decision": (
            "ADMIT_SEVEN_OBJECTIVE_CONFLICT_AWARE_INTERVENTION_SMOKE"
            if passed
            else "HOLD_FOR_EVIDENCE_OR_GEOMETRY_REPAIR"
        ),
        "raw_sha256": sha256_path(raw_path),
        "gradient_sha256": sha256_path(gradient_path),
        "summary_sha256": sha256_path(summary_path),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
