#!/usr/bin/env python3
"""Outcome-blind three-policy replay; first execution selected CUDA."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from alpha_holdem.legacy_observation_bridge_v6 import (  # noqa: E402
    legacy_observation_from_state,
    load_policy,
)
from alpha_holdem.policy_contract_v6 import action_table, from_external  # noqa: E402


MODELS = {
    "standard10": (
        ROOT / "models/baseline/standard10/latest.pt",
        "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428",
    ),
    "seed1_1m": (
        ROOT / "research/experiments/v6-integrated-seed1-1m-greedy-fresh20k-slumbot-20260903/frozen/final.pt",
        "6fbbe021b140b91e448917ae3e2cbb9bcdca444865433074ac944cae79fa844a",
    ),
    "seed1_2m": (
        ROOT / "research/experiments/v6-integrated-seed1-2m-greedy-fresh20k-slumbot-20260903/frozen/final.pt",
        "993fe99bd0a5ac0eaa0135e449315752d99efc25bedf220f93a1ad08884344c3",
    ),
}
CORPORA = {
    "seed1_1m_onpolicy": (
        ROOT / "research/experiments/v6-integrated-seed1-1m-greedy-fresh20k-slumbot-20260903",
        "seed1_1m",
    ),
    "seed1_2m_onpolicy": (
        ROOT / "research/experiments/v6-integrated-seed1-2m-greedy-fresh20k-slumbot-20260903",
        "seed1_2m",
    ),
}
PAIRS = {
    "standard10_vs_1m": ("standard10", "seed1_1m"),
    "standard10_vs_2m": ("standard10", "seed1_2m"),
    "one_m_vs_two_m": ("seed1_1m", "seed1_2m"),
}
BATCH_SIZE = 1024
MIN_SUPPORTED_STATES = 200


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@torch.no_grad()
def infer(model, observations: list[dict], device: str) -> np.ndarray:
    tensors = [
        torch.as_tensor(
            np.stack([obs[key] for obs in observations]),
            dtype=torch.float32,
            device=device,
        )
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ]
    logits, _ = model(*tensors)
    logits = logits.masked_fill(tensors[-1] <= 0, float("-inf"))
    return torch.softmax(logits, dim=-1).cpu().numpy()


def collapse_to_physical(raw: np.ndarray, legacy_table: list, state) -> np.ndarray:
    _, physical_table = action_table(state)
    result = np.zeros(9, dtype=np.float64)
    for slot, probability in enumerate(raw):
        if probability <= 0:
            continue
        action = legacy_table[slot]
        matches = [index for index, current in enumerate(physical_table) if current == action]
        if not matches:
            raise ValueError(f"Legacy action {action!r} absent from physical table")
        result[matches[0]] += float(probability)
    if not math.isclose(float(result.sum()), 1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError("Collapsed policy distribution is not normalized")
    return result


def action_class(action: str, state) -> str:
    if action == "f":
        return "fold"
    if action in {"k", "c"}:
        return "check_call"
    return "all_in" if int(action[1:]) == state.max_to else "raise"


def bucket(value: float, cuts: tuple[float, ...], labels: tuple[str, ...]) -> str:
    for cut, label in zip(cuts, labels):
        if value < cut:
            return label
    return labels[-1]


def margin(probabilities: np.ndarray) -> float:
    legal = np.sort(probabilities[probabilities > 0])
    return float(legal[-1] - legal[-2]) if len(legal) > 1 else 1.0


def summarize(rows: list[dict], pair: str) -> dict:
    if not rows:
        raise ValueError("Cannot summarize an empty partition")
    tv = np.asarray([row[f"{pair}_tv"] for row in rows], dtype=np.float64)
    disagree = np.asarray(
        [row[f"{pair}_greedy_disagreement"] for row in rows], dtype=np.float64
    )
    weights = np.asarray([row["exposure_bb"] for row in rows], dtype=np.float64)
    return {
        "states": len(rows),
        "mean_tv": float(tv.mean()),
        "p95_tv": float(np.quantile(tv, 0.95)),
        "greedy_disagreements": int(disagree.sum()),
        "greedy_disagreement_rate": float(disagree.mean()),
        "stake_weighted_greedy_disagreement_rate": float(
            np.dot(disagree, weights) / weights.sum()
        ),
        "mean_left_margin": float(
            np.mean([row[f"{pair}_left_margin"] for row in rows])
        ),
        "mean_right_margin": float(
            np.mean([row[f"{pair}_right_margin"] for row in rows])
        ),
    }


def main() -> None:
    if sys.argv[1:]:
        raise ValueError("This preregistered analysis takes no runtime arguments")
    raw_path = BASE / "drift_raw.jsonl.gz"
    analysis_path = BASE / "analysis.json"
    manifest_path = BASE / "input_manifest.json"
    if any(path.exists() for path in (raw_path, analysis_path, manifest_path)):
        raise FileExistsError("Refusing to overwrite drift evidence")

    started = time.time()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.set_num_threads(8)
    policies = {}
    for label, (path, expected_sha) in MODELS.items():
        policy = load_policy(path, device)
        if policy.sha256 != expected_sha:
            raise RuntimeError(f"Frozen {label} checkpoint mismatch")
        policies[label] = policy

    input_hands = []
    parent_audits = []
    for corpus, (experiment, expected_policy) in CORPORA.items():
        record = json.loads((experiment / "experiment.json").read_text(encoding="utf-8"))
        audit_path = experiment / "combined_audit.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if record["status"] != "COMPLETED" or audit["status"] != "PASS":
            raise RuntimeError(f"Unreviewed input corpus: {corpus}")
        if audit["model_sha256"] != MODELS[expected_policy][1]:
            raise RuntimeError(f"Corpus checkpoint mismatch: {corpus}")
        parent_audits.append(
            {"corpus": corpus, "path": str(audit_path), "sha256": sha256_file(audit_path)}
        )
        for session in range(1, 9):
            path = experiment / "sessions" / f"s{session:02d}" / "hands.jsonl"
            input_hands.append(
                {"corpus": corpus, "path": str(path), "sha256": sha256_file(path)}
            )

    manifest = {
        "schema": "cardpilot.integrated_slumbot_state_drift_inputs.v1",
        "outcome_blind": True,
        "models": {
            label: {"path": str(path), "sha256": expected}
            for label, (path, expected) in MODELS.items()
        },
        "hands": input_hands,
        "parent_audits": parent_audits,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    pending = []
    rows_by_corpus = defaultdict(list)
    logged_parity = Counter()

    def flush(handle) -> None:
        if not pending:
            return
        inferred = {}
        for label, policy in policies.items():
            include_position = bool(getattr(policy.model, "requires_position_feature", False))
            observations = [
                legacy_observation_from_state(
                    item["state"], include_position=include_position,
                    restrict_to_v6_action_table=True,
                )[0]
                for item in pending
            ]
            inferred[label] = infer(policy.model, observations, device)

        for row_index, item in enumerate(pending):
            state = item["state"]
            _, legacy_table = legacy_observation_from_state(
                state, include_position=False, restrict_to_v6_action_table=True
            )
            physical = {
                label: collapse_to_physical(matrix[row_index], legacy_table, state)
                for label, matrix in inferred.items()
            }
            actions = {}
            for label, matrix in inferred.items():
                legacy_slot = int(np.argmax(matrix[row_index]))
                actions[label] = legacy_table[legacy_slot]

            expected_action = actions[item["expected_policy"]]
            logged_parity["states"] += 1
            logged_parity["matches"] += int(item["logged_action"] == expected_action)
            effective_stack = min(state.stacks) / 100.0
            pot_bb = state.pot / 100.0
            to_call_bb = state.to_call / 100.0
            exposure_bb = pot_bb + to_call_bb
            spr = effective_stack / max(pot_bb, 0.01)
            row = {
                "corpus": item["corpus"],
                "session": item["session"],
                "hand": item["hand"],
                "decision": item["decision"],
                "street": int(state.street),
                "client_pos": int(item["client_pos"]),
                "facing_bet": bool(state.to_call > 0),
                "pot_bb": pot_bb,
                "to_call_bb": to_call_bb,
                "exposure_bb": exposure_bb,
                "effective_stack_bb": effective_stack,
                "spr": spr,
                "pot_bucket": bucket(
                    pot_bb, (4, 10, 30, float("inf")),
                    ("lt4", "4to10", "10to30", "ge30"),
                ),
                "exposure_bucket": bucket(
                    exposure_bb, (5, 20, 50, float("inf")),
                    ("lt5", "5to20", "20to50", "ge50"),
                ),
                "spr_bucket": bucket(
                    spr, (1, 3, 8, float("inf")),
                    ("lt1", "1to3", "3to8", "ge8"),
                ),
                "standard10_action_class": action_class(actions["standard10"], state),
                "logged_action_parity": item["logged_action"] == expected_action,
            }
            for pair, (left_label, right_label) in PAIRS.items():
                left, right = physical[left_label], physical[right_label]
                row.update(
                    {
                        f"{pair}_tv": float(0.5 * np.abs(left - right).sum()),
                        f"{pair}_greedy_disagreement": actions[left_label] != actions[right_label],
                        f"{pair}_left_action": actions[left_label],
                        f"{pair}_right_action": actions[right_label],
                        f"{pair}_left_margin": margin(left),
                        f"{pair}_right_margin": margin(right),
                    }
                )
            rows_by_corpus[item["corpus"]].append(row)
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        pending.clear()

    with gzip.open(raw_path, "xt", encoding="utf-8") as output:
        for corpus, (experiment, expected_policy) in CORPORA.items():
            expected_sha = MODELS[expected_policy][1]
            for session in range(1, 9):
                path = experiment / "sessions" / f"s{session:02d}" / "hands.jsonl"
                with path.open("r", encoding="utf-8") as handle:
                    for hand_index, line in enumerate(handle, 1):
                        hand = json.loads(line)
                        if hand["model_sha256"] != expected_sha:
                            raise RuntimeError("Hand-level model SHA mismatch")
                        for decision_index, decision in enumerate(hand["decisions"]):
                            response = decision["response"]
                            state = from_external(
                                response["action"], response["hole_cards"],
                                response.get("board", []), response["client_pos"],
                            )
                            pending.append(
                                {
                                    "corpus": corpus,
                                    "expected_policy": expected_policy,
                                    "session": session,
                                    "hand": hand_index,
                                    "decision": decision_index,
                                    "client_pos": response["client_pos"],
                                    "state": state,
                                    "logged_action": decision["direct_increment"],
                                }
                            )
                            if len(pending) >= BATCH_SIZE:
                                flush(output)
        flush(output)

    corpora = {}
    relevant_fields = (
        "street", "client_pos", "facing_bet", "pot_bucket",
        "exposure_bucket", "spr_bucket", "standard10_action_class",
    )
    drift_increases = {}
    for corpus, rows in rows_by_corpus.items():
        pair_metrics = {pair: summarize(rows, pair) for pair in PAIRS}
        partitions = {}
        candidates = []
        for field in relevant_fields:
            for value in sorted({row[field] for row in rows}, key=str):
                subset = [row for row in rows if row[field] == value]
                key = f"{field}={value}"
                metrics = {pair: summarize(subset, pair) for pair in PAIRS}
                partitions[key] = metrics
                if len(subset) >= MIN_SUPPORTED_STATES:
                    gap = (
                        metrics["standard10_vs_2m"]["greedy_disagreement_rate"]
                        - metrics["standard10_vs_1m"]["greedy_disagreement_rate"]
                    )
                    candidates.append(
                        {"partition": key, "states": len(subset), "disagreement_gap": gap}
                    )
        overall_gap = (
            pair_metrics["standard10_vs_2m"]["stake_weighted_greedy_disagreement_rate"]
            - pair_metrics["standard10_vs_1m"]["stake_weighted_greedy_disagreement_rate"]
        )
        drift_increases[corpus] = {
            "stake_weighted_disagreement_gap": overall_gap,
            "top_supported_partitions": sorted(
                candidates, key=lambda item: item["disagreement_gap"], reverse=True
            )[:12],
        }
        corpora[corpus] = {
            "states": len(rows),
            "pairs": pair_metrics,
            "partitions": partitions,
        }

    reproducible_gap = all(
        value["stake_weighted_disagreement_gap"] >= 0.005
        for value in drift_increases.values()
    )
    supported_partition = all(
        any(item["disagreement_gap"] >= 0.005 for item in value["top_supported_partitions"])
        for value in drift_increases.values()
    )
    parity_pass = logged_parity["states"] == logged_parity["matches"]
    mechanism_supported = reproducible_gap and supported_partition and parity_pass
    result = {
        "schema": "cardpilot.integrated_1m_2m_slumbot_state_drift.v1",
        "status": "PASS" if parity_pass else "FAIL",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "design": {
            "outcome_blind": True,
            "network_calls": 0,
            "minimum_supported_partition_states": MIN_SUPPORTED_STATES,
            "mechanism_gap_threshold": 0.005,
        },
        "device": device,
        "logged_policy_replay": dict(logged_parity),
        "corpora": corpora,
        "drift_increases": drift_increases,
        "gates": {
            "logged_action_parity_100pct": parity_pass,
            "two_m_standard10_stake_weighted_gap_reproduced": reproducible_gap,
            "supported_partition_same_direction": supported_partition,
            "mechanism_supported": mechanism_supported,
        },
        "decision": (
            "STANDARD10_EXTERNAL_STATE_DRIFT_MECHANISM_SUPPORTED"
            if mechanism_supported
            else "STANDARD10_EXTERNAL_STATE_DRIFT_NOT_SUFFICIENT"
        ),
        "raw_path": str(raw_path.resolve()),
        "raw_sha256": sha256_file(raw_path),
        "input_manifest": str(manifest_path.resolve()),
        "input_manifest_sha256": sha256_file(manifest_path),
        "offline_states": sum(len(rows) for rows in rows_by_corpus.values()),
        "model_state_queries": sum(len(rows) for rows in rows_by_corpus.values()) * 3,
        "new_training_hands": 0,
        "slumbot_hands": 0,
        "wall_time_seconds": time.time() - started,
    }
    analysis_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "decision": result["decision"],
                "offline_states": result["offline_states"],
                "drift_increases": drift_increases,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
