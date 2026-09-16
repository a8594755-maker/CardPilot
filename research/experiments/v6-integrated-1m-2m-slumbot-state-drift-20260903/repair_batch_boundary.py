#!/usr/bin/env python3
"""Re-evaluate rare batch-boundary mismatches with deployment batch size one."""
from __future__ import annotations

import gzip
import importlib.util
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent
ENGINE_PATH = BASE / "analyze_drift_cuda.py"
SOURCE_DIR = BASE / "cpu"
OUT_DIR = BASE / "cpu_exact"


def load_engine():
    spec = importlib.util.spec_from_file_location("drift_engine", ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def read_decision(experiment: Path, session: int, hand_index: int, decision_index: int):
    path = experiment / "sessions" / f"s{session:02d}" / "hands.jsonl"
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, 1):
            if index == hand_index:
                hand = json.loads(line)
                return hand["decisions"][decision_index]
    raise IndexError("Recorded decision was not found")


def main() -> None:
    if sys.argv[1:]:
        raise ValueError("This preregistered repair takes no runtime arguments")
    if OUT_DIR.exists():
        raise FileExistsError("Refusing to overwrite exact replay evidence")
    OUT_DIR.mkdir()
    started = time.time()
    engine = load_engine()
    engine.torch.set_num_threads(8)

    source_raw = SOURCE_DIR / "drift_raw.jsonl.gz"
    source_analysis = SOURCE_DIR / "analysis.json"
    source_manifest = SOURCE_DIR / "input_manifest.json"
    rows = []
    with gzip.open(source_raw, "rt", encoding="utf-8") as handle:
        for line in handle:
            rows.append(json.loads(line))
    mismatches = [row for row in rows if not row["logged_action_parity"]]
    if not mismatches:
        raise ValueError("No batch-boundary mismatch to repair")

    policies = {}
    for label, (path, expected_sha) in engine.MODELS.items():
        policy = engine.load_policy(path, "cpu")
        if policy.sha256 != expected_sha:
            raise RuntimeError(f"Frozen {label} checkpoint mismatch")
        policies[label] = policy

    repaired = []
    for row in mismatches:
        experiment, expected_policy = engine.CORPORA[row["corpus"]]
        decision = read_decision(
            experiment, row["session"], row["hand"], row["decision"]
        )
        response = decision["response"]
        state = engine.from_external(
            response["action"], response["hole_cards"],
            response.get("board", []), response["client_pos"],
        )
        physical = {}
        actions = {}
        for label, policy in policies.items():
            include_position = bool(
                getattr(policy.model, "requires_position_feature", False)
            )
            observation, legacy_table = engine.legacy_observation_from_state(
                state, include_position=include_position,
                restrict_to_v6_action_table=True,
            )
            raw = engine.infer(policy.model, [observation], "cpu")[0]
            physical[label] = engine.collapse_to_physical(raw, legacy_table, state)
            actions[label] = legacy_table[int(np.argmax(raw))]

        if actions[expected_policy] != decision["direct_increment"]:
            raise RuntimeError("Batch-size-one replay still disagrees with logged action")
        row["logged_action_parity"] = True
        row["standard10_action_class"] = engine.action_class(
            actions["standard10"], state
        )
        for pair, (left_label, right_label) in engine.PAIRS.items():
            left, right = physical[left_label], physical[right_label]
            row.update(
                {
                    f"{pair}_tv": float(0.5 * np.abs(left - right).sum()),
                    f"{pair}_greedy_disagreement": (
                        actions[left_label] != actions[right_label]
                    ),
                    f"{pair}_left_action": actions[left_label],
                    f"{pair}_right_action": actions[right_label],
                    f"{pair}_left_margin": engine.margin(left),
                    f"{pair}_right_margin": engine.margin(right),
                }
            )
        repaired.append(
            {
                "corpus": row["corpus"],
                "session": row["session"],
                "hand": row["hand"],
                "decision": row["decision"],
                "expected_policy": expected_policy,
            }
        )

    output_raw = OUT_DIR / "drift_raw.jsonl.gz"
    with gzip.open(output_raw, "xt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    rows_by_corpus = defaultdict(list)
    for row in rows:
        rows_by_corpus[row["corpus"]].append(row)
    relevant_fields = (
        "street", "client_pos", "facing_bet", "pot_bucket",
        "exposure_bucket", "spr_bucket", "standard10_action_class",
    )
    corpora = {}
    drift_increases = {}
    for corpus, corpus_rows in rows_by_corpus.items():
        pair_metrics = {
            pair: engine.summarize(corpus_rows, pair) for pair in engine.PAIRS
        }
        partitions = {}
        candidates = []
        for field in relevant_fields:
            for value in sorted({row[field] for row in corpus_rows}, key=str):
                subset = [row for row in corpus_rows if row[field] == value]
                key = f"{field}={value}"
                metrics = {
                    pair: engine.summarize(subset, pair) for pair in engine.PAIRS
                }
                partitions[key] = metrics
                if len(subset) >= engine.MIN_SUPPORTED_STATES:
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
            "states": len(corpus_rows),
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
    parity_pass = all(row["logged_action_parity"] for row in rows)
    mechanism_supported = reproducible_gap and supported_partition and parity_pass
    result = {
        "schema": "cardpilot.integrated_1m_2m_slumbot_state_drift_cpu_exact.v1",
        "status": "PASS" if parity_pass else "FAIL",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "design": {
            "outcome_blind": True,
            "network_calls": 0,
            "base_backend": "cpu_batch1024",
            "boundary_backend": "cpu_batch1",
            "minimum_supported_partition_states": engine.MIN_SUPPORTED_STATES,
            "mechanism_gap_threshold": 0.005,
        },
        "source": {
            "raw_path": str(source_raw.resolve()),
            "raw_sha256": engine.sha256_file(source_raw),
            "analysis_path": str(source_analysis.resolve()),
            "analysis_sha256": engine.sha256_file(source_analysis),
            "input_manifest_path": str(source_manifest.resolve()),
            "input_manifest_sha256": engine.sha256_file(source_manifest),
        },
        "batch_boundary_mismatches": len(mismatches),
        "repaired_rows": repaired,
        "logged_policy_replay": {"states": len(rows), "matches": len(rows)},
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
        "raw_path": str(output_raw.resolve()),
        "raw_sha256": engine.sha256_file(output_raw),
        "offline_states": len(rows),
        "additional_exact_model_state_queries": len(mismatches) * 3,
        "new_training_hands": 0,
        "slumbot_hands": 0,
        "wall_time_seconds": time.time() - started,
    }
    output_analysis = OUT_DIR / "analysis.json"
    output_analysis.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "decision": result["decision"],
                "batch_boundary_mismatches": len(mismatches),
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
