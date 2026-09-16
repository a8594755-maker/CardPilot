"""Audit frozen opponent-domain breadth before broad multi-seed training."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
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

from alpha_holdem.legacy_observation_bridge_v6 import legacy_observation_from_state
from alpha_holdem.policy_contract_v6 import action_table, apply_incr, observation
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v5_mirror_eval import init_model, read_checkpoint, resolve_obs_version


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def observation_style(checkpoint: dict) -> str:
    version = resolve_obs_version(checkpoint)
    if version == "v4":
        return "legacy_v4"
    if version == "v55":
        return "v6"
    raise ValueError(f"unsupported observation version: {version}")


def collect_balanced_states(count: int, seed: int) -> list[ChipState]:
    if count < 4 or count % 4:
        raise ValueError("reachable state count must be a positive multiple of four")
    target = count // 4
    by_street: list[list[ChipState]] = [[] for _ in range(4)]
    rng = random.Random(seed)
    hands = 0
    while min(len(rows) for rows in by_street) < target:
        deck = list(range(52))
        rng.shuffle(deck)
        state = ChipState.new(deck)
        while not state.terminal:
            if len(by_street[state.street]) < target:
                by_street[state.street].append(state)
            mask, table = action_table(state)
            legal = [index for index, value in enumerate(mask) if value > 0]
            weights = []
            for slot in legal:
                if slot == 0:
                    weights.append(0.03)
                elif slot == 1:
                    weights.append(0.72)
                else:
                    weights.append(0.25 / max(sum(index >= 2 for index in legal), 1))
            selected = rng.choices(legal, weights=weights, k=1)[0]
            state = apply_incr(state, table[selected])
        hands += 1
        if hands > count * 100:
            raise RuntimeError("could not generate street-balanced reachable states")
    return [state for street_rows in by_street for state in street_rows]


def _obs_for_state(model, state: ChipState, style: str):
    include_position = bool(getattr(model, "requires_position_feature", False)) or any(
        int(getattr(model, key, 0)) > 0
        for key in ("position_adapter_hidden", "position_value_adapter_hidden")
    )
    if style == "legacy_v4":
        return legacy_observation_from_state(state, include_position=include_position)
    if style == "v6":
        return observation(state, include_position=include_position)
    raise ValueError(style)


def query_policy(path: Path, states: list[ChipState], device: str, batch_size: int = 256) -> dict:
    checkpoint = read_checkpoint(path)
    style = observation_style(checkpoint)
    model = init_model(checkpoint, device).eval()
    observations = []
    policy_tables = []
    for state in states:
        obs, table = _obs_for_state(model, state, style)
        observations.append(obs)
        policy_tables.append(table)
    arrays = {
        key: np.stack([obs[key] for obs in observations]).astype(np.float32)
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    }
    logits_rows = []
    with torch.inference_mode():
        for start in range(0, len(states), batch_size):
            stop = min(start + batch_size, len(states))
            tensors = [
                torch.as_tensor(arrays[key][start:stop], dtype=torch.float32, device=device)
                for key in ("card_info", "action_info", "extra_info", "legal_mask")
            ]
            logits, _ = model(*tensors)
            logits_rows.append(logits.detach().cpu().numpy().astype(np.float64))
    logits = np.concatenate(logits_rows)
    physical_probabilities = np.zeros((len(states), 9), dtype=np.float64)
    greedy_actions = []
    action_counts: dict[str, int] = {}
    for index, state in enumerate(states):
        policy_mask = arrays["legal_mask"][index] > 0
        legal_slots = np.flatnonzero(policy_mask)
        legal_logits = logits[index, legal_slots]
        weights = np.exp(legal_logits - np.max(legal_logits))
        probabilities = weights / weights.sum()
        current_mask, current_table = action_table(state)
        current_by_action = {
            action: slot for slot, action in enumerate(current_table) if action is not None
        }
        for slot, probability in zip(legal_slots, probabilities):
            action = policy_tables[index][int(slot)]
            if action not in current_by_action:
                raise ValueError(f"{path}: nonphysical action {action!r}")
            physical_probabilities[index, current_by_action[action]] += float(probability)
        if not np.isclose(physical_probabilities[index].sum(), 1.0, atol=1e-6):
            raise ValueError(f"{path}: invalid mapped probability mass")
        greedy_slot = int(np.argmax(physical_probabilities[index]))
        if current_mask[greedy_slot] <= 0 or current_table[greedy_slot] is None:
            raise ValueError(f"{path}: invalid greedy physical action")
        action = str(current_table[greedy_slot])
        greedy_actions.append(action)
        action_counts[action[0] if not action.startswith("b") else "b"] = (
            action_counts.get(action[0] if not action.startswith("b") else "b", 0) + 1
        )
    signature = hashlib.sha256("\n".join(greedy_actions).encode("utf-8")).hexdigest()
    del model, checkpoint
    if device == "cuda":
        torch.cuda.empty_cache()
    return {
        "style": style,
        "greedy_actions": greedy_actions,
        "probabilities": physical_probabilities,
        "signature_sha256": signature,
        "action_counts": action_counts,
    }


def mean_js_divergence(left: np.ndarray, right: np.ndarray) -> float:
    midpoint = 0.5 * (left + right)
    left_term = np.zeros_like(left)
    right_term = np.zeros_like(right)
    left_positive = left > 0
    right_positive = right > 0
    left_term[left_positive] = left[left_positive] * np.log(
        left[left_positive] / midpoint[left_positive]
    )
    right_term[right_positive] = right[right_positive] * np.log(
        right[right_positive] / midpoint[right_positive]
    )
    return float(np.mean(0.5 * (left_term.sum(axis=1) + right_term.sum(axis=1))))


def pairwise_rows(policies: list[dict]) -> list[dict]:
    rows = []
    for left_index, left in enumerate(policies):
        for right in policies[left_index + 1 :]:
            disagreement = float(np.mean(np.asarray(left["greedy_actions"]) != np.asarray(right["greedy_actions"])))
            rows.append({
                "left": left["label"],
                "right": right["label"],
                "greedy_disagreement": disagreement,
                "mean_js_divergence": mean_js_divergence(left["probabilities"], right["probabilities"]),
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    spec_path = args.spec.resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("schema") != "cardpilot.broad_league_domain_spec.v1":
        raise ValueError("unsupported domain spec")
    training = list(spec["training_policies"])
    holdouts = list(spec["holdout_policies"])
    admission = dict(spec["admission"])
    if len(training) < int(admission["minimum_training_policies"]):
        raise ValueError("insufficient training policies")
    if len(holdouts) < int(admission["minimum_holdout_policies"]):
        raise ValueError("insufficient holdout policies")
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    states = collect_balanced_states(int(spec["reachable_states"]), int(spec["seed"]))
    state_path = args.out_dir / "state_evidence.jsonl.gz"
    with gzip.open(state_path, "xt", encoding="utf-8", newline="\n") as handle:
        for index, state in enumerate(states):
            handle.write(json.dumps({
                "index": index,
                "street": state.street,
                "actor": state.actor,
                "holes": state.holes,
                "board": state.board,
                "history": [event.__dict__ for event in state.history],
                "stacks": state.stacks,
                "bets": state.bets,
                "pot": state.pot,
            }, sort_keys=True) + "\n")
    results = []
    for role, entries in (("training", training), ("holdout", holdouts)):
        for entry in entries:
            path = Path(entry["path"]).resolve()
            if not path.is_file():
                raise FileNotFoundError(path)
            queried = query_policy(path, states, args.device)
            row = {
                "role": role,
                "label": str(entry["label"]),
                "path": str(path),
                "sha256": sha256_path(path),
                "bytes": path.stat().st_size,
                "observation_style": queried["style"],
                "signature_sha256": queried["signature_sha256"],
                "action_counts": queried["action_counts"],
                "greedy_actions": queried["greedy_actions"],
                "probabilities": queried["probabilities"],
            }
            results.append(row)
            print(f"queried {role} {row['label']} style={row['observation_style']} signature={row['signature_sha256'][:12]}", flush=True)
    train_results = [row for row in results if row["role"] == "training"]
    holdout_results = [row for row in results if row["role"] == "holdout"]
    all_pairs = pairwise_rows(results)
    train_labels = {row["label"] for row in train_results}
    train_pairs = [row for row in all_pairs if row["left"] in train_labels and row["right"] in train_labels]
    nearest_holdouts = []
    for holdout in holdout_results:
        candidates = []
        for trained in train_results:
            disagreement = float(np.mean(np.asarray(holdout["greedy_actions"]) != np.asarray(trained["greedy_actions"])))
            candidates.append({"training_label": trained["label"], "greedy_disagreement": disagreement})
        nearest_holdouts.append({"holdout_label": holdout["label"], **min(candidates, key=lambda row: row["greedy_disagreement"])})
    shas = [row["sha256"] for row in results]
    train_shas = {row["sha256"] for row in train_results}
    holdout_shas = {row["sha256"] for row in holdout_results}
    checks = {
        "training_policies": len(train_results),
        "holdout_policies": len(holdout_results),
        "reachable_states": len(states),
        "queries": len(states) * len(results),
        "unique_sha256": len(set(shas)) == len(shas),
        "unique_behavior_signatures": len({row["signature_sha256"] for row in results}) == len(results),
        "train_holdout_sha_disjoint": train_shas.isdisjoint(holdout_shas),
        "observation_styles": sorted({row["observation_style"] for row in results}),
        "minimum_train_pairwise_greedy_disagreement": min(row["greedy_disagreement"] for row in train_pairs),
        "minimum_holdout_nearest_train_greedy_disagreement": min(row["greedy_disagreement"] for row in nearest_holdouts),
    }
    gates = {
        "unique_sha256": checks["unique_sha256"] or not admission["require_unique_sha256"],
        "unique_behavior_signatures": checks["unique_behavior_signatures"],
        "train_holdout_disjoint": checks["train_holdout_sha_disjoint"] or not admission["require_train_holdout_disjoint"],
        "state_count": len(states) >= int(admission["minimum_reachable_states"]),
        "train_pairwise_diversity": checks["minimum_train_pairwise_greedy_disagreement"] >= float(admission["minimum_train_pairwise_greedy_disagreement"]),
        "holdout_novelty": checks["minimum_holdout_nearest_train_greedy_disagreement"] >= float(admission["minimum_holdout_nearest_train_greedy_disagreement"]),
        "all_state_queries_valid": True,
    }
    public_policies = [{key: value for key, value in row.items() if key not in {"greedy_actions", "probabilities"}} for row in results]
    result = {
        "schema": "cardpilot.broad_league_domain_feasibility.v1",
        "status": "COMPLETED",
        "spec": str(spec_path),
        "spec_sha256": sha256_path(spec_path),
        "policies": public_policies,
        "pairwise": all_pairs,
        "nearest_holdouts": nearest_holdouts,
        "checks": checks,
        "gates": gates,
        "admitted": all(gates.values()),
        "decision": "ADMIT_BROAD_MGDA_3SEED_65K" if all(gates.values()) else "REVISE_OPPONENT_DOMAIN_SET",
        "state_evidence": str(state_path.resolve()),
        "state_evidence_sha256": sha256_path(state_path),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"checks": checks, "gates": gates, "decision": result["decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
