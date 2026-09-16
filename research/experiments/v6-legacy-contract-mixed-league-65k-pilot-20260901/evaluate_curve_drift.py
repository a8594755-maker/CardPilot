#!/usr/bin/env python3
"""Paired 50k-state source-drift curve for four frozen FIFO archives."""
from __future__ import annotations

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
    legacy_observation_from_state,
    load_policy,
)
from alpha_holdem.policy_contract_v6 import action_table, apply_incr  # noqa: E402
from alpha_holdem.rules_v6 import ChipState  # noqa: E402

PARENT = ROOT / "models/baseline/standard10/latest.pt"
PARENT_SHA256 = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
CANDIDATES = {
    "iter04": HERE / "training/checkpoints/checkpoint_iter000004_hands000000016500.pt",
    "iter08": HERE / "training/checkpoints/checkpoint_iter000008_hands000000033016.pt",
    "iter12": HERE / "training/checkpoints/checkpoint_iter000012_hands000000049525.pt",
    "iter16": HERE / "training/checkpoints/checkpoint_iter000016_hands000000065966.pt",
}
ALLOWED_CHANGED_PREFIXES = ("policy_head.", "preflop_policy_head.", "value_head.")
STATES = 50_000
SEED = 2_026_090_113
BATCH_SIZE = 1024


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
def infer(model, observations: list[dict], device: str) -> np.ndarray:
    tensors = [
        torch.as_tensor(np.stack([obs[key] for obs in observations]), dtype=torch.float32, device=device)
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ]
    logits, _ = model(*tensors)
    logits = logits.masked_fill(tensors[-1] <= 0, float("-inf"))
    return torch.softmax(logits, dim=-1).cpu().numpy()


def tensor_scope(parent: dict, candidate: dict) -> dict:
    changed = []
    disallowed = []
    shape_mismatches = []
    for key, value in parent["model"].items():
        other = candidate["model"].get(key)
        if other is None or tuple(value.shape) != tuple(other.shape):
            shape_mismatches.append(key)
        elif not torch.equal(value.cpu(), other.cpu()):
            changed.append(key)
            if not key.startswith(ALLOWED_CHANGED_PREFIXES):
                disallowed.append(key)
    missing_or_extra = sorted(set(parent["model"]) ^ set(candidate["model"]))
    return {
        "status": "PASS" if not (disallowed or shape_mismatches or missing_or_extra) else "FAIL",
        "changed_tensor_count": len(changed),
        "changed_tensors": changed,
        "disallowed_changed_tensors": disallowed,
        "shape_mismatches": shape_mismatches,
        "missing_or_extra_tensors": missing_or_extra,
    }


def summarize(rows: list[dict], label: str) -> dict:
    tv = np.asarray([row[label]["tv"] for row in rows], dtype=np.float64)
    disagree = np.asarray([row[label]["greedy_disagreement"] for row in rows], dtype=np.float64)
    return {
        "states": len(rows),
        "mean_tv": float(tv.mean()),
        "p95_tv": float(np.quantile(tv, 0.95)),
        "max_tv": float(tv.max()),
        "greedy_disagreements": int(disagree.sum()),
        "greedy_disagreement_rate": float(disagree.mean()),
    }


def main() -> None:
    started = time.time()
    device = "cuda"
    torch.set_num_threads(8)
    parent = load_policy(PARENT, device)
    if parent.sha256 != PARENT_SHA256:
        raise RuntimeError("parent hash mismatch")
    candidates = {label: load_policy(path, device) for label, path in CANDIDATES.items()}
    scopes = {label: tensor_scope(parent.checkpoint, policy.checkpoint) for label, policy in candidates.items()}

    rng = np.random.default_rng(SEED)
    quotas = [STATES // 4] * 4
    collected = [0, 0, 0, 0]
    pending = []
    rows = []
    by_street = {label: defaultdict(list) for label in candidates}
    raw_path = HERE / "curve_drift_raw.jsonl.gz"

    def flush(handle) -> None:
        if not pending:
            return
        observations = [row["observation"] for row in pending]
        parent_probs = infer(parent.model, observations, device)
        candidate_probs = {label: infer(policy.model, observations, device) for label, policy in candidates.items()}
        for index, item in enumerate(pending):
            left = parent_probs[index]
            parent_slot = int(np.argmax(left))
            result = {"row": len(rows), "street": item["street"], "actor": item["actor"]}
            for label, matrix in candidate_probs.items():
                right = matrix[index]
                candidate_slot = int(np.argmax(right))
                metric = {
                    "tv": float(0.5 * np.abs(left - right).sum()),
                    "parent_slot": parent_slot,
                    "candidate_slot": candidate_slot,
                    "greedy_disagreement": item["table"][parent_slot] != item["table"][candidate_slot],
                }
                result[label] = metric
                by_street[label][item["street"]].append(result)
            rows.append(result)
            handle.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
        pending.clear()

    with gzip.open(raw_path, "wt", encoding="utf-8") as output:
        while any(collected[street] < quotas[street] for street in range(4)):
            state = ChipState.new(deck=rng.permutation(52).astype(int).tolist())
            while not state.terminal:
                street = state.street
                if collected[street] < quotas[street]:
                    observation, table = legacy_observation_from_state(state, restrict_to_v6_action_table=True)
                    pending.append({"street": street, "actor": state.actor, "observation": observation, "table": table})
                    collected[street] += 1
                    if len(pending) >= BATCH_SIZE:
                        flush(output)
                state = apply_incr(state, rollout_action(state, rng))
        flush(output)

    curve = {}
    for label, policy in candidates.items():
        overall = summarize(rows, label)
        curve[label] = {
            "checkpoint": str(CANDIDATES[label].resolve()),
            "sha256": policy.sha256,
            "iteration": int(policy.checkpoint["iteration"]),
            "transition_hands": int(policy.checkpoint["total_hands"]),
            "overall": overall,
            "by_street": {str(street): summarize(by_street[label][street], label) for street in range(4)},
            "tensor_scope": scopes[label],
            "preservation_gate": "PASS" if overall["mean_tv"] < 0.10 and overall["greedy_disagreement_rate"] < 0.15 and scopes[label]["status"] == "PASS" else "FAIL",
        }
    result = {
        "schema": "cardpilot.legacy_contract_source_drift_curve.v1",
        "status": "PASS" if all(row["preservation_gate"] == "PASS" for row in curve.values()) else "FAIL",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "design": {"states": STATES, "seed": SEED, "street_quotas": quotas, "mean_tv_max": 0.10, "greedy_disagreement_max": 0.15, "outcome_blind": True},
        "parent": {"path": str(PARENT.resolve()), "sha256": parent.sha256},
        "curve": curve,
        "raw_path": str(raw_path.resolve()),
        "raw_sha256": sha256_file(raw_path),
        "offline_samples": STATES * len(candidates),
        "slumbot_hands": 0,
        "wall_time_seconds": time.time() - started,
    }
    (HERE / "curve_drift_analysis.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
