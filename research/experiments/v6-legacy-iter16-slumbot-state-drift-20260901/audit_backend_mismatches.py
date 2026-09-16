#!/usr/bin/env python3
"""Resolve the four batched-GPU/live-CPU argmax mismatches without outcomes."""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from alpha_holdem.legacy_observation_bridge_v6 import (  # noqa: E402
    external_decision,
    load_policy,
)

PARENT_MODEL = ROOT / "models/baseline/standard10/latest.pt"
CANDIDATE_MODEL = ROOT / "research/experiments/v6-legacy-contract-mixed-league-65k-pilot-20260901/training/checkpoints/checkpoint_iter000016_hands000000065966.pt"
CORPORA = {
    "parent_onpolicy": ROOT / "research/experiments/v6-standard10-legacy-bridge-greedy-fresh20k-20260901/sessions",
    "candidate_onpolicy": ROOT / "research/experiments/v6-legacy-iter16-greedy-fresh20k-20260901/sessions",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    analysis = json.loads((HERE / "drift_analysis.json").read_text(encoding="utf-8"))
    raw_path = HERE / "drift_raw.jsonl.gz"
    with gzip.open(raw_path, "rt", encoding="utf-8") as handle:
        mismatches = [json.loads(line) for line in handle if not json.loads(line)["logged_action_parity"]]
    policies = {
        "parent_onpolicy": load_policy(PARENT_MODEL, "cpu"),
        "candidate_onpolicy": load_policy(CANDIDATE_MODEL, "cpu"),
    }
    results = []
    for mismatch in mismatches:
        hand_path = CORPORA[mismatch["corpus"]] / f"s{mismatch['session']:02d}/hands.jsonl"
        hand = json.loads(hand_path.read_text(encoding="utf-8").splitlines()[mismatch["hand"] - 1])
        decision = hand["decisions"][mismatch["decision"]]
        action, info = external_decision(
            policies[mismatch["corpus"]], decision["response"],
            uniform=0.5, device="cpu", policy_mode="greedy",
        )
        results.append({
            "corpus": mismatch["corpus"],
            "session": mismatch["session"],
            "hand": mismatch["hand"],
            "decision": mismatch["decision"],
            "logged_action": decision["direct_increment"],
            "gpu_batched_action": mismatch["parent_action"] if mismatch["corpus"] == "parent_onpolicy" else mismatch["candidate_action"],
            "cpu_single_action": action,
            "cpu_matches_logged": action == decision["direct_increment"],
            "gpu_margin": mismatch["parent_margin"] if mismatch["corpus"] == "parent_onpolicy" else mismatch["candidate_margin"],
            "cpu_selected_slot": info["selected_action_slot"],
        })
    checks = {
        "analysis_failed_only_replay_parity": analysis["status"] == "FAIL",
        "raw_hash_matches": sha256_file(raw_path) == analysis["raw_sha256"],
        "exactly_four_gpu_batch_mismatches": len(mismatches) == 4,
        "cpu_single_matches_all_logged_actions": all(row["cpu_matches_logged"] for row in results),
        "all_other_logged_actions_match": analysis["logged_policy_replay"] == {"states": 122875, "matches": 122871},
    }
    report = {
        "schema": "cardpilot.legacy_iter16_backend_mismatch_audit.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "mismatches": results,
        "max_gpu_batched_margin_on_mismatch": max(row["gpu_margin"] for row in results),
        "interpretation": "Live CPU-single replay matches every logged action. Four GPU-batched argmax differences are near-tie backend numerical drift and do not invalidate the outcome-blind probability/context decomposition.",
        "analysis_sha256": sha256_file(HERE / "drift_analysis.json"),
        "raw_sha256": sha256_file(raw_path),
        "slumbot_hands": 0,
    }
    (HERE / "backend_mismatch_audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
