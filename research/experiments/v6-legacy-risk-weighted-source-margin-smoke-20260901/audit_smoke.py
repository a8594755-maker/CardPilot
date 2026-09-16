#!/usr/bin/env python3
"""Audit both matched training arms and their replayable session evidence."""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from pathlib import Path

import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts/alpha_holdem"))

from train_v5 import restore_group_assignment_rng_from_evidence  # noqa: E402

SOURCE_SHA256 = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
ARCHIVE_RE = re.compile(r"^checkpoint_iter(?P<iteration>\d+)_hands(?P<hands>\d+)\.pt$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def audit_arm(label: str, expected_risk_weight: float) -> dict:
    run_dir = HERE / label
    paths = {
        "checkpoint": run_dir / "latest.pt",
        "manifest": run_dir / "run_manifest.json",
        "metrics": run_dir / "h1_training_metrics.jsonl",
        "assignments": run_dir / "opponent_assignments.jsonl",
        "train_log": run_dir / "latest_train.log",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    checkpoint = torch.load(paths["checkpoint"], map_location="cpu", weights_only=False)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    metrics = load_jsonl(paths["metrics"])
    assignments = load_jsonl(paths["assignments"])
    config = checkpoint["config"]
    iterations = [int(row["iteration"]) for row in metrics]
    transition_hands = [int(row["hands"]) for row in metrics]
    environment_hands = [
        int(row["environment_hand_accounting"]["completed_hands"])
        for row in metrics
    ]
    pool = checkpoint.get("pool_snapshots") or []
    pool_ids = [int(row["id"]) for row in pool]
    history = checkpoint.get("pool_candidate_history") or []
    source_rows = [
        row for row in history
        if (row.get("score_components") or {}).get("kind")
        == "initial_external_opponent"
    ]
    assignment_audit = restore_group_assignment_rng_from_evidence(
        assignments,
        metrics,
        rng=random.Random(0),
        seed=int(config["seed"]),
        worker_count=int(config["workers"]),
        pool_size=len(pool),
        pool_snapshot_ids=pool_ids,
        group_count=int(config["opponent_groups"]),
        self_play_fraction=float(config["self_play_fraction"]),
        checkpoint_iteration=4,
        checkpoint_total_hands=transition_hands[-1],
    )
    membership = {
        int(row["applies_to_iteration"]): [
            int(ref["snapshot_id"])
            for ref in row.get("pool_snapshot_refs", [])
        ]
        for row in assignments
    }
    archives = []
    for path in sorted((run_dir / "checkpoints").glob("checkpoint_iter*_hands*.pt")):
        match = ARCHIVE_RE.match(path.name)
        if match:
            archives.append({
                "iteration": int(match.group("iteration")),
                "hands": int(match.group("hands")),
                "path": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    final_archive = torch.load(
        Path(archives[-1]["path"]), map_location="cpu", weights_only=False
    )
    optimizer_states = (checkpoint.get("optimizer") or {}).get("state") or {}
    optimizer_steps = []
    for state in optimizer_states.values():
        step = state.get("step", 0)
        optimizer_steps.append(int(step.item() if hasattr(step, "item") else step))
    checks = {
        "contiguous_iterations": iterations == [1, 2, 3, 4],
        "strict_transition_counter": all(
            b > a for a, b in zip(transition_hands, transition_hands[1:])
        ),
        "strict_environment_counter": all(
            b > a for a, b in zip(environment_hands, environment_hands[1:])
        ),
        "physical_target_reached": environment_hands[-1] >= 8_192,
        "terminal_iteration": (
            checkpoint.get("iteration") == manifest.get("iteration") == 4
        ),
        "transition_counter_parity": (
            checkpoint.get("total_hands")
            == manifest.get("total_hands")
            == transition_hands[-1]
        ),
        "physical_counter_parity": (
            checkpoint["environment_hand_accounting"]["completed_hands"]
            == manifest["environment_hand_accounting"]["completed_hands"]
            == environment_hands[-1]
        ),
        "manifest_finished": manifest.get("status") == "finished",
        "contract_metadata": all([
            checkpoint.get("env_version") == "v6legacyv4obs",
            checkpoint.get("obs_version") == "v4",
            checkpoint.get("model_obs_version") == "v4",
            checkpoint.get("observation_bridge_contract")
            == "hunl_v6_physical_legacy_v4_observation_bridge_v1",
            checkpoint.get("raise_action_mapping") == "preflop_pot_fraction_v2",
        ]),
        "risk_config": (
            float(config["source_greedy_risk_max_weight"])
            == expected_risk_weight
            and float(config["source_greedy_risk_full_pot_fraction"]) == 0.15
            and float(config["source_greedy_margin_coef"]) == 0.1
        ),
        "final_pool": pool_ids == [0, 1],
        "candidate_history": [int(row["id"]) for row in history] == [0, 1],
        "source_history_identity": (
            len(source_rows) == 1
            and (source_rows[0].get("score_components") or {}).get(
                "checkpoint_sha256"
            ) == SOURCE_SHA256
        ),
        "assignment_replay": (
            assignment_audit["tail_iteration"] == 4
            and assignment_audit["pending_assignments"] is None
        ),
        "assignment_membership": membership == {
            1: [0], 2: [0], 3: [0], 4: [0]
        },
        "archive_cadence": [row["iteration"] for row in archives] == [2, 4],
        "final_archive_model_matches": all(
            torch.equal(value.cpu(), final_archive["model"][key].cpu())
            for key, value in checkpoint["model"].items()
        ),
        "optimizer_state": (
            bool(optimizer_steps)
            and min(optimizer_steps) == max(optimizer_steps)
            and min(optimizer_steps) > 0
        ),
        "no_kl_stop": not any(row["kl_early_stop_triggered"] for row in metrics),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "run_id": checkpoint.get("run_id"),
        "final_iteration": 4,
        "transition_hands": transition_hands[-1],
        "actual_environment_hands": environment_hands[-1],
        "target_environment_hands": 8_192,
        "metric_rows": len(metrics),
        "assignment_rows": len(assignments),
        "assignment_audit": assignment_audit,
        "final_pool_snapshot_ids": pool_ids,
        "optimizer_state_count": len(optimizer_states),
        "optimizer_step_min": min(optimizer_steps),
        "optimizer_step_max": max(optimizer_steps),
        "max_reference_policy_kl": max(
            float(row["reference_policy_kl"]) for row in metrics
        ),
        "archives": archives,
        "artifact_integrity": {
            name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for name, path in paths.items()
        },
    }


def main() -> None:
    arms = {
        "control": audit_arm("control", 1.0),
        "treatment": audit_arm("treatment", 4.0),
    }
    result = {
        "schema": "cardpilot.risk_weighted_source_margin_smoke_audit.v1",
        "status": "PASS" if all(row["status"] == "PASS" for row in arms.values()) else "FAIL",
        "arms": arms,
    }
    out = HERE / "session_audit.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
