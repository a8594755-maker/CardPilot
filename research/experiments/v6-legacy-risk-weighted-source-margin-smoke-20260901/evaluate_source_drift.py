#!/usr/bin/env python3
"""Outcome-blind matched source-state drift analysis for the risk smoke."""
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

SOURCE = ROOT / "models/baseline/standard10/latest.pt"
SOURCE_SHA256 = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
CANDIDATES = {
    "control": HERE / "control/latest.pt",
    "treatment": HERE / "treatment/latest.pt",
}
ALLOWED_CHANGED_PREFIXES = ("policy_head.", "preflop_policy_head.", "value_head.")
STATES = 50_000
SEED = 2_026_120_101
BATCH_SIZE = 1024
MAX_MARGIN = 0.1
HIGH_RISK_POT_FRACTION = 0.15


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
def infer(model, observations: list[dict], device: str) -> tuple[np.ndarray, np.ndarray]:
    tensors = [
        torch.as_tensor(
            np.stack([obs[key] for obs in observations]),
            dtype=torch.float32,
            device=device,
        )
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ]
    logits, _ = model(*tensors)
    logits = logits.float().masked_fill(tensors[-1] <= 0, float("-inf"))
    return logits.cpu().numpy(), torch.softmax(logits, dim=-1).cpu().numpy()


def tensor_scope(source: dict, candidate: dict) -> dict:
    changed = []
    disallowed = []
    shape_mismatches = []
    for key, value in source["model"].items():
        other = candidate["model"].get(key)
        if other is None or tuple(value.shape) != tuple(other.shape):
            shape_mismatches.append(key)
        elif not torch.equal(value.cpu(), other.cpu()):
            changed.append(key)
            if not key.startswith(ALLOWED_CHANGED_PREFIXES):
                disallowed.append(key)
    missing_or_extra = sorted(set(source["model"]) ^ set(candidate["model"]))
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
    disagree = np.asarray(
        [row[label]["greedy_disagreement"] for row in rows], dtype=np.float64
    )
    deficit = np.asarray(
        [row[label]["source_margin_deficit"] for row in rows], dtype=np.float64
    )
    return {
        "states": len(rows),
        "mean_tv": float(tv.mean()),
        "p95_tv": float(np.quantile(tv, 0.95)),
        "greedy_disagreements": int(disagree.sum()),
        "greedy_disagreement_rate": float(disagree.mean()),
        "source_margin_violation_rate": float((deficit > 0.0).mean()),
        "source_margin_deficit_mean": float(deficit.mean()),
        "source_margin_deficit_p95": float(np.quantile(deficit, 0.95)),
    }


def paired_delta(rows: list[dict], metric: str) -> dict:
    control = np.asarray([row["control"][metric] for row in rows], dtype=np.float64)
    treatment = np.asarray([row["treatment"][metric] for row in rows], dtype=np.float64)
    delta = treatment - control
    se = float(delta.std(ddof=1) / np.sqrt(delta.size)) if delta.size > 1 else 0.0
    point = float(delta.mean())
    return {
        "metric": metric,
        "states": int(delta.size),
        "treatment_minus_control": point,
        "normal_95_ci": [point - 1.96 * se, point + 1.96 * se],
    }


