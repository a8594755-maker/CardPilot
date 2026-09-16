#!/usr/bin/env python3
"""Audit the completed legacy-contract dynamic FIFO training session."""
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

TRAINING = HERE / "training"
SOURCE_SHA256 = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
ARCHIVE_RE = re.compile(r"^checkpoint_iter(?P<iteration>\d+)_hands(?P<hands>\d+)\.pt$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    paths = {
        "checkpoint": TRAINING / "latest.pt",
        "manifest": TRAINING / "run_manifest.json",
        "metrics": TRAINING / "h1_training_metrics.jsonl",
        "assignments": TRAINING / "opponent_assignments.jsonl",
        "train_log": TRAINING / "latest_train.log",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    checkpoint = torch.load(paths["checkpoint"], map_location="cpu", weights_only=False)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    metrics = load_jsonl(paths["metrics"])
    assignments = load_jsonl(paths["assignments"])
    config = checkpoint["config"]

    checks = {}
    iterations = [int(row["iteration"]) for row in metrics]
    transition_hands = [int(row["hands"]) for row in metrics]
    environment_hands = [int(row["environment_hand_accounting"]["completed_hands"]) for row in metrics]
    checks["contiguous_iterations"] = iterations == list(range(1, 17))
    checks["strict_transition_counter"] = all(b > a for a, b in zip(transition_hands, transition_hands[1:]))
    checks["strict_environment_counter"] = all(b > a for a, b in zip(environment_hands, environment_hands[1:]))
    checks["physical_target_reached"] = environment_hands[-1] >= 65_536
    checks["terminal_iteration"] = checkpoint.get("iteration") == manifest.get("iteration") == 16
    checks["transition_counter_parity"] = checkpoint.get("total_hands") == manifest.get("total_hands") == transition_hands[-1]
    checks["physical_counter_parity"] = (
        checkpoint["environment_hand_accounting"]["completed_hands"]
        == manifest["environment_hand_accounting"]["completed_hands"]
        == environment_hands[-1]
    )
    checks["manifest_finished"] = manifest.get("status") == "finished"
    checks["contract_metadata"] = all([
        checkpoint.get("env_version") == "v6legacyv4obs",
        checkpoint.get("obs_version") == "v4",
        checkpoint.get("model_obs_version") == "v4",
        checkpoint.get("observation_bridge_contract") == "hunl_v6_physical_legacy_v4_observation_bridge_v1",
        checkpoint.get("raise_action_mapping") == "preflop_pot_fraction_v2",
    ])

    pool = checkpoint.get("pool_snapshots") or []
    pool_ids = [int(row["id"]) for row in pool]
    history = checkpoint.get("pool_candidate_history") or []
    checks["fifo_final_pool"] = pool_ids == [1, 2, 3, 4]
    checks["candidate_history"] = [int(row["id"]) for row in history] == [0, 1, 2, 3, 4]
    source_rows = [row for row in history if (row.get("score_components") or {}).get("kind") == "initial_external_opponent"]
    checks["source_history_identity"] = (
        len(source_rows) == 1
        and (source_rows[0].get("score_components") or {}).get("checkpoint_sha256") == SOURCE_SHA256
    )

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
        checkpoint_iteration=16,
        checkpoint_total_hands=transition_hands[-1],
    )
    checks["assignment_replay"] = (
        assignment_audit["tail_iteration"] == 16
        and assignment_audit["pending_assignments"] is None
    )
    membership = {
        int(row["applies_to_iteration"]): [int(ref["snapshot_id"]) for ref in row.get("pool_snapshot_refs", [])]
        for row in assignments
    }
    expected_membership = {}
    for iteration in range(1, 17):
        if iteration <= 4:
            expected_membership[iteration] = [0]
        elif iteration <= 8:
            expected_membership[iteration] = [0, 1]
        elif iteration <= 12:
            expected_membership[iteration] = [0, 1, 2]
        else:
            expected_membership[iteration] = [0, 1, 2, 3]
    checks["assignment_membership_cadence"] = membership == expected_membership

    archives = []
    for path in sorted((TRAINING / "checkpoints").glob("checkpoint_iter*_hands*.pt")):
        match = ARCHIVE_RE.match(path.name)
        if match:
            archives.append({
                "iteration": int(match.group("iteration")),
                "hands": int(match.group("hands")),
                "path": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    checks["archive_cadence"] = [row["iteration"] for row in archives] == [4, 8, 12, 16]
    final_archive = torch.load(Path(archives[-1]["path"]), map_location="cpu", weights_only=False)
    checks["final_archive_model_matches_endpoint"] = all(
        torch.equal(value.cpu(), final_archive["model"][key].cpu())
        for key, value in checkpoint["model"].items()
    )
    checks["final_archive_optimizer_matches_endpoint"] = (
        checkpoint["optimizer"]["param_groups"] == final_archive["optimizer"]["param_groups"]
        and all(
            all(
                torch.equal(value.cpu(), final_archive["optimizer"]["state"][key][name].cpu())
                if torch.is_tensor(value)
                else value == final_archive["optimizer"]["state"][key][name]
                for name, value in state.items()
            )
            for key, state in checkpoint["optimizer"]["state"].items()
        )
    )

    optimizer_states = (checkpoint.get("optimizer") or {}).get("state") or {}
    optimizer_steps = []
    for state in optimizer_states.values():
        step = state.get("step", 0)
        optimizer_steps.append(int(step.item() if hasattr(step, "item") else step))
    checks["optimizer_state"] = (
        bool(optimizer_steps)
        and min(optimizer_steps) == max(optimizer_steps)
        and min(optimizer_steps) > 0
    )

    result = {
        "schema": "cardpilot.legacy_contract_dynamic_pool_session_audit.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "run_id": checkpoint.get("run_id"),
        "final_iteration": 16,
        "transition_hands": transition_hands[-1],
        "actual_environment_hands": environment_hands[-1],
        "target_environment_hands": 65_536,
        "no_trainable_decision_hands": checkpoint["environment_hand_accounting"]["no_trainable_decision_hands"],
        "metric_rows": len(metrics),
        "assignment_rows": len(assignments),
        "assignment_audit": assignment_audit,
        "final_pool_snapshot_ids": pool_ids,
        "candidate_history_rows": len(history),
        "optimizer_state_count": len(optimizer_states),
        "optimizer_step_min": min(optimizer_steps),
        "optimizer_step_max": max(optimizer_steps),
        "max_reference_policy_kl": max(float(row["reference_policy_kl"]) for row in metrics),
        "max_clip_fraction": max(float(row["clip_frac"]) for row in metrics),
        "kl_early_stop_count": sum(bool(row["kl_early_stop_triggered"]) for row in metrics),
        "archives": archives,
        "artifact_integrity": {
            name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for name, path in paths.items()
        },
    }
    out = TRAINING / "session_audit.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
