#!/usr/bin/env python3
"""Outcome-blind audit that v6-exact slot restriction preserves source greedy play."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
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

MODEL = ROOT / "models/baseline/standard10/latest.pt"
MODEL_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rollout_action(state, rng):
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
def infer(model, observations, device):
    tensors = [
        torch.as_tensor(np.stack([obs[key] for obs in observations]), dtype=torch.float32, device=device)
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ]
    logits, _ = model(*tensors)
    values = logits.detach().cpu().numpy()
    masks = np.stack([obs["legal_mask"] for obs in observations]).astype(bool)
    return np.asarray([
        np.flatnonzero(mask)[np.argmax(row[np.flatnonzero(mask)])]
        for row, mask in zip(values, masks)
    ], dtype=np.int64)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", type=int, default=50_000)
    parser.add_argument("--seed", type=int, default=2_026_090_111)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=512)
    args = parser.parse_args()
    torch.set_num_threads(8)
    started = time.time()
    policy = load_policy(MODEL, args.device)
    if policy.sha256 != MODEL_SHA:
        raise RuntimeError("Frozen source mismatch")
    rng = np.random.default_rng(args.seed)
    quotas = [args.states // 4] * 4
    for index in range(args.states % 4):
        quotas[index] += 1
    collected = [0, 0, 0, 0]
    pending = []
    counters = Counter()
    by_street = defaultdict(Counter)
    raw_path = HERE / "restriction_raw.jsonl.gz"

    def flush(handle):
        if not pending:
            return
        unrestricted_slots = infer(policy.model, [row["uobs"] for row in pending], args.device)
        restricted_slots = infer(policy.model, [row["robs"] for row in pending], args.device)
        for row, unrestricted_slot, restricted_slot in zip(pending, unrestricted_slots, restricted_slots):
            unrestricted_action = row["utable"][int(unrestricted_slot)]
            restricted_action = row["rtable"][int(restricted_slot)]
            mask_changed = not np.array_equal(row["uobs"]["legal_mask"], row["robs"]["legal_mask"])
            action_same = unrestricted_action == restricted_action
            counters["states"] += 1
            counters["mask_changed"] += int(mask_changed)
            counters["greedy_action_preserved"] += int(action_same)
            counters["unrestricted_greedy_removed"] += int(
                row["rtable"][int(unrestricted_slot)] is None
            )
            street = row["street"]
            by_street[street]["states"] += 1
            by_street[street]["mask_changed"] += int(mask_changed)
            by_street[street]["greedy_action_preserved"] += int(action_same)
            handle.write(json.dumps({
                "row": counters["states"] - 1,
                "street": street,
                "actor": row["actor"],
                "mask_changed": mask_changed,
                "unrestricted_slot": int(unrestricted_slot),
                "restricted_slot": int(restricted_slot),
                "unrestricted_action": unrestricted_action,
                "restricted_action": restricted_action,
                "greedy_action_preserved": action_same,
            }, sort_keys=True, separators=(",", ":")) + "\n")
        pending.clear()

    with gzip.open(raw_path, "wt", encoding="utf-8") as output:
        while any(collected[street] < quotas[street] for street in range(4)):
            state = ChipState.new(deck=rng.permutation(52).astype(int).tolist())
            while not state.terminal:
                street = state.street
                if collected[street] < quotas[street]:
                    uobs, utable = legacy_observation_from_state(
                        state, restrict_to_v6_action_table=False
                    )
                    robs, rtable = legacy_observation_from_state(
                        state, restrict_to_v6_action_table=True
                    )
                    pending.append({
                        "street": street, "actor": state.actor,
                        "uobs": uobs, "utable": utable,
                        "robs": robs, "rtable": rtable,
                    })
                    collected[street] += 1
                    if len(pending) >= args.batch_size:
                        flush(output)
                state = apply_incr(state, rollout_action(state, rng))
        flush(output)
    result = {
        "schema": "cardpilot.legacy_bridge_restriction_audit.v1",
        "status": "PASS" if counters["greedy_action_preserved"] == counters["states"] else "FAIL",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "checkpoint_sha256": policy.sha256,
        "design": {"states": args.states, "seed": args.seed, "street_quotas": quotas},
        "counts": dict(counters),
        "rates": {
            "mask_changed": counters["mask_changed"] / counters["states"],
            "greedy_action_preserved": counters["greedy_action_preserved"] / counters["states"],
            "unrestricted_greedy_removed": counters["unrestricted_greedy_removed"] / counters["states"],
        },
        "by_street": {str(key): dict(value) for key, value in sorted(by_street.items())},
        "raw_sha256": sha256_file(raw_path),
        "environment_training_hands": 0,
        "slumbot_hands": 0,
        "wall_time_seconds": time.time() - started,
    }
    (HERE / "restriction_analysis.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
