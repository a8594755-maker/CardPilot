"""Reconstruct zero-residual advantages and audit opponent-seat PPO balance."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.legacy_observation_bridge_v6 import (
    action_prefix,
    legacy_observation,
    load_policy,
)
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState


TOKEN = re.compile(r"b\d+|[fkc]")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reconstruct(deck, prefix):
    state = ChipState.new(deck)
    tokens = TOKEN.findall(prefix)
    if "".join(tokens) != prefix.replace("/", ""):
        raise ValueError(f"unparsed action prefix: {prefix}")
    for token in tokens:
        state = apply_incr(state, token)
    if state.terminal or action_prefix(state) != prefix:
        raise ValueError("reconstructed state identity mismatch")
    return state


def describe(values):
    values = np.asarray(values, dtype=np.float64)
    return {
        "count": len(values), "mean": float(values.mean()),
        "std": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
        "positive_fraction": float((values > 0).mean()),
        "minimum": float(values.min()), "maximum": float(values.max()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--training-evidence", type=Path, required=True)
    parser.add_argument("--evaluation-evidence", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    policy = load_policy(args.base_checkpoint, "cpu")

    hands = [
        json.loads(line)
        for line in gzip.open(args.training_evidence, "rt", encoding="utf-8")
    ]
    decisions = []
    pending_obs = []
    pending_refs = []
    for hand in hands:
        group = f"opponent{hand['opponent_index']}_seat{hand['hero_seat']}"
        for decision_index, decision in enumerate(hand["hero_decisions"]):
            state = reconstruct(hand["deck"], decision["action_prefix"])
            obs, _ = legacy_observation(policy, state)
            row = {
                "hand_index": hand["hand_index"], "decision_index": decision_index,
                "group": group, "opponent_index": hand["opponent_index"],
                "hero_seat": hand["hero_seat"], "action_prefix": decision["action_prefix"],
                "slot": decision["slot"], "reward_bb": hand["reward_bb"],
                "return_normalized": hand["reward_bb"] / 200.0,
            }
            decisions.append(row)
            pending_obs.append(obs)
            pending_refs.append(row)
            if len(pending_obs) == 256:
                tensors = [torch.from_numpy(np.stack([obs[key] for obs in pending_obs])).float()
                           for key in ("card_info", "action_info", "extra_info", "legal_mask")]
                with torch.no_grad():
                    values = policy.model(*tensors)[1].squeeze(1).numpy()
                for ref, value in zip(pending_refs, values): ref["base_value"] = float(value)
                pending_obs, pending_refs = [], []
    if pending_obs:
        tensors = [torch.from_numpy(np.stack([obs[key] for obs in pending_obs])).float()
                   for key in ("card_info", "action_info", "extra_info", "legal_mask")]
        with torch.no_grad():
            values = policy.model(*tensors)[1].squeeze(1).numpy()
        for ref, value in zip(pending_refs, values): ref["base_value"] = float(value)

    raw_advantages = np.asarray(
        [row["return_normalized"] - row["base_value"] for row in decisions],
        dtype=np.float64,
    )
    global_mean = float(raw_advantages.mean())
    global_std = float(raw_advantages.std(ddof=1))
    normalized = (raw_advantages - global_mean) / max(global_std, 1e-12)
    groups = sorted({row["group"] for row in decisions})
    group_indices = {
        group: np.asarray([i for i, row in enumerate(decisions) if row["group"] == group])
        for group in groups
    }
    centered = normalized.copy()
    for indices in group_indices.values():
        centered[indices] -= centered[indices].mean()
    for index, row in enumerate(decisions):
        row["raw_advantage"] = float(raw_advantages[index])
        row["global_normalized_advantage"] = float(normalized[index])
        row["group_centered_advantage"] = float(centered[index])

    hand_groups = defaultdict(list)
    hand_decisions = Counter()
    for hand in hands:
        group = f"opponent{hand['opponent_index']}_seat{hand['hero_seat']}"
        hand_groups[group].append(hand["reward_bb"])
        hand_decisions[group] += len(hand["hero_decisions"])
    group_rows = []
    total_abs = float(np.abs(normalized).sum())
    total_squared = float(np.square(normalized).sum())
    for group in groups:
        indices = group_indices[group]
        signed_mass = float(normalized[indices].sum())
        absolute_mass = float(np.abs(normalized[indices]).sum())
        squared_mass = float(np.square(normalized[indices]).sum())
        group_rows.append({
            "group": group,
            "hands": len(hand_groups[group]),
            "decisions": len(indices),
            "decision_share": len(indices) / len(decisions),
            "decisions_per_hand": len(indices) / len(hand_groups[group]),
            "hand_reward_bb": describe(hand_groups[group]),
            "decision_weighted_reward_bb": describe(
                [decisions[index]["reward_bb"] for index in indices]
            ),
            "base_value": describe([decisions[index]["base_value"] for index in indices]),
            "raw_advantage": describe(raw_advantages[indices]),
            "global_normalized_advantage": describe(normalized[indices]),
            "global_normalized_signed_mass": signed_mass,
            "signed_mass_over_global_absolute_mass": signed_mass / total_abs,
            "absolute_mass_share": absolute_mass / total_abs,
            "squared_mass_share": squared_mass / total_squared,
            "group_centered_advantage": describe(centered[indices]),
            "action_counts": dict(Counter(decisions[index]["slot"] for index in indices)),
        })

    evaluation_rows = [
        json.loads(line)
        for line in gzip.open(args.evaluation_evidence, "rt", encoding="utf-8")
    ]
    evaluation = []
    for anchor in sorted({row["anchor_index"] for row in evaluation_rows}):
        selected = [row for row in evaluation_rows if row["anchor_index"] == anchor]
        seat_means = []
        for seat in (0, 1):
            seat_means.append(float(np.mean([
                row["treatment_rewards_bb"][seat] - row["control_rewards_bb"][seat]
                for row in selected
            ])) * 100.0)
        evaluation.append({
            "anchor_index": anchor,
            "pairs": len(selected),
            "delta_bb100": float(np.mean([
                row["treatment_minus_control_pair_mean_bb"] for row in selected
            ])) * 100.0,
            "seat_delta_bb100": seat_means,
        })

    max_group_mean = max(abs(row["global_normalized_advantage"]["mean"]) for row in group_rows)
    min_support = min(row["decisions"] for row in group_rows)
    max_centered_mean = max(abs(row["group_centered_advantage"]["mean"]) for row in group_rows)
    share_ratio = max(row["decision_share"] for row in group_rows) / min(
        row["decision_share"] for row in group_rows
    )
    standard_deviation_ratio = max(
        row["global_normalized_advantage"]["std"] for row in group_rows
    ) / min(row["global_normalized_advantage"]["std"] for row in group_rows)
    max_squared_mass_share = max(row["squared_mass_share"] for row in group_rows)
    gates = {
        "all_six_groups_present": len(group_rows) == 6,
        "minimum_300_decisions_per_group": min_support >= 300,
        "material_variance_ratio": standard_deviation_ratio >= 2.0,
        "one_group_at_least_30_percent_squared_mass": max_squared_mass_share >= 0.30,
        "centering_removes_group_means": max_centered_mean < 1e-12,
    }
    raw_path = args.out_dir / "reconstructed_decisions.jsonl.gz"
    with gzip.open(raw_path, "xt", encoding="utf-8", newline="\n") as handle:
        for row in decisions:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    summary = {
        "schema": "cardpilot.dual_contract_advantage_balance.v1",
        "status": "COMPLETED", "base_sha256": policy.sha256,
        "training_hands": len(hands), "reconstructed_decisions": len(decisions),
        "global_raw_advantage": describe(raw_advantages),
        "global_normalized_advantage": describe(normalized),
        "groups": group_rows, "evaluation": evaluation,
        "max_abs_group_global_normalized_mean": max_group_mean,
        "max_abs_group_centered_mean": max_centered_mean,
        "decision_share_max_min_ratio": share_ratio,
        "group_standard_deviation_max_min_ratio": standard_deviation_ratio,
        "maximum_group_squared_mass_share": max_squared_mass_share,
        "gates": gates,
        "admit_group_rms_smoke": all(gates.values()),
        "decision": "ADMIT_GROUP_RMS_ADVANTAGE_SMOKE" if all(gates.values()) else "NO_MATERIAL_ADVANTAGE_VARIANCE_DEFECT",
        "source_training_sha256": sha256_path(args.training_evidence),
        "source_evaluation_sha256": sha256_path(args.evaluation_evidence),
        "raw_sha256": sha256_path(raw_path),
        "wall_time_seconds": time.time() - started,
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
