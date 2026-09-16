"""Exact-parity and gradient-isolation gate for a dual-contract residual policy."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.dual_contract_residual_v6 import DualContractResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import (
    action_prefix,
    legacy_observation_from_state,
    load_policy,
)
from alpha_holdem.policy_contract_v6 import apply_incr, observation
from alpha_holdem.rules_v6 import ChipState


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tensorize(rows, key):
    return torch.from_numpy(np.stack([row[key] for row in rows]).astype(np.float32))


def collect_states(count: int, seed: int):
    rng = random.Random(seed)
    rows = []
    hand_index = 0
    while len(rows) < count:
        deck = list(range(52))
        rng.shuffle(deck)
        state = ChipState.new(deck)
        while not state.terminal and len(rows) < count:
            legacy_obs, legacy_table = legacy_observation_from_state(state)
            native_obs, _ = observation(state)
            rows.append({
                "hand_index": hand_index,
                "action_prefix": action_prefix(state),
                "actor": int(state.actor),
                "street": int(state.street),
                "deck": deck,
                "legacy_cards": legacy_obs["card_info"],
                "legacy_actions": legacy_obs["action_info"],
                "legacy_extras": legacy_obs["extra_info"],
                "legacy_mask": legacy_obs["legal_mask"],
                "native_cards": native_obs["card_info"],
                "native_actions": native_obs["action_info"],
                "native_extras": native_obs["extra_info"],
                "native_mask": native_obs["legal_mask"],
            })
            legal = [action for action in legacy_table if action is not None]
            state = apply_incr(state, rng.choice(legal))
        hand_index += 1
    return rows, hand_index


def model_inputs(rows):
    return (
        tensorize(rows, "legacy_cards"), tensorize(rows, "legacy_actions"),
        tensorize(rows, "legacy_extras"), tensorize(rows, "native_cards"),
        tensorize(rows, "native_actions"), tensorize(rows, "native_extras"),
        tensorize(rows, "legacy_mask"), tensorize(rows, "native_mask"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--states", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.states < 128:
        parser.error("--states must be at least 128")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(args.seed)
    started = time.time()

    policy = load_policy(args.base_checkpoint, "cpu")
    model = DualContractResidualPolicy(policy.model, hidden=128).eval()
    rows, trajectory_hands = collect_states(args.states, args.seed)
    exact_logits = exact_values = True
    greedy_matches = 0
    max_logit_error = max_value_error = 0.0
    for start in range(0, len(rows), 128):
        batch = rows[start:start + 128]
        values = model_inputs(batch)
        with torch.no_grad():
            base_logits, base_value = policy.model(values[0], values[1], values[2], values[6])[:2]
            logits, value = model(*values)
        exact_logits &= torch.equal(logits, base_logits)
        exact_values &= torch.equal(value, base_value)
        max_logit_error = max(max_logit_error, float((logits - base_logits).abs().max()))
        max_value_error = max(max_value_error, float((value - base_value).abs().max()))
        penalty = (1.0 - values[6]) * -1e9
        greedy_matches += int(torch.eq((logits + penalty).argmax(1), (base_logits + penalty).argmax(1)).sum())

    training_batch = rows[:128]
    values = model_inputs(training_batch)
    model.train()
    logits, value = model(*values)
    targets = []
    for row in training_batch:
        legal = np.flatnonzero(row["legacy_mask"] > 0)
        targets.append(int(legal[-1]))
    loss = torch.nn.functional.cross_entropy(logits, torch.tensor(targets)) + (value - 0.25).square().mean()
    loss.backward()
    base_gradient_tensors = sum(parameter.grad is not None for parameter in model.base.parameters())
    residual_gradient_tensors = sum(
        parameter.grad is not None and bool(parameter.grad.abs().sum() > 0)
        for parameter in model.trainable_parameters()
    )
    base_before = {name: tensor.detach().clone() for name, tensor in model.base.state_dict().items()}
    optimizer = torch.optim.Adam(model.trainable_parameters(), lr=1e-3)
    optimizer.step()
    model.eval()
    with torch.no_grad():
        updated_logits, updated_value = model(*values)
    post_update_changed = not torch.equal(updated_logits, logits.detach())
    base_unchanged = all(torch.equal(base_before[name], tensor) for name, tensor in model.base.state_dict().items())

    checkpoint_path = args.out_dir / "dual_contract_residual.pt"
    torch.save({
        "schema": "cardpilot.dual_contract_residual.v1",
        "base_checkpoint": str(args.base_checkpoint.resolve()),
        "base_sha256": policy.sha256,
        "residual_state_dict": {
            name: tensor for name, tensor in model.state_dict().items() if not name.startswith("base.")
        },
        "hidden": 128,
    }, checkpoint_path)
    reloaded = DualContractResidualPolicy(policy.model, hidden=128)
    saved = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    reloaded.load_state_dict(saved["residual_state_dict"], strict=False)
    reloaded.eval()
    with torch.no_grad():
        roundtrip_logits, roundtrip_value = reloaded(*values)
    roundtrip_exact = torch.equal(updated_logits, roundtrip_logits) and torch.equal(updated_value, roundtrip_value)

    raw_path = args.out_dir / "states.jsonl.gz"
    with gzip.open(raw_path, "xt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps({
                "hand_index": row["hand_index"], "action_prefix": row["action_prefix"],
                "actor": row["actor"], "street": row["street"], "deck": row["deck"],
                "legacy_legal_mask": row["legacy_mask"].tolist(),
                "native_legal_mask": row["native_mask"].tolist(),
            }, sort_keys=True) + "\n")
    gates = {
        "exact_zero_policy_logits": bool(exact_logits),
        "exact_zero_values": bool(exact_values),
        "all_legal_greedy_slots_match": greedy_matches == len(rows),
        "base_gradients_zero": base_gradient_tensors == 0,
        "residual_gradients_nonzero": residual_gradient_tensors > 0,
        "post_update_outputs_change": post_update_changed,
        "base_state_unchanged": base_unchanged,
        "checkpoint_roundtrip_exact": roundtrip_exact,
    }
    summary = {
        "schema": "cardpilot.dual_contract_residual_feasibility.v1",
        "status": "COMPLETED", "base_sha256": policy.sha256,
        "states": len(rows), "trajectory_hands": trajectory_hands,
        "street_counts": {str(street): sum(row["street"] == street for row in rows) for street in range(4)},
        "max_zero_logit_error": max_logit_error,
        "max_zero_value_error": max_value_error,
        "greedy_matches": greedy_matches,
        "base_gradient_tensors": base_gradient_tensors,
        "residual_gradient_tensors": residual_gradient_tensors,
        "loss": float(loss.detach()), "gates": gates,
        "admit_training_smoke": all(gates.values()),
        "decision": "ADMIT_DUAL_CONTRACT_TRAINING_SMOKE" if all(gates.values()) else "REJECT_DUAL_CONTRACT_ARCHITECTURE",
        "checkpoint_sha256": sha256_path(checkpoint_path),
        "states_sha256": sha256_path(raw_path),
        "wall_time_seconds": time.time() - started,
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))
    if not all(gates.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
