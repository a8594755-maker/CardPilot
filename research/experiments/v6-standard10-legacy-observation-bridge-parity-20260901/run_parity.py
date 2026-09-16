#!/usr/bin/env python3
"""End-to-end greedy parity of the generic bridge and historical execution."""
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

from alpha_holdem.legacy_observation_bridge_v6 import (
    action_prefix,
    card_string,
    decide as bridge_decide,
    load_policy,
    reconstruct_legacy_state,
)
from alpha_holdem.play_slumbot import build_action_table, decide_action
from alpha_holdem.policy_contract_v6 import action_table, apply_incr
from alpha_holdem.rules_v6 import ChipState

MODEL = ROOT / "models" / "baseline" / "standard10" / "latest.pt"
EXPECTED_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=2_026_090_108)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    started = time.time()
    torch.set_num_threads(1)
    policy = load_policy(MODEL, args.device)
    if policy.sha256 != EXPECTED_SHA:
        raise RuntimeError(f"checkpoint identity mismatch: {policy.sha256}")
    rng = np.random.default_rng(args.seed)
    quotas = [args.states // 4] * 4
    for index in range(args.states % 4):
        quotas[index] += 1
    collected = [0, 0, 0, 0]
    counters: Counter[str] = Counter()
    by_street: dict[int, Counter[str]] = defaultdict(Counter)
    hand = 0
    row_index = 0
    raw_path = HERE / "raw_parity.jsonl.gz"
    with gzip.open(raw_path, "wt", encoding="utf-8") as output:
        while any(collected[street] < quotas[street] for street in range(4)):
            state = ChipState.new(deck=rng.permutation(52).astype(int).tolist())
            hand += 1
            while not state.terminal:
                street = state.street
                if collected[street] < quotas[street]:
                    parsed, _ = reconstruct_legacy_state(state)
                    hole = [card_string(card) for card in state.holes[state.actor]]
                    board = [card_string(card) for card in state.board]
                    direct_slot, direct_info = decide_action(
                        policy.model,
                        hole,
                        board,
                        parsed,
                        state.actor,
                        args.device,
                        greedy=True,
                        obs_version="v4",
                        policy_mode="greedy",
                        return_info=True,
                    )
                    _, old_table = build_action_table(parsed, "preflop_pot_fraction_v2")
                    direct_action = old_table[direct_slot]
                    bridge_action, bridge_info = bridge_decide(
                        policy, state, uniform=0.5, policy_mode="greedy"
                    )
                    _, current_table = action_table(state)
                    exact_action = bridge_action == direct_action
                    exact_slot = bridge_info["legacy_selected_action_slot"] == direct_slot
                    v6_legal = bridge_action in current_table
                    counters["states"] += 1
                    counters["exact_action_parity"] += int(exact_action)
                    counters["exact_legacy_slot_parity"] += int(exact_slot)
                    counters["exact_v6_legality"] += int(v6_legal)
                    by_street[street]["states"] += 1
                    by_street[street]["exact_action_parity"] += int(exact_action)
                    by_street[street]["exact_legacy_slot_parity"] += int(exact_slot)
                    by_street[street]["exact_v6_legality"] += int(v6_legal)
                    output.write(json.dumps({
                        "row": row_index,
                        "hand": hand,
                        "street": street,
                        "actor": state.actor,
                        "action_prefix": action_prefix(state),
                        "direct_slot": direct_slot,
                        "direct_action": direct_action,
                        "direct_greedy_slot": direct_info["greedy_action_slot"],
                        "bridge_legacy_slot": bridge_info["legacy_selected_action_slot"],
                        "bridge_v6_slot": bridge_info["selected_action_slot"],
                        "bridge_action": bridge_action,
                        "exact_action_parity": exact_action,
                        "exact_legacy_slot_parity": exact_slot,
                        "exact_v6_legality": v6_legal,
                    }, sort_keys=True, separators=(",", ":")) + "\n")
                    collected[street] += 1
                    row_index += 1
                state = apply_incr(state, rollout_action(state, rng))
    def rates(counter: Counter[str]) -> dict[str, float]:
        return {
            key: counter[key] / counter["states"]
            for key in ("exact_action_parity", "exact_legacy_slot_parity", "exact_v6_legality")
        }
    result = {
        "schema": "cardpilot.legacy_observation_bridge_parity.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "status": "COMPLETED",
        "checkpoint": str(MODEL),
        "checkpoint_sha256": policy.sha256,
        "design": {"states": args.states, "seed": args.seed, "street_quotas": quotas},
        "counts": dict(counters),
        "rates": rates(counters),
        "by_street": {
            str(street): {"counts": dict(counter), "rates": rates(counter)}
            for street, counter in sorted(by_street.items())
        },
        "environment_training_hands": 0,
        "slumbot_hands": 0,
        "raw_parity": str(raw_path),
        "raw_parity_sha256": sha256_file(raw_path),
        "wall_time_seconds": time.time() - started,
    }
    result["admission"] = (
        "ADMIT_FRESH5K_GENERIC_GREEDY_CALIBRATION"
        if all(value == 1.0 for value in result["rates"].values())
        else "DO_NOT_EXTERNALLY_EVALUATE_BRIDGE"
    )
    (HERE / "analysis.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
