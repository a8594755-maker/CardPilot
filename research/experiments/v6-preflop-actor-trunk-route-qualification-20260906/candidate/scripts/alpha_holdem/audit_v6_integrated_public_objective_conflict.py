"""Audit whether a public-opponent reward objective admits broad common descent.

This is a frozen, non-mutating diagnostic.  It extends the integrated three-anchor
opponent/seat audit with the separately trained public-state Slumbot behavior model
and includes Standard10 forward KL as a ninth objective.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.audit_v6_integrated_gradient_conflict import (
    action_prefix,
    geometry_for_subset,
    load_policy,
    parse_named_path,
    sha256_path,
)
from alpha_holdem.legacy_observation_bridge_v6 import decide, legacy_observation
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.public_opponent_v6 import (
    load_public_opponent,
    strategy as public_strategy,
)
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_dual_contract_advantage_balance import reconstruct
from alpha_holdem.v6_dual_contract_gradient_conflict_audit import (
    minimum_norm_simplex,
    normalized_alignments,
)


def select_public_action(policy, state: ChipState, uniform: float) -> tuple[str, dict]:
    """Sample the public model using an explicit scalar uniform for replayability."""
    from alpha_holdem.physical_v6_cfr import legal_slot_actions

    probabilities = public_strategy(policy, state)
    slot_actions = dict(legal_slot_actions(state))
    slots = sorted(slot_actions)
    scaled = probabilities[slots] / probabilities[slots].sum()
    cumulative = 0.0
    selected = slots[-1]
    for slot, probability in zip(slots, scaled):
        cumulative += float(probability)
        if uniform < cumulative:
            selected = slot
            break
    return slot_actions[selected], {
        "contract": "physical_v6_public_opponent_masked_private_sampled_v1",
        "checkpoint_sha256": policy.sha256,
        "selected_action_slot": int(selected),
        "behavior_probability": float(probabilities[selected]),
    }


def collect_candidate(
    candidate_name: str,
    candidate,
    neural_opponents: list[tuple[str, object]],
    public_opponent,
    hands_per_group: int,
    seed: int,
) -> tuple[list[dict], dict]:
    opponents = [*neural_opponents, ("public_slumbot", public_opponent)]
    rows: list[dict] = []
    group_summaries = []
    for opponent_index, (opponent_name, opponent) in enumerate(opponents):
        for hero_seat in (0, 1):
            group_index = opponent_index * 2 + hero_seat
            rewards = []
            decisions = 0
            for local_hand_index in range(hands_per_group):
                deck_rng = random.Random(
                    seed + 10_000_019 * group_index + 1_000_003 * local_hand_index
                )
                action_rng = random.Random(
                    seed + 700_000_027 + 10_000_019 * group_index
                    + 1_000_003 * local_hand_index
                )
                deck = list(range(52))
                deck_rng.shuffle(deck)
                state = ChipState.new(deck)
                hero_decisions = []
                while not state.terminal:
                    if state.actor == hero_seat:
                        prefix = action_prefix(state)
                        action, metadata = decide(
                            candidate,
                            state,
                            uniform=action_rng.random(),
                            policy_mode="sample",
                        )
                        hero_decisions.append(
                            {
                                "action_prefix": prefix,
                                "legacy_slot": int(
                                    metadata["legacy_selected_action_slot"]
                                ),
                                "behavior_probability": float(
                                    metadata["behavior_action_probability"]
                                ),
                            }
                        )
                    elif opponent_name == "public_slumbot":
                        action, _ = select_public_action(
                            opponent, state, action_rng.random()
                        )
                    else:
                        action, _ = decide(
                            opponent,
                            state,
                            uniform=action_rng.random(),
                            policy_mode="sample",
                        )
                    state = apply_incr(state, action)
                reward_bb = float(state.payoffs()[hero_seat]) / 100.0
                rewards.append(reward_bb)
                decisions += len(hero_decisions)
                rows.append(
                    {
                        "candidate": candidate_name,
                        "deck": deck,
                        "group": f"{opponent_name}_seat{hero_seat}",
                        "group_index": group_index,
                        "hero_decisions": hero_decisions,
                        "hero_seat": hero_seat,
                        "local_hand_index": local_hand_index,
                        "opponent": opponent_name,
                        "opponent_index": opponent_index,
                        "opponent_sha256": opponent.sha256,
                        "reward_bb": reward_bb,
                    }
                )
            group_summaries.append(
                {
                    "group": f"{opponent_name}_seat{hero_seat}",
                    "hands": hands_per_group,
                    "decisions": decisions,
                    "reward_bb_per_hand": float(np.mean(rewards)),
                    "reward_bb_per_100": 100.0 * float(np.mean(rewards)),
                }
            )
            print(
                f"candidate={candidate_name} group={opponent_name}_seat{hero_seat} "
                f"hands={hands_per_group} decisions={decisions}",
                flush=True,
            )
    return rows, {"groups": group_summaries}


def nine_objective_geometry(arrays: dict[str, np.ndarray]) -> dict:
    group_names = arrays["group_names"].tolist()
    group_units = arrays["group_unit_gradients"].astype(np.float64)
    source_kl = arrays["source_kl_all"].astype(np.float64)
    source_norm = float(np.linalg.norm(source_kl))
    if source_norm <= 1e-18:
        raise RuntimeError("source-KL gradient is zero")
    source_unit = source_kl / source_norm
    units = np.vstack([group_units, source_unit])
    names = [str(name) for name in group_names] + ["standard10_source_kl"]
    gram = units @ units.T
    objective, active, weights, products = minimum_norm_simplex(gram)
    aggregate = weights @ units
    alignments = normalized_alignments(units, aggregate)

    ordinary_plus_kl = arrays["ordinary_gradient"].astype(np.float64) + source_kl
    ordinary_alignments = normalized_alignments(units, ordinary_plus_kl)
    public_indices = [
        index for index, name in enumerate(group_names)
        if str(name).startswith("public_slumbot_")
    ]
    broad_indices = [
        index for index, name in enumerate(group_names)
        if not str(name).startswith("public_slumbot_")
    ]
    public_aggregate = group_units[public_indices].mean(axis=0)
    broad_aggregate = group_units[broad_indices].mean(axis=0)
    return {
        "objective_names": names,
        "minimum_norm": float(math.sqrt(max(objective, 0.0))),
        "weights": weights.tolist(),
        "active_objectives": [names[index] for index in active],
        "alignments": alignments.tolist(),
        "worst_alignment": float(alignments.min()),
        "kkt_valid": bool(np.all(products >= objective - 1e-7)),
        "ordinary_plus_coefficient_one_kl_alignments": ordinary_alignments.tolist(),
        "ordinary_plus_coefficient_one_kl_harmful_count": int(
            np.sum(ordinary_alignments <= 0.0)
        ),
        "public_vs_existing_broad_cosine": float(
            np.dot(
                public_aggregate / np.linalg.norm(public_aggregate),
                broad_aggregate / np.linalg.norm(broad_aggregate),
            )
        ),
        "public_vs_source_kl_cosine": float(
            np.dot(public_aggregate / np.linalg.norm(public_aggregate), source_unit)
        ),
    }


def verify_raw(summary: dict, raw_path: Path) -> dict:
    counts = Counter()
    decisions = Counter()
    decks = defaultdict(dict)
    legal = 0
    policies = {
        name: load_policy(Path(row["checkpoint"]), "cpu")
        for name, row in summary["candidates"].items()
    }
    rows = 0
    with gzip.open(raw_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            hand = json.loads(line)
            rows += 1
            key = (str(hand["candidate"]), str(hand["group"]))
            counts[key] += 1
            decisions[key] += len(hand["hero_decisions"])
            decks[(str(hand["group"]), int(hand["local_hand_index"]))][
                str(hand["candidate"])
            ] = tuple(hand["deck"])
            policy = policies[str(hand["candidate"])]
            for decision_row in hand["hero_decisions"]:
                state = reconstruct(hand["deck"], decision_row["action_prefix"])
                observation, _ = legacy_observation(policy, state)
                slot = int(decision_row["legacy_slot"])
                if not 0 <= slot < len(observation["legal_mask"]):
                    raise ValueError("legacy slot outside action space")
                if float(observation["legal_mask"][slot]) <= 0.0:
                    raise ValueError("recorded legacy slot is illegal")
                probability = float(decision_row["behavior_probability"])
                if not 0.0 < probability <= 1.0:
                    raise ValueError("invalid behavior probability")
                legal += 1
    expected = len(policies) * 8 * int(summary["hands_per_group"])
    return {
        "raw_hand_count_exact": rows == expected,
        "candidate_group_counts_exact": all(
            counts[(candidate, group["group"])] == summary["hands_per_group"]
            and decisions[(candidate, group["group"])] == group["decisions"]
            for candidate, row in summary["candidates"].items()
            for group in row["collection"]["groups"]
        ),
        "all_hero_decisions_reconstruct_and_legal": legal == sum(decisions.values()),
        "matched_decks_across_candidates": all(
            len(candidate_decks) == len(policies)
            and len(set(candidate_decks.values())) == 1
            for candidate_decks in decks.values()
        ),
        "raw_hands": rows,
        "legal_decisions": legal,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="append", type=parse_named_path, required=True)
    parser.add_argument("--opponent", action="append", type=parse_named_path, required=True)
    parser.add_argument("--public-opponent", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--hands-per-group", type=int, required=True)
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if len(args.opponent) != 3 or args.opponent[0][0] != "standard10":
        parser.error("exactly three neural opponents are required; first is standard10")
    if args.hands_per_group < args.folds or args.folds < 2:
        parser.error("hands-per-group must be >= folds >= 2")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(args.seed)
    started = time.time()

    source_path = args.source.resolve()
    source = load_policy(source_path, args.device)
    neural_opponents = [
        (name, load_policy(path.resolve(), args.device)) for name, path in args.opponent
    ]
    public_path = args.public_opponent.resolve()
    public_opponent = load_public_opponent(public_path)
    raw_path = args.out_dir / "frozen_training_hands.jsonl.gz"
    gradient_path = args.out_dir / "gradient_geometry.npz"
    candidates = {}
    npz_arrays = {}
    with gzip.open(raw_path, "xt", encoding="utf-8", newline="\n") as raw_handle:
        for candidate_name, candidate_path in args.candidate:
            candidate_path = candidate_path.resolve()
            candidate = load_policy(candidate_path, args.device)
            hands, collection = collect_candidate(
                candidate_name,
                candidate,
                neural_opponents,
                public_opponent,
                args.hands_per_group,
                args.seed,
            )
            for hand in hands:
                raw_handle.write(json.dumps(hand, sort_keys=True) + "\n")
            full_base, arrays = geometry_for_subset(hands, candidate, source, args.device)
            full_nine = nine_objective_geometry(arrays)
            folds = []
            for fold in range(args.folds):
                fold_hands = [
                    hand for hand in hands
                    if hand["local_hand_index"] % args.folds == fold
                ]
                _, fold_arrays = geometry_for_subset(
                    fold_hands, candidate, source, args.device
                )
                folds.append({"fold": fold, **nine_objective_geometry(fold_arrays)})
            candidates[candidate_name] = {
                "checkpoint": str(candidate_path),
                "checkpoint_sha256": candidate.sha256,
                "collection": collection,
                "base_eight_reward_geometry": full_base,
                "nine_objective_geometry": full_nine,
                "folds": folds,
            }
            prefix = candidate_name.replace("-", "_") + "__"
            for key, value in arrays.items():
                npz_arrays[prefix + key] = value
            del candidate
            if args.device == "cuda":
                torch.cuda.empty_cache()
    np.savez_compressed(gradient_path, **npz_arrays)

    fold_required = math.ceil(0.75 * args.folds)
    fold_positive_counts = {
        name: sum(
            row["worst_alignment"] > 0.0 and row["kkt_valid"]
            for row in candidate["folds"]
        )
        for name, candidate in candidates.items()
    }
    summary = {
        "schema": "cardpilot.integrated_public_objective_conflict_audit.v1",
        "status": "COMPLETED",
        "source_checkpoint": str(source_path),
        "source_sha256": source.sha256,
        "neural_opponents": [
            {"name": name, "path": str(policy.path), "sha256": policy.sha256}
            for name, policy in neural_opponents
        ],
        "public_opponent": {
            "path": str(public_path),
            "sha256": public_opponent.sha256,
            "contract": "physical_v6_public_opponent_masked_private_sampled_v1",
        },
        "hands_per_group": args.hands_per_group,
        "folds": args.folds,
        "seed": args.seed,
        "candidates": candidates,
        "preregistered_gates": {
            "full_worst_alignment_at_least_0_05_both_lineages": all(
                row["nine_objective_geometry"]["worst_alignment"] >= 0.05
                and row["nine_objective_geometry"]["kkt_valid"]
                for row in candidates.values()
            ),
            "positive_common_descent_at_least_three_of_four_folds_both_lineages": all(
                count >= fold_required for count in fold_positive_counts.values()
            ),
            "fold_positive_counts": fold_positive_counts,
            "required_folds": fold_required,
        },
        "raw_hands_sha256": sha256_path(raw_path),
        "gradient_artifact_sha256": sha256_path(gradient_path),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    summary_path = args.out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    integrity = verify_raw(summary, raw_path)
    integrity.update(
        {
            "raw_hash_exact": sha256_path(raw_path) == summary["raw_hands_sha256"],
            "gradient_hash_exact": sha256_path(gradient_path)
            == summary["gradient_artifact_sha256"],
            "candidate_hashes_exact": all(
                sha256_path(Path(row["checkpoint"])) == row["checkpoint_sha256"]
                for row in candidates.values()
            ),
            "source_hash_exact": sha256_path(source_path) == source.sha256,
            "neural_opponent_hashes_exact": all(
                sha256_path(Path(row["path"])) == row["sha256"]
                for row in summary["neural_opponents"]
            ),
            "public_opponent_hash_exact": sha256_path(public_path)
            == public_opponent.sha256,
        }
    )
    summary["integrity"] = integrity
    summary["passed"] = bool(
        all(
            value for key, value in integrity.items()
            if key not in {"raw_hands", "legal_decisions"}
        )
        and summary["preregistered_gates"][
            "full_worst_alignment_at_least_0_05_both_lineages"
        ]
        and summary["preregistered_gates"][
            "positive_common_descent_at_least_three_of_four_folds_both_lineages"
        ]
    )
    summary["decision"] = (
        "ADMIT_BOUNDED_PUBLIC_OBJECTIVE_MULTI_OBJECTIVE_UPDATE"
        if summary["passed"]
        else "REJECT_PUBLIC_OBJECTIVE_UPDATE_AT_RETAINED_1M_GEOMETRY"
    )
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
