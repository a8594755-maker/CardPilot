#!/usr/bin/env python3
"""Outcome-blind paired source-drift gate for the legacy-contract PPO smoke."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from alpha_holdem.legacy_observation_bridge_v6 import (  # noqa: E402
    BRIDGE_CONTRACT,
    legacy_observation_from_state,
    load_policy,
)
from alpha_holdem.policy_contract_v6 import (  # noqa: E402
    CONTRACT_VERSION,
    action_table,
    apply_incr,
)
from alpha_holdem.rules_v6 import ChipState, RULES_VERSION  # noqa: E402

PARENT = ROOT / "models/baseline/standard10/latest.pt"
TREATMENT = HERE / "training/latest.pt"
PARENT_SHA256 = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
ALLOWED_CHANGED_PREFIXES = ("policy_head.", "preflop_policy_head.", "value_head.")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rollout_action(state: ChipState, rng: np.random.Generator) -> str:
    _, table = action_table(state)
    raises = [action for action in table[2:8] if action is not None]
    u = float(rng.random())
    if state.to_call:
        if u < 0.08:
            return table[0]
        if u < 0.65 or not raises:
            return table[1]
        if u < 0.97:
            return raises[int(rng.integers(len(raises)))]
        return table[8]
    if u < 0.60 or not raises:
        return table[1]
    if u < 0.97:
        return raises[int(rng.integers(len(raises)))]
    return table[8]


@torch.no_grad()
def infer_probabilities(model, observations: list[dict], device: str) -> np.ndarray:
    tensors = [
        torch.as_tensor(
            np.stack([obs[key] for obs in observations]),
            dtype=torch.float32,
            device=device,
        )
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ]
    logits, _ = model(*tensors)
    masks = tensors[-1] > 0
    logits = logits.masked_fill(~masks, float("-inf"))
    return torch.softmax(logits, dim=-1).cpu().numpy()


def tensor_scope(parent: dict, treatment: dict) -> dict:
    parent_model = parent["model"]
    treatment_model = treatment["model"]
    missing = sorted(set(parent_model) - set(treatment_model))
    extra = sorted(set(treatment_model) - set(parent_model))
    changed = []
    unchanged = []
    shape_mismatches = []
    for key in sorted(set(parent_model) & set(treatment_model)):
        left, right = parent_model[key], treatment_model[key]
        if tuple(left.shape) != tuple(right.shape):
            shape_mismatches.append(key)
        elif torch.equal(left.cpu(), right.cpu()):
            unchanged.append(key)
        else:
            changed.append(key)
    disallowed = [key for key in changed if not key.startswith(ALLOWED_CHANGED_PREFIXES)]
    return {
        "parent_tensor_count": len(parent_model),
        "treatment_tensor_count": len(treatment_model),
        "changed_tensor_count": len(changed),
        "unchanged_tensor_count": len(unchanged),
        "changed_tensors": changed,
        "disallowed_changed_tensors": disallowed,
        "missing_tensors": missing,
        "extra_tensors": extra,
        "shape_mismatches": shape_mismatches,
        "status": "PASS" if not (missing or extra or shape_mismatches or disallowed) else "FAIL",
    }


def summarize(rows: list[dict]) -> dict:
    tv = np.asarray([row["tv"] for row in rows], dtype=np.float64)
    disagreements = np.asarray([row["greedy_disagreement"] for row in rows], dtype=np.float64)
    return {
        "states": len(rows),
        "mean_tv": float(tv.mean()),
        "max_tv": float(tv.max()),
        "p95_tv": float(np.quantile(tv, 0.95)),
        "greedy_disagreement_rate": float(disagreements.mean()),
        "greedy_disagreements": int(disagreements.sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", type=int, default=50_000)
    parser.add_argument("--seed", type=int, default=2_026_090_112)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--source-tv-max", type=float, default=0.03)
    parser.add_argument("--greedy-disagreement-max", type=float, default=0.05)
    args = parser.parse_args()
    started = time.time()
    torch.set_num_threads(8)

    parent = load_policy(PARENT, args.device)
    treatment = load_policy(TREATMENT, args.device)
    if parent.sha256 != PARENT_SHA256:
        raise RuntimeError("Frozen parent mismatch")
    expected_metadata = {
        "env_version": "v6legacyv4obs",
        "policy_contract": CONTRACT_VERSION,
        "rules_version": RULES_VERSION,
        "obs_version": "v4",
        "model_obs_version": "v4",
        "observation_bridge_contract": BRIDGE_CONTRACT,
        "action_space_version": "9slot_preflop_pot_fraction_v2_bridge_v1",
        "raise_action_mapping": "preflop_pot_fraction_v2",
        "starting_stack_bb": 200,
        "chips_per_bb": 100,
    }
    metadata_mismatches = {
        key: {"expected": expected, "actual": treatment.checkpoint.get(key)}
        for key, expected in expected_metadata.items()
        if treatment.checkpoint.get(key) != expected
    }
    scope = tensor_scope(parent.checkpoint, treatment.checkpoint)

    quotas = [args.states // 4] * 4
    for index in range(args.states % 4):
        quotas[index] += 1
    collected = [0, 0, 0, 0]
    rng = np.random.default_rng(args.seed)
    pending: list[dict] = []
    rows: list[dict] = []
    by_street: dict[int, list[dict]] = defaultdict(list)
    raw_path = HERE / "drift_raw.jsonl.gz"

    def flush(handle) -> None:
        if not pending:
            return
        observations = [row["observation"] for row in pending]
        parent_probs = infer_probabilities(parent.model, observations, args.device)
        treatment_probs = infer_probabilities(treatment.model, observations, args.device)
        for item, left, right in zip(pending, parent_probs, treatment_probs):
            parent_slot = int(np.argmax(left))
            treatment_slot = int(np.argmax(right))
            parent_action = item["table"][parent_slot]
            treatment_action = item["table"][treatment_slot]
            result = {
                "row": len(rows),
                "street": item["street"],
                "actor": item["actor"],
                "tv": float(0.5 * np.abs(left - right).sum()),
                "parent_slot": parent_slot,
                "treatment_slot": treatment_slot,
                "parent_action": parent_action,
                "treatment_action": treatment_action,
                "greedy_disagreement": parent_action != treatment_action,
            }
            rows.append(result)
            by_street[item["street"]].append(result)
            handle.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
        pending.clear()

    with gzip.open(raw_path, "wt", encoding="utf-8") as output:
        while any(collected[street] < quotas[street] for street in range(4)):
            state = ChipState.new(deck=rng.permutation(52).astype(int).tolist())
            while not state.terminal:
                street = state.street
                if collected[street] < quotas[street]:
                    obs, table = legacy_observation_from_state(
                        state, restrict_to_v6_action_table=True
                    )
                    pending.append({
                        "street": street,
                        "actor": state.actor,
                        "observation": obs,
                        "table": table,
                    })
                    collected[street] += 1
                    if len(pending) >= args.batch_size:
                        flush(output)
                state = apply_incr(state, rollout_action(state, rng))
        flush(output)

    overall = summarize(rows)
    street_metrics = {str(street): summarize(by_street[street]) for street in range(4)}
    thresholds_pass = (
        overall["mean_tv"] < args.source_tv_max
        and overall["greedy_disagreement_rate"] < args.greedy_disagreement_max
    )
    status = "PASS" if thresholds_pass and scope["status"] == "PASS" and not metadata_mismatches else "FAIL"
    result = {
        "schema": "cardpilot.legacy_contract_ppo_drift_gate.v1",
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "design": {
            "states": args.states,
            "seed": args.seed,
            "street_quotas": quotas,
            "source_tv_max": args.source_tv_max,
            "greedy_disagreement_max": args.greedy_disagreement_max,
            "outcome_blind": True,
        },
        "parent": {"path": str(PARENT.resolve()), "sha256": parent.sha256},
        "treatment": {"path": str(TREATMENT.resolve()), "sha256": treatment.sha256},
        "checkpoint_metadata_expected": expected_metadata,
        "checkpoint_metadata_mismatches": metadata_mismatches,
        "tensor_scope": scope,
        "overall": overall,
        "by_street": street_metrics,
        "raw_path": str(raw_path.resolve()),
        "raw_sha256": sha256_file(raw_path),
        "environment_training_hands": int(
            treatment.checkpoint["environment_hand_accounting"]["completed_hands"]
        ),
        "training_marker_hands": int(treatment.checkpoint["total_hands"]),
        "offline_samples": args.states,
        "slumbot_hands": 0,
        "wall_time_seconds": time.time() - started,
    }
    analysis_path = HERE / "drift_analysis.json"
    analysis_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
