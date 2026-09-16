#!/usr/bin/env python3
"""Outcome-blind old-Standard10 to v6 physical-action identifiability audit."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import random
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from alpha_holdem.execution_v6 import load_policy as load_v6_policy
from alpha_holdem.play_slumbot import (
    STACK_SIZE,
    build_action_table as old_action_table,
    compute_commitments,
    encode_action_history,
    encode_cards,
    encode_extra,
    parse_action,
)
from alpha_holdem.policy_contract_v6 import action_table as v6_action_table
from alpha_holdem.policy_contract_v6 import apply_incr, observation
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v5_mirror_eval import load_policy as load_old_policy

OLD_PATH = ROOT / "models" / "baseline" / "standard10" / "latest.pt"
V6_PATH = (
    ROOT
    / "research"
    / "experiments"
    / "v6-rebound-standard10-greedy-fresh5k-slumbot-20260901"
    / "frozen"
    / "final.pt"
)
OLD_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
V6_SHA = "944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2"
RANKS = "23456789TJQKA"
SUITS = "cdhs"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tensor_state_sha(state: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for key in sorted(state):
        tensor = state[key].detach().cpu().contiguous()
        digest.update(key.encode("utf-8"))
        digest.update(str(tensor.dtype).encode("ascii"))
        digest.update(np.asarray(tensor.shape, dtype=np.int64).tobytes())
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def card_string(card: int) -> str:
    return RANKS[card // 4] + SUITS[card % 4]


def action_prefix(state: ChipState) -> str:
    groups = [[] for _ in range(state.street + 1)]
    for event in state.history:
        if event.street > state.street:
            raise AssertionError("future event in a live state")
        groups[event.street].append(
            f"b{event.amount}" if event.kind == "b" else event.kind
        )
    return "/".join("".join(group) for group in groups)


def state_fingerprint(state: ChipState, prefix: str) -> str:
    payload = {
        "deck": list(state.deck),
        "prefix": prefix,
        "street": state.street,
        "actor": state.actor,
        "stacks": list(state.stacks),
        "bets": list(state.bets),
        "pot": state.pot,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def old_observation(state: ChipState) -> tuple[dict[str, np.ndarray], dict, list[str | None]]:
    prefix = action_prefix(state)
    parsed = parse_action(prefix)
    if "error" in parsed:
        raise ValueError(f"old parser rejected {prefix!r}: {parsed['error']}")
    commitments = compute_commitments(parsed)
    hole = [card_string(card) for card in state.holes[state.actor]]
    board = [card_string(card) for card in state.board]
    mask, table = old_action_table(parsed, "preflop_pot_fraction_v2")
    obs = {
        "card_info": encode_cards(hole, board, parsed["st"]),
        "action_info": encode_action_history(
            parsed, state.actor, parsed["pos"], obs_version="v4"
        ),
        "extra_info": encode_extra(
            [STACK_SIZE - commitments["hero_total"], STACK_SIZE - commitments["opp_total"]]
        ),
        "legal_mask": mask,
    }
    return obs, {"parsed": parsed, "commitments": commitments, "prefix": prefix}, table


def parity_fields(state: ChipState, parsed_info: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    parsed = parsed_info["parsed"]
    c = parsed_info["commitments"]
    expected = {
        "street": int(state.street),
        "actor": int(state.actor),
        "hero_total": int(state.initial[state.actor] - state.stacks[state.actor]),
        "opp_total": int(state.initial[1 - state.actor] - state.stacks[1 - state.actor]),
        "hero_street": int(state.bets[state.actor]),
        "opp_street": int(state.bets[1 - state.actor]),
        "to_call": int(state.to_call),
        "pot": int(state.pot),
        "stack": int(state.stacks[state.actor]),
    }
    actual = {
        "street": int(parsed["st"]),
        "actor": int(parsed["pos"]),
        **{key: int(c[key]) for key in (
            "hero_total", "opp_total", "hero_street", "opp_street", "to_call", "pot", "stack"
        )},
    }
    return actual == expected, {"expected": expected, "actual": actual}


def map_old_action(old_action: str | None, table: list[str | None], state: ChipState) -> dict[str, Any]:
    if old_action is None:
        return {"mappable": False, "reason": "old_slot_has_no_action"}
    exact_slots = [index for index, action in enumerate(table) if action == old_action]
    if exact_slots:
        slot = exact_slots[0]
        return {
            "mappable": True,
            "mapped_slot": slot,
            "mapped_action": table[slot],
            "exact_legal_action": True,
            "sizing_error_chips": 0,
            "sizing_error_postcall_pot": 0.0,
        }
    if not old_action.startswith("b"):
        return {"mappable": False, "reason": "passive_kind_not_legal"}
    target = int(old_action[1:])
    candidates = [
        (abs(int(action[1:]) - target), index, action)
        for index, action in enumerate(table)
        if action is not None and action.startswith("b")
    ]
    if not candidates:
        return {"mappable": False, "reason": "no_v6_raise_legal"}
    distance, slot, mapped = min(candidates)
    return {
        "mappable": True,
        "mapped_slot": slot,
        "mapped_action": mapped,
        "exact_legal_action": False,
        "sizing_error_chips": int(distance),
        "sizing_error_postcall_pot": float(distance / max(state.pot + state.to_call, 1)),
    }


def rollout_action(state: ChipState, rng: np.random.Generator) -> str:
    _, table = v6_action_table(state)
    fractions = [action for action in table[2:8] if action is not None]
    u = float(rng.random())
    if state.to_call:
        if u < 0.08 and table[0] is not None:
            return table[0]
        if u < 0.65 or not fractions:
            return table[1]
        if u < 0.97:
            return fractions[int(rng.integers(len(fractions)))]
        return table[8]
    if u < 0.60 or not fractions:
        return table[1]
    if u < 0.97:
        return fractions[int(rng.integers(len(fractions)))]
    return table[8]


def stack_obs(rows: list[dict[str, np.ndarray]], key: str, device: str) -> torch.Tensor:
    return torch.as_tensor(np.stack([row[key] for row in rows]), dtype=torch.float32, device=device)


@torch.no_grad()
def infer(model: torch.nn.Module, observations: list[dict[str, np.ndarray]], device: str) -> tuple[np.ndarray, np.ndarray]:
    inputs = [stack_obs(observations, key, device) for key in (
        "card_info", "action_info", "extra_info", "legal_mask"
    )]
    logits, _ = model(*inputs)
    logits_np = logits.detach().cpu().numpy().astype(np.float64)
    masks = np.stack([row["legal_mask"] for row in observations]).astype(bool)
    selected = np.empty(len(observations), dtype=np.int64)
    top_probability = np.empty(len(observations), dtype=np.float64)
    for index, (values, legal) in enumerate(zip(logits_np, masks)):
        legal_indices = np.flatnonzero(legal)
        legal_values = values[legal_indices]
        selected[index] = legal_indices[int(np.argmax(legal_values))]
        weights = np.exp(legal_values - np.max(legal_values))
        top_probability[index] = float(np.max(weights / weights.sum()))
    return selected, top_probability


def quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "p50": None, "p95": None, "max": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(array.mean()),
        "p50": float(np.quantile(array, 0.50)),
        "p95": float(np.quantile(array, 0.95)),
        "max": float(array.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", type=int, default=50_000)
    parser.add_argument("--seed", type=int, default=2_026_090_107)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args()
    if args.states < 4:
        raise ValueError("states must be at least four for street stratification")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    torch.set_num_threads(min(8, os.cpu_count() or 1))
    random.seed(args.seed)
    np.random.seed(args.seed & 0xFFFF_FFFF)
    torch.manual_seed(args.seed)

    old_sha = sha256_file(OLD_PATH)
    v6_sha = sha256_file(V6_PATH)
    if old_sha != OLD_SHA or v6_sha != V6_SHA:
        raise RuntimeError(f"frozen input mismatch: old={old_sha}, v6={v6_sha}")
    old_policy = load_old_policy("standard10_old", OLD_PATH, args.device)
    if old_policy.obs_version != "v4":
        raise RuntimeError(f"expected Standard10 v4 observation, got {old_policy.obs_version}")
    mapping = str(old_policy.checkpoint.get("raise_action_mapping"))
    if mapping != "preflop_pot_fraction_v2":
        raise RuntimeError(f"unexpected old action mapping: {mapping}")
    v6_model, v6_checkpoint, _ = load_v6_policy(V6_PATH, args.device)
    old_tensor_sha = tensor_state_sha(old_policy.checkpoint["model"])
    v6_tensor_sha = tensor_state_sha(v6_checkpoint["model"])
    if old_tensor_sha != v6_tensor_sha:
        raise RuntimeError("old and rebound checkpoints do not contain identical learned tensors")

    quotas = [args.states // 4] * 4
    for index in range(args.states % 4):
        quotas[index] += 1
    collected = [0, 0, 0, 0]
    rng = np.random.default_rng(args.seed)
    raw_path = args.output_dir / "raw_states.jsonl.gz"
    state_hasher = hashlib.sha256()
    counters: Counter[str] = Counter()
    by_street: dict[int, Counter[str]] = defaultdict(Counter)
    sizing_errors: list[float] = []
    pending: list[dict[str, Any]] = []
    hand_index = 0
    row_index = 0

    def flush(handle) -> None:
        nonlocal row_index
        if not pending:
            return
        old_selected, old_top = infer(
            old_policy.model, [row["old_obs"] for row in pending], args.device
        )
        v6_selected, v6_top = infer(
            v6_model, [row["v6_obs"] for row in pending], args.device
        )
        for offset, row in enumerate(pending):
            old_slot = int(old_selected[offset])
            v6_slot = int(v6_selected[offset])
            old_action = row["old_table"][old_slot]
            mapped = map_old_action(old_action, row["v6_table"], row["state"])
            v6_action = row["v6_table"][v6_slot]
            parity, parity_detail = parity_fields(row["state"], row["parsed_info"])
            mappable = bool(mapped["mappable"])
            mapped_agreement = bool(mappable and mapped["mapped_slot"] == v6_slot)
            physical_agreement = old_action == v6_action
            kind_agreement = bool(
                mappable and mapped["mapped_action"][0] == v6_action[0]
            )
            counters["states"] += 1
            counters["state_parity"] += int(parity)
            counters["mappable"] += int(mappable)
            counters["exact_legal_action"] += int(mapped.get("exact_legal_action", False))
            counters["mapped_greedy_agreement"] += int(mapped_agreement)
            counters["physical_greedy_agreement"] += int(physical_agreement)
            counters["kind_greedy_agreement"] += int(kind_agreement)
            street_counts = by_street[row["state"].street]
            street_counts["states"] += 1
            street_counts["state_parity"] += int(parity)
            street_counts["mappable"] += int(mappable)
            street_counts["mapped_greedy_agreement"] += int(mapped_agreement)
            street_counts["physical_greedy_agreement"] += int(physical_agreement)
            street_counts["kind_greedy_agreement"] += int(kind_agreement)
            if mappable:
                sizing_errors.append(float(mapped["sizing_error_postcall_pot"]))
            raw = {
                "row": row_index,
                "hand": row["hand"],
                "state_sha256": row["state_sha256"],
                "action_prefix": row["parsed_info"]["prefix"],
                "street": row["state"].street,
                "actor": row["state"].actor,
                "pot": row["state"].pot,
                "to_call": row["state"].to_call,
                "state_parity": parity,
                "parity": parity_detail,
                "old_slot": old_slot,
                "old_action": old_action,
                "old_top_probability": float(old_top[offset]),
                "v6_slot": v6_slot,
                "v6_action": v6_action,
                "v6_top_probability": float(v6_top[offset]),
                **mapped,
                "mapped_greedy_agreement": mapped_agreement,
                "physical_greedy_agreement": physical_agreement,
                "kind_greedy_agreement": kind_agreement,
            }
            encoded = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
            handle.write(encoded + b"\n")
            state_hasher.update((row["state_sha256"] + "\n").encode("ascii"))
            row_index += 1
        pending.clear()

    with gzip.open(raw_path, "wb", compresslevel=6) as raw_handle:
        while any(collected[street] < quotas[street] for street in range(4)):
            deck = rng.permutation(52).astype(int).tolist()
            state = ChipState.new(deck=deck)
            hand_index += 1
            while not state.terminal:
                street = state.street
                if street < 4 and collected[street] < quotas[street]:
                    old_obs, parsed_info, old_table = old_observation(state)
                    v6_obs, v6_table = observation(state)
                    prefix = parsed_info["prefix"]
                    pending.append({
                        "hand": hand_index,
                        "state": state,
                        "state_sha256": state_fingerprint(state, prefix),
                        "parsed_info": parsed_info,
                        "old_obs": old_obs,
                        "old_table": old_table,
                        "v6_obs": v6_obs,
                        "v6_table": v6_table,
                    })
                    collected[street] += 1
                    if len(pending) >= args.batch_size:
                        flush(raw_handle)
                state = apply_incr(state, rollout_action(state, rng))
        flush(raw_handle)

    def rate(counter: Counter[str], key: str) -> float:
        return float(counter[key] / counter["states"]) if counter["states"] else 0.0

    result = {
        "schema": "cardpilot.standard10_contract_identifiability.v1",
        "created_at": utc_now(),
        "status": "COMPLETED",
        "command": [sys.executable, *sys.argv],
        "working_directory": str(Path.cwd()),
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "device": args.device,
            "torch_threads": torch.get_num_threads(),
            "wall_time_seconds": time.time() - started,
        },
        "design": {
            "seed": args.seed,
            "target_states": args.states,
            "street_quotas": quotas,
            "rollout_policy": "fixed outcome-blind passive57-60_fold8_fractional32-37_allin3",
            "slumbot_hands": 0,
            "environment_training_hands": 0,
        },
        "inputs": {
            "old_checkpoint": str(OLD_PATH),
            "old_checkpoint_sha256": old_sha,
            "v6_checkpoint": str(V6_PATH),
            "v6_checkpoint_sha256": v6_sha,
            "learned_tensor_sha256": old_tensor_sha,
            "old_obs_version": old_policy.obs_version,
            "old_raise_action_mapping": mapping,
            "v6_policy_contract": v6_checkpoint["policy_contract"],
        },
        "counts": dict(counters),
        "rates": {
            key: rate(counters, key)
            for key in (
                "state_parity", "mappable", "exact_legal_action",
                "mapped_greedy_agreement", "physical_greedy_agreement",
                "kind_greedy_agreement",
            )
        },
        "by_street": {
            str(street): {
                "counts": dict(counter),
                "rates": {
                    key: rate(counter, key)
                    for key in (
                        "state_parity", "mappable", "mapped_greedy_agreement",
                        "physical_greedy_agreement", "kind_greedy_agreement",
                    )
                },
            }
            for street, counter in sorted(by_street.items())
        },
        "mapped_sizing_error_postcall_pot": quantiles(sizing_errors),
        "state_sequence_sha256": state_hasher.hexdigest(),
        "raw_states": str(raw_path),
    }
    result["gates"] = {
        "state_parity_at_least_0_99": result["rates"]["state_parity"] >= 0.99,
        "action_mappability_at_least_0_99": result["rates"]["mappable"] >= 0.99,
        "p95_sizing_error_at_most_0_10_postcall_pot": (
            result["mapped_sizing_error_postcall_pot"]["p95"] is not None
            and result["mapped_sizing_error_postcall_pot"]["p95"] <= 0.10
        ),
    }
    result["admission"] = (
        "IDENTIFIABLE_FOR_POSSIBLE_LEARNED_BRIDGE"
        if all(result["gates"].values())
        else "DO_NOT_TRAIN_CONTRACT_BRIDGE"
    )
    result_path = args.output_dir / "analysis.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact = {
        "analysis_sha256": sha256_file(result_path),
        "raw_states_sha256": sha256_file(raw_path),
        "raw_states_bytes": raw_path.stat().st_size,
    }
    (args.output_dir / "artifact_manifest.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "admission": result["admission"],
        "states": counters["states"],
        "rates": result["rates"],
        "sizing_error": result["mapped_sizing_error_postcall_pot"],
        "wall_time_seconds": result["runtime"]["wall_time_seconds"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
