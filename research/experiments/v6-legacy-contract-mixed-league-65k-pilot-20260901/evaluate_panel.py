#!/usr/bin/env python3
"""Fresh common-randomness greedy multi-anchor panel for the legacy curve."""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from alpha_holdem.execution_v6 import load_policy as load_native  # noqa: E402
from alpha_holdem.legacy_observation_bridge_v6 import (  # noqa: E402
    BRIDGE_CONTRACT,
    legacy_observation,
    load_policy as load_bridge,
)
from alpha_holdem.policy_contract_v6 import apply_incr, observation as native_observation  # noqa: E402
from alpha_holdem.rules_v6 import ChipState  # noqa: E402

PAIRS = 1024
BASE_SEED = 2_026_090_201
BONFERRONI_Z = 2.497705474412374  # two-sided 98.75%; four curve comparisons
CANDIDATES = {
    "parent": ROOT / "models/baseline/standard10/latest.pt",
    "iter04": HERE / "training/checkpoints/checkpoint_iter000004_hands000000016500.pt",
    "iter08": HERE / "training/checkpoints/checkpoint_iter000008_hands000000033016.pt",
    "iter12": HERE / "training/checkpoints/checkpoint_iter000012_hands000000049525.pt",
    "iter16": HERE / "training/checkpoints/checkpoint_iter000016_hands000000065966.pt",
}
ANCHORS = {
    "bridge_smoke": ROOT / "research/experiments/v6-legacy-contract-ppo-smoke-20260901/training/latest.pt",
    "procedural_soup": ROOT / "research/experiments/v6-procedural-iter32-soup-greedy-fresh20k-slumbot-20260901/frozen/final.pt",
    "raw_actor": ROOT / "research/experiments/v6-actor-raw-greedy-fresh20k-slumbot-20260901/frozen/final.pt",
    "source_kl_temperature": ROOT / "research/experiments/v6-source-kl-temperature-65k-pilot-20260901/frozen/treatment_iter15.pt",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class AutoPolicy:
    kind: str
    model: torch.nn.Module
    wrapped: object
    checkpoint: dict
    path: Path
    sha256: str
    device: str


def load_auto(path: Path, device: str) -> AutoPolicy:
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    if checkpoint.get("observation_bridge_contract") == BRIDGE_CONTRACT or checkpoint.get("env_version") not in {"v6", "v6legacyv4obs"}:
        wrapped = load_bridge(path, device)
        return AutoPolicy("bridge", wrapped.model, wrapped, wrapped.checkpoint, path, wrapped.sha256, device)
    model, native_checkpoint, digest = load_native(path, device)
    return AutoPolicy("native", model, model, native_checkpoint, path, digest, device)


@torch.no_grad()
def decide_batch(policy: AutoPolicy, states: list[ChipState]) -> list[str]:
    observations = []
    tables = []
    for state in states:
        if policy.kind == "bridge":
            obs, table = legacy_observation(policy.wrapped, state)
        else:
            include_position = bool(getattr(policy.model, "requires_position_feature", False)) or any(
                int(getattr(policy.model, key, 0)) > 0
                for key in ("position_adapter_hidden", "position_value_adapter_hidden")
            )
            obs, table = native_observation(state, include_position=include_position)
        observations.append(obs)
        tables.append(table)
    tensors = [
        torch.as_tensor(np.stack([obs[key] for obs in observations]), dtype=torch.float32, device=policy.device)
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ]
    logits, _ = policy.model(*tensors)
    values = logits.detach().cpu().numpy()
    masks = tensors[-1].cpu().numpy().astype(bool)
    actions = []
    for row, mask, table in zip(values, masks, tables):
        legal = np.flatnonzero(mask)
        slot = int(legal[int(np.argmax(row[legal]))])
        action = table[slot]
        if action is None:
            raise RuntimeError("selected action is not legal")
        actions.append(action)
    return actions


def cell(candidate: AutoPolicy, anchor: AutoPolicy, decks: list[list[int]], out_dir: Path) -> dict:
    started = time.time()
    games = []
    for pair_index, deck in enumerate(decks):
        for candidate_seat in (0, 1):
            games.append({
                "pair_index": pair_index,
                "candidate_seat": candidate_seat,
                "state": ChipState.new(deck=list(deck)),
                "decisions": 0,
            })
    while True:
        active = [game for game in games if not game["state"].terminal]
        if not active:
            break
        candidate_games = [game for game in active if game["state"].actor == game["candidate_seat"]]
        anchor_games = [game for game in active if game["state"].actor != game["candidate_seat"]]
        for policy, selected_games in ((candidate, candidate_games), (anchor, anchor_games)):
            for start in range(0, len(selected_games), 2048):
                batch = selected_games[start:start + 2048]
                actions = decide_batch(policy, [game["state"] for game in batch])
                for game, action in zip(batch, actions):
                    game["state"] = apply_incr(game["state"], action)
                    game["decisions"] += 1
    by_pair = [[] for _ in decks]
    decision_counts = [[] for _ in decks]
    for game in games:
        reward = game["state"].payoffs()[game["candidate_seat"]] / 100.0
        by_pair[game["pair_index"]].append(float(reward))
        decision_counts[game["pair_index"]].append(int(game["decisions"]))
    rows = [
        {
            "pair_index": index,
            "deck": decks[index],
            "candidate_rewards_bb": rewards,
            "candidate_pair_average_bb": float(statistics.fmean(rewards)),
            "decisions": decision_counts[index],
        }
        for index, rewards in enumerate(by_pair)
    ]
    out_dir.mkdir(parents=True, exist_ok=False)
    raw_path = out_dir / "pairs.jsonl"
    with raw_path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    values = [row["candidate_pair_average_bb"] * 100.0 for row in rows]
    mean = statistics.fmean(values)
    half = 1.96 * statistics.stdev(values) / math.sqrt(len(values))
    summary = {
        "schema": "cardpilot.v6_mixed_contract_mirror_cell.v1",
        "status": "COMPLETED",
        "candidate_path": str(candidate.path.resolve()),
        "candidate_sha256": candidate.sha256,
        "candidate_contract": candidate.kind,
        "anchor_path": str(anchor.path.resolve()),
        "anchor_sha256": anchor.sha256,
        "anchor_contract": anchor.kind,
        "pairs": PAIRS,
        "evaluation_hands": 2 * PAIRS,
        "policy_mode": "greedy",
        "bb_per_100": mean,
        "ci95": [mean - half, mean + half],
        "pairs_sha256": sha256_file(raw_path),
        "wall_time_seconds": time.time() - started,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"summary": summary, "pair_values_bb100": values}


def paired_summary(candidate_values: list[float], parent_values: list[float], z: float) -> dict:
    deltas = [candidate - parent for candidate, parent in zip(candidate_values, parent_values, strict=True)]
    mean = statistics.fmean(deltas)
    se = statistics.stdev(deltas) / math.sqrt(len(deltas))
    return {"pairs": len(deltas), "mean_delta_bb100": mean, "ci": [mean - z * se, mean + z * se]}


def main() -> None:
    if sys.argv[1:]:
        raise SystemExit("This preregistered evaluator takes no arguments")
    started = time.time()
    torch.set_num_threads(8)
    device = "cuda"
    out_root = HERE / "panel"
    if out_root.exists():
        raise FileExistsError(out_root)
    candidates = {label: load_auto(path, device) for label, path in CANDIDATES.items()}
    anchors = {label: load_auto(path, device) for label, path in ANCHORS.items()}
    cells = {}
    for anchor_index, (anchor_label, anchor) in enumerate(anchors.items()):
        rng = np.random.default_rng(BASE_SEED + anchor_index * 1_000_003)
        decks = [rng.permutation(52).astype(int).tolist() for _ in range(PAIRS)]
        for candidate_label, candidate in candidates.items():
            print(json.dumps({"candidate": candidate_label, "anchor": anchor_label, "status": "RUNNING"}), flush=True)
            cells[(candidate_label, anchor_label)] = cell(
                candidate, anchor, decks, out_root / f"{candidate_label}__{anchor_label}"
            )
    comparisons = {}
    eligible = []
    for candidate_label in list(candidates)[1:]:
        per_anchor = {}
        pooled_candidate = []
        pooled_parent = []
        for anchor_label in anchors:
            candidate_values = cells[(candidate_label, anchor_label)]["pair_values_bb100"]
            parent_values = cells[("parent", anchor_label)]["pair_values_bb100"]
            per_anchor[anchor_label] = paired_summary(candidate_values, parent_values, 1.96)
            pooled_candidate.extend(candidate_values)
            pooled_parent.extend(parent_values)
        pooled = paired_summary(pooled_candidate, pooled_parent, BONFERRONI_Z)
        positive_anchors = sum(row["mean_delta_bb100"] > 0 for row in per_anchor.values())
        # Mirrored seat games are already averaged within each pair, so both seats
        # have equal representation in every per-anchor and pooled comparison.
        passed = positive_anchors >= 3 and pooled["ci"][0] > 0
        comparisons[candidate_label] = {
            "per_anchor": per_anchor,
            "positive_anchors": positive_anchors,
            "pooled_bonferroni_98_75": pooled,
            "both_seats_balanced_by_design": True,
            "promotion_gate": "PASS" if passed else "FAIL",
        }
        if passed:
            eligible.append(candidate_label)
    selected = max(
        eligible,
        key=lambda label: comparisons[label]["pooled_bonferroni_98_75"]["mean_delta_bb100"],
        default=None,
    )
    result = {
        "schema": "cardpilot.legacy_contract_mixed_league_panel.v1",
        "status": "PASS",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "design": {
            "pairs_per_cell": PAIRS,
            "candidates": list(CANDIDATES),
            "anchors": list(ANCHORS),
            "policy_mode": "greedy",
            "common_decks_within_anchor": True,
            "promotion_rule": "at least 3/4 positive anchor points and pooled Bonferroni 98.75% lower bound > 0",
        },
        "checkpoint_hashes": {
            "candidates": {label: policy.sha256 for label, policy in candidates.items()},
            "anchors": {label: policy.sha256 for label, policy in anchors.items()},
        },
        "comparisons_to_parent": comparisons,
        "eligible_candidates": eligible,
        "selected_candidate": selected,
        "evaluation_hands": len(candidates) * len(anchors) * PAIRS * 2,
        "slumbot_hands": 0,
        "wall_time_seconds": time.time() - started,
    }
    (HERE / "panel_analysis.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