def main() -> None:
    started = time.time()
    device = "cuda"
    torch.set_num_threads(8)
    source = load_policy(SOURCE, device)
    if source.sha256 != SOURCE_SHA256:
        raise RuntimeError("source hash mismatch")
    candidates = {
        label: load_policy(path, device) for label, path in CANDIDATES.items()
    }
    scopes = {
        label: tensor_scope(source.checkpoint, policy.checkpoint)
        for label, policy in candidates.items()
    }

    rng = np.random.default_rng(SEED)
    quotas = [STATES // 4] * 4
    collected = [0, 0, 0, 0]
    pending: list[dict] = []
    rows: list[dict] = []
    by_street = {label: defaultdict(list) for label in candidates}
    by_risk = {label: defaultdict(list) for label in candidates}
    raw_path = HERE / "source_drift_raw.jsonl.gz"

    def flush(handle) -> None:
        if not pending:
            return
        observations = [row["observation"] for row in pending]
        source_logits, source_probs = infer(source.model, observations, device)
        candidate_outputs = {
            label: infer(policy.model, observations, device)
            for label, policy in candidates.items()
        }
        for index, item in enumerate(pending):
            left_logits = source_logits[index]
            left_probs = source_probs[index]
            source_slot = int(np.argmax(left_logits))
            other_logits = left_logits.copy()
            other_logits[source_slot] = -np.inf
            target_margin = min(
                MAX_MARGIN,
                max(0.0, float(left_logits[source_slot] - np.max(other_logits))),
            )
            result = {
                "row": len(rows),
                "street": item["street"],
                "actor": item["actor"],
                "facing_bet": item["facing_bet"],
                "pot_fraction": item["pot_fraction"],
                "risk_band": item["risk_band"],
            }
            for label, (candidate_logits, candidate_probs) in candidate_outputs.items():
                right_logits = candidate_logits[index]
                right_probs = candidate_probs[index]
                candidate_slot = int(np.argmax(right_logits))
                candidate_other = right_logits.copy()
                candidate_other[source_slot] = -np.inf
                current_margin = float(
                    right_logits[source_slot] - np.max(candidate_other)
                )
                metric = {
                    "tv": float(0.5 * np.abs(left_probs - right_probs).sum()),
                    "greedy_disagreement": bool(
                        item["table"][source_slot]
                        != item["table"][candidate_slot]
                    ),
                    "source_margin_deficit": max(
                        0.0, target_margin - current_margin
                    ),
                }
                result[label] = metric
                by_street[label][item["street"]].append(result)
                by_risk[label][item["risk_band"]].append(result)
            rows.append(result)
            handle.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
        pending.clear()

    with gzip.open(raw_path, "wt", encoding="utf-8") as output:
        while any(collected[street] < quotas[street] for street in range(4)):
            state = ChipState.new(deck=rng.permutation(52).astype(int).tolist())
            while not state.terminal:
                street = state.street
                if collected[street] < quotas[street]:
                    observation, table = legacy_observation_from_state(
                        state, restrict_to_v6_action_table=True
                    )
                    extras = observation["extra_info"]
                    pot_fraction = max(0.0, float(2.0 - extras[0] - extras[1]))
                    risk_band = (
                        "high_ge_30bb"
                        if pot_fraction >= HIGH_RISK_POT_FRACTION
                        else "low_lt_30bb"
                    )
                    pending.append({
                        "street": street,
                        "actor": state.actor,
                        "facing_bet": bool(state.to_call),
                        "pot_fraction": pot_fraction,
                        "risk_band": risk_band,
                        "observation": observation,
                        "table": table,
                    })
                    collected[street] += 1
                    if len(pending) >= BATCH_SIZE:
                        flush(output)
                state = apply_incr(state, rollout_action(state, rng))
        flush(output)

    candidate_results = {}
    for label, policy in candidates.items():
        overall = summarize(rows, label)
        candidate_results[label] = {
            "checkpoint": str(CANDIDATES[label].resolve()),
            "sha256": policy.sha256,
            "iteration": int(policy.checkpoint["iteration"]),
            "transition_hands": int(policy.checkpoint["total_hands"]),
            "overall": overall,
            "by_street": {
                str(street): summarize(by_street[label][street], label)
                for street in range(4)
            },
            "by_risk": {
                band: summarize(by_risk[label][band], label)
                for band in ("low_lt_30bb", "high_ge_30bb")
            },
            "tensor_scope": scopes[label],
            "preservation_gate": (
                "PASS"
                if overall["mean_tv"] < 0.10
                and overall["greedy_disagreement_rate"] < 0.15
                and scopes[label]["status"] == "PASS"
                else "FAIL"
            ),
        }

    high_rows = [row for row in rows if row["risk_band"] == "high_ge_30bb"]
    paired = {
        "overall_tv": paired_delta(rows, "tv"),
        "overall_greedy_disagreement": paired_delta(rows, "greedy_disagreement"),
        "overall_margin_deficit": paired_delta(rows, "source_margin_deficit"),
        "high_risk_tv": paired_delta(high_rows, "tv"),
        "high_risk_greedy_disagreement": paired_delta(
            high_rows, "greedy_disagreement"
        ),
        "high_risk_margin_deficit": paired_delta(
            high_rows, "source_margin_deficit"
        ),
    }
    treatment_useful = (
        paired["high_risk_tv"]["treatment_minus_control"] < 0.0
        and paired["high_risk_greedy_disagreement"]["treatment_minus_control"] < 0.0
        and paired["high_risk_margin_deficit"]["treatment_minus_control"] < 0.0
        and candidate_results["treatment"]["preservation_gate"] == "PASS"
        and candidate_results["treatment"]["overall"]["mean_tv"]
        <= 1.10 * candidate_results["control"]["overall"]["mean_tv"]
    )
    result = {
        "schema": "cardpilot.risk_weighted_source_drift.v1",
        "status": "PASS" if all(
            item["preservation_gate"] == "PASS"
            for item in candidate_results.values()
        ) else "FAIL",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "design": {
            "states": STATES,
            "seed": SEED,
            "street_quotas": quotas,
            "high_risk_pot_fraction": HIGH_RISK_POT_FRACTION,
            "outcome_blind": True,
            "common_states": True,
        },
        "source": {"path": str(SOURCE.resolve()), "sha256": source.sha256},
        "candidates": candidate_results,
        "paired_treatment_minus_control": paired,
        "treatment_mechanism_useful": treatment_useful,
        "raw_path": str(raw_path.resolve()),
        "raw_sha256": sha256_file(raw_path),
        "offline_samples": STATES * (1 + len(candidates)),
        "slumbot_hands": 0,
        "wall_time_seconds": time.time() - started,
    }
    (HERE / "source_drift_analysis.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
